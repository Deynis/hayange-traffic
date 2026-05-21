import os, requests

GOOGLE_API_KEY = os.environ["GOOGLE_MAPS_API_KEY"]
ORIGIN      = "31 Rue de la Mine, 57700 Hayange, France"
DESTINATION = "147 Route de Volmerange, 3593 Dudelange, Luxembourg"

ROUTES = {
    "A31":       "via:Kanfen, France|via:Volmerange-les-Mines, France",
    "Eschrange": "via:Angevillers, France|via:Escherange, France|via:Molvange, France",
    "Ottange":   "via:Angevillers, France|via:Rochonvillers, France|via:Ottange, France",
}

for name, waypoints in ROUTES.items():
    r = requests.get(
        "https://maps.googleapis.com/maps/api/directions/json",
        params={
            "origin": ORIGIN, "destination": DESTINATION,
            "waypoints": waypoints, "mode": "driving",
            "departure_time": "now", "traffic_model": "best_guess",
            "key": GOOGLE_API_KEY,
        }, timeout=10
    )
    data = r.json()
    status = data["status"]
    if status != "OK":
        print(f"  {name}: FAIL — status={status}")
        continue
    leg = data["routes"][0]["legs"][0]
    legs_count = len(data["routes"][0]["legs"])
    has_traffic = "duration_in_traffic" in leg
    dur = leg.get("duration_in_traffic", leg["duration"])["value"]
    print(f"  {name}: OK — {round(dur/60)} min {'(traffic)' if has_traffic else '(NO TRAFFIC DATA)'} | legs={legs_count}")
