"""Prayer window widget — displays a prayer with an Amen button."""

import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame
)
from PySide6.QtGui import (
    QFont, QPainter, QColor, QBrush, QPen, QPainterPath
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication


def get_prayer_text(translation_abbr):
    """Load the prayer text for a given translation abbreviation.
    Returns (title, text) or (None, None) if not found."""
    prayers_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "prayers", "prayers.json"
    )
    try:
        with open(prayers_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        prayers = data.get("prayers", [])
        if not prayers:
            return None, None
        prayer = prayers[0]
        name = prayer.get("name", "Prayer")
        reference = prayer.get("reference", "")
        title = f"{name} — {reference}" if reference else name
        translations = prayer.get("translations", {})
        text = translations.get(translation_abbr)
        if text:
            return title, text
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return None, None


class PrayerWindow(QWidget):
    def __init__(self, translation_abbr=None):
        super().__init__()
        self.setWindowTitle("The Lord's Prayer")
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._drag_pos = None
        self._backdrop_brush = QBrush(QColor(0, 0, 0, 130))
        self._no_pen = QPen(Qt.NoPen)

        # Fonts
        title_font = QFont("Calibri", 16)
        title_font.setWeight(QFont.DemiBold)
        text_font = QFont("Calibri", 20)

        # Layout - labels stretch to fill the full window width
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

        # Prayer text
        self.text_label = QLabel()
        self.text_label.setFont(text_font)
        self.text_label.setStyleSheet("color: white;")
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label)

        # Amen button
        button_layout = QHBoxLayout()
        button_layout.setAlignment(Qt.AlignCenter)
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
        button_layout.addWidget(self.amen_button)
        layout.addLayout(button_layout)

        # Load the prayer
        if translation_abbr:
            self._load_prayer(translation_abbr)

        # Size
        scr = QApplication.primaryScreen()
        if scr:
            geom = scr.geometry()
            self.resize(int(geom.width() * 0.2), int(geom.height() * 0.2))

    def _load_prayer(self, translation_abbr):
        title, text = get_prayer_text(translation_abbr)
        if title and text:
            self.title_label.setText(title)
            self.text_label.setText(text)
        else:
            self.title_label.setText("Prayer not available")
            self.text_label.setText("No prayer text found for the selected translation.")
        QTimer.singleShot(50, self._fit_text)

    def _fit_text(self):
        """Resize window to fit the wrapped prayer text content."""
        self.title_label.updateGeometry()
        self.text_label.updateGeometry()
        self.layout().activate()
        # Use actual label width; fall back to window width minus margins
        fw = self.text_label.width() or max(50, self.width() - 90)
        fm_t = self.title_label.fontMetrics()
        fm_v = self.text_label.fontMetrics()
        t_rect = fm_t.boundingRect(0, 0, fw, 9999, Qt.TextWordWrap, self.title_label.text())
        v_rect = fm_v.boundingRect(0, 0, fw, 9999, Qt.TextWordWrap, self.text_label.text())
        margins = self.layout().contentsMargins()
        spacing = self.layout().spacing()
        btn_h = 40 + spacing
        need_h = margins.top() + t_rect.height() + spacing + 1 + spacing + v_rect.height() + spacing + btn_h + margins.bottom()
        self.setMinimumHeight(max(need_h, 200))
        self.resize(self.width(), max(need_h, self.height()))
        self.layout().activate()

    def resizeEvent(self, event):
        super().resizeEvent(event)

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
    w = PrayerWindow("en_kjv")
    w.show()
    sys.exit(app.exec())