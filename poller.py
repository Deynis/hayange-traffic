"""
Hayange → PwC Dudelange — Traffic Poller
Runs Tue–Fri, 6:00–6:45 AM (enforced by GitHub Actions cron)
Polls 3 routes every 3 minutes, writes to Google Sheets, sends Telegram summary.
"""

import os
import time
import json
import requests
from datetime import datetime, timezone
import gspread
from google.oauth2.service_account import Credentials

# ── Configuration ────────────────────────────────────────────────────────────

GOOGLE_API_KEY   = os.environ["GOOGLE_MAPS_API_KEY"]
SHEET_ID         = os.environ["GOOGLE_SHEET_ID"]
GCP_CREDS_JSON   = os.environ["GCP_SERVICE_ACCOUNT_JSON"]   # full JSON string
TELEGRAM_TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

ORIGIN = "31 Rue de la Mine, 57700 Hayange, France"  # Feralia
DESTINATION = "147 Route de Volmerange, 3593 Dudelange, Luxembourg"  # PwC

ROUTES = {
    "A31": {
        "waypoints": "via:Kanfen, France|Volmerange-les-Mines, France"
    },
    "Eschrange": {
        "waypoints": "via:Angevillers, France|via:Escherange, France|Molvange, France"
    },
    "Ottange": {
        "waypoints": "via:Angevillers, France|via:Rochonvillers, France|via:Ottange, France"
    },
}

POLL_INTERVAL_SEC = 180   # 3 minutes
POLL_DURATION_SEC = 2700  # 45 minutes
SHEET_TAB_DATA    = "raw_data"
SHEET_TAB_META    = "meta"

# ── Google Sheets setup ──────────────────────────────────────────────────────

def get_sheet():
    creds_dict = json.loads(GCP_CREDS_JSON)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

def ensure_headers(sheet):
    ws = sheet.worksheet(SHEET_TAB_DATA)
    if ws.row_count == 0 or ws.cell(1, 1).value != "timestamp":
        ws.insert_row(
            ["timestamp", "date", "weekday", "time_hhmm",
             "route", "duration_sec", "duration_min"],
            index=1
        )

def append_row(ws, route_name, duration_sec, now):
    ws.append_row([
        now.isoformat(),
        now.strftime("%Y-%m-%d"),
        now.strftime("%A"),
        now.strftime("%H:%M"),
        route_name,
        duration_sec,
        round(duration_sec / 60, 2)
    ])

# ── Google Maps call ─────────────────────────────────────────────────────────

def get_duration(route_name, route_cfg):
    """Returns travel duration in seconds via Directions API with traffic."""
    params = {
        "origin":            ORIGIN,
        "destination":       DESTINATION,
        "waypoints":         route_cfg["waypoints"],
        "mode":              "driving",
        "departure_time":    "now",
        "traffic_model":     "best_guess",
        "key":               GOOGLE_API_KEY,
    }
    r = requests.get(
        "https://maps.googleapis.com/maps/api/directions/json",
        params=params, timeout=10
    )
    data = r.json()
    if data["status"] != "OK":
        print(f"  [WARN] {route_name}: API status {data['status']}")
        return None
    leg = data["routes"][0]["legs"][0]
    # duration_in_traffic is present when departure_time is set
    return leg.get("duration_in_traffic", leg["duration"])["value"]

# ── Telegram notification ────────────────────────────────────────────────────

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }, timeout=10)

def build_summary(session_data):
    """
    session_data: list of {route, duration_sec, time}
    Returns a Telegram-formatted summary string.
    """
    from collections import defaultdict
    by_route = defaultdict(list)
    for row in session_data:
        by_route[row["route"]].append(row["duration_sec"])

    lines = ["🚗 *Hayange → PwC Dudelange — Morning Report*\n"]
    ranked = []
    for route, durations in by_route.items():
        avg = sum(durations) / len(durations)
        latest = durations[-1]
        # trend: compare last 3 vs previous 3
        if len(durations) >= 6:
            recent = sum(durations[-3:]) / 3
            older  = sum(durations[-6:-3]) / 3
            delta  = recent - older
            if delta > 60:
                trend = "📈 getting slower"
            elif delta < -60:
                trend = "📉 getting faster"
            else:
                trend = "➡ stable"
        else:
            trend = "➡ not enough data yet"
        ranked.append((route, latest, avg, trend))

    ranked.sort(key=lambda x: x[1])  # sort by latest duration

    for i, (route, latest, avg, trend) in enumerate(ranked):
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else "  "
        lines.append(
            f"{medal} *{route}*: {round(latest/60)} min now "
            f"(avg {round(avg/60)} min) — {trend}"
        )

    best = ranked[0][0]
    lines.append(f"\n✅ *Take: {best}*")
    return "\n".join(lines)

# ── Main polling loop ────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now():%H:%M}] Poller starting — {POLL_DURATION_SEC//60} min window")
    sheet = get_sheet()
    ws = sheet.worksheet(SHEET_TAB_DATA)
    ensure_headers(sheet)

    session_data = []
    start = time.time()

    while time.time() - start < POLL_DURATION_SEC:
        now = datetime.now(timezone.utc).astimezone()
        print(f"\n[{now:%H:%M:%S}] Polling…")

        for route_name, route_cfg in ROUTES.items():
            secs = get_duration(route_name, route_cfg)
            if secs is not None:
                append_row(ws, route_name, secs, now)
                session_data.append({"route": route_name, "duration_sec": secs, "time": now})
                print(f"  {route_name}: {round(secs/60)} min")
            time.sleep(2)  # small gap between route calls

        elapsed = time.time() - start
        remaining = POLL_INTERVAL_SEC - (time.time() - start + elapsed % POLL_INTERVAL_SEC)
        sleep_for = max(0, POLL_INTERVAL_SEC - 6)  # 3 route calls ~6s total
        print(f"  sleeping {sleep_for}s…")
        time.sleep(sleep_for)

    # ── End of session: send Telegram summary ────────────────────────────────
    summary = build_summary(session_data)
    print("\n" + summary)
    send_telegram(summary)
    print("\n[done] Session complete.")

if __name__ == "__main__":
    main()
