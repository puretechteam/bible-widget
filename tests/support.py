"""Shared setup for the tests: runs Qt offscreen and points every file the app writes
(settings, favorites, history, colors, saved images) at a temp folder, so a test run
never touches your own settings or Pictures folder."""

import os
import sys
import shutil
import atexit
import tempfile

# The code under test: this checkout, or another copy named in BIBLE_WIDGET_TEST_APP
ROOT = os.environ.get("BIBLE_WIDGET_TEST_APP") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="bw-tests-")


def _cleanup():
    """Remove TMP, also if a test made it the working folder or left read-only files in it."""
    os.chdir(tempfile.gettempdir())

    def clear_and_retry(func, path, *_):
        try:
            os.chmod(path, 0o666)
            func(path)
        except OSError:
            pass
    if sys.version_info >= (3, 12):
        shutil.rmtree(TMP, onexc=clear_and_retry)
    else:
        shutil.rmtree(TMP, onerror=clear_and_retry)


atexit.register(_cleanup)

os.environ["QT_QPA_PLATFORM"] = "offscreen"
# Offscreen Qt has no fonts of its own: without Windows' fonts, text would be measured with
# made-up sizes (the alphabet twice as wide), and tests of what fits would prove nothing
_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
if os.path.isdir(_FONTS):
    os.environ.setdefault("QT_QPA_FONTDIR", _FONTS)
os.environ["APPDATA"] = TMP
sys.path.insert(0, ROOT)
sys.dont_write_bytecode = True
# A failure that quotes Hebrew or Japanese must print, also in a console that can't show them
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")


class Results:
    """check(name, ok, detail) collects results; finish() prints the count and sets the exit code."""

    def __init__(self):
        self.passed = 0
        self.failed = []

    def check(self, name, ok, detail=""):
        if ok:
            self.passed += 1
        else:
            self.failed.append(f"{name}  ({detail})" if detail != "" else name)
            print("FAILED:", self.failed[-1], flush=True)

    def finish(self):
        print(f"{self.passed} passed, {len(self.failed)} failed", flush=True)
        sys.exit(1 if self.failed else 0)


def app():
    """The QApplication, created once."""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def isolate_widget():
    """Import widget_window with all of its files redirected to TMP. Returns the module."""
    app()
    import colors
    colors._colors_path = lambda: os.path.join(TMP, "colors.txt")
    import share_image
    real_save = share_image.save_card
    share_image.save_card = lambda image, ref, folder=None: real_save(image, ref, folder or pictures())
    import updater
    updater.FIRST_CHECK_DELAY_MS = 10 ** 9  # no network
    import widget_window as ww
    ww.APP_DIR = TMP
    if not hasattr(ww, "real_repair_startup"):  # kept for tests that point APPDATA at a temp folder
        ww.real_repair_startup = ww.BibleWidget._repair_startup
    ww.BibleWidget._repair_startup = lambda self: None  # never touch the Startup folder
    ww.BibleWidget._watch_desktop = lambda self: None
    return ww


def pictures():
    """Where Save as Image writes during tests."""
    return os.path.join(TMP, "Pictures")
