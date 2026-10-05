import os
import re
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("AVIATIONSTACK_API_KEY")
URL = "http://api.aviationstack.com/v1/flights"  # free plan supports http only

# City / country -> airport IATA codes (extend as needed)
IATA = {
    "new delhi": ["DEL"], "delhi": ["DEL"],
    "chennai": ["MAA"], "mumbai": ["BOM"], "bangalore": ["BLR"],
    "bengaluru": ["BLR"], "hyderabad": ["HYD"], "kolkata": ["CCU"],
    "kochi": ["COK"], "goa": ["GOI"], "pune": ["PNQ"],
    "ahmedabad": ["AMD"], "jaipur": ["JAI"], "coimbatore": ["CJB"],
    "madurai": ["IXM"], "trichy": ["TRZ"], "tiruchirappalli": ["TRZ"],
    "tokyo": ["HND", "NRT"], "japan": ["HND", "NRT"],
    "osaka": ["KIX"], "kyoto": ["KIX"],
    "singapore": ["SIN"], "dubai": ["DXB"], "bangkok": ["BKK"],
    "thailand": ["BKK"], "bali": ["DPS"], "indonesia": ["DPS"],
    "kuala lumpur": ["KUL"], "malaysia": ["KUL"], "colombo": ["CMB"],
    "sri lanka": ["CMB"], "hong kong": ["HKG"], "seoul": ["ICN"],
    "south korea": ["ICN"], "london": ["LHR"], "paris": ["CDG"],
    "new york": ["JFK"], "sydney": ["SYD"], "maldives": ["MLE"],
}

FARE_NOTE = (
    "NOTE: This source gives schedules only (flights for the current day, not "
    "your travel date). No fares/prices are available, so any price must be "
    "labelled as an estimate."
)


def _local(ts: str) -> str:
    """Aviationstack tags airport-local times with '+00:00'. Show them as local."""
    if not isinstance(ts, str) or len(ts) < 16:
        return str(ts)
    return ts[:16].replace("T", " ") + " (airport local time)"


def _codes(place: str):
    place = place.lower().strip()
    for key in sorted(IATA, key=len, reverse=True):  # longest match first
        if key in place:
            return IATA[key]
    return []


def search_flights(query: str) -> str:
    """Query looks like: 'Round-trip flights from Chennai to Delhi for 2 traveller(s)'."""
    if not API_KEY:
        return "NO FLIGHT DATA: AVIATIONSTACK_API_KEY is missing in .env."

    m = re.search(r"from\s+(.+?)\s+to\s+(.+?)(?:\s+for\s|$)", query, re.IGNORECASE)
    if not m:
        return "NO FLIGHT DATA: could not read origin and destination from the request."

    origin_name, dest_name = m.group(1), m.group(2)
    origins = _codes(origin_name)
    dests = _codes(dest_name)
    if not origins or not dests:
        return (
            f"NO FLIGHT DATA: no airport code known for '{origin_name}' or "
            f"'{dest_name}'. Add it to IATA in tools/flight_tool.py. {FARE_NOTE}"
        )

    lines = []
    for dep in origins[:1]:
        for arr in dests[:2]:
            try:
                resp = requests.get(
                    URL,
                    params={
                        "access_key": API_KEY,
                        "dep_iata": dep,
                        "arr_iata": arr,
                        "limit": 25,  # fetch extra, codeshares are skipped below
                    },
                    timeout=15,
                )
                data = resp.json()
            except Exception as e:
                lines.append(f"Flight search {dep}->{arr} failed: {e}")
                continue

            if "error" in data:
                msg = data["error"].get("message", "unknown error")
                lines.append(f"Flight search {dep}->{arr} error: {msg}")
                continue

            kept = 0
            seen = set()
            for f in data.get("data", []):
                # Codeshare entries are the same physical plane sold under
                # another airline's number, so skip them.
                if f.get("codeshared"):
                    continue
                if kept >= 5:
                    break
                airline = (f.get("airline") or {}).get("name", "Unknown")
                number = (f.get("flight") or {}).get("iata", "?")
                dep_t = (f.get("departure") or {}).get("scheduled", "?")
                arr_t = (f.get("arrival") or {}).get("scheduled", "?")
                if (dep_t, arr_t) in seen:
                    continue  # same plane sold under another airline's number
                seen.add((dep_t, arr_t))
                status = f.get("flight_status", "Unknown")
                kept += 1
                lines.append(
                    f"Airline: {airline} | Flight: {number} | {dep} -> {arr} | "
                    f"Departs: {_local(dep_t)} | Arrives: {_local(arr_t)} | Status: {status}"
                )

    if not lines:
        return f"NO FLIGHT DATA: no flights found for {origin_name} -> {dest_name}. {FARE_NOTE}"

    return "\n".join(lines) + "\n" + FARE_NOTE