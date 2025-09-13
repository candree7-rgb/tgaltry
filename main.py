import os, re, requests
from telethon import events
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from math import floor

# === ENV ===
API_ID         = int(os.getenv("API_ID"))
API_HASH       = os.getenv("API_HASH")
STRING_SESSION = os.getenv("STRING_SESSION")
WEBHOOK        = os.getenv("N8N_WEBHOOK_URL")
CHAT_ID        = os.getenv("CHAT_ID", "")
CHAT_TITLE     = os.getenv("CHAT_TITLE", "")
MAX_LEVERAGE   = int(os.getenv("MAX_LEVERAGE", 75))
SAFETY_PCT     = float(os.getenv("SAFETY_PCT", 80))

# === CLIENT ===
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

def match_chat(e):
    if CHAT_ID:
        return str(e.chat_id) == str(CHAT_ID)
    if CHAT_TITLE:
        c = e.chat
        t = getattr(c, "title", "")
        f = getattr(c, "first_name", "")
        return t == CHAT_TITLE or f == CHAT_TITLE
    return True

def round_tick(value, digits=4):
    return round(value, digits)

def parse_message(text):
    text = text.strip()

    # Nur "🟢 Long" oder "🔴 Short" erlauben
    if "🟢 Long" not in text and "🔴 Short" not in text:
        return None

    side = "long" if "🟢 Long" in text else "short"
    is_long = side == "long"

    pair = re.search(r"Name:\s*([A-Z0-9]+)\s*/\s*([A-Z0-9]+)", text, re.IGNORECASE)
    entry = re.search(r"Entry\s*price.*?:\s*([0-9]*\.?[0-9]+)", text, re.IGNORECASE)
    targets = re.findall(r"\d+\)\s*([0-9]*\.?[0-9]+)", text)
    sl_match = re.search(r"(SL|Stop[- ]?Loss)\s*:\s*([0-9]*\.?[0-9]+)", text, re.IGNORECASE)

    if not pair or not entry or len(targets) < 2:
        raise ValueError("Fehlende Werte im Signal.")

    base, quote = pair.group(1).upper(), pair.group(2).upper()
    entry = float(entry.group(1))
    targets = list(map(float, targets[:4]))  # max. 4 TPs
    sl = float(sl_match.group(2)) if sl_match else None

    # 3 TPs erzeugen
    if len(targets) == 2:
        targets.append(targets[1])
    elif len(targets) == 3:
        pass
    elif len(targets) >= 4:
        mid = (targets[1] + targets[2]) / 2
        targets = [targets[0], mid, targets[3]]

    tp1, tp2, tp3 = targets[:3]

    # SL oder berechneter SL
    if sl:
        sl_pct = abs((entry - sl) / entry) * 100
        lev = floor(SAFETY_PCT / sl_pct)
    else:
        lev = MAX_LEVERAGE
        sl_pct = SAFETY_PCT / lev
        sl = entry * (1 - sl_pct / 100) if is_long else entry * (1 + sl_pct / 100)

    lev = max(1, min(lev, MAX_LEVERAGE))
    sl = round_tick(sl)

    # Plausibilität
    if is_long and not (sl < entry < tp1 < tp2 < tp3):
        raise ValueError("Long: Entry, TP, SL nicht plausibel.")
    if not is_long and not (sl > entry > tp1 > tp2 > tp3):
        raise ValueError("Short: Entry, TP, SL nicht plausibel.")

    symbol = f"BYBIF_USDT_{base}"
    signal_price = round_tick(entry)
    tp1 = round_tick(tp1)
    tp2 = round_tick(tp2)
    tp3 = round_tick(tp3)

    payload = {
        "api_key": os.getenv("ALTRADY_API_KEY"),
        "api_secret": os.getenv("ALTRADY_API_SECRET"),
        "exchange": "BYBIF",
        "action": "open",
        "symbol": symbol,
        "side": side,
        "order_type": "limit",
        "signal_price": signal_price,
        "leverage": lev,
        "take_profit": [
            {"price": tp1, "position_percentage": 15},
            {"price": tp2, "position_percentage": 25},
            {"price": tp3, "position_percentage": 30},
            {"price": tp3, "position_percentage": 30, "trailing_distance": 1.2}
        ],
        "stop_loss": {
            "stop_price": sl,
            "protection_type": "FOLLOW_TAKE_PROFIT"
        },
        "entry_expiration": {"time": 60}
    }

    return payload

@client.on(events.NewMessage())
async def handler(e):
    if not match_chat(e): return

    try:
        payload = parse_message(e.raw_text)
        if not payload:
            print("Ignoriert:", e.raw_text[:40])
            return

        res = requests.post(WEBHOOK, json=payload, timeout=10)
        print("Webhook gesendet:", res.status_code)
    except Exception as ex:
        print("Fehler:", ex)

client.start()
print("Listening…")
client.run_until_disconnected()
