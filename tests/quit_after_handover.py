"""Run by test_updater.py in its own process: the real widget and Update window, with only the
installer stubbed. Once the installer has taken over, the app must really quit (its event loop
ends), as it does before every update. Prints how long that took; exits 3 if it never quits."""
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import app, isolate_widget, TMP

ww = isolate_widget()
import updater
from PySide6.QtCore import QTimer

qt = app()
qt.setQuitOnLastWindowClosed(False)
updater.can_self_update = lambda folder=None: True
updater.start_install = lambda path, version, *a: True  # "the installer has started and reported in"
w = ww.BibleWidget()
w.show()
w._available_update = {"tag": "v9.9.9", "version": "9.9.9", "notes": "", "page": "",
                       "zip_url": "https://example.invalid/x.zip", "sha_url": "https://example.invalid/x.zip.sha256"}
w._open_update_window()
window = w._update_window
start = time.monotonic()
QTimer.singleShot(50, lambda: window._on_downloaded(os.path.join(TMP, "x.zip")))
QTimer.singleShot(5000, lambda: (print("still running after 5 s", flush=True), os._exit(3)))
code = qt.exec()
print(f"quit {time.monotonic() - start:.2f} s after handing over, exit code {code}", flush=True)
