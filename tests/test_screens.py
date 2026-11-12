"""Two screens of different sizes, offscreen but measured with the real Windows fonts: the card
is sized for the screen it is on, long verses show whole on a small screen, and prayers open on
the widget's screen."""
import os
import json
import time
from support import Results, TMP, isolate_widget

R = Results()


def screen(name, x, y, w, h):
    return {"name": name, "x": x, "y": y, "width": w, "height": h, "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1}


# A large monitor, and a 1366 x 768 laptop at 125% scaling (1093 x 614 in Qt's units)
with open(os.path.join(TMP, "screens.json"), "w") as f:
    json.dump({"screens": [screen("BIG", 0, 0, 2560, 1440), screen("LAPTOP", 2560, 0, 1093, 614)]}, f)
os.chdir(TMP)  # the platform argument is split on ":", so the file is named without a drive
os.environ["QT_QPA_PLATFORM"] = "offscreen:configfile=screens.json"
fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
if os.path.isdir(fonts):
    os.environ["QT_QPA_FONTDIR"] = fonts  # offscreen Qt has no fonts of its own
with open(os.path.join(TMP, "corner.txt"), "w", encoding="utf-8") as f:
    f.write("tr\nBIG\non")

ww = isolate_widget()
import bible_loader as bl
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import Qt, QPointF, QEvent

qt = QApplication.instance()
R.check("two screens", [s.name() for s in qt.screens()] == ["BIG", "LAPTOP"], [s.name() for s in qt.screens()])
w = ww.BibleWidget()
w.show()
qt.processEvents()
w.show_passage("John 11:35", "Jesus wept.", "en_kjv")
R.check("on the big screen the card is 20% of its width", w.width() == 512, w.width())

# Dragged onto the laptop screen and let go
if w._snap_anim:
    w._snap_anim.stop()
w.move(2560 + 300, 200)
qt.processEvents()
w._dragging = True
w.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, QPointF(5, 5), QPointF(2865, 205),
                                Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
if w._snap_anim:
    w._snap_anim.stop()
    w.move(w._snap_anim.endValue())
qt.processEvents()
R.check("dragged to the laptop, the card is 20% of the laptop's width", w.width() == int(1093 * 0.2)
        and w._snap_screen_name.startswith("LAPTOP@"), (w.width(), w._snap_screen_name))

# A screen that changes (or is chosen again) gets the card sized for it once more
w._snap_screen_name = "BIG"
w._refit()
R.check("sized again for the screen it is on", w.width() == 512, w.width())
w._snap_screen_name = "LAPTOP"
w._refit()

# The longest verses on the small screen: every one shows whole
chrome_parts = w.layout().contentsMargins()
chrome = chrome_parts.top() + chrome_parts.bottom() + ww.REF_GAP + 1 + ww.VERSE_GAP
cut, worst, t0 = [], 0, time.monotonic()
for abbr, count in (("en_kjv", 150), ("tl_angbiblia", 30)):
    verses = []
    for book, chapters in bl._load_data(abbr).items():
        for ch, vs in chapters.items():
            for v, text in vs.items():
                verses.append((len(text), f"{book} {ch}:{v}", text))
    for _, ref, text in sorted(verses, reverse=True)[:count]:
        w.show_passage(ref, bl.clean_text(text, abbr), abbr)
        need = w.verse_label.heightForWidth(w.verse_label.width()) + w.ref_label.heightForWidth(w.ref_label.width())
        if chrome + need > w.height():
            cut.append(ref)
            worst = max(worst, chrome + need - w.height())
laptop = [s for s in qt.screens() if s.name() == "LAPTOP"][0].availableGeometry()
R.check("the 180 longest verses show whole on a 1093 x 614 screen", not cut, f"{len(cut)} cut, worst {worst}px: {cut[:5]}")
R.check("the card stays on the screen", w.width() <= laptop.width() and w.height() <= laptop.height(),
        (w.width(), w.height()))
print(f"    180 long verses fitted in {time.monotonic() - t0:.1f} s", flush=True)

# A short verse after a long one: back to the normal size
w.show_passage("John 11:35", "Jesus wept.", "en_kjv")
R.check("a short verse after a long one: normal size again", w.width() == int(1093 * 0.2), w.width())

# Prayers open on the screen the widget is on, once each
w._open_prayer("magnificat")
qt.processEvents()
prayer = w._prayer_windows[-1]
R.check("a prayer opens on the widget's screen", qt.screenAt(prayer.geometry().center()).name() == "LAPTOP",
        qt.screenAt(prayer.geometry().center()).name())
R.check("the prayer window fits that screen", laptop.contains(prayer.geometry()), prayer.geometry().getRect())
prayer.close()
qt.processEvents()

# A prayer opened on the big screen and dragged onto the laptop is sized for the laptop
w._snap_screen_name = "BIG"
w._open_prayer("magnificat")
qt.processEvents()
prayer = w._prayer_windows[-1]
tall = prayer.height()
prayer.move(2560 + 100, 0)
prayer._drag_pos = None
prayer.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, QPointF(5, 5), QPointF(2665, 5),
                                     Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
qt.processEvents()
R.check("a prayer dragged to a smaller screen fits it, Amen button and all", laptop.contains(prayer.geometry())
        and prayer.height() < tall, (tall, prayer.geometry().getRect()))
prayer.close()
qt.processEvents()

# The first verse can make the card taller or wider: it is still placed in its corner
real_random = ww.get_random_passage
esther = bl.clean_text(bl._load_data("en_kjv")["Esther"][8]["9"], "en_kjv")
ww.get_random_passage = lambda *a, **k: ("Esther 8:9", esther, "en_kjv")
with open(os.path.join(TMP, "corner.txt"), "w", encoding="utf-8") as f:
    f.write("br\nLAPTOP\non")
w2 = ww.BibleWidget()
w2.show()
qt.processEvents()
ww.get_random_passage = real_random
R.check("a long first verse starts on the screen, in its corner", laptop.contains(w2.geometry())
        and w2.height() > int(614 * 0.3), (w2.geometry().getRect(), laptop.getRect()))
w2._tray_icon.hide()
w2.close()

# Two monitors of the same model have the same name (Windows names a screen after its model):
# the card still stays on the one it was dropped on
from PySide6.QtGui import QScreen
real_name = QScreen.name
QScreen.name = lambda self: "MSI G32C4W"
try:
    w._snap_screen_name = "MSI G32C4W"
    if w._snap_anim:
        w._snap_anim.stop()
    w.move(2560 + 300, 200)
    qt.processEvents()
    w._dragging = True
    w.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, QPointF(5, 5), QPointF(2865, 205),
                                    Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
    target = w._snap_anim.endValue() if w._snap_anim else w.pos()
    R.check("two monitors with the same name: the card stays on the one it was dropped on",
            target.x() >= 2560, (target.toTuple(), w._snap_screen_name))
    w._refit()
    target = w._snap_anim.endValue() if w._snap_anim and w._snap_anim.state() else w.pos()
    R.check("...also after the screens change", target.x() >= 2560, target.toTuple())
finally:
    QScreen.name = real_name

R.finish()
