# Hayange → PwC Dudelange — Traffic Monitor
## Setup Guide (one-time, ~30 minutes)

---

## 1. Google Maps API key (5 min)

1. Go to https://console.cloud.google.com
2. Create a new project (e.g. "hayange-traffic")
3. Enable **Directions API** (search in the API library)
4. Go to **Credentials** → Create API Key
5. Restrict the key to "Directions API" only (for safety)
6. Copy the key — you'll use it as `GOOGLE_MAPS_API_KEY`

**Set a safety budget cap:**
- In Google Cloud → Billing → Budgets & alerts
- Create a budget of €2/month with an email alert at 100%
- This ensures you can never be surprised by unexpected charges

---

## 2. Google Sheet (5 min)

1. Create a new Google Sheet at https://sheets.google.com
2. Rename the first tab to `raw_data`
3. Copy the Sheet ID from the URL:
   `https://docs.google.com/spreadsheets/d/THIS_PART_IS_THE_ID/edit`
4. **Publish it for the dashboard:**
   - File → Share → Publish to web
   - Choose "raw_data" tab → CSV format → Publish
   - This makes the dashboard work without login

---

## 3. Google Service Account (for the poller to write to the Sheet) (10 min)

1. In Google Cloud Console → IAM → Service Accounts → Create
2. Name it "traffic-poller", click Done
3. Click the new account → Keys tab → Add key → JSON → download the file
4. Copy the **entire content** of that JSON file (you'll need it as a GitHub secret)
5. Back in your Google Sheet: Share → add the service account email (ends in
   `@...iam.gserviceaccount.com`) with **Editor** access

---

## 4. Telegram bot (5 min)

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`, follow the prompts, get your **bot token**
3. Start a chat with your new bot (search its name, hit Start)
4. Get your **chat ID**: open this URL in a browser (replace YOUR_TOKEN):
   `https://api.telegram.org/botYOUR_TOKEN/getUpdates`
   After sending any message to the bot, you'll see `"chat":{"id":XXXXXXXX}`
5. Copy both the token and your chat ID

---

## 5. GitHub repo (10 min)

1. Create a new **private** repo on GitHub (e.g. "hayange-traffic")
2. Push the project files:
   ```
   git init
   git add .
   git commit -m "initial"
   git remote add origin https://github.com/YOUR_USERNAME/hayange-traffic.git
   git push -u origin main
   ```
3. Add GitHub Secrets (Settings → Secrets and variables → Actions → New secret):

   | Secret name               | Value                                  |
   |---------------------------|----------------------------------------|
   | `GOOGLE_MAPS_API_KEY`     | Your Maps API key                      |
   | `GOOGLE_SHEET_ID`         | The Sheet ID from step 2               |
   | `GCP_SERVICE_ACCOUNT_JSON`| The full JSON content from step 3      |
   | `TELEGRAM_BOT_TOKEN`      | Your bot token from step 4             |
   | `TELEGRAM_CHAT_ID`        | Your chat ID from step 4               |

---

## 6. Enable GitHub Pages for the dashboard (2 min)

1. In your GitHub repo: Settings → Pages
2. Source: Deploy from branch → `main` → `/dashboard` folder
3. Save — your dashboard will be at:
   `https://YOUR_USERNAME.github.io/hayange-traffic/`
4. Bookmark this on your phone

---

## 7. Seasonal cron adjustment

Luxembourg is UTC+2 in summer (CEST, late Mar–late Oct) and UTC+1 in winter (CET).

In `.github/workflows/traffic.yml`:
- **Summer (Mar–Oct):** use `cron: "0 4 * * 2-5"` (4:00 UTC = 6:00 CEST)
- **Winter (Oct–Mar):** use `cron: "0 5 * * 2-5"` (5:00 UTC = 6:00 CET)

---

## 8. Test it manually

Once everything is set up, go to your GitHub repo → Actions tab → "Traffic Poller" → "Run workflow" button. This triggers an immediate run so you can verify the Sheet gets data and you receive a Telegram message.

---

## File structure

```
hayange-traffic/
├── poller.py                        # Main polling script (runs on GitHub Actions)
├── .github/
│   └── workflows/
│       └── traffic.yml              # Scheduler (Tue–Fri 6 AM)
├── dashboard/
│   └── index.html                   # Live dashboard (GitHub Pages)
└── SETUP.md                         # This file
```

---

## How the dashboard works

- Opens on your phone/laptop any time from 6 AM onwards
- Shows current travel time for all 3 routes with a live trend arrow
- Automatically refreshes every 3 minutes
- Once you have a few weeks of data, shows "historical average for this weekday/time" next to each route
- The "fastest now" badge updates in real time

## The Telegram message (sent at ~6:45 AM)

```
🚗 Hayange → PwC Dudelange — Morning Report

🥇 A31: 24 min now (avg 26 min) — 📉 getting faster
🥈 Ottange: 27 min now (avg 27 min) — → stable
🥉 Secondary: 29 min now (avg 28 min) — 📈 getting slower

✅ Take: A31
```

If you've already left before 6:45, just check the dashboard on your phone.
