# ============================================
# 🤖 ربات جامع تابلوخوانی و کدال بورس ایران (TSETMC + Codal -> بله)
# ============================================

import os
import sys
import json
import time
import requests
import urllib3
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BALE_TOKEN = os.getenv("BALE_TOKEN")
BALE_CHAT_ID = os.getenv("BALE_CHAT_ID")
STATE_FILE = "bourse_state.json"

def send_bale_message(text: str) -> bool:
    """ارسال پیام به پیام‌رسان بله"""
    if not BALE_TOKEN or not BALE_CHAT_ID:
        print("⚠️ توکن یا چت‌آیدی بله تنظیم نشده است.")
        print(text)
        return False

    url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
    payload = {
        "chat_id": BALE_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
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
            return {"tsetmc": {}, "codal": []}
    return {"tsetmc": {}, "codal": []}

def save_state(state):
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def get_tsetmc_data():
    """دریافت دیتای آنلاین بازار با اتصال مستقیم چندگانه"""
    urls_mw = [
        "https://old.tsetmc.com/tsev2/data/MarketWatchPlus.aspx",
        "http://old.tsetmc.com/tsev2/data/MarketWatchPlus.aspx",
        "https://tsetmc.com/tsev2/data/MarketWatchPlus.aspx"
    ]
    url_client = "https://old.tsetmc.com/tsev2/data/ClientTypeAll.aspx"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive"
    }
    
    mw_data, client_data = None, None

    for url in urls_mw:
        try:
            res1 = requests.get(url, headers=headers, timeout=10, verify=False)
            if res1.status_code == 200 and len(res1.text) > 500:
                mw_data = res1.text
                break
        except Exception:
            continue

    try:
        res2 = requests.get(url_client, headers=headers, timeout=10, verify=False)
        if res2.status_code == 200 and len(res2.text) > 100:
            client_data = res2.text
    except Exception:
        pass

    return mw_data, client_data

def get_codal_latest_letters():
    """دریافت آخرین اطلاعیه‌های کل بازار تنها با ۱ درخواست سبک"""
    url = "https://search.codal.ir/api/search/v2/q"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "application/json"}
    letters = []
    
    params = {"Page": 1, "PageSize": 10}
    try:
        res = requests.get(url, headers=headers, params=params, timeout=10, verify=False)
        if res.status_code == 200:
            data = res.json()
            items = data.get("Letters", [])
            for item in items:
                letters.append({
                    "id": str(item.get("TracingNo")),
                    "sym": item.get("Symbol"),
                    "title": item.get("Title"),
                    "time": item.get("PublishDateTime"),
                    "url": f"https://codal.ir/Reports/Decision.aspx?LetterSerial={item.get('Url')}" if item.get('Url') else "https://codal.ir"
                })
    except Exception as e:
        print(f"خطا در دریافت کدال کل بازار: {e}")

    return letters

def analyze_all_market():
    mw_raw, client_raw = get_tsetmc_data()
    now_str = datetime.now().strftime("%H:%M - %Y/%m/%d")
    
    if not mw_raw:
        return None, f"⚠️ <b>خطا در دریافت اطلاعات TSETMC ({now_str})</b>\nارتباط با سرور بورس برقرار نشد."

    client_dict = {}
    if client_raw:
        for line in client_raw.split(";"):
            parts = line.split(",")
            if len(parts) >= 9:
                ins_code = parts[0]
                client_dict[ins_code] = {
                    "buy_count": float(parts[1]) if parts[1] else 1,
                    "sell_count": float(parts[3]) if parts[3] else 1,
                    "buy_vol": float(parts[5]) if parts[5] else 0,
                    "sell_vol": float(parts[7]) if parts[7] else 0,
                }

    filtered_signals = []
    total_scanned = 0

    sections = mw_raw.split("@")
    if len(sections) >= 3:
        price_data = sections[2].split(";")
        for item in price_data:
            parts = item.split(",")
            if len(parts) >= 11:
                ins_code = parts[0]
                symbol_name = parts[2].strip()
                last_price = float(parts[7]) if parts[7] != "0" else float(parts[6])
                close_price = float(parts[6])
                vol = float(parts[9])
                value = float(parts[10])

                total_scanned += 1

                buyer_power = 1.0
                net_money_flow = 0
                if ins_code in client_dict:
                    cd = client_dict[ins_code]
                    buy_capita = (cd["buy_vol"] / cd["buy_count"]) if cd["buy_count"] > 0 else 0
                    sell_capita = (cd["sell_vol"] / cd["sell_count"]) if cd["sell_count"] > 0 else 0
                    
                    if sell_capita > 0:
                        buyer_power = round(buy_capita / sell_capita, 2)
                    
                    net_money_flow = (cd["buy_vol"] - cd["sell_vol"]) * last_price

                money_flow_toman = net_money_flow / 10
                if (buyer_power >= 1.5 and money_flow_toman > 0) or money_flow_toman >= 3_000_000_000:
                    filtered_signals.append({
                        "sym": symbol_name,
                        "price": last_price,
                        "close": close_price,
                        "vol": vol,
                        "value_toman": value / 10,
                        "power": buyer_power,
                        "money_flow_toman": money_flow_toman,
                        "time": now_str
                    })

    return filtered_signals, total_scanned

def main():
    print("شروع اسکن کل بازار بورس و کدال...")
    state = load_state()
    now_time = datetime.now().strftime("%H:%M - %Y/%m/%d")

    # ۱. پردازش کدال کل بازار
    codal_history = state.get("codal", [])
    latest_letters = get_codal_latest_letters()
    new_letters = []

    for ltr in latest_letters:
        if ltr["id"] not in codal_history:
            new_letters.append(ltr)
            codal_history.append(ltr["id"])

    state["codal"] = codal_history[-100:]

    if new_letters:
        for l in new_letters:
            msg = (
                f"📰 <b>اطلاعیه جدید کدال | #{l['sym']}</b>\n\n"
                f"📝 <b>عنوان:</b> {l['title']}\n"
                f"⏰ <b>زمان:</b> {l['time']}\n\n"
                f"🔗 <a href='{l['url']}'>مشاهده در کدال</a>"
            )
            send_bale_message(msg)
            time.sleep(0.3)

    # ۲. اسکن تابلوخوانی کل بازار
    signals, total_scanned = analyze_all_market()

    if signals is None and isinstance(total_scanned, str):
        send_bale_message(total_scanned)
        save_state(state)
        return

    tsetmc_state = state.get("tsetmc", {})
    new_signals = []

    if signals:
        for sig in signals:
            last_sent = tsetmc_state.get(sig["sym"])
            today_date = sig["time"].split(" - ")[1]
            if last_sent != today_date:
                new_signals.append(sig)
                tsetmc_state[sig["sym"]] = today_date

        state["tsetmc"] = tsetmc_state
        save_state(state)

    if new_signals:
        summary_text = f"🎯 <b>سیگنال‌های تابلوخوانی کل بازار ({now_time})</b>\n\n"
        for s in new_signals[:10]:
            summary_text += (
                f"🔹 <b>نماد: #{s['sym']}</b>\n"
                f"▫️ قیمت: <b>{s['price']:,.0f} ریال</b>\n"
                f"▫️ قدرت خریدار: <b>{s['power']}</b>\n"
                f"▫️ ورود پول حقیقی: <b>{s['money_flow_toman']/1e8:,.1f} میلیارد تومان</b>\n"
                f"----------------------------\n"
            )
        send_bale_message(summary_text)
    elif not new_letters:
        msg = (
            f"📊 <b>گزارش اسکن کل بازار ({now_time})</b>\n\n"
            f"• کل نمادهای اسکن‌شده: <b>{total_scanned} نماد</b>\n"
            f"• وضعیت: <i>هیچ سهمی واجد شرایط قدرت خریدار بالای ۱.۵ یا ورود پول سنگین نگردید.</i>\n\n"
            f"🟢 ربات فعال است."
        )
        send_bale_message(msg)

    print("پایان اسکن کل بازار.")

if __name__ == "__main__":
    main()
            
