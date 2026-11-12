"""Smoke test: the widget starts and shows a verse, the colour dialog and prayers open,
every verse of every translation is free of source-file leftovers, and random passages from
each translation come out clean."""
import re
from support import Results, app, isolate_widget

R = Results()
ww = isolate_widget()
qt = app()
import bible_loader as bl
from prayer_window import PrayerWindow

w = ww.BibleWidget(); w.show(); qt.processEvents()
R.check("widget shows a reference", bool(w.ref_label.text()))
R.check("widget shows verse text", bool(w._verse_text))

w._open_color_settings(); qt.processEvents()
R.check("colour dialog opens", w._color_dialog is not None and w._color_dialog.isVisible())
w._color_dialog.showMinimized(); qt.processEvents()
w._open_color_settings(); qt.processEvents()
R.check("colour dialog restores from minimized", not w._color_dialog.isMinimized() and w._color_dialog.isVisible())
w._color_dialog.close(); qt.processEvents()

for abbr in ("en_kjv", "fi_finnish", "en_wycliffe", "eo_esperanto", "ar_svd", "ja_bungo", "he_delitzsch",
             "hi_irv", "la_vulgate", "sw_ulb"):
    for pid in ("lords-prayer", "jobs-prayer", "acts-prayer"):
        p = PrayerWindow(abbr, pid, "en")
        R.check(f"prayer {pid} {abbr} has a title", bool(p.title_label.text()))
        R.check(f"prayer {pid} {abbr} has text", bool(p.text_label.text()))

# The arrow keys move the way the buttons point: in right-to-left menus the buttons swap sides
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
ids = [pr["id"] for pr in PrayerWindow("en_kjv", "lords-prayer", "en")._prayers_list]
after = {}
for direction in (Qt.LeftToRight, Qt.RightToLeft):
    p = PrayerWindow("en_kjv", ids[1], "en")
    p.setLayoutDirection(direction)
    p.show(); qt.processEvents()
    QTest.keyClick(p, Qt.Key_Left); qt.processEvents()
    left_on_screen = p.prev_button.x() < p.next_button.x()
    after[direction] = (p._prayer_id, left_on_screen)
    p.close()
R.check("Left goes back in a left-to-right window", after[Qt.LeftToRight] == (ids[0], True), after[Qt.LeftToRight])
R.check("Left goes forward in a right-to-left window, where Next is on the left",
        after[Qt.RightToLeft] == (ids[2], False), after[Qt.RightToLeft])

widths = set()
for _ in range(6):
    w._fit_text_size(); qt.processEvents(); widths.add(w.width())
R.check("width stays the same", len(widths) == 1, widths)
R.check("stats text builds", "Translation:" in w._build_stats_text())

translations = bl.get_available_translations()
R.check("34 translations in 27 languages", (len(translations), len({lang for _, _, lang in translations})) == (34, 27),
        (len(translations), len({lang for _, _, lang in translations})))

# Every Bible shipped is free to share, with its license recorded (build.py refuses otherwise)
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(bl.__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(bl.__file__)))
import build
problems = build.check_bible_licenses()
R.check("every Bible has an allowed license, a year and a source, and is in LICENSE", not problems, problems[:3])
# A year that LICENSE does not give (another edition) is caught
import shutil, tempfile
fake_root = tempfile.mkdtemp(prefix="bw-license-")
os.makedirs(os.path.join(fake_root, "bibles"))
shutil.copy(os.path.join(build.ROOT, "bibles", "index.json"), os.path.join(fake_root, "bibles"))
with open(os.path.join(fake_root, "bibles", "vi_vietnamese.json"), "w", encoding="utf-8") as f:
    f.write("{}")
with open(os.path.join(build.ROOT, "LICENSE"), encoding="utf-8") as f:
    license_text = f.read()
with open(os.path.join(fake_root, "LICENSE"), "w", encoding="utf-8") as f:
    f.write(license_text.replace("New Testament 1923, Old Testament 1925", "1934"))
real_root, build.ROOT = build.ROOT, fake_root
try:
    wrong_year = build.check_bible_licenses()
finally:
    build.ROOT = real_root
    shutil.rmtree(fake_root, ignore_errors=True)
R.check("a year in index.json that LICENSE does not give is refused",
        "vi_vietnamese: index.json says 1923, LICENSE does not" in wrong_year, wrong_year[:2])
# A Bible listed under the other license in LICENSE is caught (public domain in index.json, but
# listed under CC BY-SA, or the other way round)
import json
fake_root = tempfile.mkdtemp(prefix="bw-license-")
os.makedirs(os.path.join(fake_root, "bibles"))
with open(os.path.join(build.ROOT, "bibles", "index.json"), encoding="utf-8-sig") as f:
    index = json.load(f)
for group in index:
    for version in group["versions"]:
        if version["abbreviation"] == "hi_irv":
            version["license"] = "Public Domain"
with open(os.path.join(fake_root, "bibles", "index.json"), "w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False)
for abbr in ("hi_irv", "en_kjv"):
    with open(os.path.join(fake_root, "bibles", f"{abbr}.json"), "w", encoding="utf-8") as f:
        f.write("{}")
with open(os.path.join(fake_root, "LICENSE"), "w", encoding="utf-8") as f:
    f.write(license_text)
real_root, build.ROOT = build.ROOT, fake_root
try:
    wrong_section = build.check_bible_licenses()
finally:
    build.ROOT = real_root
    shutil.rmtree(fake_root, ignore_errors=True)
wrong_section = [p for p in wrong_section if "lists it as" in p]
R.check("a Bible listed under the other license in LICENSE is refused (and only that one)",
        wrong_section == ["hi_irv: index.json says Public Domain, LICENSE lists it as CC BY-SA 4.0"], wrong_section)
# LICENSE names the Python and PySide6 the download is built with; build.py refuses another (here
# any Python 3.9 to 3.14 can run the tests, so this checks the refusal is right either way)
import PySide6
built_with = f"Python {sys.version_info.major}.{sys.version_info.minor}," in license_text \
    and f"PySide6 and Shiboken6 {PySide6.__version__})" in license_text
version_problems = build.check_software_versions()
R.check("build.py builds only with the Python and PySide6 LICENSE names",
        version_problems == [] if built_with else len(version_problems) >= 1, version_problems)
# A Bible named in capitals (XX.JSON) is neither loaded by the app nor checked: the build refuses it
fake_root = tempfile.mkdtemp(prefix="bw-license-")
os.makedirs(os.path.join(fake_root, "bibles"))
shutil.copy(os.path.join(build.ROOT, "bibles", "index.json"), os.path.join(fake_root, "bibles"))
shutil.copy(os.path.join(build.ROOT, "LICENSE"), fake_root)
open(os.path.join(fake_root, "bibles", "zz_unlicensed.JSON"), "w").close()
real_root, build.ROOT = build.ROOT, fake_root
try:
    caps = [p for p in build.check_bible_licenses() if "zz_unlicensed" in p]
    os.makedirs(os.path.join(fake_root, "prayers")); os.makedirs(os.path.join(fake_root, "screenshots"))
    caps_shipped = [n for _, n in build.data_files() if "zz_" in n]
finally:
    build.ROOT = real_root
    shutil.rmtree(fake_root, ignore_errors=True)
R.check("a Bible file named in capitals is refused, and never shipped", len(caps) == 1 and not caps_shipped, (caps, caps_shipped))
# --self-test writes its report to the file named after it, also after --network
import selftest
R.check("the self-test report goes to the named file",
        [selftest.report_path(a) for a in (["x", "--self-test", "r.json"], ["x", "--self-test", "--network", "r.json"],
                                           ["x", "--self-test"], ["x", "--self-test", "--network"])]
        == ["r.json", "r.json", None, None])
# Only the data files themselves are shipped: not junk Windows makes, notes, or kept-aside copies
fake_root = tempfile.mkdtemp(prefix="bw-data-")
for folder in build.SHIPPED_DATA:
    shutil.copytree(os.path.join(build.ROOT, folder), os.path.join(fake_root, folder))
for junk in ("Thumbs.db", "Desktop.ini", "notes.txt", "en_kjv.json.edited-20261110-1200"):
    open(os.path.join(fake_root, "bibles", junk), "w").close()
os.makedirs(os.path.join(fake_root, "bibles", "old"))
real_root, build.ROOT = build.ROOT, fake_root
try:
    shipped = [f"{folder}/{name}" for folder, name in build.data_files()]
finally:
    build.ROOT = real_root
    shutil.rmtree(fake_root, ignore_errors=True)
R.check("the download ships no junk from the data folders", not any(
    j in s for s in shipped for j in ("Thumbs", "Desktop", "notes", "edited", "old")), [s for s in shipped if not s.endswith((".json", ".png"))])
R.check("...but every Bible, the prayers and the README's screenshots",
        sum(s.startswith("bibles/") for s in shipped) == 36 and "prayers/prayers.json" in shipped
        and sum(s.startswith("screenshots/") for s in shipped) == 7, len(shipped))
R.check("no translation that was taken out is shipped",
        not {"pt_nvi", "pt_acf", "pt_aa", "zh_ncv", "fi_pr", "fr_apee", "de_schlachter", "ko_ko",
             "zh_cuv", "ro_cornilescu"} & {a for a, _, _ in translations})

# Leftovers from the source files that must never reach the screen: verse numbers or
# cross references in the text, footnote markers, editing marks, broken characters,
# HTML codes such as &lt; and invisible direction marks.
# (The Chinese Union Version's own notes, such as (歷代下九章14節作亞拉伯), are part of it.)
LEFTOVER = re.compile(r"\d+:\s*\d+|\(H\d|\(\d+-\)|\[|\]|\{|\}|<|>|`|\+|\u200b|\ufffd|&[a-zA-Z]+;|&#\d+;"
                      r"|[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff\u00ad]|[^\W\d_\u4e00-\u9fff]\d"
                      r"|[\u4e00-\u9fff\u3041-\u30ff] [\u4e00-\u9fff\u3041-\u30ff]|\(Zingatia"
                      r"|@|\*|\(\s*\)|,\s*[,;]|;\s*,|(?<![.])\.\.;"
                      r"|[×§´／｀−]|,\.|\.,(?!\d)|\d[^\W\d_]"  # stray signs, ",." and digits typed for letters
                      r"|[^\W\d_]{2}[.!?;][^\W\d_\s]")  # a missing space after a full stop: "sinulles.Niin"  # garbled letters, gap stars, typos
# Leftovers that only some Bibles can have
LEFTOVER_IN = {"en": re.compile(r"[a-z][A-Z]"             # a missing space: "YetGod"
                                r"|\bHeb\.|\bGr\.|\.\.\.;? or\b"),  # KJV margin notes
               "vi": re.compile(r"[\u00a0-\u00bf]"),        # half of a broken letter
               "eo": re.compile(r":(?=[^\W\d_])"),          # a missing space after a colon
               "fi": re.compile(r"\([a-z]\)"),               # footnote letters (in Czech "(o)" is a word)
               "sw": re.compile(r"\.{4}"),                  # long runs of dots (Darby's "...." is his own)
               "he": re.compile(r"[A-Za-z]"), "ar": re.compile(r"[A-Za-z]"),  # a Latin letter typed for a Hebrew one
               "fa": re.compile(r"[A-Za-z]")}
leftovers, verses_checked = [], 0
for abbr, _, _ in translations:
    for book, chapters in bl._load_data(abbr).items():
        for chapter, verses in chapters.items():
            for v, raw in verses.items():
                verses_checked += 1
                text = bl.clean_text(raw, abbr)
                m = LEFTOVER.search(text) or (LEFTOVER_IN[abbr[:2]].search(text) if abbr[:2] in LEFTOVER_IN else None)
                if m or (abbr.startswith("eo") and re.search("[cghjsuĉĝĥĵŝŭ]x", text)):
                    leftovers.append(f"{abbr} {book} {chapter}:{v} {text[max(0, m.start() - 15):m.end() + 15] if m else ''}")
R.check(f"no source leftovers in {verses_checked:,} verses", not leftovers, f"{len(leftovers)}: {leftovers[:4]}")

# Words the American Standard Version's source ran together (its italics were dropped with the spaces)
asv = " ".join(t for chapters in bl._load_data("en_asv").values() for verses in chapters.values() for t in verses.values())
joined = [w for w in ("Davidmade", "withhis", "keephis", "Godisfor", "whoisagainst", "Jehovahappeared", "isreadyfor",
                      "andsacrificesfor", "towersthereof", "Eventhe") if w in asv]
R.check("no words run together in the ASV", not joined, joined)
# Verses the repaired Bibles had merged into the verse before, lost, or left empty: each is there again
canonical = bl._get_book_names()["canonical"]
missing = []
for abbr, book, chapter, verse in (("en_geneva", "Job", 39, 38), ("en_geneva", "Daniel", 3, 33), ("en_geneva", "Romans", 1, 32),
                                   ("en_wycliffe", "Genesis", 3, 21), ("en_wycliffe", "Matthew", 10, 32),
                                   ("fi_finnish", "Ecclesiastes", 1, 18), ("fi_finnish", "Jeremiah", 15, 21),
                                   ("vi_vietnamese", "Genesis", 16, 16), ("vi_vietnamese", "Job", 34, 37),
                                   ("da_1871", "Leviticus", 5, 26), ("da_1871", "Job", 39, 38), ("da_1871", "John", 1, 52),
                                   ("hu_karoli", "John", 21, 1), ("hu_karoli", "Acts", 12, 6), ("hu_karoli", "Acts", 15, 18),
                                   ("pl_gdanska", "1 Chronicles", 7, 40), ("pl_gdanska", "Revelation", 12, 18),
                                   ("sv_1917", "Job", 39, 38), ("sv_1917", "Hosea", 2, 1), ("ar_svd", "3 John", 1, 1)):
    bible = bl._load_data(abbr)
    verses = list(bible.values())[canonical.index(book)].get(chapter, {})
    if not bl.has_words(bl.clean_text(verses.get(str(verse), ""), abbr)):
        missing.append(f"{abbr} {book} {chapter}:{verse}")
R.check("the 20 verses the repairs brought back are there", not missing, missing)
counts = {a: sum(len(v) for c in bl._load_data(a).values() for v in c.values()) for a in ("vi_vietnamese", "fi_finnish")}
R.check("the Vietnamese and Finnish Bibles have all 31,102 verses", set(counts.values()) == {31102}, counts)
empty = sum(1 for c in bl._load_data("he_delitzsch").values() for v in c.values() for t in v.values()
            if not bl.has_words(bl.clean_text(t, "he_delitzsch")))
R.check("no verse of the Hebrew New Testament is only its end mark", empty == 0, empty)

# Verses that are only punctuation ("..." in the Bible in Basic English, "׃" in the Hebrew New
# Testament, ":" in the Arabic 3 John 1:1) are never shown as a passage
empty = []
for abbr, _, _ in translations:
    for book, chapters in bl._load_data(abbr).items():
        for chapter, verses in chapters.items():
            nums = sorted(int(v) for v in verses)
            for i, n in enumerate(nums):
                if not bl.has_words(bl.clean_text(verses[str(n)], abbr)):
                    ref, text = bl._passage_that_fits(book, chapter, verses, i, i, nums, abbr, None)
                    if not bl.has_words(text):
                        empty.append(f"{abbr} {ref} {text!r}")
R.check("no passage is only punctuation", not empty, f"{len(empty)}: {empty[:4]}")
R.check("the Bible in Basic English marks its gaps with an ellipsis",
        bl.clean_text(bl._load_data("en_bbe")["Judges"][5]["7"], "en_bbe").count("…") == 1)
R.check("the broken Vietnamese letters are repaired",
        "chàng ở tù" in bl.clean_text(bl._load_data("vi_vietnamese")[list(bl._load_data("vi_vietnamese"))[0]][39]["20"], "vi_vietnamese"))

# The Arabic source wraps two verse endings as "( [ (I Timothy 6:22) ) text ]": the text stays in
# its verse, with no stray parentheses and no made-up verse 6:22
ar = bl._load_data("ar_svd")
tim, john3 = ar[list(ar)[53]][6], ar[list(ar)[63]][1]
R.check("Arabic 1 Timothy 6 has 21 verses, the last ending with its greeting",
        len(tim) == 21 and tim["21"].endswith("الايمان. النعمة معك. آمين"), (len(tim), tim.get("21", "")[-40:]))
R.check("Arabic 3 John keeps its last verse's text without stray parentheses",
        "سلام لك" in john3["14"] and "(" not in john3["14"] and ")" not in john3["14"], john3.get("14", "")[-60:])

# The KJV has every verse, numbered as printed: its source left out 6 (Herod's verse, Matthew
# 2:16, among them) and split 4 in two, which moved every verse after them to the wrong number
kjv, webster = bl._load_data("en_kjv"), bl._load_data("en_webster")
R.check("the KJV has its 31,102 verses", sum(len(v) for c in kjv.values() for v in c.values()) == 31102,
        sum(len(v) for c in kjv.values() for v in c.values()))
off = [f"{b} {c}" for b in kjv for c in kjv[b] if len(kjv[b][c]) != len(webster[b][c])]
R.check("every KJV chapter has as many verses as Webster's revision of it", not off, off[:6])
for ref, start in (("Matthew 2:16", "Then Herod, when he saw"), ("Matthew 22:37", "Jesus said unto him, Thou shalt love"),
                   ("Mark 8:8", "So they did eat"), ("1 Kings 22:53", "For he served Baal"),
                   ("3 John 1:14", "But I trust I shall shortly see thee"), ("Revelation 13:1", "And I stood upon the sand")):
    book, cv = ref.rsplit(" ", 1)
    c, v = cv.split(":")
    got = bl.clean_text(kjv[book][int(c)].get(v, ""), "en_kjv")
    R.check(f"KJV {ref} is the right verse", got.startswith(start), got[:50])
R.check("KJV 3 John 1:14 is whole", bl.clean_text(kjv["3 John"][1]["14"], "en_kjv").endswith("Greet the friends by name."),
        kjv["3 John"][1]["14"][-60:])

bad = []
for abbr, _, _ in translations:
    for _ in range(100):
        ref, text = bl.get_random_passage(abbr)
        if not text or ref == "Error":
            bad.append(f"{abbr} {ref}")
    ref, text = bl.get_verse_of_the_day(abbr)
    R.check(f"verse of the day {abbr}", ref != "Error" and bool(text))
R.check(f"{100 * len(translations):,} random passages load", not bad, bad[:5])

# Hand-edited index.json and book_names.json: saved in ANSI, with a byte order mark or in the
# wrong shape, they are read or skipped, and the app still starts
import paths
edit_dir = tempfile.mkdtemp(prefix="bw-index-")
def index_from(raw):
    with open(os.path.join(edit_dir, "index.json"), "wb") as f:
        f.write(raw)
    saved = bl._BIBLES_DIR, bl._INDEX
    bl._BIBLES_DIR, bl._INDEX = edit_dir, None
    try:
        return bl._get_index()
    finally:
        bl._BIBLES_DIR, bl._INDEX = saved
ansi = '[{"language": "Português", "versions": [{"name": "Almeida", "abbreviation": "pt_x"}]}]'
R.check("an index.json saved in ANSI keeps its accented names",
        index_from(ansi.encode("cp1252"))[0]["language"] == "Português")
R.check("an index.json with a byte order mark is read",
        index_from(b"\xef\xbb\xbf" + ansi.encode("utf-8"))[0]["versions"][0]["abbreviation"] == "pt_x")
R.check("an index.json that is not a list is ignored", index_from(b'{"a": 1}') == [])
R.check("entries of the wrong shape in index.json are skipped",
        index_from(b'[5, {"versions": [7]}, {"language": "X", "versions": [{"abbreviation": "x_y"}]}]')
        == [{"versions": []}, {"language": "X", "versions": [{"abbreviation": "x_y"}]}])
with open(os.path.join(edit_dir, "book_names.json"), "wb") as f:
    f.write(b'\xef\xbb\xbf{"names": {"x": ["A"]}}')
saved = bl._BIBLES_DIR, bl._BOOK_NAMES
bl._BIBLES_DIR, bl._BOOK_NAMES = edit_dir, None
try:
    R.check("a book_names.json with a byte order mark is read", bl._get_book_names() == {"names": {"x": ["A"]}})
finally:
    bl._BIBLES_DIR, bl._BOOK_NAMES = saved
shutil.rmtree(edit_dir, ignore_errors=True)

# Settings are replaced in one step: a write that fails midway leaves the old file whole
save_dir = tempfile.mkdtemp(prefix="bw-save-")
setting = os.path.join(save_dir, "mode.txt")
paths.write_text(setting, "daily")
try:
    paths.write_text(setting, "random" + "\udc80")  # can't be encoded: fails partway through writing
except UnicodeEncodeError:
    pass
with open(setting, encoding="utf-8") as f:
    R.check("a failed save keeps the old setting", f.read() == "daily")
R.check("a failed save leaves no temporary file", os.listdir(save_dir) == ["mode.txt"], os.listdir(save_dir))
# Another program has the file open (a backup tool, a viewer): the save still happens
import threading
holder = open(setting, "r")
threading.Timer(0.3, holder.close).start()
paths.write_text(setting, "hourly")  # let go after 0.3 s: replaced in one step once it is free
with open(setting, encoding="utf-8") as f:
    R.check("a file held open for a moment is still saved", f.read() == "hourly")
holder = open(setting, "r")
paths.write_text(setting, "random")  # held throughout: written in place rather than lost
holder.close()
with open(setting, encoding="utf-8") as f:
    R.check("a file held open throughout is written in place", f.read() == "random")
R.check("...leaving no temporary file", os.listdir(save_dir) == ["mode.txt"], os.listdir(save_dir))
shutil.rmtree(save_dir, ignore_errors=True)

# Saving a colour keeps the rest of a hand-edited colors.txt
import colors
from PySide6.QtGui import QColor
with open(colors._colors_path(), "w", encoding="utf-8") as f:
    f.write("# my colours\ntext=#ffffffff\nbackground=#cc000000\n")
colors.set_color("text", QColor("#ff112233"))
with open(colors._colors_path(), encoding="utf-8") as f:
    saved = f.read()
R.check("saving a colour keeps comments and other colours",
        saved == "# my colours\ntext=#ff112233\nbackground=#cc000000\n", repr(saved))
# colors.txt saved with a byte order mark, or in ANSI with an accented comment
with open(colors._colors_path(), "wb") as f:
    f.write(b"\xef\xbb\xbftext=#ff445566\n")
R.check("colors.txt with a byte order mark is read", colors.get_colors()["text"].name() == "#445566",
        colors.get_colors()["text"].name())
with open(colors._colors_path(), "wb") as f:
    f.write("# Farbe für den Hintergrund\nbackground=#cc000000\n".encode("cp1252"))
colors.set_color("text", QColor("#ff112233"))
with open(colors._colors_path(), encoding="utf-8") as f:
    saved = f.read()
R.check("saving a colour keeps an ANSI comment readable", saved.startswith("# Farbe für den Hintergrund\n"), repr(saved[:40]))
# On Japanese, Chinese or Korean Windows the ANSI code page can't decode every byte: a stray one
# in a hand-edited colors.txt or updates.txt must not stop the app starting
import paths
real_ansi = paths._ANSI
paths._ANSI = "cp932"  # what "mbcs" is on Japanese Windows
try:
    with open(colors._colors_path(), "wb") as f:
        f.write(b"# note \x81\ntext=#ff445566\n")
    try:
        got = colors.get_colors()["text"].name()
    except Exception as e:
        got = repr(e)
    R.check("colors.txt with a byte Japanese Windows can't read still loads", got == "#445566", got)
    try:
        colors.set_color("text", QColor("#ff112233"))
        set_ok = "ok"
    except Exception as e:
        set_ok = repr(e)
    R.check("...and a colour can still be saved", set_ok == "ok", set_ok)
    upd = tempfile.mkdtemp(prefix="bw-upd-")
    with open(os.path.join(upd, "updates.txt"), "wb") as f:
        f.write(b"# \x81\nauto=off\n")
    import updater
    try:
        got = updater.UpdateSettings(upd).auto
    except Exception as e:
        got = repr(e)
    R.check("...and so does updates.txt", got is False, got)
    shutil.rmtree(upd, ignore_errors=True)
finally:
    paths._ANSI = real_ansi

# A verse that is only markup (another numbering's verse number, as in one Finnish file) never
# shows as an empty passage, and adds nothing inside one
chapter = {"4": "Who hath wrought", "5": "(H40:19)", "6": " (H40:20) ", "7": "So the carpenter"}
nums = [4, 5, 6, 7]
R.check("a passage never starts on a verse that is only markup",
        bl._passage_that_fits("Isaiah", 41, chapter, 1, 1, nums, "fi_x", None) == ("Isaiah 41:7", "So the carpenter"),
        bl._passage_that_fits("Isaiah", 41, chapter, 1, 1, nums, "fi_x", None))
R.check("verses that are only markup add nothing to a passage",
        bl._passage_that_fits("Isaiah", 41, chapter, 0, 2, nums, "fi_x", None) == ("Isaiah 41:4-6", "Who hath wrought"),
        bl._passage_that_fits("Isaiah", 41, chapter, 0, 2, nums, "fi_x", None))

# Favorites saved in ANSI by an editor are read, not set aside as damaged
import verses as vs
fav_dir = tempfile.mkdtemp(prefix="bw-fav-")
fav_path = os.path.join(fav_dir, "favorites.json")
with open(fav_path, "wb") as f:
    f.write('[{"ref": "João 3:16", "text": "Porque Deus amou", "translation": "pt_almeida", "at": ""}]'.encode("cp1252"))
fav = vs.VerseList(fav_path)
R.check("favorites saved in ANSI are read", [e["ref"] for e in fav.entries] == ["João 3:16"]
        and os.listdir(fav_dir) == ["favorites.json"], (fav.entries, os.listdir(fav_dir)))
shutil.rmtree(fav_dir, ignore_errors=True)

R.finish()
