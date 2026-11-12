import os
import logging
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor
from paths import app_path, read_text, write_text

log = logging.getLogger("bible_widget")

VALID_KEYS = (
    "backdrop",
    "text",
    "separator",
    "accent",
    "button_bg",
    "button_border",
    "button_hover",
    "button_pressed",
    "scroll_track",
    "scroll_handle",
    "shadow",
)

DEFAULT_COLORS = {
    "backdrop": QColor(0, 0, 0, 130),
    "text": QColor(255, 255, 255, 255),
    "separator": QColor(180, 180, 180, 120),
    "accent": QColor(100, 149, 237, 200),
    "button_bg": QColor(0, 0, 0, 100),
    "button_border": QColor(255, 255, 255, 100),
    "button_hover": QColor(255, 255, 255, 30),
    "button_pressed": QColor(255, 255, 255, 50),
    "scroll_track": QColor(0, 0, 0, 30),
    "scroll_handle": QColor(255, 255, 255, 80),
    "shadow": QColor(0, 0, 0, 100),
}


def rgba(color):
    """Stylesheet colour that keeps the alpha channel (QColor.name() drops it)."""
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"


def separator_style(color):
    """Stylesheet for a 1px line that fades out at both ends."""
    c = rgba(color)
    return (
        f"border: none; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
        f"stop:0 transparent, stop:0.3 {c}, stop:0.7 {c}, stop:1 transparent);"
    )


def paint_card(painter, rect, backdrop, shadow, radius=16, spread=8, offset=2):
    """Paint the rounded card with a soft drop shadow in one pass.

    QGraphicsDropShadowEffect is not used because on a translucent window it asks
    Windows to update an area larger than the window; that update fails and leaves
    stale, darker pixels behind."""
    rect = QRectF(rect)
    painter.setPen(Qt.NoPen)
    # Stacked layers: the shadow is darkest under the card and fades out over `spread` px
    target = shadow.alphaF() * backdrop.alphaF()
    if target > 0:
        layer = QColor(shadow)
        layer.setAlphaF(1 - (1 - target) ** (1 / spread))
        painter.setBrush(layer)
        for i in range(spread, 0, -1):
            painter.drawRoundedRect(rect.adjusted(-i, -i + offset, i, i + offset), radius + i, radius + i)
    painter.setBrush(backdrop)
    painter.drawRoundedRect(rect, radius, radius)


def _colors_path():
    return app_path("colors.txt")


def _read_all():
    path = _colors_path()
    result = {}
    if not os.path.isfile(path):
        return result
    try:
        for line in read_text(path).splitlines():  # also with a byte order mark, or saved in ANSI
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key in VALID_KEYS:
                result[key] = value
    except OSError:
        pass
    return result


def get_colors():
    stored = _read_all()
    colors = {}
    for key in VALID_KEYS:
        if key in stored:
            c = QColor(stored[key])
            if c.isValid():
                colors[key] = c
                continue
        colors[key] = QColor(DEFAULT_COLORS[key])
    return colors


def set_color(key, color):
    if key not in VALID_KEYS:
        raise ValueError(f"Invalid color key: {key}")
    entry = f"{key}={color.name(QColor.NameFormat.HexArgb)}"
    path = _colors_path()
    try:
        lines = read_text(path).splitlines()  # kept as written, even if saved in ANSI
    except OSError:
        lines = []
    # Replace this colour's line and keep every other line (comments, other colours) as it was
    out, replaced = [], False
    for line in lines:
        if not line.strip().startswith("#") and "=" in line and line.partition("=")[0].strip() == key:
            if not replaced:
                out.append(entry)
                replaced = True
            continue
        out.append(line)
    if not replaced:
        out.append(entry)
    try:
        write_text(path, "\n".join(out) + "\n")
    except OSError:
        log.warning("Could not save %s", path, exc_info=True)


