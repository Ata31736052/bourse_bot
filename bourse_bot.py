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

# غیرفعال کردن هشدارهای عدم بررسی گواهی SSL برای سرورهای داخلی
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
    """خواندن آخرین وضعیت سیگنال‌ها از فایل ذخیره"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(state):
    """ذخیره وضعیت جدید در فایل"""
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def get_tsetmc_market_watch():
    """دریافت اطلاعات دیده‌بان بازار از سرورهای TSETMC (با لینک‌های پشتیبان)"""
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
            res = requests.get(url, headers=headers, timeout=15, verify=False)
            if res.status_code == 200 and len(res.text) > 100:
                return res.text
        except Exception as e:
            print(f"تلاش ناموفق برای دریافت از {url}: {e}")
            continue

    return None

def analyze_bourse():
    """تحلیل نمادها و بررسی شرایط حجم و قیمت"""
    raw_data = get_tsetmc_market_watch()
    now_str = datetime.now().strftime("%H:%M")
    
    if not raw_data:
        return None, f"⚠️ **خطا در پایش بورس ({now_str})**\n\nامکان دریافت اطلاعات از سرور TSETMC (خارج از ساعت بازار یا اختلال شبکه) برقرار نشد."

    signals = []
    scanned_count = 0

    # اگر پاسخ به‌صورت JSON از API جدید باشد
    if raw_data.startswith("{") or raw_data.startswith("["):
        try:
            data = json.loads(raw_data)
            market_list = data.get("marketWatch", []) if isinstance(data, dict) else data
            for item in market_list:
                lval = item.get("lVal18RFC", "")  # نام نماد
                if lval in WATCHLIST:
                    scanned_count += 1
                    price = item.get("pClosing", 0)
                    vol = item.get("tVol", 0)
                    if vol > 1000000:  # فیلتر نمونه: حجم بیش از ۱ میلیون
                        signals.append({
                            "sym": lval,
                            "price": price,
                            "vol": vol,
                            "time": now_str
                        })
            return signals, scanned_count
        except Exception as e:
            print(f"خطا در پردازش JSON: {e}")

    # اگر پاسخ به‌صورت متنی (قدیمی) باشد
    sections = raw_data.split("@")
    if len(sections) >= 3:
        price_data = sections[2].split(";")
        for item in price_data:
            parts = item.split(",")
            if len(parts) >= 11:
                symbol_name = parts[2]
                last_price = parts[7]
                vol = parts[9]

                if symbol_name in WATCHLIST:
                    scanned_count += 1
                    try:
                        vol_num = float(vol)
                        price_num = float(last_price)
                        if vol_num > 1000000:
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
    print("شروع اسکن بازار بورس...")
    state = load_state()
    now_time = datetime.now().strftime("%H:%M - %Y/%m/%d")

    signals, result_info = analyze_bourse()

    # ۱. حالت خطا در اتصال به TSETMC
    if signals is None and isinstance(result_info, str):
        send_bale_message(result_info)
        return

    # ۲. حالت ثبت سیگنال‌های جدید
    new_signals = []
    if signals:
        for sig in signals:
            last_time = state.get(sig["sym"], {}).get("last_sent")
            if last_time != sig["time"]:
                new_signals.append(sig)
                state[sig["sym"]] = {"last_sent": sig["time"]}

        save_state(state)

    if new_signals:
        for s in new_signals:
            msg = (
                f"🚀 **#سیگنال_بورس | {s['sym']}**\n\n"
                f"💰 آخرین قیمت: **{s['price']:,.0f} ریال**\n"
                f"📊 حجم معاملات: **{s['vol']:,.0f}**\n"
                f"⏰ زمان ثبت: {s['time']}\n\n"
                f"🟢 وضعیت: حجم مشکوک / ورود پول شناسایی شد."
            )
            send_bale_message(msg)
            time.sleep(0.5)
    else:
        # ۳. حالت اجرا بدون سیگنال جدید (گزارش سلامت ربات)
        msg = (
            f"📊 **گزارش دیده‌بان بورس ({now_time})**\n\n"
            f"• تعداد نمادهای بررسی شده: **{result_info} نماد**\n"
            f"• وضعیت: *ارتباط برقرار شد اما هیچ سهمی فیلتر ورود را کسب نکرد.*\n\n"
            f"🟢 ربات فعال و آماده اسکن بعدی است."
        )
        send_bale_message(msg)

    print("پایان اسکن بورس.")

if __name__ == "__main__":
    main()
