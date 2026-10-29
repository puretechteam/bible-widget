import sys
import os
import time
import getpass
import datetime
import logging
import traceback
from logging.handlers import RotatingFileHandler
from PySide6.QtWidgets import (
    QWidget, QApplication, QVBoxLayout, QLabel,
    QFrame, QSystemTrayIcon, QMenu, QMessageBox, QGraphicsDropShadowEffect,
    QDialog, QDialogButtonBox, QPushButton, QHBoxLayout, QColorDialog
)
from PySide6.QtGui import (
    QFont, QPainter, QColor, QBrush, QPen, QRegion, QPainterPath, QIcon, QPixmap,
    QAction, QActionGroup, QGuiApplication
)
from PySide6.QtCore import (
    Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve, Signal, qInstallMessageHandler, QtMsgType
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from bible_loader import (
    get_random_passage, get_verse_of_the_day, get_available_translations,
    get_translation_info
)
from prayer_window import PrayerWindow
from menu_strings import get_string, get_available_languages, get_translated_language_name
from colors import get_colors, set_color, DEFAULT_COLORS

APP_DIR = os.path.dirname(os.path.abspath(__file__))
RANDOM_TRANSLATION = "random"
MODE_INTERVALS = {"hourly": 3600000, "random": 900000}  # daily is scheduled for midnight

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
    DESKTOP_CLASSES = ("WorkerW", "Progman")


def _rgba(color: QColor) -> str:
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"


def _separator_style(color: QColor) -> str:
    c = _rgba(color)
    return (
        f"border: none; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
        f"stop:0 transparent, stop:0.3 {c}, stop:0.7 {c}, stop:1 transparent);"
    )


class BibleWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bible Widget")
        self._verbose = "--verbose" in sys.argv
        self._start_time = datetime.datetime.now()
        self._quote_count = 0
        self._translation = None
        self._shown_translation = ""
        self._menu_lang = "en"
        self._prayer_windows = []
        self._color_dialog = None
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
        self._backdrop_brush = QBrush(self._colors["backdrop"])
        self._text_color = self._colors["text"]
        self._separator_color = self._colors["separator"]
        self._no_pen = QPen(Qt.NoPen)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(self._colors["shadow"])
        self.setGraphicsEffect(shadow)

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

        self._setup_tray()
        self._repair_startup()

        scr = self._screen_for_snap().geometry()
        self.resize(int(scr.width() * 0.2), int(scr.height() * 0.3))
        self._place()

        app = QApplication.instance()
        app.screenAdded.connect(lambda _: QTimer.singleShot(1000, self._place))
        app.screenRemoved.connect(lambda _: QTimer.singleShot(1000, self._place))

        self.show_new_verse()
        self._schedule_next()

    def _s(self, key):
        return get_string(key, self._menu_lang)

    def _build_menu(self):
        """Build the tray menu with translated strings."""
        s = self._s
        menu = QMenu()

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
        copy_action.triggered.connect(self._copy_verse)
        menu.addAction(copy_action)

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
            action = QAction(f"{name} ({translated_lang})", trans_menu)
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
        for mode, label in ((None, "Off"), ("silent", "Silent (no terminal)"), ("console", "With console")):
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

        exit_action = QAction(s("Exit"), menu)
        exit_action.triggered.connect(self._exit_app)
        menu.addAction(exit_action)

        return menu

    def _make_tray_pixmap(self):
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(self._text_color)
        color.setAlpha(255)
        painter.setPen(QPen(color, 2))
        painter.drawLine(8, 1, 8, 15)
        painter.drawLine(3, 5, 13, 5)
        painter.end()
        return pixmap

    def _setup_tray(self):
        self._tray_icon = QSystemTrayIcon(self)
        self._tray_icon.setIcon(QIcon(self._make_tray_pixmap()))
        self._tray_icon.setToolTip("Bible Widget")
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._menu = self._build_menu()
        self._tray_icon.setContextMenu(self._menu)
        self._tray_icon.show()

    def _rebuild_menu(self):
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

    def _apply_colors(self):
        self._colors = get_colors()
        self._backdrop_brush = QBrush(self._colors["backdrop"])
        self._text_color = self._colors["text"]
        self._separator_color = self._colors["separator"]
        self._apply_label_styles()

        shadow = self.graphicsEffect()
        if isinstance(shadow, QGraphicsDropShadowEffect):
            shadow.setColor(self._colors["shadow"])

        self._tray_icon.setIcon(QIcon(self._make_tray_pixmap()))
        self.update()

        for window in self._prayer_windows:
            window._apply_colors()

    def _apply_label_styles(self):
        self.ref_label.setStyleSheet(f"color: {_rgba(self._text_color)};")
        self.verse_label.setStyleSheet(f"color: {_rgba(self._text_color)}; letter-spacing: 0.5px;")
        for sep in self._separators:
            sep.setStyleSheet(_separator_style(self._separator_color))

    def _open_color_settings(self):
        if self._color_dialog is not None and self._color_dialog.isVisible():
            self._color_dialog.raise_()
            self._color_dialog.activateWindow()
            return
        dlg = ColorSettingsDialog(get_colors(), self._s)
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.colors_changed.connect(self._apply_colors)
        dlg.destroyed.connect(lambda: setattr(self, "_color_dialog", None))
        dlg.adjustSize()
        geo = self._screen_for_snap().availableGeometry()
        dlg.move(geo.center() - dlg.rect().center())
        self._color_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

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
        self.show_new_verse(manual=True)

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
        content = self._read_startup_file()
        if content is None:
            return None
        if "mode=console" in content:
            return "console"
        if "mode=silent" in content or "pythonw" in content or "pyw" in content:
            return "silent"
        return "console"

    def _startup_content(self, mode):
        script = os.path.join(APP_DIR, "widget_window.py")
        if mode == "silent":
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
                if os.path.exists(p):
                    os.remove(p)
            else:
                os.makedirs(self._startup_dir(), exist_ok=True)
                # UTF-16 with BOM so Windows Script Host reads non-ASCII paths correctly
                with open(p, "w", encoding="utf-16", newline="") as f:
                    f.write(self._startup_content(mode))
        except OSError:
            log.exception("Could not update the startup launcher")
        self._rebuild_menu()

    def _repair_startup(self):
        """Rewrite the startup launcher only if it no longer matches this install."""
        content = self._read_startup_file()
        if content is None:
            return
        mode = self._startup_mode()
        if content != self._startup_content(mode):
            log.info("Repairing startup launcher (mode=%s)", mode)
            self._set_startup(mode)

    # ----- Preferences -----

    def _load_translation_preference(self):
        try:
            if os.path.isfile(self._translation_path):
                with open(self._translation_path, "r", encoding="utf-8") as f:
                    val = f.read().strip()
                if val == RANDOM_TRANSLATION:
                    self._translation = None
                elif val in {a for a, _, _ in get_available_translations()}:
                    self._translation = val
        except OSError:
            pass

    def _save_translation_preference(self):
        try:
            with open(self._translation_path, "w", encoding="utf-8") as f:
                f.write(self._translation or RANDOM_TRANSLATION)
        except OSError:
            pass

    def _load_language_preference(self):
        try:
            if os.path.isfile(self._language_path):
                with open(self._language_path, "r", encoding="utf-8") as f:
                    val = f.read().strip()
                if val and val in dict(get_available_languages()):
                    self._menu_lang = val
        except OSError:
            pass

    def _save_language_preference(self):
        try:
            with open(self._language_path, "w", encoding="utf-8") as f:
                f.write(self._menu_lang)
        except OSError:
            pass

    def _load_mode(self):
        try:
            if os.path.isfile(self._mode_path):
                with open(self._mode_path, "r", encoding="utf-8") as f:
                    val = f.read().strip()
                if val in ("hourly", "daily", "random"):
                    self._mode = val
        except OSError:
            pass

    def _save_mode(self):
        try:
            with open(self._mode_path, "w", encoding="utf-8") as f:
                f.write(self._mode)
        except OSError:
            pass

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

    def _on_timer(self):
        self.show_new_verse()
        self._schedule_next()

    def _open_prayer(self, prayer_id="lords-prayer"):
        """Open a prayer window using the current (or last shown) translation."""
        abbr = self._translation or self._shown_translation or "en_kjv"
        window = PrayerWindow(abbr, prayer_id, self._menu_lang)
        window.setAttribute(Qt.WA_DeleteOnClose)
        self._prayer_windows.append(window)
        window.destroyed.connect(lambda _=None, w=window: self._forget_prayer(w))
        window.show()

    def _forget_prayer(self, window):
        if window in self._prayer_windows:
            self._prayer_windows.remove(window)

    def _exit_app(self):
        try:
            if os.path.exists(self._pid_path):
                os.remove(self._pid_path)
        except OSError:
            pass
        self._tray_icon.hide()
        QApplication.quit()

    # ----- UI -----

    def _setup_fonts(self):
        self.verse_font = QFont("Segoe UI", 26)
        self.verse_font.setWeight(QFont.Medium)
        self.ref_font = QFont("Segoe UI", 16)
        self.ref_font.setWeight(QFont.Medium)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 35, 50, 35)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignCenter)

        self._separators = []
        separator_top = QFrame()
        separator_top.setFrameShape(QFrame.HLine)
        separator_top.setFixedHeight(1)
        layout.addWidget(separator_top)
        self._separators.append(separator_top)

        self.ref_label = QLabel()
        self.ref_label.setFont(self.ref_font)
        self.ref_label.setAlignment(Qt.AlignCenter)
        self.ref_label.setWordWrap(True)
        layout.addWidget(self.ref_label)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFixedHeight(1)
        layout.addWidget(separator)
        self._separators.append(separator)

        self.verse_label = QLabel()
        self.verse_label.setFont(self.verse_font)
        self.verse_label.setAlignment(Qt.AlignCenter)
        self.verse_label.setWordWrap(True)
        layout.addWidget(self.verse_label)

        self._apply_label_styles()

    def show_new_verse(self, manual=False):
        if self._mode == "daily" and not manual:
            ref, text, abbr = get_verse_of_the_day(self._translation, with_translation=True)
        else:
            ref, text, abbr = get_random_passage(self._translation, with_translation=True)
        self._shown_translation = abbr
        self.ref_label.setText(ref)
        self.verse_label.setText(text)
        self._quote_count += 1
        self._fit_text_size()
        if self._verbose:
            self._print_stats()

    def _build_stats_text(self):
        now = datetime.datetime.now()
        uptime = now - self._start_time
        total_seconds = int(uptime.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        next_refresh = now + datetime.timedelta(milliseconds=max(0, self._timer.remainingTime()))
        next_time = next_refresh.strftime("%I:%M %p").lstrip("0")

        books, verses = get_translation_info(self._shown_translation) if self._shown_translation else (0, 0)
        names = {a: n for a, n, _ in get_available_translations()}
        translation = names.get(self._shown_translation, self._shown_translation)
        if self._translation is None:
            translation += " (random)"

        return (
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

    def _copy_verse(self):
        text = f"{self.verse_label.text()}\n{self.ref_label.text()}"
        QApplication.clipboard().setText(text)

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
                with open(self._corner_path, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines()
                if lines and lines[0].strip() in ("tl", "tr", "bl", "br"):
                    self._snap_corner = lines[0].strip()
                if len(lines) >= 2:
                    self._snap_screen_name = lines[1].strip()
                if len(lines) >= 3:
                    self._snap_enabled = lines[2].strip() != "off"
                if len(lines) >= 4 and "," in lines[3]:
                    x, y = lines[3].split(",", 1)
                    self._free_pos = QPoint(int(x), int(y))
        except (OSError, ValueError):
            pass

    def _save_snap_corner(self):
        try:
            with open(self._corner_path, "w", encoding="utf-8") as f:
                enabled = "on" if self._snap_enabled else "off"
                f.write(f"{self._snap_corner}\n{self._snap_screen_name}\n{enabled}")
                if self._free_pos is not None:
                    f.write(f"\n{self._free_pos.x()},{self._free_pos.y()}")
        except OSError:
            pass

    def _screen_for_snap(self):
        if self._snap_screen_name:
            for s in QApplication.screens():
                if s.name() == self._snap_screen_name:
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
        if self._snap_anim is not None:
            self._snap_anim.stop()
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(self.pos())
        anim.setEndValue(target)
        anim.start()
        self._snap_anim = anim

    def _fit_text_size(self):
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return

        screen_height = screen.geometry().height()
        base_size = max(14, min(60, screen_height // 30))
        total_len = len(self.verse_label.text()) + len(self.ref_label.text())
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
        size = max(12, min(72, size))

        layout = self.layout()
        margins = layout.contentsMargins()
        fw = max(50, self.width() - margins.left() - margins.right())
        self.verse_label.setFixedWidth(fw)
        self.ref_label.setFixedWidth(fw)

        # Two separators plus the spacing between the four layout items
        chrome = margins.top() + margins.bottom() + 2 + 3 * layout.spacing()
        available_h = self.height() - chrome

        while True:
            self.verse_font.setPointSize(size)
            self.verse_label.setFont(self.verse_font)
            self.ref_font.setPointSize(max(10, min(28, size // 2 + 2)))
            self.ref_label.setFont(self.ref_font)
            v_rect = self.verse_label.fontMetrics().boundingRect(
                0, 0, fw, 9999, Qt.TextWordWrap, self.verse_label.text())
            r_rect = self.ref_label.fontMetrics().boundingRect(
                0, 0, fw, 9999, Qt.TextWordWrap, self.ref_label.text())
            if v_rect.height() + r_rect.height() <= available_h or size <= 12:
                break
            size -= 1
        layout.activate()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 16, 16)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))
        if not self._resizing:
            self._resizing = True
            self._fit_text_size()
            self._resizing = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        margins = self.layout().contentsMargins()
        rect = self.rect().adjusted(
            margins.left() - 35,
            margins.top() - 25,
            -(margins.right() - 35),
            -(margins.bottom() - 25)
        )

        painter.setBrush(self._backdrop_brush)
        painter.setPen(self._no_pen)
        painter.drawRoundedRect(rect, 16, 16)

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
        self._snap_screen_name = screen.name() or ""
        if not self._snap_enabled:
            self._clamp_to_screen()
            self._free_pos = self.pos()
            self._save_snap_corner()
            return
        sg = screen.availableGeometry()
        center = self.frameGeometry().center()
        left = center.x() - sg.x() < sg.width() / 2
        top = center.y() - sg.y() < sg.height() / 2
        self._snap_corner = ("t" if top else "b") + ("l" if left else "r")
        self._save_snap_corner()
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
    handler = RotatingFileHandler(
        os.path.join(APP_DIR, "widget.log"), maxBytes=512 * 1024, backupCount=1, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

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


def run_widget():
    _setup_logging()
    app = QApplication(sys.argv)
    # The widget is a tool window; closing a dialog must not end the app
    app.setQuitOnLastWindowClosed(False)

    server_name = f"BibleWidget-{getpass.getuser()}"
    if _notify_running_instance(server_name):
        log.info("Already running; asked the existing widget to show itself")
        return

    QLocalServer.removeServer(server_name)
    server = QLocalServer()
    server.listen(server_name)

    pid_path = os.path.join(APP_DIR, "widget.pid")
    with open(pid_path, "w") as f:
        f.write(str(os.getpid()))

    log.info("Bible Widget starting (pid %s)", os.getpid())
    widget = BibleWidget()
    widget.show()

    def on_connection():
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.disconnected.connect(conn.deleteLater)
            widget._bring_back()

    server.newConnection.connect(on_connection)
    sys.exit(app.exec())


if __name__ == "__main__":
    run_widget()
