# ============================================
# 🤖 ربات جامع بورس ایران (TSETMC + Codal -> بله) - نسخه بهبودیافته
# ============================================

import os
import sys
import json
import time
import requests
import urllib3
from datetime import datetime
from typing import Optional, Tuple, List, Dict

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BALE_TOKEN = os.getenv("BALE_TOKEN")
BALE_CHAT_ID = os.getenv("BALE_CHAT_ID")
IRAN_PROXY = os.getenv("IRAN_PROXY")  # مثال: http://user:pass@ip:port
STATE_FILE = "bourse_state.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://tsetmc.com/",
    "Origin": "https://tsetmc.com",
}

def get_proxies() -> Optional[Dict]:
    if IRAN_PROXY:
        return {"http": IRAN_PROXY, "https": IRAN_PROXY}
    return None

def send_bale_message(text: str) -> bool:
    if not BALE_TOKEN or not BALE_CHAT_ID:
        print("⚠️ توکن یا چت‌آیدی بله تنظیم نشده است.")
        print(text)
        return False

    url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
    payload = {
        "chat_id": BALE_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        res = requests.post(url, json=payload, timeout=15)
        return res.status_code == 200
    except Exception as e:
        print(f"خطا در ارسال پیام به بله: {e}")
        return False

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"tsetmc": {}, "codal": []}

def save_state(state: dict):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"خطا در ذخیره state: {e}")

def get_tsetmc_data() -> Tuple[Optional[list], Optional[dict]]:
    """دریافت دیده‌بان بازار + حقیقی/حقوقی از API جدید"""
    proxies = get_proxies()
    
    # ۱. دیده‌بان بازار (همه بازارها)
    mw_url = (
        "https://cdn.tsetmc.com/api/ClosingPrice/GetMarketWatch"
        "?market=0"
        "&paperTypes[0]=1&paperTypes[1]=2&paperTypes[2]=3"
        "&paperTypes[3]=4&paperTypes[4]=5&paperTypes[5]=6"
        "&paperTypes[6]=7&paperTypes[7]=8&paperTypes[8]=9"
        "&withBestLimits=false&hEven=0&RefID=0"
    )
    
    market_watch = None
    try:
        res = requests.get(mw_url, headers=HEADERS, proxies=proxies, timeout=12, verify=False)
        if res.status_code == 200:
            data = res.json()
            # کلید واقعی معمولاً marketwatch است
            market_watch = data.get("marketwatch") or data.get("marketWatch") or data.get("MarketWatch")
    except Exception as e:
        print(f"خطا در دریافت MarketWatch: {e}")

    # ۲. حقیقی/حقوقی همه نمادها
    client_url = "https://cdn.tsetmc.com/api/ClientType/GetClientTypeAll"
    client_dict = {}
    try:
        res = requests.get(client_url, headers=HEADERS, proxies=proxies, timeout=12, verify=False)
        if res.status_code == 200:
            data = res.json()
            items = data.get("clientTypeAllDto") or data.get("clientTypeAll") or []
            for item in items:
                ins = str(item.get("insCode") or item.get("InsCode"))
                # فیلدهای رایج در API جدید
                buy_i_vol = float(item.get("buy_I_Volume") or item.get("buyIVolume") or 0)
                sell_i_vol = float(item.get("sell_I_Volume") or item.get("sellIVolume") or 0)
                buy_i_count = float(item.get("buy_CountI") or item.get("buyCountI") or 1)
                sell_i_count = float(item.get("sell_CountI") or item.get("sellCountI") or 1)
                
                client_dict[ins] = {
                    "buy_vol": buy_i_vol,
                    "sell_vol": sell_i_vol,
                    "buy_count": max(buy_i_count, 1),
                    "sell_count": max(sell_i_count, 1),
                }
    except Exception as e:
        print(f"خطا در دریافت ClientTypeAll: {e}")

    return market_watch, client_dict

def get_codal_latest_letters(page_size: int = 15) -> List[dict]:
    """آخرین اطلاعیه‌های کدال"""
    url = "https://search.codal.ir/api/search/v2/q"
    params = {
        "PageNumber": 1,
        "PageSize": page_size,
        # می‌توانید فیلتر اضافه کنید: LetterType=-1 و غیره
    }
    letters = []
    try:
        res = requests.get(
            url,
            headers={"User-Agent": HEADERS["User-Agent"], "Accept": "application/json"},
            params=params,
            timeout=12,
            verify=False,
        )
        if res.status_code == 200:
            data = res.json()
            for item in data.get("Letters", []):
                serial = item.get("LetterSerial") or item.get("Url") or ""
                letters.append({
                    "id": str(item.get("TracingNo")),
                    "sym": item.get("Symbol") or "—",
                    "title": item.get("Title") or "بدون عنوان",
                    "time": item.get("PublishDateTime") or "",
                    "url": f"https://codal.ir/Reports/Decision.aspx?LetterSerial={serial}" if serial else "https://codal.ir",
                })
    except Exception as e:
        print(f"خطا در دریافت کدال: {e}")
    return letters

def analyze_market(market_watch: list, client_dict: dict) -> Tuple[List[dict], int]:
    """فیلتر سیگنال‌های قوی"""
    signals = []
    total = 0
    now_str = datetime.now().strftime("%H:%M - %Y/%m/%d")

    if not market_watch:
        return [], 0

    for item in market_watch:
        total += 1
        ins_code = str(item.get("insCode") or item.get("InsCode") or "")
        symbol = str(item.get("lVal18AFC") or item.get("lVal18RFC") or item.get("lVal18") or "").strip()
        if not symbol or not ins_code:
            continue

        last_price = float(item.get("pDrCotVal") or item.get("pDrvc") or item.get("last") or 0)
        close_price = float(item.get("pClosing") or item.get("close") or 0)
        vol = float(item.get("qTotTran5J") or item.get("tVol") or 0)
        value = float(item.get("qTotCap") or item.get("tVal") or 0)

        buyer_power = 1.0
        money_flow_toman = 0.0

        if ins_code in client_dict:
            cd = client_dict[ins_code]
            buy_capita = cd["buy_vol"] / cd["buy_count"]
            sell_capita = cd["sell_vol"] / cd["sell_count"]
            if sell_capita > 0:
                buyer_power = round(buy_capita / sell_capita, 2)
            # ورود پول حقیقی (تقریبی)
            net_vol = cd["buy_vol"] - cd["sell_vol"]
            money_flow_toman = (net_vol * last_price) / 10  # تبدیل به تومان

        # شرط سیگنال
        if (buyer_power >= 1.5 and money_flow_toman > 500_000_000) or money_flow_toman >= 3_000_000_000:
            signals.append({
                "sym": symbol,
                "price": last_price,
                "close": close_price,
                "vol": vol,
                "value_toman": value / 10,
                "power": buyer_power,
                "money_flow_toman": money_flow_toman,
                "time": now_str,
            })

    # مرتب‌سازی بر اساس قدرت ورود پول
    signals.sort(key=lambda x: x["money_flow_toman"], reverse=True)
    return signals, total

def main():
    print("شروع اسکن بورس و کدال...")
    state = load_state()
    now_time = datetime.now().strftime("%H:%M - %Y/%m/%d")

    # ========== ۱. کدال ==========
    codal_history = set(state.get("codal", []))
    latest_letters = get_codal_latest_letters()
    new_letters = []

    for ltr in latest_letters:
        if ltr["id"] not in codal_history:
            new_letters.append(ltr)
            codal_history.add(ltr["id"])

    state["codal"] = list(codal_history)[-150:]  # نگهداری آخرین ۱۵۰ تا

    for l in new_letters:
        msg = (
            f"📰 <b>اطلاعیه جدید کدال | #{l['sym']}</b>\n\n"
            f"📝 <b>عنوان:</b> {l['title']}\n"
            f"⏰ <b>زمان:</b> {l['time']}\n\n"
            f"🔗 <a href=\"{l['url']}\">مشاهده در کدال</a>"
        )
        send_bale_message(msg)
        time.sleep(0.4)

    # ========== ۲. تابلوخوانی ==========
    market_watch, client_dict = get_tsetmc_data()

    if not market_watch:
        err_msg = (
            f"⚠️ <b>خطا در دریافت اطلاعات TSETMC ({now_time})</b>\n"
            f"ارتباط با سرور بورس برقرار نشد.\n"
            f"• بررسی کنید پروکسی ایرانی (IRAN_PROXY) تنظیم شده باشد.\n"
            f"• یا ربات را روی سرور داخل ایران اجرا کنید."
        )
        send_bale_message(err_msg)
        save_state(state)
        return

    signals, total_scanned = analyze_market(market_watch, client_dict)

    tsetmc_state = state.get("tsetmc", {})
    new_signals = []

    today_date = datetime.now().strftime("%Y/%m/%d")
    for sig in signals:
        last_sent = tsetmc_state.get(sig["sym"])
        if last_sent != today_date:
            new_signals.append(sig)
            tsetmc_state[sig["sym"]] = today_date

    state["tsetmc"] = tsetmc_state
    save_state(state)

    if new_signals:
        summary = f"🎯 <b>سیگنال‌های تابلوخوانی ({now_time})</b>\n"
        summary += f"تعداد نماد اسکن‌شده: <b>{total_scanned}</b>\n\n"
        for s in new_signals[:12]:
            money_b = s["money_flow_toman"] / 1e9
            summary += (
                f"🔹 <b>#{s['sym']}</b>\n"
                f"▫️ قیمت: <b>{s['price']:,.0f}</b> ریال\n"
                f"▫️ قدرت خریدار حقیقی: <b>{s['power']}</b>\n"
                f"▫️ ورود پول حقیقی: <b>{money_b:,.2f} میلیارد تومان</b>\n"
                f"----------------------------\n"
            )
        send_bale_message(summary)
    elif not new_letters:
        msg = (
            f"📊 <b>گزارش اسکن ({now_time})</b>\n\n"
            f"• نمادهای اسکن‌شده: <b>{total_scanned}</b>\n"
            f"• هیچ سیگنال جدیدی (قدرت ≥ ۱.۵ + ورود پول مثبت) یافت نشد.\n\n"
            f"🟢 ربات فعال است."
        )
        send_bale_message(msg)

    print("پایان اسکن.")

if __name__ == "__main__":
    main()
