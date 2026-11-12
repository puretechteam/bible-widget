"""Render the current verse as a shareable card image, save it and copy it.

The card copies the widget's look (see widget_window._setup_ui, _set_passage and
_apply_label_styles) at CARD_SCALE times its size, on a background from backgrounds.py
that is different for every image. Text is measured and drawn with the same
QTextDocument, so the fit check and the pixels can never disagree.
"""
import os
import datetime
from types import SimpleNamespace

from PySide6.QtCore import Qt, QRectF, QStandardPaths
from PySide6.QtGui import (
    QImage, QPainter, QColor, QFont, QLinearGradient, QBrush,
    QTextDocument, QTextOption, QTextCursor, QTextBlockFormat, QTextCharFormat,
    QAbstractTextDocumentLayout, QGuiApplication, QFontMetricsF
)

from colors import paint_card, DEFAULT_COLORS
from backgrounds import paint_background
from verses import is_rtl as _is_rtl

# Same values as widget_window; the card is drawn at CARD_SCALE times the widget's size
REF_GAP, VERSE_GAP = 12, 16
VERSE_LINE_HEIGHT = 120  # percent
CARD_SCALE = 2

WIDTH, HEIGHT, PIXEL_RATIO = 1600, 900, 2
CARD_W = 1040
CARD_MIN_H = 360
PAD_X, PAD_Y = 35 * CARD_SCALE, 24 * CARD_SCALE  # widget margins minus the card inset
TOP_MARGIN = 56
FOOTER_TOP, FOOTER_H = 838, 30  # fixed, in the darkened bottom edge of every background
CARD_GAP = 22  # least space between the card and the footer
MIN_VERSE_PX = 6

BACKGROUND_TRIES = 6  # backgrounds tried for the user's colours, then for the defaults

FOLDER_NAME = "Bible Widget"
_ILLEGAL = set('<>"/\\|?*')


def _verse_font(px, rtl):
    font = QFont("Segoe UI")
    font.setPixelSize(px)
    font.setWeight(QFont.Medium)
    # Spacing would pull apart the joined letters of Arabic script
    font.setLetterSpacing(QFont.AbsoluteSpacing, 0 if rtl else 0.5 * CARD_SCALE)
    return font


def _ref_font(px, rtl):
    font = QFont("Segoe UI")
    font.setPixelSize(px)
    font.setWeight(QFont.DemiBold)
    font.setCapitalization(QFont.AllUppercase)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 0 if rtl else 1.5 * CARD_SCALE)
    return font


def _make_doc(text, font, color, width, device, line_height=None):
    """A centred, wrapped text block laid out for `device`."""
    rtl = _is_rtl(text)
    doc = QTextDocument()
    doc.documentLayout().setPaintDevice(device)
    doc.setDocumentMargin(0)
    doc.setDefaultFont(font)
    option = QTextOption(Qt.AlignHCenter)
    # Break inside a word only when one word is wider than the card, so nothing overflows
    option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    option.setTextDirection(Qt.RightToLeft if rtl else Qt.LeftToRight)
    doc.setDefaultTextOption(option)
    doc.setPlainText(text)

    cursor = QTextCursor(doc)
    cursor.select(QTextCursor.Document)
    block = QTextBlockFormat()
    block.setAlignment(Qt.AlignHCenter)
    block.setLayoutDirection(Qt.RightToLeft if rtl else Qt.LeftToRight)
    if line_height:
        block.setLineHeight(line_height, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
    cursor.mergeBlockFormat(block)
    char = QTextCharFormat()
    char.setForeground(QBrush(color))
    cursor.mergeCharFormat(char)

    doc.setTextWidth(width)
    return doc


def _start_size(length):
    """Starting verse size by passage length, the same steps as the widget."""
    base = 64
    if length > 500:
        return int(base * 0.55)
    if length > 300:
        return int(base * 0.70)
    if length > 200:
        return int(base * 0.85)
    if length > 100:
        return base
    return int(base * 1.15)


def _new_image():
    image = QImage(WIDTH * PIXEL_RATIO, HEIGHT * PIXEL_RATIO, QImage.Format_RGB32)
    image.setDevicePixelRatio(PIXEL_RATIO)
    return image


def card_layout(ref, text, colors, device):
    """Pick font sizes and the card rectangle. Shrinks the fonts until the reference
    and verse fit; `need <= available` holds unless even MIN_VERSE_PX is too big."""
    text_w = CARD_W - 2 * PAD_X
    chrome = 2 * PAD_Y + (REF_GAP + 1 + VERSE_GAP) * CARD_SCALE
    max_card_h = FOOTER_TOP - CARD_GAP - TOP_MARGIN
    available = max_card_h - chrome

    muted = _muted(colors)
    rtl_ref, rtl_text = _is_rtl(ref), _is_rtl(text)

    def measure(px):
        ref_px = max(20, min(32, px // 2))
        ref_doc = _make_doc(ref, _ref_font(ref_px, rtl_ref), muted, text_w, device)
        verse_doc = _make_doc(text, _verse_font(px, rtl_text), colors["text"], text_w, device,
                              VERSE_LINE_HEIGHT)
        return ref_px, ref_doc, verse_doc, ref_doc.size().height() + verse_doc.size().height()

    # The largest size from the start size down that fits, found by halving the range
    # (a long passage used to be measured once per pixel, up to about a second)
    size = _start_size(len(text) + len(ref))
    ref_px, ref_doc, verse_doc, need = measure(size)
    if need > available and size > MIN_VERSE_PX:
        lo, hi, fit = MIN_VERSE_PX, size - 1, None
        while lo <= hi:
            mid = (lo + hi) // 2
            m = measure(mid)
            if m[3] <= available:
                fit, lo = (mid, m), mid + 1
            else:
                hi = mid - 1
        size, (ref_px, ref_doc, verse_doc, need) = fit if fit else (MIN_VERSE_PX, measure(MIN_VERSE_PX))

    card_h = max(CARD_MIN_H, min(max_card_h, chrome + need))
    top = TOP_MARGIN + (max_card_h - card_h) / 2
    card = QRectF((WIDTH - CARD_W) / 2, top, CARD_W, card_h)
    return SimpleNamespace(
        card=card, text_w=text_w, available=available, need=need,
        verse_px=size, ref_px=ref_px, ref_doc=ref_doc, verse_doc=verse_doc,
    )


def _draw_doc(p, doc, x, y):
    p.save()
    p.translate(x, y)
    doc.documentLayout().draw(p, QAbstractTextDocumentLayout.PaintContext())
    p.restore()


MIN_CONTRAST = 4.5  # WCAG AA for normal text: the verse
REF_CONTRAST = 3.0  # WCAG AA for large text: the reference line and the footer


def _muted(colors):
    """The reference line's colour: the verse colour, a little see-through."""
    muted = QColor(colors["text"])
    muted.setAlphaF(colors["text"].alphaF() * 0.65)
    return muted


def _luminance(c):
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * channel(c.red()) + 0.7152 * channel(c.green()) + 0.0722 * channel(c.blue())


def _over(top, bottom):
    a = top.alphaF()
    return QColor(*(round(t * a + b * (1 - a)) for t, b in
                    ((top.red(), bottom.red()), (top.green(), bottom.green()), (top.blue(), bottom.blue()))))


def _contrast(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def card_color(colors, behind):
    """The card's colour as painted on the colour `behind` it: paint_card lays its drop shadow
    under the whole card first (shadow alpha times backdrop alpha, in all), then the backdrop."""
    shadow = QColor(colors["shadow"])
    shadow.setAlphaF(colors["shadow"].alphaF() * colors["backdrop"].alphaF())
    return _over(colors["backdrop"], _over(shadow, behind))


def card_contrast(colors, behind):
    """Contrast between the verse text and the card as it lands on the colour `behind` it."""
    card = card_color(colors, behind)
    return _contrast(_over(colors["text"], card), card)


def _samples(image, rect, columns=32, rows=12):
    """Background colours on a grid across `rect` (logical coordinates)."""
    ratio = image.devicePixelRatio()
    out = []
    for i in range(columns):
        for j in range(rows):
            x = (rect.left() + rect.width() * (i + 0.5) / columns) * ratio
            y = (rect.top() + rect.height() * (j + 0.5) / rows) * ratio
            out.append(image.pixelColor(int(x), int(y)))
    return out


def worst_contrast(colors, behind):
    """The lowest verse-text contrast over all the background colours behind the card."""
    return min(card_contrast(colors, c) for c in behind)


def worst_reference_contrast(colors, behind):
    """The same for the reference line, which is drawn a little see-through."""
    return worst_contrast(dict(colors, text=_muted(colors)), behind)


def _readability(colors, behind):
    """(verse contrast, score): score >= 1 when the verse and the reference both reach their targets."""
    verse = worst_contrast(colors, behind)
    return verse, min(verse / MIN_CONTRAST, worst_reference_contrast(colors, behind) / REF_CONTRAST)


def _default_colors(colors):
    fixed = dict(colors)
    for key in ("text", "backdrop", "separator", "shadow"):
        fixed[key] = QColor(DEFAULT_COLORS[key])
    return fixed


_EXTREMES = [QColor(r, g, b) for r in (0, 255) for g in (0, 255) for b in (0, 255)]


def _never_readable(colors):
    """True when the verse could not reach MIN_CONTRAST on any background. The card's brightness
    is most extreme over pure colours, so checking the corners of the colour cube is enough."""
    return max(card_contrast(colors, c) for c in _EXTREMES) < MIN_CONTRAST


def _paint_readable_background(image, card, colors, seed=None, style=None):
    """Paint backgrounds until the verse (4.5:1) and its reference (3:1) are readable on one.
    The user's colours are kept when one of a few backgrounds suits them; otherwise the default
    colours are used. With a fixed `seed` there is one try per colour set, so the result can fall
    short. Returns (colors, style, seed, verse contrast)."""
    p = QPainter(image)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    try:
        best, best_score = None, -1
        candidates = [colors, _default_colors(colors)]
        if _never_readable(colors):
            del candidates[0]  # no background could help, so do not paint six for nothing
        for candidate in candidates:
            for _ in range(1 if seed is not None else BACKGROUND_TRIES):
                used_style, used_seed = paint_background(p, WIDTH, HEIGHT, seed, style)
                contrast, score = _readability(candidate, _samples(image, card))
                if score >= 1:
                    return candidate, used_style, used_seed, contrast
                if score > best_score:
                    best, best_score = (candidate, used_style, used_seed, contrast), score
        # None reached the targets: paint the most readable one found again
        paint_background(p, WIDTH, HEIGHT, best[2], best[1])
        return best
    finally:
        p.end()


FOOTER_BACKING = QColor(8, 8, 16, 150)


def _footer_color(image, rect):
    """White or near-black footer text, whichever stands out more on the strip behind `rect`.
    Returns (colour, contrast, backing): when neither reaches REF_CONTRAST (bright clouds, say),
    the text goes white on a soft dark pill, and `backing` is that pill's colour."""
    behind = _samples(image, rect, 24, 3)
    light, dark = QColor(255, 255, 255, 190), QColor(12, 12, 20, 200)
    score = lambda c, under: min(_contrast(_over(c, b), b) for b in under)
    color = max((light, dark), key=lambda c: score(c, behind))
    contrast = score(color, behind)
    if contrast >= REF_CONTRAST:
        return color, contrast, None
    backed = [_over(FOOTER_BACKING, b) for b in behind]
    return light, score(light, backed), FOOTER_BACKING


def render_card(ref, text, translation_name, colors, seed=None, style=None):
    """Draw the share card: 1600x900 logical at device pixel ratio 2 (3200x1800 pixels).
    `colors` is the dict from colors.get_colors(). The background is new every time unless a
    `seed` (and `style`) is given; the PNG's "Background" text records which one was used."""
    image = _new_image()
    lay = card_layout(ref, text, colors, image)
    used, style, seed, contrast = _paint_readable_background(image, lay.card, colors, seed, style)
    if used is not colors:  # fell back to the default colours: same sizes, new text colour
        lay = card_layout(ref, text, used, image)
    colors = used
    card = lay.card
    image.setText("Background", f"{style} {seed:064x}")
    image.setText("Contrast", f"{contrast:.1f}")

    p = QPainter(image)
    p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
    paint_card(p, card, colors["backdrop"], colors["shadow"],
               radius=16 * CARD_SCALE, spread=8 * CARD_SCALE, offset=2 * CARD_SCALE)

    # Reference, fading separator and verse, centred in the card like the widget's layout
    content_h = lay.need + (REF_GAP + 1 + VERSE_GAP) * CARD_SCALE
    y = card.top() + (card.height() - content_h) / 2
    x = card.left() + PAD_X
    _draw_doc(p, lay.ref_doc, x, y)
    y += lay.ref_doc.size().height() + REF_GAP * CARD_SCALE

    line = QLinearGradient(x, 0, x + lay.text_w, 0)
    sep = colors["separator"]
    clear = QColor(sep)
    clear.setAlpha(0)
    line.setColorAt(0, clear)
    line.setColorAt(0.3, sep)
    line.setColorAt(0.7, sep)
    line.setColorAt(1, clear)
    p.fillRect(QRectF(x, y, lay.text_w, CARD_SCALE * 0.75), line)
    y += (1 + VERSE_GAP) * CARD_SCALE

    _draw_doc(p, lay.verse_doc, x, y)

    p.end()
    if translation_name:  # the translation's name, small, at the bottom
        font = QFont("Segoe UI")
        font.setPixelSize(17)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 0 if _is_rtl(translation_name) else 1.2)
        text_w = QFontMetricsF(font, image).horizontalAdvance(translation_name)
        pill = QRectF((WIDTH - text_w) / 2 - 16, FOOTER_TOP + 1, text_w + 32, FOOTER_H - 2)
        color, footer_contrast, backing = _footer_color(image, pill)
        image.setText("FooterContrast", f"{footer_contrast:.1f}")
        p = QPainter(image)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        if backing is not None:
            p.setPen(Qt.NoPen)
            p.setBrush(backing)
            p.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
        p.setFont(font)
        p.setPen(color)
        p.drawText(QRectF(0, FOOTER_TOP, WIDTH, FOOTER_H),
                   Qt.AlignHCenter | Qt.AlignVCenter | Qt.TextSingleLine, translation_name)
        p.end()
    return image


def _safe_name(ref):
    name = "".join(
        "." if ch == ":" else ch
        for ch in ref
        if ch not in _ILLEGAL and ord(ch) >= 32
    )
    name = " ".join(name.split())[:100].rstrip(" .")
    # (Windows' reserved names such as CON can't come up: a date and time always follow)
    if not name:
        name = "Verse"
    return name


def save_card(image, ref, folder=None):
    """Save the card as a PNG and return its path. By default the file goes to
    Pictures/Bible Widget; `folder` overrides that (tests pass a temp folder).
    A colon in the reference becomes a dot (John 11.35); other characters Windows
    does not allow in file names are dropped."""
    if folder is None:
        pictures = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)
        folder = os.path.join(pictures or os.path.expanduser("~"), FOLDER_NAME)
    os.makedirs(folder, exist_ok=True)

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H%M%S")
    stem = f"{_safe_name(ref)} {stamp}"
    n = 1
    while True:
        path = os.path.join(folder, f"{stem}.png" if n == 1 else f"{stem} ({n}).png")
        try:
            open(path, "xb").close()  # claim the name, so two saves at once never pick the same file
            break
        except FileExistsError:
            n += 1
    if not image.save(path, "PNG"):
        try:
            os.remove(path)
        except OSError:
            pass
        raise OSError(f"Could not save {path}")
    return path


def copy_to_clipboard(image):
    """Put the card on the system clipboard, ready to paste."""
    QGuiApplication.clipboard().setImage(image)
