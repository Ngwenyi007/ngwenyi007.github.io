# Deriv Trading Bot

Secure and resilient Deriv WebSocket trading bot with candlestick pattern detection.

## Setup

1. Create and populate `.env` (use `.env.example` as a template):
   - Use a Gmail App Password for `EMAIL_APP_PASSWORD`.
   - Rotate any previously exposed tokens/passwords.

2. Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python deriv_stream.py
```

## Notes
- Trades are only placed when a pattern's learned accuracy >= `MIN_ACCURACY` and sample size >= `MIN_SAMPLE_SIZE`.
- Contract settlement is polled until sold/expired.
- Data files: `learning.json`, `trade_history.json`, `candles.json`.