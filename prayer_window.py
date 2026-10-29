"""Prayer window widget: displays a prayer with scrollable text and an Amen button."""

import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame, QScrollArea, QSizePolicy, QGraphicsDropShadowEffect
)
from PySide6.QtGui import (
    QFont, QPainter, QColor, QBrush, QPen
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication
from colors import get_colors
from bible_loader import clean_text
from menu_strings import get_string


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


def get_prayer_text(prayer_id, translation_abbr, lang="en"):
    """Load a specific prayer text by ID for a given translation.
    Returns (title, text) or (None, None) if not found."""
    prayers = get_prayers_list()
    for prayer in prayers:
        if prayer.get("id") == prayer_id:
            name = get_string(prayer.get("name", "Prayer"), lang)
            reference = prayer.get("reference", "")
            title = f"{name} ({reference})" if reference and reference not in name else name
            translations = prayer.get("translations", {})
            # Prefer the chosen translation, then one in the same language, then KJV
            prefix = translation_abbr.split("_")[0] + "_"
            candidates = [translation_abbr]
            candidates += [a for a in translations if a.startswith(prefix)]
            candidates += ["en_kjv"] + list(translations)
            for abbr in candidates:
                text = translations.get(abbr)
                if text:
                    return title, clean_text(text, abbr)
            return title, None
    return None, None


class PrayerWindow(QWidget):
    def __init__(self, translation_abbr=None, prayer_id="lords-prayer", lang="en"):
        super().__init__()
        self._translation_abbr = translation_abbr or "en_kjv"
        self._prayer_id = prayer_id
        self._lang = lang
        self._prayers_list = get_prayers_list()
        
        self.setWindowTitle("Prayer")
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._drag_pos = None
        self._fitting = False

        self._colors = get_colors()
        self._backdrop_brush = QBrush(self._colors["backdrop"])
        self._text_color = self._colors["text"]
        self._separator_color = self._colors["separator"]
        self._button_bg_color = self._colors["button_bg"]
        self._button_border_color = self._colors["button_border"]
        self._button_hover_color = self._colors["button_hover"]
        self._button_pressed_color = self._colors["button_pressed"]
        self._scroll_track_color = self._colors["scroll_track"]
        self._scroll_handle_color = self._colors["scroll_handle"]
        self._no_pen = QPen(Qt.NoPen)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(self._colors["shadow"])
        self.setGraphicsEffect(shadow)

        self._setup_ui()
        self._load_current_prayer()

    def _setup_ui(self):
        title_font = QFont("Segoe UI", 16)
        title_font.setWeight(QFont.DemiBold)
        text_font = QFont("Segoe UI", 20)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 35, 50, 35)
        layout.setSpacing(12)

        accent = QFrame()
        accent.setObjectName("accent_bar")
        accent.setFrameShape(QFrame.HLine)
        accent.setStyleSheet(f"background-color: {self._color_to_rgba(self._colors['accent'])};")
        accent.setFixedHeight(2)
        layout.addWidget(accent)

        self.title_label = QLabel()
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet(f"color: {self._color_to_rgba(self._text_color)};")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet(f"background-color: {self._color_to_rgba(self._separator_color)};")
        separator.setFixedHeight(1)
        layout.addWidget(separator)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self._apply_scrollbar_stylesheet()

        self.text_label = QLabel()
        self.text_label.setFont(text_font)
        self.text_label.setStyleSheet(
            f"color: {self._color_to_rgba(self._text_color)}; background: transparent;"
            f"border: 1px solid {self._color_to_rgba(self._separator_color)};"
            f"border-radius: 4px; padding: 4px;"
        )
        self.text_label.setAlignment(Qt.AlignTop)
        self.text_label.setWordWrap(True)
        self.scroll_area.setWidget(self.text_label)
        layout.addWidget(self.scroll_area)

        nav_button_layout = QHBoxLayout()
        nav_button_layout.setAlignment(Qt.AlignCenter)
        nav_button_layout.setSpacing(15)

        self.prev_button = QPushButton("◀")
        self.prev_button.setFixedSize(60, 44)
        self._apply_button_stylesheet(self.prev_button)
        self.prev_button.clicked.connect(self._prev_prayer)
        nav_button_layout.addWidget(self.prev_button)

        self.amen_button = QPushButton(get_string("Amen", self._lang))
        self.amen_button.setMinimumSize(60, 44)
        self.amen_button.setFixedHeight(44)
        self._apply_button_stylesheet(self.amen_button)
        self.amen_button.clicked.connect(self.close)
        nav_button_layout.addWidget(self.amen_button)

        self.next_button = QPushButton("▶")
        self.next_button.setFixedSize(60, 44)
        self._apply_button_stylesheet(self.next_button)
        self.next_button.clicked.connect(self._next_prayer)
        nav_button_layout.addWidget(self.next_button)

        layout.addLayout(nav_button_layout)

        scr = QApplication.primaryScreen()
        if scr:
            geom = scr.geometry()
            self.resize(int(geom.width() * 0.32), int(geom.height() * 0.5))
        self._fixed_size = self.size()

    def _clamp_to_screen(self):
        screen = self.screen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = max(geo.x(), min(self.x(), geo.x() + geo.width() - self.width()))
        y = max(geo.y(), min(self.y(), geo.y() + geo.height() - self.height()))
        self.move(x, y)

    def _color_to_rgba(self, color):
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"

    def _apply_scrollbar_stylesheet(self):
        track = self._color_to_rgba(self._scroll_track_color)
        handle = self._color_to_rgba(self._scroll_handle_color)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                width: 8px;
                background: {track};
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {handle};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

    def _apply_button_stylesheet(self, button):
        bg = self._color_to_rgba(self._button_bg_color)
        border = self._color_to_rgba(self._button_border_color)
        hover = self._color_to_rgba(self._button_hover_color)
        pressed = self._color_to_rgba(self._button_pressed_color)
        text = self._color_to_rgba(self._text_color)
        button.setStyleSheet(f"""
            QPushButton {{
                color: {text};
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 20px;
                font-size: 14pt;
                font-family: Segoe UI;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:pressed {{
                background-color: {pressed};
            }}
        """)

    def _apply_colors(self):
        self._colors = get_colors()
        self._backdrop_brush = QBrush(self._colors["backdrop"])
        self._text_color = self._colors["text"]
        self._separator_color = self._colors["separator"]
        self._button_bg_color = self._colors["button_bg"]
        self._button_border_color = self._colors["button_border"]
        self._button_hover_color = self._colors["button_hover"]
        self._button_pressed_color = self._colors["button_pressed"]
        self._scroll_track_color = self._colors["scroll_track"]
        self._scroll_handle_color = self._colors["scroll_handle"]

        self.title_label.setStyleSheet(f"color: {self._color_to_rgba(self._text_color)};")
        self.text_label.setStyleSheet(
            f"color: {self._color_to_rgba(self._text_color)}; background: transparent;"
            f"border: 1px solid {self._color_to_rgba(self._separator_color)};"
            f"border-radius: 4px; padding: 4px;"
        )
        for child in self.findChildren(QFrame):
            if child.frameShape() == QFrame.HLine and child.objectName() != "accent_bar":
                child.setStyleSheet(f"background-color: {self._color_to_rgba(self._separator_color)};")
            elif child.objectName() == "accent_bar":
                child.setStyleSheet(f"background-color: {self._color_to_rgba(self._colors['accent'])};")

        shadow = self.graphicsEffect()
        if isinstance(shadow, QGraphicsDropShadowEffect):
            shadow.setColor(self._colors["shadow"])

        self._apply_scrollbar_stylesheet()
        self._apply_button_stylesheet(self.prev_button)
        self._apply_button_stylesheet(self.amen_button)
        self._apply_button_stylesheet(self.next_button)

        self.setStyleSheet("")
        self.update()

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
        title, text = get_prayer_text(self._prayer_id, self._translation_abbr, self._lang)
        if title and text:
            self.title_label.setText(title)
            self.text_label.setText(text)
        else:
            self.title_label.setText(get_string("Prayer not available", self._lang))
            self.text_label.setText("")
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

        fw = max(50, self._fixed_size.width() - 90)
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
        self.resize(self._fixed_size.width(), new_h)
        self._clamp_to_screen()

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
            self._clamp_to_screen()


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    w = PrayerWindow("en_kjv", "lords-prayer")
    w.show()
    sys.exit(app.exec())