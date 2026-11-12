"""Save as Image: every background is new, the text is always readable (WCAG contrast on 140
cards, all 7 styles), the lake reflection, file names, and saving."""
import os
import time
import statistics
from support import Results, TMP, app

R = Results()
qt = app()
from PySide6.QtGui import QColor, QImage, QPainter
import colors
import share_image as si
import bible_loader as bl
from backgrounds import STYLES, reflect

defaults = {k: QColor(c) for k, c in colors.DEFAULT_COLORS.items()}
text = bl._clean_text(bl._load_data("en_kjv")["Isaiah"][40]["31"], "en_kjv")

# 20 cards per style: verse >= 4.5:1, translation name >= 3:1, and every background different
verse, footer, times, backgrounds = [], [], [], set()
for style in STYLES:
    for _ in range(20):
        t0 = time.perf_counter()
        im = si.render_card("Isaiah 40:31", text, "King James Version", defaults, style=style)
        times.append((time.perf_counter() - t0) * 1000)
        verse.append(float(im.text("Contrast")))
        footer.append(float(im.text("FooterContrast")))
        backgrounds.add(im.text("Background"))
R.check("7 styles", len(STYLES) == 7, STYLES)
R.check("verse contrast >= 4.5 on all 140 cards", min(verse) >= 4.5, f"lowest {min(verse)}")
R.check("translation name contrast >= 3 on all 140 cards", min(footer) >= 3.0, f"lowest {min(footer)}")
R.check("140 cards, 140 different backgrounds", len(backgrounds) == 140, len(backgrounds))
R.check("backgrounds carry a 256-bit seed", all(len(b.split()[1]) == 64 for b in backgrounds))
print(f"   render_card: median {statistics.median(times):.0f} ms, slowest {max(times):.0f} ms")

# The reference line >= 3:1, measured on the pixels behind it
img = si._new_image()
lay = si.card_layout("Isaiah 40:31", text, defaults, img)
refs = []
for _ in range(60):
    used, style, seed, c = si._paint_readable_background(img, lay.card, defaults)
    refs.append(si.worst_reference_contrast(used, si._samples(img, lay.card)))
R.check("reference contrast >= 3 on 60 backgrounds", min(refs) >= 3.0, f"lowest {min(refs):.2f}")

# The same seed and style draw the same picture
a = si.render_card("John 11:35", "Jesus wept.", "KJV", defaults, seed=12345, style="aurora")
b = si.render_card("John 11:35", "Jesus wept.", "KJV", defaults, seed=12345, style="aurora")
R.check("a seed redraws the same image", a == b)

# Colours that could never be read fall back to the defaults, quickly
dark = dict(defaults, text=QColor(40, 40, 40))
t0 = time.perf_counter()
im = si.render_card("John 11:35", "Jesus wept.", "", dark)
ms = (time.perf_counter() - t0) * 1000
R.check("unreadable custom colours fall back", float(im.text("Contrast")) >= 4.5, im.text("Contrast"))
print(f"   unreadable colours fell back in {ms:.0f} ms")

# Lake reflection mirrors the image's own sky on 2x images
img = QImage(3200, 1800, QImage.Format_RGB32); img.setDevicePixelRatio(2); img.fill(QColor(0, 0, 0))
p = QPainter(img)
p.fillRect(0, 500, 1600, 100, QColor(255, 0, 0))  # a red band just above the horizon
reflect(p, 1600, 900, 600, 1.0)
p.end()
R.check("the reflection uses the sky above it", img.pixelColor(1600, 2 * 620).red() > 200)

# File names and saving
R.check("colons become dots", si._safe_name("John 11:35") == "John 11.35")
R.check("an empty name becomes Verse", si._safe_name(":") == "Verse" and si._safe_name("") == "Verse")
R.check("characters Windows forbids are dropped", si._safe_name('a<b>c"d|e?f*g') == "abcdefg")
folder = os.path.join(TMP, "saved")
paths = [si.save_card(a, "John 11:35", folder) for _ in range(3)]
R.check("same second, three files", len(set(paths)) == 3 and all(os.path.getsize(p) > 0 for p in paths),
        [os.path.basename(p) for p in paths])
R.check("the file holds the image", QImage(paths[0]).size() == a.size())

# A seed and the style it chose repaint exactly the same picture (the readability fallback and
# the seed saved in the PNG both rely on it)
from backgrounds import paint_background
def painted(seed, style):
    image = QImage(400, 225, QImage.Format_RGB32)
    image.fill(QColor(0, 0, 0))
    p = QPainter(image)
    chosen = paint_background(p, 400, 225, seed, style)
    p.end()
    return image, chosen
same = []
for seed in (777, 2 ** 200 + 5, 31337):
    first, (style, _) = painted(seed, None)
    same.append(painted(seed, style)[0] == first)
R.check("a seed with its style repaints the same picture", all(same), same)

# The contrast check uses the card as it is painted: the drop shadow goes under the whole card
# first, which darkens a see-through card (most with a dark shadow edited into colors.txt)
from PySide6.QtCore import QRect
off = []
for backdrop, shadow, behind in (("#8cffffff", "#ff000000", "#3070c0"), ("#8cffffff", "#66000000", "#f0e0a0"),
                                 (colors.DEFAULT_COLORS["backdrop"], colors.DEFAULT_COLORS["shadow"], "#204060")):
    cols = dict(defaults, backdrop=QColor(backdrop), shadow=QColor(shadow))
    img = QImage(200, 120, QImage.Format_ARGB32)
    img.fill(QColor(behind))
    p = QPainter(img)
    colors.paint_card(p, QRect(30, 20, 140, 80), cols["backdrop"], cols["shadow"])
    p.end()
    painted_px, computed = img.pixelColor(100, 60), si.card_color(cols, QColor(behind))
    diff = max(abs(painted_px.red() - computed.red()), abs(painted_px.green() - computed.green()),
               abs(painted_px.blue() - computed.blue()))
    if diff > 2:
        off.append((backdrop, shadow, behind, painted_px.name(), computed.name()))
R.check("the contrast check sees the card as painted, shadow and all (within 2 of 255)", not off, off)
R.finish()
