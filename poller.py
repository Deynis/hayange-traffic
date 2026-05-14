"""
Hayange → PwC Dudelange — Traffic Poller
Runs Tue–Fri, 6:20–7:00 AM (enforced by GitHub Actions cron).
Polls 3 routes every 3 minutes, writes to Google Sheets,
sends a Telegram update every ~10 min (5 messages per session).
"""

import os
import time
import json
import requests
from datetime import datetime, timezone
import gspread

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

POLL_INTERVAL_SEC    = 180   # 3 minutes
POLL_DURATION_SEC    = 2400  # 40 minutes (6:20 → 7:00)
TELEGRAM_INTERVAL_SEC = 600  # send update every 10 minutes
SHEET_TAB_DATA    = "raw_data"
SHEET_TAB_META    = "meta"

# ── Google Sheets setup ──────────────────────────────────────────────────────

def get_sheet():
    try:
        creds_dict = json.loads(GCP_CREDS_JSON)
    except json.JSONDecodeError:
        raise RuntimeError("GCP_SERVICE_ACCOUNT_JSON is not valid JSON") from None
    gc = gspread.service_account_from_dict(creds_dict)
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
    for attempt in range(3):
        try:
            r = requests.get(
                "https://maps.googleapis.com/maps/api/directions/json",
                params=params, timeout=10
            )
            data = r.json()
            if data["status"] != "OK":
                print(f"  [WARN] {route_name}: API status {data['status']}")
                return None
            leg = data["routes"][0]["legs"][0]
            if "duration_in_traffic" not in leg:
                print(f"  [WARN] {route_name}: duration_in_traffic missing from response")
                return None
            return leg["duration_in_traffic"]["value"]
        except requests.RequestException as e:
            if attempt == 2:
                print(f"  [ERROR] {route_name}: failed after 3 attempts — {e}")
                return None
            time.sleep(2 ** attempt)

# ── Telegram notification ────────────────────────────────────────────────────

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=10)
    except Exception as e:
        print(f"  [WARN] Telegram send failed: {e}")

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
    next_telegram = start  # send immediately at 6:20

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

        if session_data and time.time() >= next_telegram:
            summary = build_summary(session_data)
            print(f"\n[{datetime.now():%H:%M}] Sending Telegram update…\n" + summary)
            send_telegram(summary)
            next_telegram += TELEGRAM_INTERVAL_SEC

        sleep_for = max(0, POLL_INTERVAL_SEC - 6)  # 3 route calls ~6s total
        print(f"  sleeping {sleep_for}s…")
        time.sleep(sleep_for)

    # ── Final message at 7:00 AM ─────────────────────────────────────────────
    if session_data:
        summary = build_summary(session_data)
        print(f"\n[{datetime.now():%H:%M}] Final Telegram update…\n" + summary)
        send_telegram(summary)
    print("\n[done] Session complete.")

if __name__ == "__main__":
    main()
