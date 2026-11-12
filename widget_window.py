import sys
import os
import html
import re
import time
import threading
import getpass
import datetime
import logging
import traceback
from logging.handlers import RotatingFileHandler
from PySide6.QtWidgets import (
    QWidget, QApplication, QVBoxLayout, QLabel,
    QFrame, QSystemTrayIcon, QMenu, QMessageBox, QLayout,
    QDialog, QDialogButtonBox, QPushButton, QHBoxLayout, QColorDialog
)
from PySide6.QtGui import (
    QFont, QPainter, QColor,
    QAction, QActionGroup, QGuiApplication, QDesktopServices
)
from PySide6.QtCore import (
    Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve, Signal, qInstallMessageHandler, QtMsgType,
    QLockFile, QDir, QUrl
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from paths import APP_DIR, FROZEN, folder_writable, read_text, write_text
import crash_log
from version import VERSION, REPO
from verses import VerseList, is_rtl
from tray_icon import make_tray_icon, taskbar_is_light
import updater
from updater import UpdateChecker, UpdateSettings
from bible_loader import (
    get_random_passage, get_verse_of_the_day, get_available_translations,
    get_translation_info, get_short_name, get_translation_name, REPLACED
)
from prayer_window import PrayerWindow
from menu_strings import get_string, get_available_languages, get_translated_language_name, install_qt_translator
from colors import (
    get_colors, set_color, DEFAULT_COLORS, paint_card, rgba as _rgba, separator_style as _separator_style
)

RANDOM_TRANSLATION = "random"
MODE_INTERVALS = {"hourly": 3600000, "random": 900000}  # daily is scheduled for midnight
MIN_VERSE_PT = 10
HISTORY_SIZE = 100
RTL_MENU_LANGUAGES = ("ar", "fa", "he")  # menus and windows read from right to left
# Where a reader can suggest a better wording for a machine-translated menu
TRANSLATION_ISSUE_URL = f"https://github.com/{REPO}/issues/new?title=Menu%20translation%20({{lang}})"
READ_ONLY_CHECK_DELAY_MS = 5000  # after the tray icon is up, before the first update check
REF_GAP, VERSE_GAP = 12, 16  # space above and below the separator
VERSE_LINE_HEIGHT = 120  # percent

log = logging.getLogger("bible_widget")

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_uint
    ]
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]

    HWND_TOPMOST = wintypes.HWND(-1)
    HWND_NOTOPMOST = wintypes.HWND(-2)
    HWND_BOTTOM = wintypes.HWND(1)
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOACTIVATE = 0x0010
    SW_SHOWNOACTIVATE = 4
    WM_SETTINGCHANGE = 0x001A
    WM_ENDSESSION = 0x0016
    DESKTOP_CLASSES = ("WorkerW", "Progman")


class BibleWidget(QWidget):
    _image_saved = Signal(object, bool)  # (saved path or None, image is on the clipboard)

    def __init__(self):
        super().__init__()
        self._image_saved.connect(self._on_image_saved)
        self._save_threads = []
        # Quitting (Exit, an update, Windows shutting down) first lets image files finish
        QApplication.instance().aboutToQuit.connect(self._finish_saves)
        self.setWindowTitle("Bible Widget")
        self._verbose = "--verbose" in sys.argv
        self._start_time = datetime.datetime.now()
        self._quote_count = 0
        self._translation = None
        self._shown_translation = ""
        self._shown_passage = None  # (reference, text) on show; the labels can hold trial text
        self._error_shown = False  # the "No verses found" card is showing
        self._toast_action = None  # what clicking the current tray notification does
        self._menu_lang = "en"
        self._prayer_windows = []
        self._color_dialog = None
        self._verses_window = None
        self._context_menu = None
        self._favorites = VerseList(os.path.join(APP_DIR, "favorites.json"))
        self._history = VerseList(os.path.join(APP_DIR, "history.json"), cap=HISTORY_SIZE)
        self._history_pos = 0  # 0 = the newest history entry; Back steps to older ones
        self._about_window = None
        self._update_window = None
        self._available_update = None
        self._manual_check = False
        self._update_settings = UpdateSettings(APP_DIR)
        # Tool: no taskbar button. DoesNotAcceptFocus: clicking it never steals focus
        # (WS_EX_NOACTIVATE). Not WindowStaysOnBottomHint: Qt would force the window back
        # to the bottom on every z-order change, so it could never rise after Win+D.
        # The bottom layer is managed by _set_layer instead.
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        if sys.platform != "win32":
            self.setWindowFlag(Qt.WindowStaysOnBottomHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._on_top = False
        self._peek_until = 0.0
        if sys.platform == "win32":
            # Win+D and clicks on the desktop bring the desktop to the front; while the
            # desktop is focused the widget is lifted above it, then dropped back down.
            self._desktop_timer = QTimer(self)
            self._desktop_timer.timeout.connect(self._watch_desktop)
            self._desktop_timer.start(400)

        self._drag_pos = None
        self._dragging = False
        self._resizing = False
        self._base_size = (384, 324)  # replaced with 20% x 30% of the screen below
        self._mode = "hourly"
        self._snap_anim = None
        self._corner_path = os.path.join(APP_DIR, "corner.txt")
        self._mode_path = os.path.join(APP_DIR, "mode.txt")
        self._snap_corner = "tr"
        self._snap_screen_name = ""
        self._snap_enabled = True
        self._free_pos = None
        self._load_snap_corner()
        self._load_mode()

        self._colors = get_colors()
        self._text_color = self._colors["text"]
        self._separator_color = self._colors["separator"]

        self._setup_fonts()
        self._setup_ui()

        self._pid_path = os.path.join(APP_DIR, "widget.pid")
        self._translation_path = os.path.join(APP_DIR, "translation.txt")
        self._language_path = os.path.join(APP_DIR, "language.txt")

        self._load_translation_preference()
        self._load_language_preference()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timer)
        # The timer may not count time the PC spends asleep, so also compare the clock:
        # after waking past midnight (Daily) or the hour, the new verse comes straight away
        self._due = None
        self._wake_check = QTimer(self)
        self._wake_check.timeout.connect(self._check_overdue)
        self._wake_check.start(30000)

        self._setup_tray()
        self._repair_startup()
        QTimer.singleShot(READ_ONLY_CHECK_DELAY_MS, self._warn_if_read_only)

        scr = self._screen_for_snap().geometry()
        self._base_size = (int(scr.width() * 0.2), int(scr.height() * 0.3))
        self.resize(*self._base_size)
        self._place()

        # A screen added, removed or changed (resolution, scaling): size and place the card again
        app = QApplication.instance()
        for screen in app.screens():
            screen.geometryChanged.connect(self._on_screens_changed)
        app.screenAdded.connect(lambda screen: (screen.geometryChanged.connect(self._on_screens_changed),
                                                self._on_screens_changed()))
        app.screenRemoved.connect(lambda _: self._on_screens_changed())

        try:
            self.show_new_verse()
        except Exception:
            # Never fail to start over one bad verse; the refresh timer tries again
            log.exception("Could not show the first verse")
            self._set_passage("", self._s("No verses found"))
        self._place()  # the first verse may have made the card taller or wider
        self._schedule_next()

        self._updater = UpdateChecker(self._update_settings, self)
        self._updater.found.connect(self._on_update_found)
        self._updater.up_to_date.connect(lambda: self._on_update_result(True))
        self._updater.failed.connect(lambda _: self._on_update_result(False))
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(lambda: self._check_for_updates(manual=False))
        self._update_timer.start(updater.CHECK_INTERVAL_MS)
        QTimer.singleShot(updater.FIRST_CHECK_DELAY_MS, lambda: self._check_for_updates(manual=False))

    def _s(self, key):
        return get_string(key, self._menu_lang)

    def _build_menu(self):
        """Build the tray menu with translated strings."""
        s = lambda key: self._s(key).replace("&", "&&")  # "&" would become a shortcut marker
        # Arabic, Persian and Hebrew menus and windows run right to left (checkmarks and submenu
        # arrows on the other side), like Windows itself in those languages
        QApplication.setLayoutDirection(Qt.RightToLeft if self._menu_lang in RTL_MENU_LANGUAGES
                                        else Qt.LeftToRight)
        install_qt_translator(self._menu_lang)  # Qt's own (human-made) translations of OK, Cancel...
        menu = QMenu()

        if self._available_update is not None:
            update_action = QAction(s("Update to {version}...").format(version=self._available_update["version"]), menu)
            update_action.triggered.connect(self._open_update_window)
            menu.addAction(update_action)
            menu.addSeparator()

        mode_group = QActionGroup(menu)
        self._mode_actions = {}
        for mode, label in (("hourly", "Hourly Mode"), ("daily", "Daily Mode"), ("random", "Random Mode")):
            action = QAction(s(label), menu)
            action.setCheckable(True)
            action.setChecked(self._mode == mode)
            action.triggered.connect(lambda _, m=mode: self._set_mode(m))
            mode_group.addAction(action)
            menu.addAction(action)
            self._mode_actions[mode] = action

        change_action = QAction(s("Change Quote"), menu)
        change_action.triggered.connect(lambda: self.show_new_verse(manual=True))
        menu.addAction(change_action)

        copy_action = QAction(s("Copy Verse"), menu)
        copy_action.triggered.connect(lambda: self._copy_verse())
        menu.addAction(copy_action)

        verses_action = QAction(s("Verses..."), menu)
        verses_action.triggered.connect(lambda: self._open_verses("find"))
        menu.addAction(verses_action)

        menu.addSeparator()

        # Translation submenu
        trans_menu = menu.addMenu(s("Translation"))
        trans_group = QActionGroup(trans_menu)
        all_action = QAction(s("All (Random)"), trans_menu)
        all_action.setCheckable(True)
        all_action.setChecked(self._translation is None)
        all_action.triggered.connect(lambda: self._set_translation(None))
        trans_group.addAction(all_action)
        trans_menu.addAction(all_action)
        trans_menu.addSeparator()

        for abbr, name, lang in get_available_translations():
            translated_lang = get_translated_language_name(lang, self._menu_lang)
            action = QAction(f"{name} ({translated_lang})".replace("&", "&&"), trans_menu)
            action.setCheckable(True)
            action.setChecked(abbr == self._translation)
            action.triggered.connect(lambda _, a=abbr: self._set_translation(a))
            trans_group.addAction(action)
            trans_menu.addAction(action)

        # Menu Language submenu: changes tray menu text, independent from Translation
        lang_menu = menu.addMenu(s("Menu Language"))
        lang_group = QActionGroup(lang_menu)
        for code, native_name in get_available_languages():
            action = QAction(f"{native_name} ({code})", lang_menu)
            action.setCheckable(True)
            action.setChecked(code == self._menu_lang)
            action.triggered.connect(lambda _, c=code: self._set_language(c))
            lang_group.addAction(action)
            lang_menu.addAction(action)
        if self._menu_lang != "en":
            # Menus other than English are machine translations (apart from the parts taken from
            # human sources): say so, in English, with a way to suggest a better wording
            lang_menu.addSeparator()
            note = QAction("Machine-translated menu: suggest a fix...", lang_menu)
            note.triggered.connect(lambda: QDesktopServices.openUrl(
                QUrl(TRANSLATION_ISSUE_URL.format(lang=self._menu_lang))))
            lang_menu.addAction(note)

        # Prayers submenu
        prayers_menu = menu.addMenu(s("Prayers"))
        prayer_ids = [
            ("lords-prayer", "The Lord's Prayer"),
            ("jonahs-prayer", "Jonah's Prayer"),
            ("magnificat", "Mary's Magnificat"),
            ("jobs-prayer", "Job's Prayer"),
            ("acts-prayer", "Acts 4:24-26"),
            ("solomons-prayer", "Solomon's Prayer"),
        ]
        for pid, pname in prayer_ids:
            action = QAction(s(pname), prayers_menu)
            action.triggered.connect(lambda _, p=pid: self._open_prayer(p))
            prayers_menu.addAction(action)

        # Run on Startup submenu
        startup_menu = menu.addMenu(s("Run on Startup"))
        startup_group = QActionGroup(startup_menu)
        current = self._startup_mode()
        modes = ((None, "Off"), ("silent", "On")) if FROZEN else \
            ((None, "Off"), ("silent", "Silent (no terminal)"), ("console", "With console"))
        for mode, label in modes:
            action = QAction(s(label), startup_menu)
            action.setCheckable(True)
            action.setChecked(current == mode)
            action.triggered.connect(lambda _, m=mode: self._set_startup(m))
            startup_group.addAction(action)
            startup_menu.addAction(action)

        stats_action = QAction(s("Stats"), menu)
        stats_action.triggered.connect(self._show_stats)
        menu.addAction(stats_action)

        menu.addSeparator()

        show_action = QAction(s("Show Widget"), menu)
        show_action.triggered.connect(self._bring_back)
        menu.addAction(show_action)

        colors_action = QAction(s("Customize Colors..."), menu)
        colors_action.triggered.connect(self._open_color_settings)
        menu.addAction(colors_action)

        snap_action = QAction(s("Snap to Corners"), menu)
        snap_action.setCheckable(True)
        snap_action.setChecked(self._snap_enabled)
        snap_action.toggled.connect(self._toggle_snap)
        menu.addAction(snap_action)

        menu.addSeparator()
        check_action = QAction(s("Check for Updates"), menu)
        check_action.triggered.connect(lambda: self._check_for_updates(manual=True))
        menu.addAction(check_action)
        about_action = QAction(s("About Bible Widget"), menu)
        about_action.triggered.connect(self._open_about)
        menu.addAction(about_action)

        exit_action = QAction(s("Exit"), menu)
        exit_action.triggered.connect(lambda: self._exit_app())
        menu.addAction(exit_action)

        return menu

    def _setup_tray(self):
        self._tray_icon = QSystemTrayIcon(self)
        self._tray_light = taskbar_is_light()
        self._tray_icon.setIcon(make_tray_icon(self._tray_light))
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _: self._refresh_tray_icon())
        self._tray_icon.setToolTip(f"Bible Widget {VERSION}")
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.messageClicked.connect(self._on_toast_clicked)
        self._menu = self._build_menu()
        self._tray_icon.setContextMenu(self._menu)
        self._tray_icon.show()

    def _refresh_tray_icon(self):
        """Redraw the tray icon if the taskbar turned light or dark. Windows can switch the taskbar
        alone (Personalization, Colors, Custom), which Qt's colour scheme does not follow."""
        light = taskbar_is_light()
        if light != self._tray_light:
            self._tray_light = light
            self._tray_icon.setIcon(make_tray_icon(light))

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32" and event_type == b"windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_SETTINGCHANGE:
                    QTimer.singleShot(0, self._refresh_tray_icon)
                elif msg.message == WM_ENDSESSION and msg.wParam:
                    # Windows ends the app right after this: not a crash
                    crash_log.mark_ended("Windows is shutting down or signing out")
            except (TypeError, ValueError):
                pass
        return super().nativeEvent(event_type, message)

    def _rebuild_menu(self):
        if self._menu is not None and self._menu.isVisible():
            # Not under the user's pointer: rebuild once the open menu closes
            if not self._menu.property("rebuild_pending"):
                self._menu.setProperty("rebuild_pending", True)
                self._menu.aboutToHide.connect(lambda: QTimer.singleShot(0, self._rebuild_menu))
            return
        old = self._menu
        self._menu = self._build_menu()
        self._tray_icon.setContextMenu(self._menu)
        if old is not None:
            old.deleteLater()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._bring_back()

    # ----- Desktop layering (Windows) -----

    def _set_layer(self, on_top):
        hwnd = int(self.winId())
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        if on_top:
            _user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
        else:
            _user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
            _user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, flags)
        self._on_top = on_top

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32" and not self._on_top:
            QTimer.singleShot(0, lambda: self._set_layer(False))

    def _watch_desktop(self):
        if not self.isVisible():
            return
        hwnd = int(self.winId())
        if _user32.IsIconic(hwnd):
            _user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)

        fg = _user32.GetForegroundWindow()
        if fg:
            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
            if pid.value == os.getpid():
                return  # our own menu or dialog has focus; leave the layer alone
            buf = ctypes.create_unicode_buffer(64)
            _user32.GetClassNameW(fg, buf, 64)
            on_desktop = buf.value in DESKTOP_CLASSES
        else:
            on_desktop = False
        want_top = on_desktop or time.monotonic() < self._peek_until
        if want_top != self._on_top:
            self._set_layer(want_top)

    # ----- Menu actions -----

    def _set_language(self, code):
        """Change the menu language and rebuild the tray."""
        self._menu_lang = code
        self._save_language_preference()
        self._rebuild_menu()
        if self._error_shown:  # the "No verses found" card, in the new language
            self._set_passage("", self._s("No verses found"))
            self._shown_passage = ("", self._s("No verses found"))
        if QApplication.activeModalWidget() is not None:
            return  # a message box or colour picker is open: leave the windows as they are
        if self._verses_window is not None:
            self._verses_window.close()
        about = self._about_window
        if about is not None and about.isVisible():
            pos = about.pos()
            about.close()
            self._about_window = None
            self._open_about()
            self._about_window.move(pos)
        update = self._update_window
        if update is not None and update.isVisible() and not (update._downloading or update._installing):
            pos = update.pos()
            update.close()
            self._update_window = None
            self._open_update_window()
            if self._update_window is not None:
                self._update_window.move(pos)
        dialog = self._color_dialog
        if dialog is not None and dialog.isVisible():
            pos, pending = dialog.pos(), dict(dialog._pending)  # colours picked but not applied stay
            dialog.close()
            self._color_dialog = None
            self._open_color_settings(pending)
            self._color_dialog.move(pos)
        for window in list(self._prayer_windows):
            if window.isVisible():
                pos, prayer_id, abbr = window.pos(), window._prayer_id, window._translation_abbr
                window.close()
                self._forget_prayer(window)
                self._open_prayer(prayer_id, abbr, reuse=False).move(pos)

    def _apply_colors(self):
        self._colors = get_colors()
        self._text_color = self._colors["text"]
        self._separator_color = self._colors["separator"]
        self._apply_label_styles()

        self.update()

        for window in self._prayer_windows:
            window._apply_colors()

    def _apply_label_styles(self):
        muted = QColor(self._text_color)
        muted.setAlphaF(self._text_color.alphaF() * 0.65)
        self.ref_label.setStyleSheet(f"color: {_rgba(muted)};")
        self.verse_label.setStyleSheet(f"color: {_rgba(self._text_color)};")
        self.separator.setStyleSheet(_separator_style(self._separator_color))

    @staticmethod
    def _bring_to_front(window):
        """Show a window the user asked for, restoring it if it was minimized (Win+D
        minimizes open dialogs, and raise_() alone leaves a minimized window hidden)."""
        window.setWindowState(window.windowState() & ~Qt.WindowMinimized)
        window.show()
        window.raise_()
        window.activateWindow()

    def _forget(self, attr, window):
        """A window has gone: forget it, unless it was already replaced by a new one."""
        if getattr(self, attr, None) is window:
            setattr(self, attr, None)

    def _open_color_settings(self, colors=None):
        if self._color_dialog is not None and self._color_dialog.isVisible():
            self._bring_to_front(self._color_dialog)
            return
        dlg = ColorSettingsDialog(colors or get_colors(), self._s)
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.colors_changed.connect(self._apply_colors)
        dlg.destroyed.connect(lambda _=None, d=dlg: self._forget("_color_dialog", d))
        dlg.adjustSize()
        geo = self._screen_for_snap().availableGeometry()
        dlg.move(geo.center() - dlg.rect().center())
        self._color_dialog = dlg
        self._bring_to_front(dlg)

    def _bring_back(self):
        """Show the widget and lift it above other windows for a few seconds."""
        self.show()
        if sys.platform == "win32":
            hwnd = int(self.winId())
            if _user32.IsIconic(hwnd):
                _user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            self._peek_until = time.monotonic() + 4
            self._set_layer(True)
        else:
            self.raise_()
        self._place()

    def _toggle_snap(self, enabled: bool) -> None:
        self._snap_enabled = enabled
        if enabled:
            self._snap_to_corner(self._snap_corner)
        else:
            self._free_pos = self.pos()
        self._save_snap_corner()

    def _set_translation(self, abbr):
        self._translation = abbr
        self._save_translation_preference()
        self.show_new_verse()

    # ----- Run on Startup -----

    def _startup_dir(self):
        appdata = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")

    def _startup_file_path(self):
        return os.path.join(self._startup_dir(), "BibleWidget.vbs")

    def _read_startup_file(self):
        p = self._startup_file_path()
        if not os.path.isfile(p):
            return None
        try:
            with open(p, "rb") as f:
                raw = f.read()
        except OSError:
            return None
        if raw.startswith(b"\xff\xfe"):
            return raw.decode("utf-16", errors="replace")
        return raw.decode("mbcs" if sys.platform == "win32" else "latin-1", errors="replace")

    def _startup_mode(self):
        """How Run on Startup starts this copy, or None. A launcher that starts another copy
        (such as an older version in another folder) does not count as on."""
        content = self._read_startup_file()
        if content is None or self._starts_other_copy(content):
            return None
        return self._launcher_mode(content)

    def _starts_other_copy(self, content):
        target = self._startup_target(content)
        return bool(target) and os.path.normcase(os.path.dirname(target)) != os.path.normcase(APP_DIR)

    @staticmethod
    def _launcher_mode(content):
        """The mode a launcher's text was written for."""
        if FROZEN:
            return "silent"
        if "mode=console" in content:
            return "console"
        if "mode=silent" in content or "pythonw" in content or "pyw" in content:
            return "silent"
        return "console"

    def _startup_content(self, mode):
        script = os.path.join(APP_DIR, "widget_window.py")
        if FROZEN:
            mode = "silent"
            cmd = f'""{sys.executable}""'
            show = 1
        elif mode == "silent":
            pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            exe = f'""{pythonw}""' if os.path.isfile(pythonw) else "pyw -3"
            cmd = f'{exe} ""{script}""'
            show = 0
        else:
            cmd = f'py -3 ""{script}"" --verbose'
            show = 1
        return (
            f"' Bible Widget startup launcher (mode={mode})\r\n"
            f'Set sh = CreateObject("Wscript.Shell")\r\n'
            f'sh.CurrentDirectory = "{APP_DIR}"\r\n'
            f'sh.Run "{cmd}", {show}, False\r\n'
        )

    def _set_startup(self, mode):
        p = self._startup_file_path()
        try:
            if mode is None:
                content = self._read_startup_file()
                if content is not None and self._starts_other_copy(content) \
                        and os.path.exists(self._startup_target(content)):
                    log.info("Run on Startup: the launcher starts another copy; leaving it")
                elif os.path.exists(p):
                    os.remove(p)
            else:
                os.makedirs(self._startup_dir(), exist_ok=True)
                # UTF-16 with BOM so Windows Script Host reads non-ASCII paths correctly
                with open(p, "w", encoding="utf-16", newline="") as f:
                    f.write(self._startup_content(mode))
        except OSError:
            log.exception("Could not update the startup launcher")
        self._rebuild_menu()

    @staticmethod
    def _startup_target(content):
        """The widget_window.py or BibleWidget.exe a launcher starts, or None."""
        found = re.findall(r'""([^"]*?(?:widget_window\.py|BibleWidget\.exe))""', content, re.IGNORECASE)
        return found[-1] if found else None

    def _repair_startup(self):
        """Rewrite the startup launcher only if it no longer matches this install. A launcher
        that starts another copy that still exists (say, the exe next to a source copy) is left
        alone, so two copies never fight over it."""
        content = self._read_startup_file()
        if content is None:
            return
        target = self._startup_target(content)
        if self._starts_other_copy(content) and os.path.exists(target):
            log.info("Startup launcher starts another copy (%s); leaving it", target)
            return
        mode = self._launcher_mode(content)  # the copy it started is gone: start this one the same way
        if content != self._startup_content(mode):
            log.info("Repairing startup launcher (mode=%s)", mode)
            self._set_startup(mode)

    # ----- Preferences -----

    def _load_translation_preference(self):
        try:
            if os.path.isfile(self._translation_path):
                val = read_text(self._translation_path).strip()
                available = {a for a, _, _ in get_available_translations()}
                if val not in available:
                    val = REPLACED.get(val, val)  # a translation taken out in 2.1.0: its replacement
                if val == RANDOM_TRANSLATION:
                    self._translation = None
                elif val in available:
                    self._translation = val
        except (OSError, ValueError):  # unreadable: keep the default
            pass

    def _save_translation_preference(self):
        try:
            write_text(self._translation_path, self._translation or RANDOM_TRANSLATION)
        except OSError:
            log.warning("Could not save the translation choice", exc_info=True)

    def _load_language_preference(self):
        try:
            if os.path.isfile(self._language_path):
                val = read_text(self._language_path).strip()
                if val and val in dict(get_available_languages()):
                    self._menu_lang = val
        except (OSError, ValueError):  # unreadable: keep the default
            pass

    def _save_language_preference(self):
        try:
            write_text(self._language_path, self._menu_lang)
        except OSError:
            log.warning("Could not save the menu language", exc_info=True)

    def _load_mode(self):
        try:
            if os.path.isfile(self._mode_path):
                val = read_text(self._mode_path).strip()
                if val in ("hourly", "daily", "random"):
                    self._mode = val
        except (OSError, ValueError):  # unreadable: keep the default
            pass

    def _save_mode(self):
        try:
            write_text(self._mode_path, self._mode)
        except OSError:
            log.warning("Could not save the mode", exc_info=True)

    # ----- Refresh timing -----

    def _set_mode(self, mode):
        self._mode = mode
        self._save_mode()
        self.show_new_verse()
        self._schedule_next()

    def _schedule_next(self):
        if self._mode == "daily":
            now = datetime.datetime.now()
            midnight = datetime.datetime.combine(now.date() + datetime.timedelta(days=1), datetime.time())
            ms = int((midnight - now).total_seconds() * 1000) + 1000
        else:
            ms = MODE_INTERVALS.get(self._mode, MODE_INTERVALS["hourly"])
        self._timer.start(ms)
        self._due = time.time() + ms / 1000

    def _check_overdue(self):
        if self._due is not None and self._timer.isActive() and time.time() > self._due + 5:
            self._timer.stop()
            self._on_timer()

    def _on_timer(self):
        try:
            self.show_new_verse()
        finally:
            self._schedule_next()

    def _open_prayer(self, prayer_id="lords-prayer", abbr=None, reuse=True):
        """Open a prayer window using the current (or last shown) translation. A prayer already
        open in that translation is brought to the front instead of opened twice."""
        abbr = abbr or self._translation or self._shown_translation or "en_kjv"
        for window in self._prayer_windows if reuse else ():
            if (window._prayer_id, window._translation_abbr, window._lang) == (prayer_id, abbr, self._menu_lang):
                self._bring_to_front(window)
                return window
        window = PrayerWindow(abbr, prayer_id, self._menu_lang, screen=self._screen_for_snap())
        window.setAttribute(Qt.WA_DeleteOnClose)
        self._prayer_windows.append(window)
        window.destroyed.connect(lambda _=None, w=window: self._forget_prayer(w))
        window.show()
        return window

    def _forget_prayer(self, window):
        if window in self._prayer_windows:
            self._prayer_windows.remove(window)

    def _exit_app(self, reason="Exit was chosen"):
        window = self._update_window
        if window is not None and window._installing:
            # The update is being unpacked: quit once it is clear whether the installer took over
            window.quit_when_done = True
            return
        crash_log.end_run(reason, APP_DIR)  # also removes widget.pid
        self._tray_icon.hide()
        QApplication.quit()

    # ----- UI -----

    def _setup_fonts(self):
        self.verse_font = QFont("Segoe UI", 26)
        self.verse_font.setWeight(QFont.Medium)
        # On the font rather than in the stylesheet so text measurement includes it
        self.verse_font.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
        self.ref_font = QFont("Segoe UI", 9)
        self.ref_font.setWeight(QFont.DemiBold)
        self.ref_font.setCapitalization(QFont.AllUppercase)
        self.ref_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 34, 50, 34)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignCenter)
        # The window size is managed by _fit_text_size, not by the labels' size hints
        layout.setSizeConstraint(QLayout.SetNoConstraint)

        # Same structure as the prayer window: small-caps reference, one separator, text
        self.ref_label = QLabel()
        self.ref_label.setFont(self.ref_font)
        self.ref_label.setAlignment(Qt.AlignCenter)
        self.ref_label.setWordWrap(True)
        layout.addWidget(self.ref_label)
        layout.addSpacing(REF_GAP)

        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.HLine)
        self.separator.setFixedHeight(1)
        layout.addWidget(self.separator)
        layout.addSpacing(VERSE_GAP)

        self.verse_label = QLabel()
        self.verse_label.setFont(self.verse_font)
        self.verse_label.setTextFormat(Qt.RichText)
        self.verse_label.setAlignment(Qt.AlignCenter)
        self.verse_label.setWordWrap(True)
        layout.addWidget(self.verse_label)
        self._verse_text = ""

        self._apply_label_styles()

    def show_new_verse(self, manual=False):
        try:
            if self._mode == "daily" and not manual:
                ref, text, abbr = get_verse_of_the_day(self._translation, with_translation=True, fits=self._fits)
            else:
                ref, text, abbr = get_random_passage(self._translation, with_translation=True, fits=self._fits)
        except Exception:
            self._redisplay()  # measuring left trial text on the labels
            raise
        self._display(ref, text, abbr)

    def _display(self, ref, text, abbr, record=True):
        """Show a passage. New passages go into history; Back replays history without recording."""
        self._error_shown = not abbr and ref == "Error"
        if self._error_shown:  # no Bible could be loaded: say so in the menu language
            log.warning("Nothing to show: %s", text)
            ref, text = "", self._s("No verses found")
        self._shown_translation = abbr
        self._shown_passage = (ref, text)
        self._set_passage(ref, text)
        self._quote_count += 1
        self._fit_text_size()
        if record and abbr:
            self._history.add(ref, text, abbr, unique=False)
            self._history_pos = 0
            self._refresh_verses_window()
        if self._verbose:
            self._print_stats()

    def show_passage(self, ref, text, abbr):
        """Pin a passage picked in the Verses window. It stays until the next refresh."""
        self._display(ref, text, abbr)
        self._bring_back()

    def _can_go_back(self):
        return self._history_pos + 1 < len(self._history.entries)

    def _go_back(self):
        if not self._can_go_back():
            return
        self._history_pos += 1
        entry = self._history.entries[self._history_pos]
        self._display(entry["ref"], entry["text"], entry["translation"], record=False)

    def _current(self):
        ref, text = self._shown_passage or (self.ref_label.text(), self._verse_text)
        return ref, text, self._shown_translation

    def _redisplay(self):
        """Put the widget's own passage back, after something measured trial text on it."""
        if self._has_passage():
            ref, text, _ = self._current()
            self._set_passage(ref, text)
            self._fit_text_size()

    def _has_passage(self):
        """False while an error message is showing instead of a verse."""
        return bool(self._shown_translation and self._shown_passage and self._shown_passage[1])

    def _toggle_favorite(self, passage=None):
        ref, text, abbr = passage or self._current()
        if not abbr:
            return
        if self._favorites.contains(ref, abbr):
            self._favorites.remove(ref, abbr)
        else:
            self._favorites.add(ref, text, abbr)
        self._refresh_verses_window()

    def _save_image(self, ref=None, text=None, abbr=None):
        """Save the passage as a card image in Pictures\\Bible Widget and copy it to the clipboard."""
        if ref is None:
            if not self._has_passage():
                return None
            ref, text, abbr = self._current()
        QApplication.setOverrideCursor(Qt.WaitCursor)  # making and writing the image takes a moment
        try:
            return self._make_and_save_image(ref, text, abbr)
        finally:
            QApplication.restoreOverrideCursor()

    def _make_and_save_image(self, ref, text, abbr):
        """Draw the card and copy it to the clipboard here; the PNG file is written on a worker
        thread (the slow part), so the widget never freezes. Returns the thread."""
        from share_image import render_card, copy_to_clipboard
        try:
            image = render_card(ref, text, get_translation_name(abbr), get_colors())
        except Exception:
            log.exception("Could not make the verse image")
            self._notify(self._s("Could not save the image"))
            return None
        copied = True
        try:
            copy_to_clipboard(image)  # first, so a folder problem still leaves the image to paste
        except Exception:
            log.exception("Could not copy the verse image")
            copied = False
        # Not a daemon thread: quitting waits for the file to be finished
        thread = threading.Thread(target=self._write_image, args=(image, ref, copied), name="save-image")
        self._save_threads = [t for t in self._save_threads if t.is_alive()] + [thread]
        thread.start()
        return thread

    def _finish_saves(self, timeout=15):
        """Wait (on quit) for image files still being written, while the widget still exists;
        otherwise the app could be torn down under a worker that is about to report back."""
        deadline = time.monotonic() + timeout
        for thread in self._save_threads:
            thread.join(max(0.0, deadline - time.monotonic()))
        self._save_threads = [t for t in self._save_threads if t.is_alive()]

    def _write_image(self, image, ref, copied):
        """Runs on the worker thread; the result goes back to the UI thread as a queued signal."""
        from share_image import save_card
        try:
            path = save_card(image, ref)
            log.info("Saved verse image to %s", path)
        except Exception:
            log.exception("Could not save the verse image")
            path = None
        try:
            self._image_saved.emit(path, copied)
        except RuntimeError:
            pass  # the widget was closed while the file was being written

    def _on_image_saved(self, path, copied):
        if path is None:
            self._notify(self._s("The image is on the clipboard, but it could not be saved") if copied
                         else self._s("Could not save the image"))
        else:
            self._notify(self._s("Saved image to {path}").format(path=path),
                         lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))

    def _notify(self, message, on_click=None):
        """A tray notification. Clicking it runs `on_click` (if any), never another toast's action."""
        self._toast_action = on_click
        if self._tray_icon is not None and QSystemTrayIcon.supportsMessages():
            self._tray_icon.showMessage("Bible Widget", message, self._tray_icon.icon(), 6000)

    def _warn_if_read_only(self):
        """Settings, favorites and history are kept next to the app. If that folder can't be
        written (for example under Program Files), say so instead of losing changes silently.
        Clicking the notification opens the folder."""
        if folder_writable(APP_DIR):
            return False
        log.warning("Cannot write to %s: settings, favorites and history will not be saved", APP_DIR)
        self._notify(self._s("Settings can't be saved in the Bible Widget folder. "
                             "Move it somewhere you can write to, such as Documents."),
                     lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(APP_DIR)))
        return True

    def _on_toast_clicked(self):
        action, self._toast_action = self._toast_action, None
        if action is not None:
            action()

    # ----- Updates and About -----

    def _check_for_updates(self, manual=False):
        if not manual and not self._update_settings.auto:
            return
        if not manual and self._updater.checking():
            return  # one is already on its way (Check for Updates, say): its answer will do
        self._manual_check = manual
        if manual and self._about_window is not None:
            self._about_window.set_status(self._s("Checking for updates..."))
        self._updater.check(manual=manual)

    def _on_update_found(self, release):
        self._available_update = release
        self._rebuild_menu()
        message = self._s("Bible Widget {version} is available").format(version=release["version"])
        if self._about_window is not None:
            self._about_window.set_status(message)
        if self._manual_check:
            self._open_update_window()
        else:
            self._notify(message, self._open_update_window)

    def _on_update_result(self, up_to_date):
        window = self._update_window
        busy = window is not None and (window._downloading or window._installing)
        if up_to_date and self._available_update is not None and not busy:
            self._clear_update()  # the release on offer was withdrawn, or skipped
        if not self._manual_check:
            return
        text = self._s("You're up to date") if up_to_date else self._s("Couldn't check for updates")
        if self._about_window is not None and self._about_window.isVisible():
            self._about_window.set_status(text)
        else:
            self._notify(text)

    def _set_auto_update(self, enabled):
        self._update_settings.auto = bool(enabled)
        self._update_settings.save()

    def _clear_update(self):
        self._available_update = None
        self._rebuild_menu()

    def _open_update_window(self):
        if self._available_update is None:
            return
        old = self._update_window
        if old is not None and old._release.get("tag") != self._available_update.get("tag") \
                and not (old._downloading or old._installing):
            old.close()  # it offers an older release than the one now available
            self._update_window = None
        if self._update_window is None:
            from about_window import UpdateWindow
            window = UpdateWindow(self, self._available_update)
            window.setAttribute(Qt.WA_DeleteOnClose)
            window.destroyed.connect(lambda _=None, w=window: self._forget("_update_window", w))
            self._update_window = window
        self._bring_to_front(self._update_window)

    def _open_about(self):
        if self._about_window is None:
            from about_window import AboutWindow
            window = AboutWindow(self)
            window.setAttribute(Qt.WA_DeleteOnClose)
            window.destroyed.connect(lambda _=None, w=window: self._forget("_about_window", w))
            self._about_window = window
        self._bring_to_front(self._about_window)

    def _open_verses(self, tab="find"):
        if self._verses_window is None:
            from verses_window import VersesWindow
            window = VersesWindow(self)
            window.setAttribute(Qt.WA_DeleteOnClose)
            window.destroyed.connect(lambda: setattr(self, "_verses_window", None))
            window.resize(760, 500)
            geo = self._screen_for_snap().availableGeometry()
            window.move(geo.center() - window.rect().center())
            self._verses_window = window
        else:
            self._verses_window.refresh()
        self._bring_to_front(self._verses_window)
        self._verses_window.show_tab(tab)

    def _refresh_verses_window(self):
        if self._verses_window is not None and self._verses_window.isVisible():
            self._verses_window.refresh()

    def contextMenuEvent(self, event):
        """Right-click on the widget: quick actions for the verse it shows."""
        # Menus treat "&" as a shortcut marker, so "Favorites & History" needs "&&" to show it
        s = lambda key: self._s(key).replace("&", "&&")
        menu = QMenu(self)
        back = menu.addAction(s("Back"))
        back.setEnabled(self._can_go_back())
        back.triggered.connect(lambda: self._go_back())
        menu.addAction(s("Next Verse")).triggered.connect(lambda: self.show_new_verse(manual=True))
        menu.addSeparator()
        current = self._current()
        favorite = "Remove from Favorites" if self._favorites.contains(current[0], current[2]) else "Add to Favorites"
        verse_actions = [
            menu.addAction(s(favorite)),
            menu.addAction(s("Copy Verse")),
            menu.addAction(s("Save as Image")),
        ]
        # All three act on the verse the menu was opened on, even if the verse changes meanwhile
        verse_actions[0].triggered.connect(lambda: self._toggle_favorite(current))
        verse_actions[1].triggered.connect(lambda: self._copy_verse(current))
        verse_actions[2].triggered.connect(lambda: self._save_image(*current))
        for action in verse_actions:
            action.setEnabled(self._has_passage())  # nothing to keep while an error is showing
        menu.addSeparator()
        menu.addAction(s("Find a Verse...")).triggered.connect(lambda: self._open_verses("find"))
        menu.addAction(s("Favorites & History...")).triggered.connect(lambda: self._open_verses("favorites"))
        if self._context_menu is not None:
            self._context_menu.deleteLater()
        self._context_menu = menu
        menu.popup(event.globalPos())

    def _build_stats_text(self):
        now = datetime.datetime.now()
        uptime = now - self._start_time
        total_seconds = int(uptime.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        next_refresh = now + datetime.timedelta(milliseconds=max(0, self._timer.remainingTime()))
        next_time = next_refresh.strftime("%I:%M %p").lstrip("0")

        books, verses = get_translation_info(self._shown_translation) if self._shown_translation else (0, 0)
        translation = get_translation_name(self._shown_translation)
        if self._translation is None:
            translation += " (random)"

        return (
            f"Version:        {VERSION}\n"
            f"Current Quote:  {self.ref_label.text()}\n"
            f"Translation:    {translation}\n"
            f"Mode:           {self._mode.capitalize()}\n"
            f"Next refresh:   {next_time}\n"
            f"Verses:         {verses}\n"
            f"Books:          {books}\n"
            f"Uptime:         {hours}h {minutes}m {seconds}s\n"
            f"Quotes shown:   {self._quote_count}\n"
            f"Widget size:    {self.width()} x {self.height()}\n"
            f"Menu language:  {self._menu_lang}"
        )

    def _print_stats(self):
        print("--- Bible Widget - Stats for Nerds ---")
        print(self._build_stats_text())
        print("---------------------------------------", flush=True)

    def _copy_verse(self, passage=None):
        """Copy a passage (the one on the widget by default) as its text, then the reference
        with the translation, e.g. "John 11:35 (KJV)"."""
        if passage is None:
            if not self._has_passage():
                return
            passage = self._current()
        ref, text, abbr = passage
        short = get_short_name(abbr)
        QApplication.clipboard().setText(f"{text}\n{ref} ({short})" if short else f"{text}\n{ref}")
        self._notify(self._s("Verse copied"))

    def _show_stats(self):
        msg = QMessageBox()
        msg.setWindowTitle(f"Bible Widget - {self._s('Stats')}")
        msg.setIcon(QMessageBox.Information)
        msg.setFont(QFont("Consolas", 10))
        msg.setText(self._build_stats_text())
        label = msg.findChild(QLabel, "qt_msgbox_label")
        if label is not None:
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        msg.exec()

    # ----- Position and snapping -----

    def _clamp_to_screen(self):
        screen = self._screen_at_center()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = max(geo.x(), min(self.x(), geo.x() + geo.width() - self.width()))
        y = max(geo.y(), min(self.y(), geo.y() + geo.height() - self.height()))
        self.move(x, y)

    def _load_snap_corner(self):
        try:
            if os.path.isfile(self._corner_path):
                lines = read_text(self._corner_path).splitlines()
                if lines and lines[0].strip() in ("tl", "tr", "bl", "br"):
                    self._snap_corner = lines[0].strip()
                if len(lines) >= 2:
                    self._snap_screen_name = lines[1].strip()
                if len(lines) >= 3:
                    self._snap_enabled = lines[2].strip() != "off"
                if len(lines) >= 4 and "," in lines[3]:
                    x, y = (int(n) for n in lines[3].split(",", 1))
                    if abs(x) < 10 ** 6 and abs(y) < 10 ** 6:  # a real screen position
                        self._free_pos = QPoint(x, y)
        except (OSError, ValueError):
            pass

    def _save_snap_corner(self):
        enabled = "on" if self._snap_enabled else "off"
        text = f"{self._snap_corner}\n{self._snap_screen_name}\n{enabled}"
        if self._free_pos is not None:
            text += f"\n{self._free_pos.x()},{self._free_pos.y()}"
        try:
            write_text(self._corner_path, text)
        except OSError:
            log.warning("Could not save the widget's position", exc_info=True)

    def _screen_for_snap(self):
        """The screen the card belongs on. Saved as name@x,y: Windows names a screen after its
        monitor's model, so two monitors of the same model share a name and only their place
        tells them apart. A name alone (as 2.0.2 saved it), or a screen since moved, is found by
        its name."""
        saved = self._snap_screen_name
        if saved:
            screens = QApplication.screens()
            for s in screens:
                if _screen_id(s) == saved:
                    return s
            name = saved.rpartition("@")[0] if re.fullmatch(r".*@-?\d+,-?\d+", saved) else saved
            for s in screens:
                if s.name() == name:
                    return s
        return QApplication.primaryScreen()

    def _screen_at_center(self):
        center = self.frameGeometry().center()
        return QGuiApplication.screenAt(center) or self.screen() or QApplication.primaryScreen()

    def _place(self):
        """Put the widget where the saved settings say: a corner, or its free position."""
        if self._snap_enabled or self._free_pos is None:
            self._snap_to_corner(self._snap_corner)
        else:
            self.move(self._free_pos)
            self._clamp_to_screen()

    def _snap_to_corner(self, corner: str) -> None:
        screen = self._screen_for_snap()
        if screen is None:
            return
        if corner not in ("tl", "tr", "bl", "br"):
            corner = "tr"
        self._snap_corner = corner
        sg = screen.availableGeometry()
        margin = 20
        w = self.width()
        h = self.height()
        x = sg.x() + margin if corner in ("tl", "bl") else sg.x() + sg.width() - w - margin
        y = sg.y() + margin if corner in ("tl", "tr") else sg.y() + sg.height() - h - margin
        x = max(sg.x(), min(x, sg.x() + sg.width() - w))
        y = max(sg.y(), min(y, sg.y() + sg.height() - h))
        target = QPoint(x, y)
        if self.isVisible() and self.pos() != target:
            self._animate_to(target)
        else:
            self.move(target)

    def _animate_to(self, target: QPoint) -> None:
        if self._snap_anim is None:
            self._snap_anim = QPropertyAnimation(self, b"pos", self)
            self._snap_anim.setDuration(200)
            self._snap_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._snap_anim.stop()
        self._snap_anim.setStartValue(self.pos())
        self._snap_anim.setEndValue(target)
        self._snap_anim.start()

    def _set_passage(self, ref, text):
        """Show a passage. The verse label holds rich text for the line spacing,
        so the plain text is kept for copying and measuring."""
        self._verse_text = text
        # Letter spacing pulls joined Arabic letters apart (and breaks ligatures such as الله)
        self.verse_font.setLetterSpacing(QFont.AbsoluteSpacing, 0 if is_rtl(text) else 0.5)
        self.ref_font.setLetterSpacing(QFont.AbsoluteSpacing, 0 if is_rtl(ref) else 1.5)
        self.verse_label.setFont(self.verse_font)
        self.ref_label.setFont(self.ref_font)
        self.ref_label.setText(ref)
        self.verse_label.setText(
            f'<div style="line-height: {VERSE_LINE_HEIGHT}%;">{html.escape(text)}</div>'
        )

    def _fits(self, ref, text):
        """Would this passage fit the card at the normal widget size?"""
        self._set_passage(ref, text)
        return self._fit_text_size(allow_grow=False)

    def _set_font_size(self, size, fw):
        """Apply a verse font size; returns the height the reference and verse need."""
        self.verse_font.setPointSize(size)
        self.verse_label.setFont(self.verse_font)
        self.ref_font.setPointSize(max(9, min(16, size // 2)))
        self.ref_label.setFont(self.ref_font)
        return self.verse_label.heightForWidth(fw) + self.ref_label.heightForWidth(fw)

    def _fit_text_size(self, allow_grow=True):
        """Use the largest font that fits the card, down to MIN_VERSE_PT.
        Returns True if the text fits at the normal size. If it does not and allow_grow
        is set, the widget grows taller for this passage only."""
        screen = self._screen_for_snap() or self.screen()
        if screen is None:
            return True

        # 20% x 30% of the screen the card is on (it may have moved to another, or changed)
        geo = screen.geometry()
        self._base_size = base_w, base_h = int(geo.width() * 0.2), int(geo.height() * 0.3)
        screen_height = geo.height()
        base_size = max(14, min(60, screen_height // 30))
        total_len = len(self._verse_text) + len(self.ref_label.text())
        if total_len > 500:
            size = int(base_size * 0.55)
        elif total_len > 300:
            size = int(base_size * 0.70)
        elif total_len > 200:
            size = int(base_size * 0.85)
        elif total_len > 100:
            size = int(base_size * 1.0)
        else:
            size = int(base_size * 1.15)
        size = max(MIN_VERSE_PT, min(72, size))

        layout = self.layout()
        margins = layout.contentsMargins()
        fw = max(50, base_w - margins.left() - margins.right())
        self.verse_label.setFixedWidth(fw)
        self.ref_label.setFixedWidth(fw)

        # The separator and the gaps around it
        chrome = margins.top() + margins.bottom() + REF_GAP + 1 + VERSE_GAP
        available_h = base_h - chrome

        need = self._set_font_size(size, fw)
        if need > available_h and size > MIN_VERSE_PT:
            # The largest smaller size that fits (a smaller font never needs more room),
            # found in a few layouts instead of one per point
            best, lo, hi = MIN_VERSE_PT, MIN_VERSE_PT, size - 1
            while lo <= hi:
                mid = (lo + hi) // 2
                if self._set_font_size(mid, fw) <= available_h:
                    best, lo = mid, mid + 1
                else:
                    hi = mid - 1
            size = best
            need = self._set_font_size(size, fw)
        fits = need <= available_h

        if allow_grow:
            max_h = int(screen.availableGeometry().height() * 0.85)
            card_w = base_w
            if chrome + need > max_h:
                # Even the smallest font is too tall for the screen (a long verse on a small
                # screen): widen the card, up to half the screen, until the whole verse shows
                max_w = max(base_w, int(screen.availableGeometry().width() * 0.5))
                while chrome + need > max_h and card_w < max_w:
                    card_w = min(max_w, card_w + max(20, base_w // 4))
                    fw = max(50, card_w - margins.left() - margins.right())
                    self.verse_label.setFixedWidth(fw)
                    self.ref_label.setFixedWidth(fw)
                    need = self._set_font_size(size, fw)
            target_h = base_h if fits else min(max_h, chrome + need)
            if (self.width(), self.height()) != (card_w, target_h):
                self._resizing = True
                self.resize(card_w, target_h)
                self._resizing = False
                if self.isVisible():
                    self._place()
            layout.activate()
            self.update()
        return fits

    def _on_screens_changed(self, *_):
        QTimer.singleShot(1000, self._refit)

    def _refit(self):
        """Size the card (and open prayers) for their screens again and put them back in place
        (not mid-drag)."""
        for window in self._prayer_windows:
            window.refit()
        if self._dragging:
            return
        self._fit_text_size()
        self._place()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._resizing:
            self._resizing = True
            self._fit_text_size()
            self._resizing = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # The card is inset (15, 10) from the window edge to leave room for its shadow
        paint_card(painter, self.rect().adjusted(15, 10, -15, -10),
                   self._colors["backdrop"], self._colors["shadow"])

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
            self._dragging = True
            if self._snap_anim is not None:
                self._snap_anim.stop()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self._dragging:
            return
        self._drag_pos = None
        self._dragging = False
        screen = self._screen_at_center()
        if screen is None:
            return
        self._snap_screen_name = _screen_id(screen)
        if not self._snap_enabled:
            self._clamp_to_screen()
            self._free_pos = self.pos()
            self._save_snap_corner()
            self._fit_text_size()  # sized for the screen it was dropped on
            return
        sg = screen.availableGeometry()
        center = self.frameGeometry().center()
        left = center.x() - sg.x() < sg.width() / 2
        top = center.y() - sg.y() < sg.height() / 2
        self._snap_corner = ("t" if top else "b") + ("l" if left else "r")
        self._save_snap_corner()
        self._fit_text_size()  # sized for the screen it was dropped on
        self._snap_to_corner(self._snap_corner)


class ColorSettingsDialog(QDialog):
    _ROW_KEYS = [
        ("text", "Verse Text"),
        ("backdrop", "Background"),
        ("separator", "Separator Line"),
    ]

    colors_changed = Signal()

    def __init__(self, current_colors, tr=lambda key: key, parent=None):
        super().__init__(parent)
        self._tr = tr
        self.setWindowTitle(tr("Customize Colors"))
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setFont(QFont("Segoe UI", 10))
        self.setMinimumWidth(320)

        self._pending = {key: QColor(current_colors[key]) for key, _ in self._ROW_KEYS}
        self._swatches = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        for key, label in self._ROW_KEYS:
            row = self._make_color_row(key, tr(label), self._pending[key])
            layout.addWidget(row)

        layout.addSpacing(8)

        reset_btn = QPushButton(tr("Reset to Defaults"))
        reset_btn.clicked.connect(self._on_reset)
        layout.addWidget(reset_btn)

        buttons = QDialogButtonBox()
        apply_btn = buttons.addButton(tr("Apply"), QDialogButtonBox.ApplyRole)
        ok_btn = buttons.addButton(QDialogButtonBox.Ok)
        cancel_btn = buttons.addButton(QDialogButtonBox.Cancel)
        ok_btn.setText(tr("OK"))
        cancel_btn.setText(tr("Cancel"))
        apply_btn.clicked.connect(self._on_apply)
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def _make_color_row(self, key: str, label: str, color: QColor) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)

        h.addWidget(QLabel(label), 1)

        swatch = QPushButton()
        swatch.setFixedSize(48, 24)
        swatch.setCursor(Qt.PointingHandCursor)
        swatch.clicked.connect(lambda _, k=key, n=label: self._pick_color(k, n))
        self._update_swatch(swatch, color)
        h.addWidget(swatch)

        self._swatches[key] = swatch
        return row

    def _update_swatch(self, swatch: QPushButton, color: QColor) -> None:
        swatch.setStyleSheet(
            f"background-color: {_rgba(color)}; border: 1px solid #888; border-radius: 3px;"
        )
        swatch.setToolTip(f"{color.name()}  ({round(color.alphaF() * 100)}%)")

    def _pick_color(self, key: str, label: str) -> None:
        chosen = QColorDialog.getColor(
            self._pending[key], self, label, QColorDialog.ShowAlphaChannel
        )
        if chosen.isValid():
            self._pending[key] = chosen
            self._update_swatch(self._swatches[key], chosen)

    def _on_reset(self) -> None:
        for key, _ in self._ROW_KEYS:
            default = QColor(DEFAULT_COLORS[key])
            self._pending[key] = default
            self._update_swatch(self._swatches[key], default)

    def _on_apply(self) -> None:
        for key, _ in self._ROW_KEYS:
            set_color(key, self._pending[key])
        self.colors_changed.emit()

    def _on_ok(self) -> None:
        self._on_apply()
        self.accept()


def _setup_logging():
    """Everything runs without a console, so errors go to widget.log."""
    try:
        handler = RotatingFileHandler(
            os.path.join(APP_DIR, "widget.log"), maxBytes=512 * 1024, backupCount=1, encoding="utf-8"
        )
    except OSError:
        handler = logging.NullHandler()  # read-only folder: run without a log file
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    crash_log.install(APP_DIR)  # errors in other threads, fatal errors, Windows ending the app

    def excepthook(exc_type, exc, tb):
        log.error("Unhandled exception:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        if sys.__excepthook__ and sys.stderr is not None:
            sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = excepthook

    levels = {
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def qt_handler(msg_type, context, message):
        if msg_type in levels:
            log.log(levels[msg_type], "Qt: %s", message)

    qInstallMessageHandler(qt_handler)


def _screen_id(screen):
    """A screen's name and place, which tell apart two monitors of the same model."""
    geo = screen.geometry()
    return f"{screen.name()}@{geo.x()},{geo.y()}"


def _notify_running_instance(name):
    """If another widget is already running, ask it to show itself. Returns True if so."""
    socket = QLocalSocket()
    socket.connectToServer(name)
    if not socket.waitForConnected(500):
        return False
    socket.write(b"show")
    socket.flush()
    socket.waitForBytesWritten(500)
    socket.disconnectFromServer()
    return True


def _claim_single_instance(server_name):
    """Keep to one running copy per user: returns the held lock, or None if a copy is already
    running (it is asked to show itself)."""
    lock = QLockFile(os.path.join(QDir.tempPath(), server_name + ".lock"))
    if not lock.tryLock(200):
        if lock.error() == QLockFile.LockFailedError:
            _notify_running_instance(server_name)
            log.info("Already running; asked the existing widget to show itself")
            return None
        # The lock file can't be made (the temp folder is missing or read-only): the pipe check
        # below still finds a running copy
        log.warning("Could not create the lock file in %s (%s)", QDir.tempPath(), lock.error())
    # Version 2.0.2 and older don't take the lock, only answer on the pipe: one may be running
    if _notify_running_instance(server_name):
        log.info("An older version is running; asked it to show itself")
        lock.unlock()
        return None
    return lock


def run_widget():
    if "--install-update" in sys.argv:
        # This exe is a newly downloaded version installing itself over the old one
        sys.exit(updater.install_main(sys.argv))
    if "--self-test" in sys.argv:
        from selftest import run
        sys.exit(run())
    _setup_logging()
    app = QApplication(sys.argv)
    app.setWindowIcon(make_tray_icon(light_taskbar=False))  # dialogs and windows show the cross
    # The widget is a tool window; closing a dialog must not end the app
    app.setQuitOnLastWindowClosed(False)

    server_name = f"BibleWidget-{getpass.getuser()}"
    lock = _claim_single_instance(server_name)
    if lock is None:
        return

    QLocalServer.removeServer(server_name)
    server = QLocalServer()
    server.listen(server_name)

    log.info("Bible Widget starting (version %s, pid %s)", VERSION, os.getpid())
    # How the last run ended, if it never quit; then widget.pid, kept up to date while running
    crash_log.start_run()
    heartbeat = QTimer(app)
    heartbeat.timeout.connect(crash_log.heartbeat)
    heartbeat.start(crash_log.HEARTBEAT_MS)
    widget = BibleWidget()
    widget.show()

    def on_connection():
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.disconnected.connect(conn.deleteLater)
            widget._bring_back()

    server.newConnection.connect(on_connection)
    # Once running: confirm to an installer that this new version started, and tidy up
    QTimer.singleShot(0, updater.confirm_started)
    QTimer.singleShot(30000, updater.clean_leftovers)
    code = app.exec()
    crash_log.end_run(f"the app's event loop ended (exit code {code})")
    sys.exit(code)


if __name__ == "__main__":
    run_widget()
