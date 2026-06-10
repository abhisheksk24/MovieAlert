import threading
import winsound
from datetime import datetime
from curl_cffi import requests as cf_requests

_alarm_stop = threading.Event()  # ← define it globally

def _play_alarm():
    while not _alarm_stop.is_set():
        winsound.Beep(1000, 500)

def main():
    alarm_thread = threading.Thread(target=_play_alarm, daemon=True)
    alarm_thread.start()
    
    input("Alarm running... Press Enter to stop.\n")  # ← keep main alive
    _alarm_stop.set()  # ← signal the thread to stop
    alarm_thread.join()  # ← wait for thread to finish cleanly

if __name__ == "__main__":
    main()