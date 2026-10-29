import os
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
