import sys
import struct
from PySide6.QtCore import Qt, QRectF, QPointF, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap, QRadialGradient

# Windows asks the tray for 16px at 100% scaling, 20 at 125%, 24 at 150%, 32 at 200% and so on
TRAY_SIZES = (16, 20, 24, 32, 40, 48, 64)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

CROSS_COLOR = QColor(255, 255, 255)
GLOW_COLOR = QColor(0xFF, 0xD2, 0x7A)
GLOW_ALPHA = 0.34  # at the centre; fades to nothing at the edge of the icon
EDGE_COLOR = QColor(0, 0, 0, 150)  # outline that keeps the white cross visible on a light taskbar

_PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def _px(value):
    """Round half up to a whole pixel (round() would send 2.5 to 2)."""
    return int(value + 0.5)


def _cross_rects(size):
    """The upright and the crossbar as rectangles on whole pixels, so straight edges stay sharp."""
    width = max(2, _px(size / 8))
    margin = max(1, _px(size / 16))
    height = size - 2 * margin
    left = (size - width) // 2
    upright = QRectF(left, margin, width, height)
    # Arms span about 60% of the height, the same reach on both sides of the upright
    reach = max(2, _px((height * 0.6 - width) / 2))
    bar_top = margin + _px(height / 3 - width / 2)
    crossbar = QRectF(left - reach, bar_top, width + 2 * reach, width)
    return upright, crossbar


def _paint_glow(painter, size, crossbar):
    """Faint warm light behind the cross, centred between the crossing and the middle of the icon."""
    cx = size / 2
    cy = (crossbar.center().y() + size / 2) / 2
    radius = min(cy, size - cy, cx)
    gradient = QRadialGradient(QPointF(cx, cy), radius)
    for stop, strength in ((0.0, 1.0), (0.45, 0.5), (1.0, 0.0)):
        c = QColor(GLOW_COLOR)
        c.setAlphaF(GLOW_ALPHA * strength)
        gradient.setColorAt(stop, c)
    painter.setPen(Qt.NoPen)
    painter.setBrush(gradient)
    painter.drawEllipse(QPointF(cx, cy), radius, radius)


def render_cross(size, light_taskbar=False):
    """One hand-drawn image of the tray cross at exactly `size` x `size` pixels."""
    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    upright, crossbar = _cross_rects(size)
    _paint_glow(painter, size, crossbar)
    # Fully rounded ends; a 2px stroke is too thin to show a curve, rounding would only blur its tips
    radius = upright.width() / 2 if upright.width() >= 3 else 0
    painter.setPen(Qt.NoPen)
    if light_taskbar:
        edge = max(1, _px(size / 24))
        painter.setBrush(EDGE_COLOR)
        for rect in (upright, crossbar):
            grown = rect.adjusted(-edge, -edge, edge, edge)
            painter.drawRoundedRect(grown, radius + edge, radius + edge)
    # Both edges go down before either fill, so no edge is drawn across the white
    painter.setBrush(CROSS_COLOR)
    for rect in (upright, crossbar):
        painter.drawRoundedRect(rect, radius, radius)
    painter.end()
    return image


def taskbar_is_light():
    """True when Windows draws the taskbar in its light theme."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PERSONALIZE_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
        return bool(value)
    except (ImportError, OSError, ValueError):
        return False


def make_tray_icon(light_taskbar=None):
    """Tray icon with a separate crisp pixmap for every size Windows may ask for."""
    if light_taskbar is None:
        light_taskbar = taskbar_is_light()
    icon = QIcon()
    for size in TRAY_SIZES:
        icon.addPixmap(QPixmap.fromImage(render_cross(size, light_taskbar)))
    return icon


def _png_bytes(image):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def write_ico(path):
    """Write a multi-size .ico of the cross (dark taskbar look) for the app icon.

    Qt's ico plugin only writes one image per file, so the container is built here
    with PNG-compressed entries, which Windows has read since Vista."""
    entries = [(size, _png_bytes(render_cross(size))) for size in ICO_SIZES]
    offset = 6 + 16 * len(entries)
    header = struct.pack("<HHH", 0, 1, len(entries))
    directory = b""
    for size, png in entries:
        side = 0 if size >= 256 else size  # 0 means 256 in an icon directory
        directory += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
    with open(path, "wb") as f:
        f.write(header + directory + b"".join(png for _, png in entries))
