"""
BookMyShow Show Monitor — Miraj Cinemas: IMAX, Wadala
Alerts with a loud continuous beep when a new show is detected.

Setup (one-time):
    pip install curl_cffi

Run:
    python main.py
"""

import re
import sys
import time
import threading
import winsound
from datetime import datetime

from curl_cffi import requests as cf_requests

# ── Configuration ─────────────────────────────────────────────────────────────
URL = (
    "https://in.bookmyshow.com/movies/mumbai/the-odyssey"
    "/buytickets/ET00480917/20260717"
)
VENUE_CODE = "MCIW"                          # Miraj Cinemas: IMAX, Wadala
KNOWN_SHOWS = {"09:50 AM", "08:15 PM"}      # baseline as of 2026-06-08
CHECK_INTERVAL = 60                          # seconds between checks
# ─────────────────────────────────────────────────────────────────────────────

_INITIAL_STATE_MARKER = "window.__INITIAL_STATE__ = "
_SESSION = cf_requests.Session()
_alarm_stop = threading.Event()


def _normalize_time(raw: str) -> str:
    raw = raw.strip().upper().replace(" ", " ").replace("\xa0", " ")
    m = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)", raw)
    if m:
        h, mi, period = m.groups()
        return f"{int(h):02d}:{mi} {period}"
    return raw


def get_show_times() -> set[str]:
    """
    Fetch the BMS page and return the set of show-time strings for VENUE_CODE.
    Uses curl_cffi to impersonate Chrome's TLS fingerprint, bypassing Cloudflare.
    """
    resp = _SESSION.get(URL, impersonate="chrome124", timeout=20)
    resp.raise_for_status()
    html = resp.text

    # Extract the __INITIAL_STATE__ JSON blob (BMS embeds all SSR data here)
    marker_pos = html.find(_INITIAL_STATE_MARKER)
    if marker_pos < 0:
        raise RuntimeError("__INITIAL_STATE__ not found in page")
    raw = html[marker_pos + len(_INITIAL_STATE_MARKER):]
    raw = raw[: html.find("</script>", marker_pos + len(_INITIAL_STATE_MARKER))].rstrip().rstrip(";")

    # Find the showtimes array that belongs to our venue.
    # Each venue's analytics block contains "venue_code":"MCIW" immediately
    # before the venue's "showtimes":[...] array, with no other venue_code
    # in between.
    venue_pattern = f'"venue_code":"{VENUE_CODE}"'
    pos = 0
    while True:
        vc_idx = raw.find(venue_pattern, pos)
        if vc_idx < 0:
            raise RuntimeError(
                f"Venue code {VENUE_CODE!r} not found in page data"
            )

        show_idx = raw.find('"showtimes":[', vc_idx)
        if show_idx < 0:
            break

        # Confirm no other venue_code appears between our match and showtimes
        between = raw[vc_idx:show_idx]
        if not re.search(r'"venue_code":"(?!' + re.escape(VENUE_CODE) + r')', between):
            # Extract "title":"HH:MM AM/PM" entries from this showtimes array
            titles = re.findall(r'"title":"([^"]+)"', raw[show_idx: show_idx + 8_000])
            times = {_normalize_time(t) for t in titles if re.match(r"\d{1,2}:\d{2}\s*[AP]M", t, re.I)}
            return times

        pos = vc_idx + 1

    raise RuntimeError(f"showtimes array for {VENUE_CODE!r} not found")


def _play_alarm():
    while not _alarm_stop.is_set():
        winsound.Beep(1000, 500)


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def main():
    known = KNOWN_SHOWS.copy()
    print(f"[{_ts()}] Monitoring Miraj Cinemas: IMAX, Wadala (venue code {VENUE_CODE})")
    print(f"[{_ts()}] Baseline shows : {sorted(known)}")
    print(f"[{_ts()}] Check interval : {CHECK_INTERVAL}s")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            print(f"[{_ts()}] Checking...", end=" ", flush=True)
            try:
                current = get_show_times()
                new_shows = current - known

                if new_shows:
                    print()
                    print("=" * 54)
                    print(f"  *** NEW SHOW(S) DETECTED: {sorted(new_shows)} ***")
                    print(f"  All current shows : {sorted(current)}")
                    print("=" * 54)

                    alarm_thread = threading.Thread(target=_play_alarm, daemon=True)
                    alarm_thread.start()
                    print("Alarm playing — press Ctrl+C to stop.")
                    try:
                        while True:
                            time.sleep(1)
                    except KeyboardInterrupt:
                        pass
                    _alarm_stop.set()
                    alarm_thread.join(timeout=2)
                    print(f"\n[{_ts()}] Alarm stopped. Exiting.")
                    return

                else:
                    print(f"No new shows. Current: {sorted(current)}")

            except KeyboardInterrupt:
                raise
            except Exception as exc:
                print(f"Warning — {exc}")

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print(f"\n[{_ts()}] Stopped by user.")


if __name__ == "__main__":
    main()
