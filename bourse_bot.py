# ============================================
# 🤖 ربات سیگنال‌دهی و پایش بورس ایران (TSETMC -> پیام‌رسان بله)
# ============================================

import os
import sys
import json
import time
import requests
import urllib3
from datetime import datetime

# غیرفعال کردن هشدارهای عدم بررسی گواهی SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# دریافت توکن و چت‌آیدی بله از متغیرهای محیطی گیت‌هاب
BALE_TOKEN = os.getenv("BALE_TOKEN")
BALE_CHAT_ID = os.getenv("BALE_CHAT_ID")
STATE_FILE = "bourse_state.json"

# لیست نمادهای مورد نظر برای پایش روزانه (قابل ویرایش)
WATCHLIST = [
    "وبملت", "شپدیس", "فسپا", "کپرور", "تکیمیا", 
    "کتوکا", "حگردش", "فسرب", "خمحرکه", "خودرو", "خساپا"
]

def send_bale_message(text: str) -> bool:
    """ارسال پیام به پیام‌رسان بله"""
    if not BALE_TOKEN or not BALE_CHAT_ID:
        print("⚠️ توکن یا چت‌آیدی بله تنظیم نشده است.")
        print(text)
        return False

    url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
    payload = {
        "chat_id": BALE_CHAT_ID,
        "text": text
    }
    
    try:
        res = requests.post(url, json=payload, timeout=15)
        return res.status_code == 200
    except Exception as e:
        print(f"خطا در ارسال پیام به بله: {e}")
        return False

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(state):
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def get_tsetmc_data():
    """دریافت اطلاعات آنلاین یا آخرین روز معاملاتی ثبت‌شده از TSETMC"""
    urls = [
        "https://cdn.tsetmc.com/api/ClosingPrice/GetMarketWatch?market=0&organ=0",
        "https://old.tsetmc.com/tsev2/data/MarketWatchPlus.aspx"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }
    
    for url in urls:
        try:
            res = requests.get(url, headers=headers, timeout=20, verify=False)
            if res.status_code == 200 and len(res.text) > 100:
                return res.text
        except Exception as e:
            print(f"تلاش ناموفق برای دریافت از {url}: {e}")
            continue

    return None

def analyze_bourse():
    """تحلیل نمادها بر اساس اطلاعات امروز/آخرین روز معاملاتی"""
    raw_data = get_tsetmc_data()
    now_str = datetime.now().strftime("%H:%M - %Y/%m/%d")
    
    if not raw_data:
        return None, f"⚠️ **خطا در دریافت اطلاعات TSETMC ({now_str})**\n\nسرور TSETMC در حال حاضر پاسخگو نیست."

    signals = []
    scanned_count = 0
    is_offline_data = False

    # بررسی خروجی JSON (سرویس جدید CDN)
    if raw_data.startswith("{") or raw_data.startswith("["):
        try:
            data = json.loads(raw_data)
            market_list = data.get("marketWatch", []) if isinstance(data, dict) else data
            
            for item in market_list:
                lval = item.get("lVal18RFC", "").strip()
                if lval in WATCHLIST:
                    scanned_count += 1
                    price = item.get("pClosing", 0) or item.get("priceChange", 0)
                    vol = item.get("tVol", 0)
                    
                    # بررسی حجم معامله (در صورت تعطیلی بازار، آخرین حجم ثبت‌شده روز قبل بررسی می‌شود)
                    if vol > 500000:
                        signals.append({
                            "sym": lval,
                            "price": price,
                            "vol": vol,
                            "time": now_str
                        })
            return signals, scanned_count
        except Exception as e:
            print(f"خطا در پردازش JSON: {e}")

    # بررسی خروجی متنی (TSETMC v2 - دیتای آخرین معامله/روز قبل)
    sections = raw_data.split("@")
    if len(sections) >= 3:
        price_data = sections[2].split(";")
        for item in price_data:
            parts = item.split(",")
            if len(parts) >= 11:
                symbol_name = parts[2].strip()
                last_price = parts[6] if parts[6] != "0" else parts[7]  # اولویت با قیمت پایانی آخرین روز
                vol = parts[9]

                if symbol_name in WATCHLIST:
                    scanned_count += 1
                    try:
                        vol_num = float(vol)
                        price_num = float(last_price)
                        if vol_num > 500000:  # فیلتر حجم بالای ۵۰۰ هزار
                            signals.append({
                                "sym": symbol_name,
                                "price": price_num,
                                "vol": vol_num,
                                "time": now_str
                            })
                    except ValueError:
                        continue

    return signals, scanned_count

def main():
    print("شروع اسکن بازار بورس (زنده / آخرین روز معاملاتی)...")
    state = load_state()
    now_time = datetime.now().strftime("%H:%M - %Y/%m/%d")

    signals, result_info = analyze_bourse()

    # ۱. حالت خطا در اتصال به TSETMC
    if signals is None and isinstance(result_info, str):
        send_bale_message(result_info)
        return

    # ۲. بررسی سیگنال‌های جدید
    new_signals = []
    if signals:
        for sig in signals:
            last_sent = state.get(sig["sym"], {}).get("last_sent")
            # جلوگیری از ارسال تکراری در یک روز
            if last_sent != sig["time"].split(" - ")[1]:
                new_signals.append(sig)
                state[sig["sym"]] = {"last_sent": sig["time"].split(" - ")[1]}

        save_state(state)

    if new_signals:
        for s in new_signals:
            msg = (
                f"🚀 **#سیگنال_بورس | {s['sym']}**\n\n"
                f"💰 قیمت پایانی/آخرین: **{s['price']:,.0f} ریال**\n"
                f"📊 حجم معاملات (روز/آخرین معامله): **{s['vol']:,.0f}**\n"
                f"⏰ تاریخ اسکن: {s['time']}\n\n"
                f"🟢 وضعیت: حجم معاملات بالای ۵۰۰ هزار معامله ثبت شد."
            )
            send_bale_message(msg)
            time.sleep(0.5)
    else:
        # ۳. گزارش خلاصه اسکن
        msg = (
            f"📊 **گزارش دیده‌بان بورس ({now_time})**\n\n"
            f"• تعداد نمادهای پایش‌شده: **{result_info} نماد** از لیست دیده‌بان\n"
            f"• وضعیت: *اطلاعات آخرین روز معاملاتی دریافت شد و هیچ سیگنال جدیدی ثبت نگردید.*\n\n"
            f"🟢 ربات فعال است."
        )
        send_bale_message(msg)

    print("پایان اسکن بورس.")

if __name__ == "__main__":
    main()
