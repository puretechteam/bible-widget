import sys
import os
import datetime
from PySide6.QtWidgets import (
    QWidget, QApplication, QVBoxLayout, QLabel,
    QFrame, QSystemTrayIcon, QMenu
)
from PySide6.QtGui import (
    QFont, QPainter, QColor, QBrush, QPen, QRegion, QPainterPath, QIcon, QPixmap, QAction
)
from PySide6.QtCore import Qt, QTimer
from bible_loader import get_random_passage, get_verse_of_the_day, _load_data, get_available_translations


class BibleWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bible Widget")
        self._verbose = "--verbose" in sys.argv
        self._start_time = datetime.datetime.now()
        self._quote_count = 0
        self._translation = None
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._drag_pos = None
        self._resizing = False
        self._mode = "hourly"
        self._anchor_pos = None
        self._backdrop_brush = QBrush(QColor(0, 0, 0, 130))
        self._no_pen = QPen(Qt.NoPen)

        self._setup_fonts()
        self._setup_ui()

        self._screen = QApplication.primaryScreen()

        self._pid_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "widget.pid")

        self._setup_tray()

        bible = _load_data()
        self._total_verses = sum(
            len(v) for book in bible.values() for c in book.values() for v in c.values()
        )

        self.show_new_verse()
        QTimer.singleShot(200, self._save_anchor)

        self._timer = QTimer()
        self._timer.timeout.connect(self.show_new_verse)
        self._timer.start(3600000)

        # Default to Medium size (20% of screen) after auto-sizing
        scr = self._screen.geometry()
        self.resize(int(scr.width() * 0.2), int(scr.height() * 0.2))
        self._fit_text_size()

    def _setup_tray(self):
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawLine(8, 1, 8, 15)
        painter.drawLine(3, 5, 13, 5)
        painter.end()

        self._tray_icon = QSystemTrayIcon()
        self._tray_icon.setIcon(QIcon(pixmap))
        self._tray_icon.setToolTip("Bible Widget")

        menu = QMenu()

        self._hourly_action = QAction("Hourly Mode")
        self._hourly_action.setCheckable(True)
        self._hourly_action.setChecked(True)
        self._hourly_action.triggered.connect(lambda: self._set_mode("hourly"))
        menu.addAction(self._hourly_action)

        self._daily_action = QAction("Daily Mode")
        self._daily_action.setCheckable(True)
        self._daily_action.triggered.connect(lambda: self._set_mode("daily"))
        menu.addAction(self._daily_action)

        menu.addSeparator()

        # Translation submenu
        trans_menu = QMenu("Translation")
        self._translation_group = []
        all_action = QAction("All (Random)")
        all_action.setCheckable(True)
        all_action.setChecked(True)
        all_action.triggered.connect(lambda: self._set_translation(None))
        trans_menu.addAction(all_action)
        self._translation_group.append(all_action)
        trans_menu.addSeparator()

        for abbr, name, lang in get_available_translations():
            action = QAction(f"{name} ({lang})")
            action.setCheckable(True)
            action.triggered.connect(lambda checked, a=abbr: self._set_translation(a))
            trans_menu.addAction(action)
            self._translation_group.append(action)

        menu.addMenu(trans_menu)

        menu.addSeparator()

        self._change_action = QAction("Change Quote")
        self._change_action.triggered.connect(self.show_new_verse)
        menu.addAction(self._change_action)

        menu.addSeparator()

        startup_menu = QMenu("Run on Startup")
        self._startup_silent_action = QAction("Silent (no terminal)")
        self._startup_silent_action.setCheckable(True)
        self._startup_silent_action.triggered.connect(lambda: self._set_startup("silent"))
        startup_menu.addAction(self._startup_silent_action)

        self._startup_terminal_action = QAction("With terminal")
        self._startup_terminal_action.setCheckable(True)
        self._startup_terminal_action.triggered.connect(lambda: self._set_startup("terminal"))
        startup_menu.addAction(self._startup_terminal_action)

        sm = self._startup_mode()
        if sm == "silent":
            self._startup_silent_action.setChecked(True)
        elif sm == "terminal":
            self._startup_terminal_action.setChecked(True)

        menu.addMenu(startup_menu)

        menu.addSeparator()

        self._exit_action = QAction("Exit")
        self._exit_action.triggered.connect(self._exit_app)
        menu.addAction(self._exit_action)

        self._tray_icon.setContextMenu(menu)
        self._tray_icon.show()

    def _set_translation(self, abbr):
        self._translation = abbr
        for i, action in enumerate(self._translation_group):
            action.setChecked(i == 0 and abbr is None)
        self.show_new_verse()

    def _startup_dir(self):
        return os.path.join(
            os.path.expanduser("~"),
            "AppData", "Roaming", "Microsoft", "Windows",
            "Start Menu", "Programs", "Startup"
        )

    def _startup_file_path(self):
        return os.path.join(self._startup_dir(), "BibleWidget.vbs")

    def _startup_mode(self):
        p = self._startup_file_path()
        if not os.path.exists(p):
            return None
        try:
            with open(p, "r") as f:
                content = f.read()
            if "start_widget_no_terminal" in content:
                return "silent"
            elif "start_widget" in content:
                return "terminal"
        except OSError:
            pass
        return None

    def _set_startup(self, mode):
        p = self._startup_file_path()
        if mode is None:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
            return
        widget_dir = os.path.dirname(os.path.abspath(__file__))
        launcher = os.path.join(widget_dir, "start_widget_no_terminal.vbs" if mode == "silent" else "start_widget.bat")
        content = f'CreateObject("Wscript.Shell").Run "pythonw ""{launcher}""", 0, False\n'
        with open(p, "w") as f:
            f.write(content)

    def _set_mode(self, mode):
        self._mode = mode
        self._hourly_action.setChecked(mode == "hourly")
        self._daily_action.setChecked(mode == "daily")
        self._timer.stop()
        if mode == "hourly":
            self._timer.start(3600000)
        else:
            self._timer.start(86400000)
        self.show_new_verse()

    def _exit_app(self):
        try:
            if os.path.exists(self._pid_path):
                os.remove(self._pid_path)
        except OSError:
            pass
        QApplication.quit()

    def _setup_fonts(self):
        self.verse_font = QFont("Calibri", 26)
        self.verse_font.setWeight(QFont.Normal)
        self.ref_font = QFont("Calibri", 15)
        self.ref_font.setWeight(QFont.DemiBold)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(45, 30, 45, 30)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignCenter)

        self.ref_label = QLabel()
        self.ref_label.setFont(self.ref_font)
        self.ref_label.setStyleSheet("color: white;")
        self.ref_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.ref_label)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: rgba(180, 180, 180, 120);")
        separator.setFixedHeight(1)
        layout.addWidget(separator)

        self.verse_label = QLabel()
        self.verse_label.setFont(self.verse_font)
        self.verse_label.setStyleSheet("color: white;")
        self.verse_label.setAlignment(Qt.AlignCenter)
        self.verse_label.setWordWrap(True)
        layout.addWidget(self.verse_label)

    def show_new_verse(self):
        if self._mode == "daily":
            ref, text = get_verse_of_the_day(self._translation)
        else:
            ref, text = get_random_passage(self._translation)
        self.ref_label.setText(ref)
        self.verse_label.setText(text)
        self._quote_count += 1
        self._fit_text_size()
        if self._verbose:
            self._print_stats()

    def _print_stats(self):
        now = datetime.datetime.now()
        uptime = now - self._start_time
        total_seconds = int(uptime.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if self._mode == "hourly":
            interval_mins = 60
        else:
            interval_mins = 1440
        next_refresh = now + datetime.timedelta(minutes=interval_mins)
        next_time = next_refresh.strftime("%I:%M %p").lstrip("0")

        print("--- Bible Widget - Stats for Nerds ---")
        print(f"  Current Quote:  {self.ref_label.text()}")
        print(f"  Mode:           {self._mode.capitalize()}")
        print(f"  Next refresh:   {next_time}")
        print(f"  Verses in DB:   {self._total_verses}")
        print(f"  Books:          66")
        print(f"  Uptime:         {hours}h {minutes}m {seconds}s")
        print(f"  Quotes shown:   {self._quote_count}")
        print(f"  Widget size:    {self.width()} x {self.height()}")
        print("---------------------------------------")

    def _save_anchor(self):
        self._anchor_pos = self.frameGeometry().center()

    def _fit_text_size(self):
        if not self._screen:
            return

        self.verse_label.setWordWrap(True)
        self.ref_label.setWordWrap(True)

        screen_height = self._screen.geometry().height()
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

        self.verse_font.setPointSize(size)
        self.verse_label.setFont(self.verse_font)
        ref_size = max(10, min(28, size // 2 + 2))
        self.ref_font.setPointSize(ref_size)
        self.ref_label.setFont(self.ref_font)

        fw = max(50, self.width() - 90)
        self.verse_label.setFixedWidth(fw)
        self.ref_label.setFixedWidth(fw)
        self.verse_label.updateGeometry()
        self.ref_label.updateGeometry()
        # Calculate required height from font metrics
        fm_v = self.verse_label.fontMetrics()
        fm_r = self.ref_label.fontMetrics()
        # Use boundingRect with word-wrap width to get actual rect
        v_rect = fm_v.boundingRect(0, 0, fw, 9999, Qt.TextWordWrap, self.verse_label.text())
        r_rect = fm_r.boundingRect(0, 0, fw, 9999, Qt.TextWordWrap, self.ref_label.text())
        need_h = v_rect.height() + r_rect.height() + 60 + 12
        if need_h > self.height():
            self.resize(self.width(), need_h)
        self.layout().activate()

        if self._anchor_pos is not None:
            new_rect = self.frameGeometry()
            new_rect.moveCenter(self._anchor_pos)
            self.move(new_rect.topLeft())

    def resizeEvent(self, event):
        if self._resizing:
            return
        self._resizing = True
        super().resizeEvent(event)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 16, 16)
        region = QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)
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

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = None
            self._save_anchor()


def run_widget():
    pid_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "widget.pid")
    with open(pid_path, "w") as f:
        f.write(str(os.getpid()))

    app = QApplication(sys.argv)
    widget = BibleWidget()
    widget.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_widget()