# Inventory-Automation

Automates the daily Rithum inventory submission flow using Playwright.

## What This Automates

1. Log in to Rithum.
2. Handle profile selection (first available Select/Continue option).
3. Open Inventory Update page.
4. Check All (`#selectAllIBL`).
5. Click Next (`#iblsubmit`).
6. Check Mark all SKU's as Current (`input[name='skudates'][value='1']`).
7. Click Submit (`#submitButton`).
8. Save screenshots for traceability.

## Setup

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

3. Create your env file:

```bash
cp .env.example .env
```

4. Edit `.env` and set values:

```dotenv
RITHUM_URL=https://dsm.commercehub.com/dsm/gotoHome.do
RITHUM_USERNAME=your-email@example.com
RITHUM_PASSWORD=your-password
HEADLESS=true
TIMEOUT_MS=30000
```

## Run

```bash
python run_rithum.py
```

Screenshots are saved under `screenshots/`.

## Scheduling (Linux cron example)

Run daily at 7:00 AM:

```bash
0 7 * * * cd /workspaces/Inventory-Automation && . .venv/bin/activate && python run_rithum.py >> cron.log 2>&1
```

## Security Notes

- Do not commit `.env`.
- Use a dedicated automation account when possible.
- Rotate credentials if they were shared in chat or email.