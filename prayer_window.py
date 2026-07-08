"""Prayer window widget — displays a prayer with scrollable text and an Amen button."""

import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame, QScrollArea, QSizePolicy
)
from PySide6.QtGui import (
    QFont, QPainter, QColor, QBrush, QPen
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication


def get_prayers_list():
    """Return the list of available prayers from prayers.json."""
    prayers_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "prayers", "prayers.json"
    )
    try:
        with open(prayers_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data.get("prayers", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def get_prayer_text(prayer_id, translation_abbr):
    """Load a specific prayer text by ID for a given translation.
    Returns (title, text) or (None, None) if not found."""
    prayers = get_prayers_list()
    for prayer in prayers:
        if prayer.get("id") == prayer_id:
            name = prayer.get("name", "Prayer")
            reference = prayer.get("reference", "")
            title = f"{name} — {reference}" if reference else name
            translations = prayer.get("translations", {})
            text = translations.get(translation_abbr)
            if text:
                return title, text
            # Fall back to first available translation
            for t in translations.values():
                return title, t
            return title, None
    return None, None


class PrayerWindow(QWidget):
    def __init__(self, translation_abbr=None, prayer_id="lords-prayer"):
        super().__init__()
        self._translation_abbr = translation_abbr or "en_kjv"
        self._prayer_id = prayer_id
        self._prayers_list = get_prayers_list()
        
        self.setWindowTitle("Prayer")
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._drag_pos = None
        self._fitting = False
        self._backdrop_brush = QBrush(QColor(0, 0, 0, 130))
        self._no_pen = QPen(Qt.NoPen)

        # Fonts
        title_font = QFont("Calibri", 16)
        title_font.setWeight(QFont.DemiBold)
        text_font = QFont("Calibri", 20)

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(45, 30, 45, 30)
        layout.setSpacing(12)

        # Title
        self.title_label = QLabel()
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet("color: white;")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: rgba(180, 180, 180, 120);")
        separator.setFixedHeight(1)
        layout.addWidget(separator)

        # Scrollable prayer text area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                width: 8px;
                background: rgba(0, 0, 0, 30);
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 80);
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        self.text_label = QLabel()
        self.text_label.setFont(text_font)
        self.text_label.setStyleSheet("color: white; background: transparent;")
        self.text_label.setAlignment(Qt.AlignTop)
        self.text_label.setWordWrap(True)
        self.scroll_area.setWidget(self.text_label)
        layout.addWidget(self.scroll_area)

        # Navigation + Amen button layout
        nav_button_layout = QHBoxLayout()
        nav_button_layout.setAlignment(Qt.AlignCenter)
        nav_button_layout.setSpacing(15)

        # Previous prayer button
        self.prev_button = QPushButton("◀")
        self.prev_button.setFixedSize(50, 40)
        self.prev_button.setStyleSheet("""
            QPushButton {
                color: white;
                background-color: rgba(0, 0, 0, 100);
                border: 1px solid rgba(255, 255, 255, 100);
                border-radius: 8px;
                font-size: 16pt;
                font-family: Calibri;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 30);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 50);
            }
        """)
        self.prev_button.clicked.connect(self._prev_prayer)
        nav_button_layout.addWidget(self.prev_button)

        # Amen button
        self.amen_button = QPushButton("Amen")
        self.amen_button.setFixedSize(100, 40)
        self.amen_button.setStyleSheet("""
            QPushButton {
                color: white;
                background-color: rgba(0, 0, 0, 100);
                border: 1px solid rgba(255, 255, 255, 100);
                border-radius: 8px;
                font-size: 14pt;
                font-family: Calibri;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 30);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 50);
            }
        """)
        self.amen_button.clicked.connect(self.close)
        nav_button_layout.addWidget(self.amen_button)

        # Next prayer button
        self.next_button = QPushButton("▶")
        self.next_button.setFixedSize(50, 40)
        self.next_button.setStyleSheet("""
            QPushButton {
                color: white;
                background-color: rgba(0, 0, 0, 100);
                border: 1px solid rgba(255, 255, 255, 100);
                border-radius: 8px;
                font-size: 16pt;
                font-family: Calibri;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 30);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 50);
            }
        """)
        self.next_button.clicked.connect(self._next_prayer)
        nav_button_layout.addWidget(self.next_button)

        layout.addLayout(nav_button_layout)

        # Size (set before loading so the text wraps to the correct width)
        scr = QApplication.primaryScreen()
        if scr:
            geom = scr.geometry()
            self.resize(int(geom.width() * 0.32), int(geom.height() * 0.5))

        # Load the prayer
        self._fit_window()
        self._load_current_prayer()

    def _find_current_index(self):
        """Find the index of the current prayer in the prayers list."""
        for i, p in enumerate(self._prayers_list):
            if p.get("id") == self._prayer_id:
                return i
        return 0

    def _load_by_index(self, index):
        """Load prayer at the given index."""
        if 0 <= index < len(self._prayers_list):
            prayer = self._prayers_list[index]
            self._prayer_id = prayer.get("id", "lords-prayer")
            self._load_current_prayer()

    def _prev_prayer(self):
        idx = self._find_current_index()
        self._load_by_index((idx - 1) % len(self._prayers_list))

    def _next_prayer(self):
        idx = self._find_current_index()
        self._load_by_index((idx + 1) % len(self._prayers_list))

    def _load_current_prayer(self):
        title, text = get_prayer_text(self._prayer_id, self._translation_abbr)
        if title and text:
            self.title_label.setText(title)
            self.text_label.setText(text)
        else:
            self.title_label.setText("Prayer not available")
            self.text_label.setText("No prayer text found for the selected translation.")
        QTimer.singleShot(50, self._fit_window)

    def _fit_window(self):
        """Resize the window and the scroll area to fit the content. The label
        gets its full wrapped height; the scroll area gets only the visible
        text area (capped), so long prayers scroll and short prayers are snug.
        Both heights are set explicitly so the layout can't overflow and clip
        the buttons."""
        if self._fitting:
            return
        self._fitting = True

        fw = max(50, self.width() - 90)
        self.text_label.setFixedWidth(fw)
        fm = self.text_label.fontMetrics()
        rect = fm.boundingRect(
            0, 0, fw, 9999, Qt.TextWordWrap, self.text_label.text()
        )
        text_natural = rect.height()
        self.text_label.setFixedHeight(text_natural)

        scr = QApplication.primaryScreen()
        max_h = int(scr.geometry().height() * 0.5) if scr else 600
        margins = self.layout().contentsMargins()
        spacing = self.layout().spacing()
        btn_h = 40 + spacing
        chrome = (
            margins.top()
            + self.title_label.height()
            + spacing
            + 1
            + spacing
            + spacing
            + btn_h
            + margins.bottom()
        )
        avail_for_text = max(50, max_h - chrome)
        text_area = min(text_natural, avail_for_text)
        self.scroll_area.setFixedHeight(text_area)
        new_h = max(150, min(chrome + text_area, max_h))
        self.resize(self.width(), new_h)

        self._fitting = False

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_window()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_window()

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


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    w = PrayerWindow("en_kjv", "lords-prayer")
    w.show()
    sys.exit(app.exec())