"""Prayer window widget: displays a prayer with scrollable text and an Amen button."""

import os
import json
import html
import unicodedata
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame, QScrollArea,
    QGraphicsDropShadowEffect, QApplication
)
from PySide6.QtGui import QFont, QPainter, QBrush, QPen, QColor
from PySide6.QtCore import Qt
from colors import get_colors, rgba, separator_style
from bible_loader import clean_text, localize_reference
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


def get_prayer(prayer_id, translation_abbr, lang="en"):
    """Load a prayer by ID for a given translation.
    Returns (name, reference, text, translation_used) or None if the prayer doesn't exist."""
    for prayer in get_prayers_list():
        if prayer.get("id") != prayer_id:
            continue
        name = get_string(prayer.get("name", "Prayer"), lang)
        reference = prayer.get("reference", "")
        translations = prayer.get("translations", {})
        # Prefer the chosen translation, then one in the same language, then KJV
        prefix = translation_abbr.split("_")[0] + "_"
        candidates = [translation_abbr]
        candidates += [a for a in translations if a.startswith(prefix)]
        candidates += ["en_kjv"] + list(translations)
        for abbr in candidates:
            text = translations.get(abbr)
            if text:
                return name, localize_reference(reference, abbr), clean_text(text, abbr), abbr
        return name, reference, None, None
    return None


def get_prayer_text(prayer_id, translation_abbr, lang="en"):
    """Returns (title, text) or (None, None) if not found."""
    prayer = get_prayer(prayer_id, translation_abbr, lang)
    if prayer is None:
        return None, None
    name, reference, text, _ = prayer
    title = f"{name} ({reference})" if reference and reference not in name else name
    return title, text


def _is_rtl(text):
    for ch in text:
        direction = unicodedata.bidirectional(ch)
        if direction in ("R", "AL"):
            return True
        if direction == "L":
            return False
    return False


class PrayerWindow(QWidget):
    def __init__(self, translation_abbr=None, prayer_id="lords-prayer", lang="en"):
        super().__init__()
        self._translation_abbr = translation_abbr or "en_kjv"
        self._prayer_id = prayer_id
        self._lang = lang
        self._prayers_list = get_prayers_list()
        self._placed = False

        self.setWindowTitle("Prayer")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._drag_pos = None
        self._no_pen = QPen(Qt.NoPen)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

        self._setup_ui()
        self._apply_colors()
        self._load_current_prayer()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        # The card is drawn inset by (15, 10) to leave room for the shadow
        layout.setContentsMargins(50, 38, 50, 34)
        layout.setSpacing(0)

        self.ref_label = QLabel()
        ref_font = QFont("Segoe UI", 9)
        ref_font.setWeight(QFont.DemiBold)
        ref_font.setCapitalization(QFont.AllUppercase)
        ref_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        self.ref_label.setFont(ref_font)
        self.ref_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.ref_label)
        layout.addSpacing(6)

        self.title_label = QLabel()
        title_font = QFont("Segoe UI", 17)
        title_font.setWeight(QFont.DemiBold)
        self.title_label.setFont(title_font)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        layout.addSpacing(16)

        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.HLine)
        self.separator.setFixedHeight(1)
        layout.addWidget(self.separator)
        layout.addSpacing(18)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.viewport().setAutoFillBackground(False)

        self.text_label = QLabel()
        self.text_label.setFont(QFont("Segoe UI", 13))
        self.text_label.setTextFormat(Qt.RichText)
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.text_label.setContentsMargins(4, 0, 4, 0)
        self.text_label.setAutoFillBackground(False)
        self.text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.scroll_area.setWidget(self.text_label)
        layout.addWidget(self.scroll_area)
        layout.addSpacing(22)

        nav = QHBoxLayout()
        nav.setSpacing(14)
        nav.addStretch(1)
        self.prev_button = QPushButton("‹")
        self.prev_button.setFixedSize(40, 40)
        self.prev_button.clicked.connect(self._prev_prayer)
        nav.addWidget(self.prev_button)

        self.amen_button = QPushButton(get_string("Amen", self._lang))
        self.amen_button.setFixedHeight(40)
        self.amen_button.setMinimumWidth(128)
        self.amen_button.clicked.connect(self.close)
        nav.addWidget(self.amen_button)

        self.next_button = QPushButton("›")
        self.next_button.setFixedSize(40, 40)
        self.next_button.clicked.connect(self._next_prayer)
        nav.addWidget(self.next_button)
        nav.addStretch(1)
        layout.addLayout(nav)

        for button in (self.prev_button, self.amen_button, self.next_button):
            button.setCursor(Qt.PointingHandCursor)
            button.setFocusPolicy(Qt.NoFocus)

    def _apply_colors(self):
        self._colors = get_colors()
        self._backdrop_brush = QBrush(self._colors["backdrop"])
        text = self._colors["text"]
        muted = QColor(text)
        muted.setAlphaF(text.alphaF() * 0.65)

        self.ref_label.setStyleSheet(f"color: {rgba(muted)};")
        self.title_label.setStyleSheet(f"color: {rgba(text)};")
        self.text_label.setStyleSheet(f"color: {rgba(text)}; background: transparent;")
        self.separator.setStyleSheet(separator_style(self._colors["separator"]))
        self.scroll_area.setStyleSheet(f"""
            QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                width: 6px; margin: 2px 0 2px 6px; background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: {rgba(self._colors["scroll_handle"])}; border-radius: 3px; min-height: 24px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)

        button_css = f"""
            QPushButton {{
                color: {rgba(text)};
                background-color: {rgba(self._colors["button_bg"])};
                border: 1px solid {rgba(self._colors["button_border"])};
                border-radius: 20px;
                font-family: "Segoe UI";
                padding: 0 22px;
            }}
            QPushButton:hover {{ background-color: {rgba(self._colors["button_hover"])}; }}
            QPushButton:pressed {{ background-color: {rgba(self._colors["button_pressed"])}; }}
        """
        self.amen_button.setStyleSheet(button_css + "QPushButton { font-size: 12pt; font-weight: 600; }")
        for button in (self.prev_button, self.next_button):
            button.setStyleSheet(button_css + "QPushButton { font-size: 18pt; padding: 0 0 4px 0; }")

        shadow = self.graphicsEffect()
        if isinstance(shadow, QGraphicsDropShadowEffect):
            shadow.setColor(self._colors["shadow"])
        self.update()

    # ----- Prayer navigation -----

    def _find_current_index(self):
        """Find the index of the current prayer in the prayers list."""
        for i, p in enumerate(self._prayers_list):
            if p.get("id") == self._prayer_id:
                return i
        return 0

    def _load_by_index(self, index):
        """Load prayer at the given index."""
        if 0 <= index < len(self._prayers_list):
            self._prayer_id = self._prayers_list[index].get("id", "lords-prayer")
            self._load_current_prayer()

    def _prev_prayer(self):
        if self._prayers_list:
            self._load_by_index((self._find_current_index() - 1) % len(self._prayers_list))

    def _next_prayer(self):
        if self._prayers_list:
            self._load_by_index((self._find_current_index() + 1) % len(self._prayers_list))

    def _load_current_prayer(self):
        prayer = get_prayer(self._prayer_id, self._translation_abbr, self._lang)
        if prayer is None or prayer[2] is None:
            self.ref_label.setText("")
            self.title_label.setText(get_string("Prayer not available", self._lang))
            self.text_label.setText("")
        else:
            name, reference, text, _ = prayer
            self.ref_label.setText(reference if reference != name else "")
            self.ref_label.setVisible(reference != name)
            self.title_label.setText(name)
            rtl = _is_rtl(text)
            self.text_label.setLayoutDirection(Qt.RightToLeft if rtl else Qt.LeftToRight)
            align = "right" if rtl else "left"
            self.text_label.setText(
                f'<div style="line-height: 150%; text-align: {align};">{html.escape(text)}</div>'
            )
        self.scroll_area.verticalScrollBar().setValue(0)
        self._fit_window()

    # ----- Sizing and placement -----

    def _fit_window(self):
        """Fixed width; height follows the text up to 70% of the screen, after which it scrolls."""
        screen = self.screen() or QApplication.primaryScreen()
        avail = screen.availableGeometry()
        width = int(min(600, max(440, avail.width() * 0.27)))
        layout = self.layout()
        m = layout.contentsMargins()
        inner = width - m.left() - m.right()

        self.title_label.setFixedWidth(inner)
        text_h = self.text_label.heightForWidth(inner)
        chrome = (
            m.top() + m.bottom()
            + (self.ref_label.sizeHint().height() + 6 if self.ref_label.isVisibleTo(self) else 0)
            + self.title_label.heightForWidth(inner)
            + 16 + 1 + 18 + 22 + 40
        )
        max_text = max(120, int(avail.height() * 0.7) - chrome)
        self.scroll_area.setFixedHeight(min(text_h, max_text) + 2)
        self.setFixedSize(width, chrome + self.scroll_area.height())
        if self._placed:
            self._clamp_to_screen()

    def _clamp_to_screen(self):
        screen = self.screen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = max(geo.x(), min(self.x(), geo.x() + geo.width() - self.width()))
        y = max(geo.y(), min(self.y(), geo.y() + geo.height() - self.height()))
        self.move(x, y)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._placed:
            self._placed = True
            self._fit_window()
            geo = (self.screen() or QApplication.primaryScreen()).availableGeometry()
            self.move(geo.center() - self.rect().center())
            self.activateWindow()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self._backdrop_brush)
        painter.setPen(self._no_pen)
        painter.drawRoundedRect(self.rect().adjusted(15, 10, -15, -10), 16, 16)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_Left:
            self._prev_prayer()
        elif event.key() == Qt.Key_Right:
            self._next_prayer()
        else:
            super().keyPressEvent(event)

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
    app = QApplication(sys.argv)
    w = PrayerWindow("en_kjv", "lords-prayer")
    w.show()
    sys.exit(app.exec())
