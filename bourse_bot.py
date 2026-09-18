# ============================================
# 🟢 ربات جامع اسکن بورس ایران + کدال ویژه پیام‌رسان بله
# ============================================

import os
import json
import time
import ssl
import urllib.request

# دریافت کلیدها از تنظیمات امنیتی گیت‌هاب (Secrets)
BALE_TOKEN = os.getenv("BALE_TOKEN")
BALE_CHAT_ID = os.getenv("BALE_CHAT_ID")

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

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

def get_tsetmc_market_watch():
    """دریافت دیدبان کامل بورس و فرابورس"""
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
                    hevol = float(cols[9])    # حجم امروز
                    pdrst = float(cols[10])   # آخرین قیمت
                    pcle = float(cols[7])     # قیمت پایانی
                    yesterday = float(cols[5])# دیروز
                    
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
    """دریافت سابقه برای میانگین حجم ماهانه و RSI"""
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
    """بررسی آخرین وضعیت کدال برای افشای الف و ب"""
    url = f"https://api.codal.ir/api/search/v2/q?Symbol={ticker}&PageNumber=1"
    raw = http_get(url)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        letters = data.get('Letters', [])
        
        for letter in letters[:5]:
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
    print("🔎 شروع اسکن کل بازار بورس و فرابورس ایران...")
    market_symbols = get_tsetmc_market_watch()
    print(f"تعداد {len(market_symbols)} نماد فعال دریافت شد.")

    signals = []
    
    for sym in market_symbols:
        # فیلتر اولیه برای سرعت‌دهی و حذف سهم‌های بسیار کم‌حجم
        if sym['volume'] < 50000:
            continue
            
        closes, volumes = get_symbol_history(sym['id'])
        if not volumes or len(volumes) < 15:
            continue
            
        avg_vol_monthly = sum(volumes[-20:]) / len(volumes[-20:]) if len(volumes) >= 20 else sum(volumes)/len(volumes)
        if avg_vol_monthly == 0:
            continue

        vol_ratio = round(sym['volume'] / avg_vol_monthly, 2)
        rsi_val = calculate_rsi(closes)
        
        # 📌 فیلترهای سیگنال‌دهی:
        # ۱. حجم امروز بیش از ۲ برابر میانگین ماهانه
        # ۲. RSI در محدوده مناسب ۴۵ تا ۶۸
        # ۳. کندل امروز مثبت (قیمت پایانی صعودی)
        is_volume_spike = vol_ratio >= 2.0
        is_rsi_bullish = 45 <= rsi_val <= 68
        is_green = sym['close_price'] > sym['yesterday']
        
        if is_volume_spike and is_rsi_bullish and is_green:
            change_pct = round(((sym['close_price'] - sym['yesterday']) / sym['yesterday']) * 100, 2)
            codal_info = check_codal_disclosure(sym['ticker'])
            
            signals.append({
                'ticker': sym['ticker'],
                'name': sym['name'],
                'price': int(sym['close_price']),
                'change_pct': change_pct,
                'vol_ratio': vol_ratio,
                'rsi': rsi_val,
                'codal': codal_info,
                'tsetmc_url': f"https://main.tsetmc.com/instInfo/{sym['id']}"
            })

    # ارسال به بله
    if signals:
        print(f"🎯 تعداد {len(signals)} سیگنال کشف شد. ارسال به بله...")
        for sig in signals:
            msg = (
                f"🟢 <b>#سیگنال_بورس | {sig['ticker']} ({sig['name']})</b>\n\n"
                f"💰 قیمت پایانی: <b>{sig['price']:,} ریال</b> ({sig['change_pct']}%)\n"
                f"📊 <b>حجم امروز:</b> <b>{sig['vol_ratio']} برابر</b> میانگین ماهانه 🔥\n"
                f"📈 <b>وضعیت RSI:</b> {sig['rsi']}\n\n"
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
        print("هیچ سیگنال جدیدی در این اسکن یافت نشد.")

if __name__ == "__main__":
    run_bourse_scanner()
