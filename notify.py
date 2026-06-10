"""
BookMyShow Show Monitor — cloud version for GitHub Actions.
Runs once per invocation, sends a WhatsApp group message via Green API
if new shows are detected at Miraj Cinemas: IMAX, Wadala.

Setup (one-time):
1. Register at https://green-api.com (free, no credit card for 3 months)
2. Create an instance and scan the QR code with your WhatsApp
3. Create a WhatsApp group with your friends
4. Find the group chat ID via Green API dashboard → "Get Groups"
5. Add these GitHub Actions secrets to your repo:
      GREEN_API_INSTANCE  →  your Instance ID  (e.g. 1234567890)
      GREEN_API_TOKEN     →  your API Token    (e.g. abc123...)
      GREEN_API_CHAT_ID   →  group chat ID     (e.g. 120363XXXXXX@g.us)
6. Push repo to GitHub (public repo = unlimited free Action minutes)
7. Go to Actions tab → Run workflow once to test before leaving
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request

from curl_cffi import requests as cf_requests

# ── Configuration ─────────────────────────────────────────────────────────────
URL = (
    "https://in.bookmyshow.com/movies/mumbai/the-odyssey"
    "/buytickets/ET00480917/20260717"
)
VENUE_CODE = "MCIW"                      # Miraj Cinemas: IMAX, Wadala
KNOWN_SHOWS = {"09:50 AM", "08:15 PM"}  # baseline as of 2026-06-08
BMS_LINK = URL
# ─────────────────────────────────────────────────────────────────────────────

_INITIAL_STATE_MARKER = "window.__INITIAL_STATE__ = "
_SESSION = cf_requests.Session()


def _normalize_time(raw: str) -> str:
    raw = raw.strip().upper().replace(" ", " ").replace("\xa0", " ")
    m = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)", raw)
    if m:
        h, mi, period = m.groups()
        return f"{int(h):02d}:{mi} {period}"
    return raw


def get_show_times() -> set[str]:
    """Fetch the BMS page and return show-time strings for VENUE_CODE."""
    resp = _SESSION.get(URL, impersonate="chrome124", timeout=20)
    resp.raise_for_status()
    html = resp.text

    marker_pos = html.find(_INITIAL_STATE_MARKER)
    if marker_pos < 0:
        raise RuntimeError("__INITIAL_STATE__ not found in page")

    start = marker_pos + len(_INITIAL_STATE_MARKER)
    raw = html[start : html.find("</script>", start)].rstrip().rstrip(";")

    venue_pattern = f'"venue_code":"{VENUE_CODE}"'
    pos = 0
    while True:
        vc_idx = raw.find(venue_pattern, pos)
        if vc_idx < 0:
            raise RuntimeError(f"Venue code {VENUE_CODE!r} not found in page data")

        show_idx = raw.find('"showtimes":[', vc_idx)
        if show_idx < 0:
            break

        between = raw[vc_idx:show_idx]
        if not re.search(r'"venue_code":"(?!' + re.escape(VENUE_CODE) + r')', between):
            titles = re.findall(r'"title":"([^"]+)"', raw[show_idx : show_idx + 8_000])
            return {
                _normalize_time(t)
                for t in titles
                if re.match(r"\d{1,2}:\d{2}\s*[AP]M", t, re.I)
            }

        pos = vc_idx + 1

    raise RuntimeError(f"showtimes array for {VENUE_CODE!r} not found")


def send_whatsapp_group(id_instance: str, api_token: str, chat_id: str, text: str) -> None:
    """Send a message to a WhatsApp group via Green API (stdlib only)."""
    url = (
        f"https://api.green-api.com/waInstance{id_instance}"
        f"/sendMessage/{api_token}"
    )
    payload = json.dumps({"chatId": chat_id, "message": text}).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status not in (200, 201):
            raise RuntimeError(f"Green API returned HTTP {resp.status}")


def main() -> None:
    instance = os.environ.get("GREEN_API_INSTANCE", "")
    token = os.environ.get("GREEN_API_TOKEN", "")
    chat_id = os.environ.get("GREEN_API_CHAT_ID", "")

    if not all([instance, token, chat_id]):
        print(
            "ERROR: Set GREEN_API_INSTANCE, GREEN_API_TOKEN, and GREEN_API_CHAT_ID "
            "environment variables (or GitHub Secrets)."
        )
        sys.exit(1)

    print("Fetching BMS show times...")
    try:
        current = get_show_times()
    except Exception as exc:
        print(f"ERROR fetching show times: {exc}")
        sys.exit(1)

    print(f"Current shows: {sorted(current)}")
    new_shows = current - KNOWN_SHOWS

    if not new_shows:
        print("No new shows. Nothing to notify.")
        return

    new_sorted = sorted(new_shows)
    all_sorted = sorted(current)

    message = (
        "NEW SHOW at Miraj Cinemas IMAX Wadala!\n"
        "Movie: The Odyssey (Jul 17)\n"
        f"New: {', '.join(new_sorted)}\n"
        f"All shows: {', '.join(all_sorted)}\n\n"
        f"Book here: {BMS_LINK}"
    )

    print(f"Sending WhatsApp notification for new shows: {new_sorted}")
    try:
        send_whatsapp_group(instance, token, chat_id, message)
        print("WhatsApp message sent successfully.")
    except Exception as exc:
        print(f"ERROR sending WhatsApp message: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
