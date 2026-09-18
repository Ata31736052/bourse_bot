# ============================================
# 🟢 ربات پیشرفته بورس ایران + کدال + تابلوخوانی
# ============================================

import os
import json
import time
import ssl
import urllib.request

BALE_TOKEN = os.getenv("BALE_TOKEN")
BALE_CHAT_ID = os.getenv("BALE_CHAT_ID")

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# لیست برای ذخیره نمادهای سیگنال‌شده در طول اجرای فعلی
SENT_SIGNALS = set()

def http_get(url, timeout=15):
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, context=CTX, timeout=timeout) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"⚠️ خطا در دریافت اطلاعات از {url}: {e}")
        return None

def send_bale_message(text):
    if not BALE_TOKEN or not BALE_CHAT_ID:
        print("❌ توکن یا چت‌آیدی بله تنظیم نشده است.")
        print(text)
        return False
    
    url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": BALE_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }).encode('utf-8')
    
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=10) as response:
            return response.status == 200
    except Exception as e:
        print(f"⚠️ خطا در ارسال پیام به بله: {e}")
        return False

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 1)

def get_client_power(ins_id):
    """محاسبه قدرت خریدار حقیقی به فروشنده حقیقی (تابلوخوانی)"""
    url = f"https://old.tsetmc.com/tsev2/data/clienttype.aspx?i={ins_id}"
    raw = http_get(url)
    if not raw:
        return 1.0
    try:
        # دریافت آخرین سطر داده حقیقی حقوقی
        lines = raw.strip().split(';')
        if lines:
            cols = lines[-1].split(',')
            if len(cols) >= 9:
                buy_real_vol = float(cols[1])   # حجم خرید حقیقی
                buy_real_count = float(cols[5]) # تعداد خریدار حقیقی
                sell_real_vol = float(cols[3])  # حجم فروش حقیقی
                sell_real_count = float(cols[7])# تعداد فروشنده حقیقی

                if buy_real_count > 0 and sell_real_count > 0 and sell_real_vol > 0:
                    buy_per_capita = buy_real_vol / buy_real_count
                    sell_per_capita = sell_real_vol / sell_real_count
                    if sell_per_capita > 0:
                        return round(buy_per_capita / sell_per_capita, 2)
    except Exception as e:
        print(f"⚠️ خطا در دریافت اطلاعات حقیقی/حقوقی {ins_id}: {e}")
    return 1.0

def get_tsetmc_market_watch():
    url = "https://old.tsetmc.com/tsev2/data/MarketWatchPlus.aspx"
    raw_data = http_get(url)
    if not raw_data:
        return []

    symbols = []
    try:
        sections = raw_data.split('@')
        if len(sections) > 2:
            rows = sections[2].split(';')
            for row in rows:
                cols = row.split(',')
                if len(cols) >= 11:
                    ins_id = cols[0]
                    ticker = cols[2]
                    name = cols[3]
                    hevol = float(cols[9])
                    pdrst = float(cols[10])
                    pcle = float(cols[7])
                    yesterday = float(cols[5])
                    
                    if hevol > 0 and pcle > 0 and not ticker.startswith("حسابه"):
                        symbols.append({
                            'id': ins_id,
                            'ticker': ticker,
                            'name': name,
                            'volume': hevol,
                            'last_price': pdrst,
                            'close_price': pcle,
                            'yesterday': yesterday
                        })
    except Exception as e:
        print(f"⚠️ خطا در پردازش دیده‌بان: {e}")
        
    return symbols

def get_symbol_history(ins_id):
    url = f"https://old.tsetmc.com/tsev2/data/Export-Txt.aspx?t=i&a=1&b=0&i={ins_id}"
    csv_data = http_get(url)
    if not csv_data:
        return None, None
    
    closes, volumes = [], []
    lines = csv_data.strip().split('\n')
    
    for line in lines[1:30]:
        cols = line.split(',')
        if len(cols) >= 7:
            try:
                closes.append(float(cols[4]))
                volumes.append(float(cols[6]))
            except ValueError:
                continue
                
    closes.reverse()
    volumes.reverse()
    return closes, volumes

def check_codal_disclosure(ticker):
    url = f"https://api.codal.ir/api/search/v2/q?Symbol={ticker}&PageNumber=1"
    raw = http_get(url)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        letters = data.get('Letters', [])
        
        for letter in letters[:3]:
            title = letter.get('Title', '')
            disclosure_type = None
            if "افشای اطلاعات با اهمیت" in title and "گروه الف" in title:
                disclosure_type = "🚨 گروه الف (با اهمیت بالا)"
            elif "افشای اطلاعات با اهمیت" in title and "گروه ب" in title:
                disclosure_type = "⚠️ گروه ب"
            
            if disclosure_type:
                return {
                    'type': disclosure_type,
                    'title': title,
                    'publish_date': letter.get('PublishDateTime', ''),
                    'url': f"https://codal.ir{letter.get('Url', '')}"
                }
    except Exception as e:
        print(f"⚠️ خطا در کدال {ticker}: {e}")
        
    return None

def run_bourse_scanner():
    print("🔎 شروع اسکن پیشرفته بورس و فرابورس...")
    market_symbols = get_tsetmc_market_watch()
    print(f"تعداد {len(market_symbols)} نماد فعال دریافت شد.")

    signals = []
    
    for sym in market_symbols:
        if sym['volume'] < 100000:
            continue
            
        closes, volumes = get_symbol_history(sym['id'])
        if not volumes or len(volumes) < 15:
            continue
            
        avg_vol_monthly = sum(volumes[-20:]) / len(volumes[-20:]) if len(volumes) >= 20 else sum(volumes)/len(volumes)
        if avg_vol_monthly == 0:
            continue

        vol_ratio = round(sym['volume'] / avg_vol_monthly, 2)
        rsi_val = calculate_rsi(closes)
        
        # ۱. حجم مشکوک (بیش از ۱.۸ برابر)
        # ۲. RSI در محدوده مناسب ۴۲ تا ۶۸
        # ۳. قیمت پایانی مثبت
        if vol_ratio >= 1.8 and (42 <= rsi_val <= 68) and (sym['close_price'] > sym['yesterday']):
            
            # بررسی قدرت خریدار (تابلوخوانی)
            buyer_power = get_client_power(sym['id'])
            
            # شرط ورود پول حقیقی: قدرت خریدار حداقل ۱.۳ برابر فروشنده
            if buyer_power >= 1.3:
                change_pct = round(((sym['close_price'] - sym['yesterday']) / sym['yesterday']) * 100, 2)
                codal_info = check_codal_disclosure(sym['ticker'])
                
                signals.append({
                    'ticker': sym['ticker'],
                    'name': sym['name'],
                    'price': int(sym['close_price']),
                    'change_pct': change_pct,
                    'vol_ratio': vol_ratio,
                    'rsi': rsi_val,
                    'buyer_power': buyer_power,
                    'codal': codal_info,
                    'tsetmc_url': f"https://main.tsetmc.com/instInfo/{sym['id']}"
                })

    if signals:
        print(f"🎯 تعداد {len(signals)} سیگنال با کیفیت بالا کشف شد.")
        for sig in signals:
            msg = (
                f"🟢 <b>#سیگنال_پیشرفته | {sig['ticker']} ({sig['name']})</b>\n\n"
                f"💰 قیمت پایانی: <b>{sig['price']:,} ریال</b> ({sig['change_pct']}%)\n"
                f"📊 <b>حجم امروز:</b> <b>{sig['vol_ratio']} برابر</b> میانگین ماهانه 🔥\n"
                f"💪 <b>قدرت خریدار:</b> <b>{sig['buyer_power']} برابر</b> فروشنده 👑\n"
                f"📈 <b>شاخص RSI:</b> {sig['rsi']}\n\n"
            )
            
            if sig['codal']:
                msg += (
                    f"📢 <b>افشای اطلاعات کدال:</b> {sig['codal']['type']}\n"
                    f"▪️ <a href='{sig['codal']['url']}'>{sig['codal']['title']}</a>\n"
                    f"📅 تاریخ: {sig['codal']['publish_date']}\n\n"
                )
                
            msg += f"🔗 <a href='{sig['tsetmc_url']}'>مشاهده نماد در TSETMC</a>"
            send_bale_message(msg)
            time.sleep(0.5)
    else:
        print("هیچ سیگنال واجد شرایطی در این اسکن یافت نشد.")

if __name__ == "__main__":
    run_bourse_scanner()
    
