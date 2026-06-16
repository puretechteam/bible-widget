import sys
import os
import datetime
from PySide6.QtWidgets import (
    QWidget, QApplication, QVBoxLayout, QLabel,
    QGraphicsDropShadowEffect, QFrame, QSystemTrayIcon, QMenu
)
from PySide6.QtGui import (
    QFont, QPainter, QColor, QBrush, QPen, QRegion, QPainterPath, QIcon, QPixmap, QAction
)
from PySide6.QtCore import Qt, QTimer
from bible_loader import get_random_passage, get_verse_of_the_day, _load_data

class BibleWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bible Widget")
        self._verbose = "--verbose" in sys.argv
        self._start_time = datetime.datetime.now()
        self._quote_count = 0
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

        # Cache screen reference
        self._screen = QApplication.primaryScreen()

        # Store PID path for clean exit
        self._pid_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "widget.pid")

        # Setup tray icon
        self._setup_tray()

        # Cache total verse count for stats
        bible = _load_data()
        self._total_verses = sum(len(c) for book in bible.values() for c in book.values())

        # Show a verse right away
        self.show_new_verse()
        # On first render, anchor to center
        QTimer.singleShot(200, self._save_anchor)

        # Timer for refreshing the verse
        self._timer = QTimer()
        self._timer.timeout.connect(self.show_new_verse)
        self._timer.start(3600000)

    def _setup_tray(self):
        # Create a simple icon programmatically
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        # Draw a Latin cross (horizontal beam at first quadsection)
        painter.drawLine(8, 1, 8, 15)
        painter.drawLine(3, 5, 13, 5)
        painter.end()

        self._tray_icon = QSystemTrayIcon()
        self._tray_icon.setIcon(QIcon(pixmap))
        self._tray_icon.setToolTip("Bible Widget")

        # Build menu
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

        self._change_action = QAction("Change Quote")
        self._change_action.triggered.connect(self.show_new_verse)
        menu.addAction(self._change_action)

        menu.addSeparator()

        self._startup_action = QAction("Run on Startup")
        self._startup_action.setCheckable(True)
        startup_path = os.path.join(
            os.path.expanduser("~"),
            "AppData", "Roaming", "Microsoft", "Windows",
            "Start Menu", "Programs", "Startup", "BibleWidget.bat"
        )
        self._startup_action.setChecked(os.path.exists(startup_path))
        self._startup_action.triggered.connect(lambda checked: self._toggle_startup(checked, startup_path))
        menu.addAction(self._startup_action)

        menu.addSeparator()

        self._exit_action = QAction("Exit")
        self._exit_action.triggered.connect(self._exit_app)
        menu.addAction(self._exit_action)

        self._tray_icon.setContextMenu(menu)
        self._tray_icon.show()

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

    def _toggle_startup(self, checked, startup_path):
        if checked:
            vbs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "start_widget_no_terminal.vbs")
            content = '@echo off\nstart "" "' + vbs_path + '"\n'
            with open(startup_path, "w") as f:
                f.write(content)
        else:
            try:
                if os.path.exists(startup_path):
                    os.remove(startup_path)
            except OSError:
                pass

    def _exit_app(self):
        # Clean up PID file
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

        # Reference label (above the verse)
        self.ref_label = QLabel()
        self.ref_label.setFont(self.ref_font)
        self.ref_label.setStyleSheet("color: white;")
        self.ref_label.setAlignment(Qt.AlignCenter)
        self._add_drop_shadow(self.ref_label)
        layout.addWidget(self.ref_label)

        # Dark separator line between reference and verse
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: rgba(180, 180, 180, 120);")
        separator.setFixedHeight(1)
        layout.addWidget(separator)

        # Verse text label
        self.verse_label = QLabel()
        self.verse_label.setFont(self.verse_font)
        self.verse_label.setStyleSheet("color: white;")
        self.verse_label.setAlignment(Qt.AlignCenter)
        self.verse_label.setWordWrap(True)
        self._add_drop_shadow(self.verse_label)
        layout.addWidget(self.verse_label)

    def _add_drop_shadow(self, label):
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(8)
        shadow.setOffset(2, 2)
        shadow.setColor(QColor(0, 0, 0, 180))
        label.setGraphicsEffect(shadow)

    def show_new_verse(self):
        if self._mode == "daily":
            ref, text = get_verse_of_the_day()
        else:
            ref, text = get_random_passage()
        self.ref_label.setText(ref)
        self.verse_label.setText(text)
        self._quote_count += 1
        self._fit_text_size()
        if self._verbose:
            self._print_stats()

    def _print_stats(self):
        """Print a stats-for-nerds banner to the terminal."""
        now = datetime.datetime.now()
        uptime = now - self._start_time
        total_seconds = int(uptime.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        # Calculate next refresh time
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
        """Adjust font size dynamically based on screen size and verse length."""
        if not self._screen:
            return
        screen_height = self._screen.geometry().height()

        # Base font size proportional to screen (about 1/30th of screen height)
        base_size = max(14, min(60, screen_height // 30))

        # Adjust for verse length
        total_len = len(self.verse_label.text()) + len(self.ref_label.text())

        # Scale factor based on total text length
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

        # Clamp
        size = max(12, min(72, size))

        self.verse_font.setPointSize(size)
        self.verse_label.setFont(self.verse_font)

        ref_size = max(10, min(28, size // 2 + 2))
        self.ref_font.setPointSize(ref_size)
        self.ref_label.setFont(self.ref_font)

        # Adjust window size to fit content
        self.adjustSize()

        # Reposition to anchored center if set
        if self._anchor_pos is not None:
            new_rect = self.frameGeometry()
            new_rect.moveCenter(self._anchor_pos)
            self.move(new_rect.topLeft())

    def resizeEvent(self, event):
        """Apply rounded corners and refit text on resize."""
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
        """Draw the dark glass-morphism backdrop behind the text."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Backdrop extends outward past the text margins for breathing room
        margins = self.layout().contentsMargins()
        rect = self.rect().adjusted(
            margins.left() - 35,
            margins.top() - 25,
            -(margins.right() - 35),
            -(margins.bottom() - 25)
        )

        painter.setBrush(self._backdrop_brush)
        painter.setPen(self._no_pen)

        # Rounded rectangle backdrop
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
    # Write PID file for the stop script
    pid_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "widget.pid")
    with open(pid_path, "w") as f:
        f.write(str(os.getpid()))

    app = QApplication(sys.argv)
    widget = BibleWidget()
    widget.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_widget()