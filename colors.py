import os
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor

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
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "colors.txt")


def _read_all():
    path = _colors_path()
    result = {}
    if not os.path.isfile(path):
        return result
    try:
        with open(path, "r") as f:
            for line in f:
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
    stored = _read_all()
    stored[key] = color.name(QColor.NameFormat.HexArgb)
    try:
        with open(_colors_path(), "w") as f:
            for k, v in stored.items():
                f.write(f"{k}={v}\n")
    except OSError:
        pass


def reset_colors():
    path = _colors_path()
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass
