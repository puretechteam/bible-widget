"""Run by test_crash_log.py in its own process: the real app (run_widget, offscreen), with its
files in the folder given, and one way of ending it.

    python crash_driver.py <folder> <action>

Actions: run (until it is ended from outside), quit (Exit after a second), thread-error (an error
in another thread, then Exit), segfault (an access violation), qt-fatal (Qt's fatal error)."""
import os
import sys
import time
import threading

folder, action = sys.argv[1], sys.argv[2]
ROOT = os.environ.get("BIBLE_WIDGET_TEST_APP") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
if os.path.isdir(_FONTS):
    os.environ.setdefault("QT_QPA_FONTDIR", _FONTS)
os.environ["APPDATA"] = folder  # the Startup folder it repairs is a temp one
sys.path.insert(0, ROOT)
sys.dont_write_bytecode = True

if sys.platform == "win32":
    # Crash reports on, as when started from Explorer or PowerShell (some shells turn them off for
    # the programs they start, which then inherit it)
    import ctypes
    ctypes.windll.kernel32.SetErrorMode(int(os.environ.get("BW_TEST_ERROR_MODE", "0x8001"), 0))
import paths
paths.APP_DIR = folder
import bible_loader
bible_loader._BIBLES_DIR = os.path.join(ROOT, "bibles")
import colors
colors._colors_path = lambda: os.path.join(folder, "colors.txt")
import updater
updater.FIRST_CHECK_DELAY_MS = 10 ** 9  # no network
import widget_window as ww
ww.APP_DIR = folder
ww.BibleWidget._watch_desktop = lambda self: None
try:
    import crash_log
    crash_log.HEARTBEAT_MS = 300
except ImportError:  # an older version without it
    crash_log = None

from PySide6.QtCore import QTimer

real_init = ww.BibleWidget.__init__


def init(self, *args, **kwargs):
    real_init(self, *args, **kwargs)
    open(os.path.join(folder, "started.txt"), "w").write(str(os.getpid()))
    if action == "quit":
        def quit_when_reported(tries=100):
            # Let the look-up of Windows' crash report for the last run finish first
            busy = any(t.name == "windows-report" and t.is_alive() for t in threading.enumerate())
            if busy and tries:
                QTimer.singleShot(200, lambda: quit_when_reported(tries - 1))
            else:
                self._exit_app()
        QTimer.singleShot(1000, quit_when_reported)
    elif action == "thread-error":
        def fail():
            raise ZeroDivisionError("a test error in another thread")
        QTimer.singleShot(300, lambda: threading.Thread(target=fail, name="test-thread").start())
        QTimer.singleShot(1500, self._exit_app)
    elif action == "segfault":
        # A native thread that starts at an invalid address: an access violation outside Python, as a
        # crash in Qt or a driver would be (faulthandler._read_null turns Windows' reports off first)
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.CreateThread.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p,
                                          ctypes.c_uint32, ctypes.c_void_p]
        kernel32.CreateThread.restype = ctypes.c_void_p
        QTimer.singleShot(1000, lambda: kernel32.CreateThread(None, 0, 0x10, None, 0, None))
    elif action == "qt-fatal":
        from PySide6.QtCore import qFatal
        QTimer.singleShot(1000, lambda: qFatal("a test fatal error"))


ww.BibleWidget.__init__ = init
ww.run_widget()
