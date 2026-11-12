"""Backgrounds for Save as Image, painted with QPainter only.

Every picture comes from a fresh 256-bit random seed, so no two saved images are alike: one of
seven styles (starry night, aurora, sunrise, ocean, heavenly light, nebula, bokeh), each with
its own random colours, shapes and placement. The same seed and style always paint the same
picture. Bright focal points (sun, moon, light source, nebula core) sit beside the verse card.
"""
import math
import random
import secrets
import colorsys
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QLinearGradient, QRadialGradient, QPainterPath, QPainter, QPen, QImage



def new_seed():
    return secrets.randbits(256)  # a repeat is about 1 in 4x10^38 even if everyone saved every second for a century


def hsv(h, s, v, a=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0, min(1, s)), max(0, min(1, v)))
    return QColor(int(r * 255), int(g * 255), int(b * 255), int(max(0, min(1, a)) * 255))


def mix(c1, c2, t):
    return QColor(*(int(a + (b - a) * t) for a, b in ((c1.red(), c2.red()), (c1.green(), c2.green()),
                                                      (c1.blue(), c2.blue()), (c1.alpha(), c2.alpha()))))


def side_x(rng, w, inner=0.16):
    """An x in the left or right margin, beside the centred card."""
    return w * (rng.uniform(0.04, inner) if rng.random() < 0.5 else rng.uniform(1 - inner, 0.96))


def vertical(p, w, h, stops):
    g = QLinearGradient(0, 0, 0, h)
    for t, c in stops:
        g.setColorAt(t, c)
    p.fillRect(QRectF(0, 0, w, h), g)


def glow(p, x, y, r, color, mode=QPainter.CompositionMode_Screen):
    g = QRadialGradient(QPointF(x, y), r)
    g.setColorAt(0, color)
    edge = QColor(color)
    edge.setAlpha(0)
    g.setColorAt(1, edge)
    p.save()
    p.setCompositionMode(mode)
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(QPointF(x, y), r, r)
    p.restore()


def stars(p, rng, w, h, count, max_y=1.0, sparkle=0.03):
    p.save()
    p.setPen(Qt.NoPen)
    for _ in range(count):
        x, y = rng.uniform(0, w), h * max_y * rng.random() ** 1.3
        r = rng.choice((0.5, 0.7, 0.9, 1.1, 1.4, 1.8))
        warm = rng.random()
        p.setBrush(QColor(255, int(235 + 20 * warm), int(225 + 30 * (1 - warm)),
                          int(255 * rng.uniform(0.3, 1.0) * (1 - 0.6 * y / h))))
        p.drawEllipse(QPointF(x, y), r, r)
        if rng.random() < sparkle:
            glow(p, x, y, r * 9, QColor(255, 255, 255, 70))
            p.setPen(QPen(QColor(255, 255, 255, 110), 0.8))
            s = r * rng.uniform(6, 12)
            p.drawLine(QPointF(x - s, y), QPointF(x + s, y))
            p.drawLine(QPointF(x, y - s), QPointF(x, y + s))
            p.setPen(Qt.NoPen)
    p.restore()


def ridge(p, rng, w, h, base_y, amplitude, roughness, color, jagged=False):
    """A hill or mountain silhouette from layered sine waves, or sharp peaks."""
    path = QPainterPath(QPointF(0, h))
    waves = [(rng.uniform(0.5, 3.5), rng.uniform(0, 6.3), rng.uniform(0.3, 1.0)) for _ in range(4)]
    peaks = rng.uniform(7, 15)
    for i in range(201):
        x = w * i / 200
        y = base_y
        for f, ph, a in waves:
            y -= math.sin(x / w * math.pi * 2 * f * roughness + ph) * amplitude * a / 2.2
        if jagged:
            y -= abs(math.sin(x / w * math.pi * peaks + waves[0][1])) ** 1.6 * amplitude * 0.6
        path.lineTo(x, min(y, h))  # never below the base line (for a lake, the shoreline)
    path.lineTo(w, h)
    path.closeSubpath()
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawPath(path)
    p.restore()


def ridges(p, rng, w, h, sky_low, n, top, jagged=False):
    """Layers of hills fading into the haze: far ones take the sky colour, near ones go dark."""
    dark = hsv(rng.random(), 0.45, 0.06)
    for i in range(n):
        t = (i + 1) / n
        base = top + (h - top) * (0.15 + 0.75 * t)
        ridge(p, rng, w, h, base, h * rng.uniform(0.05, 0.13) * (1.2 - t * 0.5), rng.uniform(0.6, 1.6),
              mix(sky_low, dark, 0.35 + 0.65 * t), jagged)


def reflect(p, w, h, horizon, strength):
    """Mirror what is above the horizon into the water below it."""
    device = p.device()
    if not isinstance(device, QImage):
        return
    band = h - horizon
    # A taller slice of sky, squeezed into the water, so the aurora's colour reaches the lake.
    # deviceTransform includes the image's pixel ratio (2 for saved cards); transform() does not.
    sky = min(horizon, band * 2.2)
    src = p.deviceTransform().mapRect(QRectF(0, horizon - sky, w, sky)).toRect().intersected(device.rect())
    if src.isEmpty():
        return
    mirrored = device.copy(src).mirrored(False, True)
    p.save()
    p.setOpacity(strength)
    p.drawImage(QRectF(0, horizon, w, band), mirrored)
    p.restore()


def vignette(p, w, h, strength):
    g = QRadialGradient(QPointF(w / 2, h * 0.45), w * 0.75)
    g.setColorAt(0.55, QColor(0, 0, 0, 0))
    g.setColorAt(1.0, QColor(0, 0, 0, int(255 * strength)))
    p.fillRect(QRectF(0, 0, w, h), g)
    f = QLinearGradient(0, h * 0.82, 0, h)  # keeps the footer area calm and dark
    f.setColorAt(0, QColor(0, 0, 0, 0))
    f.setColorAt(1, QColor(0, 0, 0, 150))
    p.fillRect(QRectF(0, h * 0.82, w, h * 0.18), f)


# ----- Styles -----

def starry_night(p, rng, w, h):
    hue = rng.choice((0.62, 0.66, 0.70, 0.75, 0.55, 0.80, 0.85)) + rng.uniform(-0.03, 0.03)
    top, mid = hsv(hue, 0.85, 0.07), hsv(hue + 0.02, 0.7, rng.uniform(0.18, 0.3))
    low = hsv(hue + rng.uniform(0.15, 0.45), rng.uniform(0.35, 0.6), rng.uniform(0.5, 0.7))
    vertical(p, w, h, ((0, top), (0.55, mid), (1, low)))
    if rng.random() < 0.8:  # Milky Way band
        p.save()
        p.translate(w * rng.uniform(0.2, 0.8), h * rng.uniform(0.15, 0.4))
        p.rotate(rng.uniform(-45, 45))
        band_hue = hue + rng.uniform(-0.1, 0.2)
        for _ in range(45):
            glow(p, rng.gauss(0, w * 0.35), rng.gauss(0, h * 0.045), rng.uniform(40, 130), hsv(band_hue + rng.uniform(-0.05, 0.05), 0.35, 0.95, 0.06))
        p.setPen(Qt.NoPen)
        for _ in range(600):
            p.setBrush(QColor(255, 255, 255, rng.randint(25, 130)))
            p.drawEllipse(QPointF(rng.gauss(0, w * 0.35), rng.gauss(0, h * 0.035)), 0.6, 0.6)
        p.restore()
    stars(p, rng, w, h, rng.randint(200, 450), 0.8, sparkle=0.05)
    if rng.random() < 0.65:  # moon beside the card
        mx, my, mr = side_x(rng, w), rng.uniform(0.1, 0.32) * h, rng.uniform(16, 32)
        glow(p, mx, my, mr * 9, QColor(255, 245, 220, 70))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(250, 246, 232))
        p.drawEllipse(QPointF(mx, my), mr, mr)
        if rng.random() < 0.6:
            p.setBrush(mix(top, mid, min(1, my / h * 1.6)))
            off = mr * rng.uniform(0.35, 0.7)
            p.drawEllipse(QPointF(mx + off * rng.choice((-1, 1)), my - off * 0.3), mr * 0.95, mr * 0.95)
    ridges(p, rng, w, h, low, rng.randint(2, 4), h * 0.62, jagged=rng.random() < 0.4)
    vignette(p, w, h, 0.45)


AURORA_PALETTES = ((0.36, 0.45), (0.36, 0.86), (0.48, 0.75), (0.30, 0.12), (0.80, 0.92), (0.40, 0.55), (0.33, 0.97))


def aurora(p, rng, w, h):
    sky = rng.uniform(0.58, 0.76)
    vertical(p, w, h, ((0, hsv(sky, 0.85, 0.04)), (0.6, hsv(sky - 0.02, 0.7, rng.uniform(0.1, 0.16))),
                       (1, hsv(sky - 0.05, 0.5, rng.uniform(0.16, 0.26)))))
    stars(p, rng, w, h, rng.randint(180, 380), 0.8)
    palette = rng.choice(AURORA_PALETTES)
    lake = rng.random() < 0.55
    horizon = h * rng.uniform(0.66, 0.74)
    p.save()
    p.setCompositionMode(QPainter.CompositionMode_Plus)
    for _ in range(rng.randint(2, 5)):
        hue = rng.choice(palette) + rng.uniform(-0.03, 0.03)
        base = h * rng.uniform(0.22, 0.5)
        amp, freq, ph = h * rng.uniform(0.04, 0.12), rng.uniform(0.6, 2.4), rng.uniform(0, 6.3)
        height = h * rng.uniform(0.2, 0.42)
        bright = rng.uniform(0.11, 0.2)
        ripple = rng.uniform(30, 80)
        for i in range(0, int(w), 2):
            y = base + math.sin(i / w * math.pi * 2 * freq + ph) * amp + math.sin(i / w * 17 + ph) * amp * 0.15
            flicker = 0.45 + 0.55 * math.sin(i / w * ripple + ph) ** 2
            g = QLinearGradient(0, y - height, 0, y + 6)
            g.setColorAt(0, hsv(hue + 0.12, 0.6, 0.9, 0.0))
            g.setColorAt(0.55, hsv(hue + 0.05, 0.75, 0.9, bright * 0.45 * flicker))
            g.setColorAt(0.9, hsv(hue, 0.85, 1.0, bright * flicker))
            g.setColorAt(1, hsv(hue, 0.6, 1.0, 0.0))
            p.fillRect(QRectF(i, y - height, 2, height + 6), g)
    p.restore()
    if lake:
        reflect(p, w, h, horizon, rng.uniform(0.35, 0.55))
        water = QLinearGradient(0, horizon, 0, h)
        water.setColorAt(0, QColor(0, 10, 25, 60))
        water.setColorAt(1, QColor(0, 5, 15, 200))
        p.fillRect(QRectF(0, horizon, w, h - horizon), water)
        ridge(p, rng, w, horizon + 4, horizon - h * 0.02, h * rng.uniform(0.08, 0.16), rng.uniform(0.8, 1.4),
              hsv(sky, 0.5, 0.06), jagged=True)
    else:
        ridges(p, rng, w, h, hsv(sky - 0.05, 0.4, 0.22), rng.randint(2, 3), h * 0.58, jagged=True)
    vignette(p, w, h, 0.5)


def sunrise(p, rng, w, h):
    hue = rng.choice((0.02, 0.06, 0.09, 0.95, 0.90, 0.12))
    top = hsv(rng.choice((0.62, 0.68, 0.75)), 0.55, rng.uniform(0.25, 0.4))
    mid = hsv(hue + rng.uniform(0.86, 0.94), 0.45, 0.65)
    low = hsv(hue, 0.55, 0.95)
    vertical(p, w, h, ((0, top), (0.5, mid), (0.78, low), (1, hsv(hue, 0.35, 0.8))))
    sx, sy = side_x(rng, w, 0.2), h * rng.uniform(0.5, 0.68)
    glow(p, sx, sy, w * rng.uniform(0.35, 0.6), hsv(hue + 0.05, 0.6, 1.0, 0.55))
    glow(p, sx, sy, rng.uniform(80, 130), QColor(255, 240, 210, 200))
    r = rng.uniform(26, 44)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 246, 225))
    p.drawEllipse(QPointF(sx, sy), r, r)
    for _ in range(rng.randint(3, 8)):  # cloud streaks lit from below
        cy, cx, half = h * rng.uniform(0.12, 0.5), w * rng.uniform(0, 1), rng.uniform(150, 380)
        g = QLinearGradient(cx - half, 0, cx + half, 0)
        g.setColorAt(0, hsv(hue, 0.5, 1, 0))
        g.setColorAt(0.5, hsv(hue + 0.97, 0.45, 1, rng.uniform(0.25, 0.5)))
        g.setColorAt(1, hsv(hue, 0.5, 1, 0))
        p.setBrush(g)
        p.drawRoundedRect(QRectF(cx - half, cy, 2 * half, rng.uniform(4, 12)), 6, 6)
    ridges(p, rng, w, h, mix(low, mid, 0.3), rng.randint(3, 5), h * 0.62)
    if rng.random() < 0.5:  # birds, beside the card
        p.setPen(QPen(QColor(30, 20, 40, 170), 1.4))
        bx, by = side_x(rng, w, 0.22), h * rng.uniform(0.15, 0.4)
        for _ in range(rng.randint(3, 8)):
            x, y, s = bx + rng.uniform(-70, 70), by + rng.uniform(-45, 45), rng.uniform(5, 10)
            path = QPainterPath(QPointF(x - s, y))
            path.quadTo(x - s / 2, y - s / 2, x, y)
            path.quadTo(x + s / 2, y - s / 2, x + s, y)
            p.drawPath(path)
    vignette(p, w, h, 0.4)


def ocean(p, rng, w, h):
    night = rng.random() < 0.5
    hue = rng.choice((0.58, 0.62, 0.66, 0.72)) if night else rng.choice((0.03, 0.08, 0.92, 0.97))
    horizon = h * rng.uniform(0.56, 0.66)
    if night:
        vertical(p, w, h, ((0, hsv(hue, 0.8, 0.06)), (horizon / h, hsv(hue, 0.6, rng.uniform(0.22, 0.34))), (1, hsv(hue, 0.8, 0.05))))
        stars(p, rng, w, horizon, rng.randint(150, 320), 0.95)
        light = QColor(240, 240, 255)
    else:
        vertical(p, w, h, ((0, hsv(rng.uniform(0.6, 0.72), 0.5, 0.35)), (horizon / h * 0.9, hsv(hue, 0.55, 0.95)),
                           (horizon / h, hsv(hue + 0.02, 0.4, 1.0)), (1, hsv(0.62, 0.7, 0.15))))
        light = QColor(255, 235, 200)
    lx = side_x(rng, w, 0.2)
    ly = horizon - h * rng.uniform(0.06, 0.28)
    glow(p, lx, ly, w * 0.3, QColor(light.red(), light.green(), light.blue(), 70))
    r = rng.uniform(20, 38)
    p.setPen(Qt.NoPen)
    p.setBrush(light)
    p.drawEllipse(QPointF(lx, ly), r, r)
    sea = QLinearGradient(0, horizon, 0, h)
    sea.setColorAt(0, hsv(hue, 0.6, 0.35 if night else 0.55))
    sea.setColorAt(1, hsv(hue + 0.02, 0.8, 0.06))
    p.fillRect(QRectF(0, horizon, w, h - horizon), sea)
    for _ in range(rng.randint(260, 460)):  # shimmering path of light under the sun or moon
        t = rng.random() ** 0.7
        y = horizon + (h - horizon) * t
        x = lx + rng.gauss(0, (18 + 220 * t) * 0.45)
        length = rng.uniform(8, 40) * (0.3 + t)
        p.setBrush(QColor(light.red(), light.green(), light.blue(), int(200 * (1 - t) * rng.uniform(0.3, 1))))
        p.drawRect(QRectF(x - length / 2, y, length, 1.2 + 2 * t))
    p.setPen(QPen(QColor(255, 255, 255, 22), 1))
    for _ in range(rng.randint(40, 90)):
        y = horizon + (h - horizon) * rng.random() ** 0.8
        x = rng.uniform(0, w)
        p.drawLine(QPointF(x, y), QPointF(x + rng.uniform(30, 160), y))
    vignette(p, w, h, 0.45)


HEAVEN_PALETTES = (
    ("#1f3d6e", "#e9b872", "#fff1d6"),   # golden dawn
    ("#1b4a8a", "#7fb2e8", "#eaf5ff"),   # clear sky
    ("#35285a", "#d98ca6", "#ffe5d8"),   # rose
    ("#20304f", "#9fb7c9", "#f3efe6"),   # silver morning
    ("#2a1f4a", "#b48ad8", "#fbe9ff"),   # lavender
)


def heavenly_light(p, rng, w, h):
    top, mid, low = (QColor(c) for c in rng.choice(HEAVEN_PALETTES))
    vertical(p, w, h, ((0, top), (rng.uniform(0.45, 0.65), mid), (1, low)))
    sx, sy = side_x(rng, w, 0.25), -h * rng.uniform(0.02, 0.12)
    glow(p, sx, sy + h * 0.05, w * rng.uniform(0.4, 0.6), QColor(255, 248, 225, 150))
    p.save()
    p.setCompositionMode(QPainter.CompositionMode_Screen)
    p.setPen(Qt.NoPen)
    toward = math.degrees(math.atan2(h * 0.7 - sy, w / 2 - sx))  # rays fan toward the middle
    for _ in range(rng.randint(10, 18)):
        angle = math.radians(toward + rng.uniform(-38, 38))
        width = math.radians(rng.uniform(1.2, 4.5))
        length = math.hypot(w, h) * 1.2
        poly = QPainterPath(QPointF(sx, sy))
        poly.lineTo(sx + math.cos(angle - width) * length, sy + math.sin(angle - width) * length)
        poly.lineTo(sx + math.cos(angle + width) * length, sy + math.sin(angle + width) * length)
        poly.closeSubpath()
        g = QLinearGradient(sx, sy, sx + math.cos(angle) * length * 0.8, sy + math.sin(angle) * length * 0.8)
        g.setColorAt(0, QColor(255, 250, 230, rng.randint(50, 100)))
        g.setColorAt(1, QColor(255, 250, 230, 0))
        p.setBrush(g)
        p.drawPath(poly)
    p.restore()
    for _ in range(rng.randint(5, 9)):  # cloud banks: flat bottoms, puffy tops, lit from above
        cx, cy, spread = w * rng.uniform(-0.1, 1.1), h * rng.uniform(0.55, 1.0), rng.uniform(90, 200)
        for _ in range(rng.randint(14, 26)):
            r = rng.uniform(30, 95)
            x, y = cx + rng.gauss(0, spread), cy - abs(rng.gauss(0, 30))
            glow(p, x, y + r * 0.2, r * 1.05, QColor(40, 40, 70, 35), QPainter.CompositionMode_SourceOver)
            glow(p, x, y, r, QColor(255, 252, 245, 90), QPainter.CompositionMode_SourceOver)
    vignette(p, w, h, 0.5)


def nebula(p, rng, w, h):
    vertical(p, w, h, ((0, hsv(rng.uniform(0.62, 0.75), 0.7, 0.04)), (1, hsv(rng.uniform(0.68, 0.8), 0.6, 0.07))))
    base = rng.random()
    hues = [base, base + rng.uniform(0.08, 0.2), base + rng.uniform(0.45, 0.55)]
    cx, cy = side_x(rng, w, 0.28), h * rng.uniform(0.25, 0.55)
    angle = rng.uniform(0, math.pi)
    p.save()
    p.setCompositionMode(QPainter.CompositionMode_Plus)
    for _ in range(rng.randint(90, 150)):  # clouds stretched along a random axis
        along, across = rng.gauss(0, w * 0.3), rng.gauss(0, h * 0.12)
        x = cx + along * math.cos(angle) - across * math.sin(angle)
        y = cy + along * math.sin(angle) + across * math.cos(angle)
        hue = rng.choice(hues) + rng.uniform(-0.03, 0.03)
        glow(p, x, y, rng.uniform(40, 200), hsv(hue, rng.uniform(0.55, 0.95), rng.uniform(0.6, 1.0), rng.uniform(0.05, 0.12)),
             QPainter.CompositionMode_Plus)
    glow(p, cx, cy, rng.uniform(80, 140), QColor(255, 240, 230, 120), QPainter.CompositionMode_Plus)  # bright core
    p.restore()
    for _ in range(rng.randint(25, 45)):  # dark dust lanes
        along, across = rng.gauss(0, w * 0.25), rng.gauss(0, h * 0.08)
        x = cx + along * math.cos(angle) - across * math.sin(angle)
        y = cy + along * math.sin(angle) + across * math.cos(angle)
        glow(p, x, y, rng.uniform(30, 110), QColor(4, 2, 10, rng.randint(70, 140)), QPainter.CompositionMode_SourceOver)
    stars(p, rng, w, h, rng.randint(400, 750), 1.0, sparkle=0.07)
    vignette(p, w, h, 0.55)


def bokeh(p, rng, w, h):
    h1 = rng.random()
    h2 = h1 + rng.uniform(0.08, 0.3)
    vertical(p, w, h, ((0, hsv(h1, 0.6, rng.uniform(0.08, 0.16))), (1, hsv(h2, 0.7, rng.uniform(0.22, 0.36)))))
    for _ in range(rng.randint(35, 80)):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        r = rng.choice((rng.uniform(8, 26), rng.uniform(26, 95)))
        c = hsv(rng.choice((h1, h2, h2 + 0.1, 0.12)), rng.uniform(0.3, 0.7), 1.0, rng.uniform(0.06, 0.22))
        g = QRadialGradient(QPointF(x, y), r)
        g.setColorAt(0, c)
        g.setColorAt(0.85, c)
        rim = QColor(c)
        rim.setAlpha(min(255, c.alpha() + 40))
        g.setColorAt(0.95, rim)
        g.setColorAt(1, QColor(c.red(), c.green(), c.blue(), 0))
        p.save()
        p.setCompositionMode(QPainter.CompositionMode_Screen)
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(x, y), r, r)
        p.restore()
    vignette(p, w, h, 0.5)


PAINTERS = {"starry_night": starry_night, "aurora": aurora, "sunrise": sunrise, "ocean": ocean,
            "heavenly_light": heavenly_light, "nebula": nebula, "bokeh": bokeh}
STYLES = tuple(PAINTERS)


def paint_background(p, w, h, seed=None, style=None):
    """Paint a background; returns (style, seed). The same seed and style give the same picture."""
    seed = new_seed() if seed is None else seed
    rng = random.Random(seed)
    chosen = rng.choice(STYLES)  # always drawn, so a given style repaints exactly what it painted
    style = style or chosen
    p.save()
    PAINTERS[style](p, rng, w, h)
    p.restore()
    return style, seed
