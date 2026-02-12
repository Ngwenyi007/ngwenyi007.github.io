import json
import os
import asyncio
import websockets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from typing import Any, Callable, Dict

from dotenv import load_dotenv

# === LOAD ENV ===
load_dotenv()

# === CONFIGURATION ===
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN", "")
DERIV_APP_ID = os.getenv("DERIV_APP_ID", "")
SYMBOL = os.getenv("DERIV_SYMBOL", "R_100")
STAKE = float(os.getenv("DERIV_STAKE", "100.0"))
DURATION = int(os.getenv("DERIV_DURATION_MIN", "1"))  # minutes
TIMEFRAME = int(os.getenv("DERIV_TIMEFRAME_SEC", "60"))  # seconds (1 minute)

EMAIL_SENDER = os.getenv("EMAIL_SENDER", "")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "")  # Gmail App Password
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER", "")

LEARNING_FILE = os.getenv("LEARNING_FILE", "learning.json")
TRADE_HISTORY_FILE = os.getenv("TRADE_HISTORY_FILE", "trade_history.json")
CANDLES_FILE = os.getenv("CANDLES_FILE", "candles.json")

MIN_ACCURACY = int(os.getenv("MIN_ACCURACY", "70"))  # % minimum accuracy before trusting pattern
MIN_SAMPLE_SIZE = int(os.getenv("MIN_SAMPLE_SIZE", "5"))

# === INIT DATA FILES IF MISSING ===
for file, content in [
    (LEARNING_FILE, {"patterns": {}, "rules": []}),
    (TRADE_HISTORY_FILE, [])
]:
    if not os.path.exists(file):
        with open(file, "w") as f:
            json.dump(content, f, indent=2)

# === EMAIL ALERT FUNCTION ===

def send_email(subject: str, message: str) -> None:
    if not (EMAIL_SENDER and EMAIL_APP_PASSWORD and EMAIL_RECEIVER):
        print("✉️ Email not configured; skipping send.")
        return
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECEIVER
        msg["Subject"] = subject
        msg.attach(MIMEText(message, "plain"))
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        server.quit()
        print("📧 Email sent!")
    except Exception as e:
        print(f"❌ Email failed: {e}")

# === CANDLESTICK PATTERN DETECTION FUNCTIONS ===

def check_trend(candles: list[Dict[str, float]]) -> str:
    if len(candles) < 5:
        return "neutral"
    return "bullish" if candles[-1]["close"] > candles[0]["close"] else "bearish"


def is_bullish_engulfing(c1: Dict[str, float], c2: Dict[str, float]) -> bool:
    return (
        c1["close"] < c1["open"]
        and c2["close"] > c2["open"]
        and c2["open"] < c1["close"]
        and c2["close"] > c1["open"]
    )


def is_bearish_engulfing(c1: Dict[str, float], c2: Dict[str, float]) -> bool:
    return (
        c1["close"] > c1["open"]
        and c2["close"] < c2["open"]
        and c2["open"] > c1["close"]
        and c2["close"] < c1["open"]
    )


def is_hammer(c: Dict[str, float]) -> bool:
    body = abs(c["close"] - c["open"])
    upper_shadow = c["high"] - max(c["open"], c["close"]) 
    lower_shadow = min(c["open"], c["close"]) - c["low"]
    return upper_shadow <= body * 0.5 and lower_shadow >= body * 2


def is_shooting_star(c: Dict[str, float]) -> bool:
    body = abs(c["close"] - c["open"])
    upper_shadow = c["high"] - max(c["open"], c["close"]) 
    lower_shadow = min(c["open"], c["close"]) - c["low"]
    return upper_shadow >= body * 2 and lower_shadow <= body * 0.5


def is_doji(c: Dict[str, float]) -> bool:
    return abs(c["close"] - c["open"]) <= (c["high"] - c["low"]) * 0.1


def detect_pattern(candles: list[Dict[str, float]]) -> Dict[str, Any]:
    if len(candles) < 3:
        return {"matched": False}
    last = candles[-1]
    prev = candles[-2]
    trend = check_trend(candles[-5:]) if len(candles) >= 5 else "neutral"

    if is_bullish_engulfing(prev, last) and trend == "bearish":
        return {
            "matched": True,
            "pattern": "Bullish Engulfing",
            "decision": "BUY",
            "message": "Bullish engulfing in bearish trend",
            "confidence": 90,
        }
    if is_bearish_engulfing(prev, last) and trend == "bullish":
        return {
            "matched": True,
            "pattern": "Bearish Engulfing",
            "decision": "SELL",
            "message": "Bearish engulfing in bullish trend",
            "confidence": 90,
        }
    if is_hammer(last) and trend == "bearish":
        return {
            "matched": True,
            "pattern": "Hammer",
            "decision": "BUY",
            "message": "Hammer candlestick in bearish trend",
            "confidence": 80,
        }
    if is_shooting_star(last) and trend == "bullish":
        return {
            "matched": True,
            "pattern": "Shooting Star",
            "decision": "SELL",
            "message": "Shooting star in bullish trend",
            "confidence": 80,
        }
    if is_doji(last):
        return {
            "matched": True,
            "pattern": "Doji",
            "decision": "HOLD",
            "message": "Market indecision",
            "confidence": 50,
        }

    return {"matched": False}

# === LEARNING FUNCTIONS ===

def update_learning(pattern: str, won: bool) -> None:
    with open(LEARNING_FILE) as f:
        learning = json.load(f)

    patterns = learning.get("patterns", {})
    if pattern not in patterns:
        patterns[pattern] = {"wins": 0, "losses": 0, "accuracy": 0.0}

    if won:
        patterns[pattern]["wins"] += 1
    else:
        patterns[pattern]["losses"] += 1

    total = patterns[pattern]["wins"] + patterns[pattern]["losses"]
    if total > 0:
        patterns[pattern]["accuracy"] = round(patterns[pattern]["wins"] / total * 100, 2)

    learning["patterns"] = patterns
    with open(LEARNING_FILE, "w") as f:
        json.dump(learning, f, indent=2)


def get_accuracy(pattern: str) -> float:
    if not os.path.exists(LEARNING_FILE):
        return 0
    with open(LEARNING_FILE) as f:
        try:
            learning = json.load(f)
        except Exception:
            learning = {"patterns": {}, "rules": []}
            with open(LEARNING_FILE, "w") as fw:
                json.dump(learning, fw, indent=2)
    if not isinstance(learning, dict):
        learning = {"patterns": {}, "rules": []}
        with open(LEARNING_FILE, "w") as fw:
            json.dump(learning, fw, indent=2)

    stats = learning.get("patterns", {}).get(pattern)
    if not stats:
        return 0
    samples = stats.get("wins", 0) + stats.get("losses", 0)
    if samples < MIN_SAMPLE_SIZE:
        return 0
    return float(stats.get("accuracy", 0))

# === LOGGING ===

def log_trade(trade: Dict[str, Any]) -> None:
    if not os.path.exists(TRADE_HISTORY_FILE):
        with open(TRADE_HISTORY_FILE, "w") as f:
            json.dump([], f)
    with open(TRADE_HISTORY_FILE) as f:
        history = json.load(f)
    history.append(trade)
    with open(TRADE_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

# === WEBSOCKET HELPERS ===

def next_req_id() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


async def recv_until(ws: websockets.WebSocketClientProtocol, predicate: Callable[[Dict[str, Any]], bool]) -> Dict[str, Any]:
    while True:
        raw = await ws.recv()
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        if "error" in msg:
            raise RuntimeError(f"Deriv API error: {msg['error']}")
        if predicate(msg):
            return msg


# === DERIV API FUNCTIONS ===

async def request_candles(ws: websockets.WebSocketClientProtocol) -> list[Dict[str, float]]:
    now = int(datetime.now(timezone.utc).timestamp())
    start = now - TIMEFRAME * 30
    rid = next_req_id()
    await ws.send(
        json.dumps(
            {
                "ticks_history": SYMBOL,
                "adjust_start_time": 1,
                "count": 30,
                "granularity": TIMEFRAME,
                "style": "candles",
                "start": start,
                "end": "latest",
                "req_id": rid,
            }
        )
    )
    msg = await recv_until(
        ws,
        lambda m: m.get("req_id") == rid and m.get("msg_type") in ("history", "candles"),
    )
    candles = msg.get("candles") or []
    return candles


async def place_trade(ws: websockets.WebSocketClientProtocol, contract_type: str) -> str | None:
    # 1) Proposal
    pid_req = next_req_id()
    await ws.send(
        json.dumps(
            {
                "proposal": 1,
                "amount": STAKE,
                "basis": "stake",
                "contract_type": contract_type,  # "CALL" or "PUT"
                "currency": "USD",
                "duration": DURATION,
                "duration_unit": "m",
                "symbol": SYMBOL,
                "req_id": pid_req,
            }
        )
    )
    prop = await recv_until(ws, lambda m: m.get("msg_type") == "proposal" and m.get("req_id") == pid_req)
    if "proposal" not in prop:
        print("❌ Proposal failed:", prop)
        return None
    proposal_id = prop["proposal"]["id"]

    # 2) Buy
    buy_req = next_req_id()
    await ws.send(json.dumps({"buy": proposal_id, "price": STAKE, "req_id": buy_req}))
    buy = await recv_until(ws, lambda m: m.get("msg_type") == "buy" and m.get("req_id") == buy_req)
    if "buy" in buy:
        print(f"✅ Trade placed: {buy['buy'].get('transaction_id')}")
        return str(buy["buy"].get("contract_id"))
    else:
        print("❌ Trade failed:", buy)
        return None


async def wait_for_settlement(ws: websockets.WebSocketClientProtocol, contract_id: str, timeout_s: int = 300) -> float:
    start_ts = int(datetime.now(timezone.utc).timestamp())
    while int(datetime.now(timezone.utc).timestamp()) - start_ts < timeout_s:
        rid = next_req_id()
        await ws.send(json.dumps({"proposal_open_contract": 1, "contract_id": contract_id, "req_id": rid}))
        poc = await recv_until(ws, lambda m: m.get("msg_type") == "proposal_open_contract" and m.get("req_id") == rid)
        data = poc.get("proposal_open_contract", {})
        if data.get("is_sold") or data.get("is_expired"):
            return float(data.get("profit", 0.0))
        await asyncio.sleep(2)
    return 0.0


# === MAIN BOT LOOP ===

async def main() -> None:
    if not (DERIV_APP_ID and DERIV_API_TOKEN):
        print("❌ Missing DERIV_APP_ID or DERIV_API_TOKEN env vars.")
        return

    uri = f"wss://ws.derivws.com/websockets/v3?app_id={DERIV_APP_ID}"
    async with websockets.connect(uri) as ws:
        print("✅ Connected to Deriv WebSocket")

        # Authorize
        auth_rid = next_req_id()
        await ws.send(json.dumps({"authorize": DERIV_API_TOKEN, "req_id": auth_rid}))
        auth = await recv_until(ws, lambda m: m.get("msg_type") == "authorize" and m.get("req_id") == auth_rid)
        if "error" in auth:
            print(f"❌ Auth failed: {auth['error'].get('message')}")
            return
        print("🔑 Authorized")

        while True:
            try:
                candles = await request_candles(ws)
            except Exception as e:
                print(f"⚠️ Candle request failed: {e}")
                await asyncio.sleep(5)
                continue

            if not candles:
                print("⚠️ No candles received yet.")
                await asyncio.sleep(5)
                continue

            try:
                with open(CANDLES_FILE, "w") as f:
                    json.dump(candles, f, indent=2)
            except Exception as e:
                print(f"⚠️ Failed to write candles file: {e}")

            decision = detect_pattern(candles)
            print(f"📊 Pattern Detection: {decision}")

            if decision.get("matched") and decision.get("decision") in ["BUY", "SELL"]:
                accuracy = get_accuracy(decision["pattern"])  # 0..100
                print(f"🔎 Pattern accuracy: {accuracy}%")
                if accuracy >= MIN_ACCURACY:
                    action = "CALL" if decision["decision"] == "BUY" else "PUT"
                    try:
                        contract_id = await place_trade(ws, action)
                    except Exception as e:
                        print(f"❌ Trade placement error: {e}")
                        contract_id = None
                    if contract_id:
                        print("⏳ Waiting for settlement...")
                        try:
                            profit = await wait_for_settlement(ws, contract_id)
                        except Exception as e:
                            print(f"⚠️ Settlement check failed: {e}")
                            profit = 0.0
                        won = profit > 0
                        update_learning(decision["pattern"], won)
                        log_trade(
                            {
                                "time": str(datetime.now()),
                                "pattern": decision["pattern"],
                                "decision": decision["decision"],
                                "profit": profit,
                                "accuracy_at_trade": accuracy,
                                "contract_id": contract_id,
                            }
                        )
                        send_email(
                            f"Trade Result: {'WIN' if won else 'LOSS'}",
                            (
                                f"Pattern: {decision['pattern']}\n"
                                f"Decision: {decision['decision']}\n"
                                f"Profit: {profit}\n"
                                f"Accuracy at trade: {accuracy}%\n"
                            ),
                        )
                else:
                    print(f"⚠️ Pattern accuracy below threshold ({MIN_ACCURACY}%), skipping trade.")
            else:
                print("⏳ No confident trade signal, skipping.")

            await asyncio.sleep(5)  # Adjust frequency as you want


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Stopped by user.")