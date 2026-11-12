"""verses.py: reference parsing (40 cases), word search, and the favorites/history files."""
import json
import re
import os
import time
import tempfile
import unicodedata
from support import Results, TMP
import verses as vs

R = Results()


def check(name, got, want):
    R.check(name, got == want, f"got {got!r}, want {want!r}")


# (query, translation, expected (book, chapter, start, end) or None)
CASES = [
    ("John 3:16", "en_kjv", ("John", 3, 16, 16)),
    ("john 3:16", "en_kjv", ("John", 3, 16, 16)),
    ("Jn 3:16", "en_kjv", ("John", 3, 16, 16)),
    ("jhn 3:16-18", "en_kjv", ("John", 3, 16, 18)),
    ("John 3", "en_kjv", ("John", 3, 1, 5)),
    ("John3:16", "en_kjv", ("John", 3, 16, 16)),
    ("Joh 3.16", "en_kjv", ("John", 3, 16, 16)),
    ("Jonah 2:2", "en_kjv", ("Jonah", 2, 2, 2)),
    ("1 Cor 13:4-7", "en_kjv", ("1 Corinthians", 13, 4, 7)),
    ("1co13:4", "en_kjv", ("1 Corinthians", 13, 4, 4)),
    ("1 Corinthians 13:4", "en_kjv", ("1 Corinthians", 13, 4, 4)),
    ("Gen 1:1", "en_kjv", ("Genesis", 1, 1, 1)),
    ("gn 1:1", "en_kjv", ("Genesis", 1, 1, 1)),
    ("Psalm 23:1", "en_kjv", ("Psalms", 23, 1, 1)),
    ("Ps 23", "en_kjv", ("Psalms", 23, 1, 5)),
    ("Prov 3:5-6", "en_kjv", ("Proverbs", 3, 5, 6)),
    ("Song of Solomon 2:1", "en_kjv", ("Song of Solomon", 2, 1, 1)),
    ("SoS 2:1", "en_kjv", ("Song of Solomon", 2, 1, 1)),
    ("Phil 4:13", "en_kjv", ("Philippians", 4, 13, 13)),
    ("Phm 1:4", "en_kjv", ("Philemon", 1, 4, 4)),
    ("Rev 21:4", "en_kjv", ("Revelation", 21, 4, 4)),
    ("3 John 1:2", "en_kjv", ("3 John", 1, 2, 2)),
    ("Jude 1:24", "en_kjv", ("Jude", 1, 24, 24)),
    ("Jas 1:5", "en_kjv", ("James", 1, 5, 5)),
    ("Ruth 1:16-99", "en_kjv", ("Ruth", 1, 16, 22)),  # end clamps to the last verse
    ("I Timothy 1:15", "en_asv", ("1 Timothy", 1, 15, 15)),  # dict-format file, Roman numeral alias
    ("Revelation of John 1:8", "en_asv", ("Revelation", 1, 8, 8)),
    ("Juan 3:16", "es_rvr", ("Juan", 3, 16, 16)),
    ("Salmos 23:1", "es_rvr", ("Salmos", 23, 1, 1)),
    ("John 3:16", "es_rvr", ("Juan", 3, 16, 16)),  # English name, Spanish Bible
    ("Juan 3:16", "en_kjv", ("John", 3, 16, 16)),  # Spanish name, English Bible
    ("Mateus 5:9", "pt_almeida", ("Mateus", 5, 9, 9)),  # names come from the file itself
    ("1. Mose 1:1", "de_luther", ("1. Mose", 1, 1, 1)),
    # The languages added in 2.1.0, each in its own script and with an English name
    ("Giovanni 3:16", "it_riveduta", ("Giovanni", 3, 16, 16)),
    ("Jana 3:16", "pl_gdanska", ("Jana", 3, 16, 16)),
    ("János 3:16", "hu_karoli", ("János", 3, 16, 16)),
    ("Johannes 3:16", "sv_1917", ("Johannes", 3, 16, 16)),
    ("Yohana 3:16", "sw_ulb", ("Yohana", 3, 16, 16)),
    ("Juan 3:16", "tl_angbiblia", ("Juan", 3, 16, 16)),
    ("Ioannes 3:16", "la_vulgate", ("Ioannes", 3, 16, 16)),
    ("יוחנן 3:16", "he_delitzsch", ("יוחנן", 3, 16, 16)),
    ("یوحنا 3:16", "fa_opv", ("یوحنا", 3, 16, 16)),
    ("यूहन्ना 3:16", "hi_irv", ("यूहन्ना", 3, 16, 16)),
    ("ヨハネ 3:16", "ja_bungo", ("ヨハネ", 3, 16, 16)),
    ("John 3:16", "ja_bungo", ("ヨハネ", 3, 16, 16)),
    ("John 3:16", "uk_kulish", ("Йоана", 3, 16, 16)),
    ("Genesis 1:1", "sw_ulb", ("Mwanzo", 1, 1, 1)),
    ("Ин 3:16", "ru_synodal", ("От Иоанна", 3, 16, 16)),  # the usual Russian short form
    ("От Иоанна 3:16", "ru_synodal", ("От Иоанна", 3, 16, 16)),
    ("約翰福音 3:16", "en_kjv", ("John", 3, 16, 16)),  # a Chinese book name, English Bible
    ("John 99:1", "en_kjv", None),
    ("John 3:99", "en_kjv", None),
    ("love one another", "en_kjv", None),
    ("", "en_kjv", None),
]
for q, t, want in CASES:
    check(f"parse {q!r} [{t}]", vs.parse_reference(q, t), want)

# A bare word opens a book only in this Bible's own language or in English; another language's
# book name ("Judas" is Jude in German) is a word search. With a chapter, any language works.
BARE = [
    ("Jakob", "de_luther", None),  # Danish for James
    ("Judas", "en_kjv", None),  # German/Spanish for Jude
    ("esta", "es_rvr", None),  # Swahili for Esther
    ("nombres", "es_rvr", None),  # French for Numbers
    ("Mica", "fr_lsg", None),  # Romanian for Micah
    ("Job", "es_rvr", ("Job", 1, 1, 5)),  # the Bible's own name wins over the word
    ("Judas", "es_rvr", ("Judas", 1, 1, 5)),
    ("Jakob", "da_1871", None),  # also Jacob, in 271 verses: a word search (Jakob 1 opens James)
    ("Jakob 1", "da_1871", ("Jakob", 1, 1, 5)),
    ("Jakobus", "de_luther", ("Jakobus", 1, 1, 5)),
    ("1 John", "en_kjv", ("1 John", 1, 1, 5)),
    ("John", "es_rvr", ("Juan", 1, 1, 5)),  # English names work in every Bible
    ("John", "ja_bungo", ("ヨハネ", 1, 1, 5)),
    ("I Timothy", "en_kjv", ("1 Timothy", 1, 1, 5)),  # English alias
    ("Juan", "en_kjv", None),
    ("Judas 1:24", "en_kjv", ("Jude", 1, 24, 24)),
    ("Jakob 1:5", "de_luther", ("Jakobus", 1, 5, 5)),
    ("Mica 6:8", "fr_lsg", ("Michée", 6, 8, 8)),
]
for q, t, want in BARE:
    check(f"bare word {q!r} [{t}]", vs.parse_reference(q, t), want)
kind, res, passage = vs.find("Judas", "en_kjv")
check("find 'Judas' in the KJV is a word search", (kind, len(res), passage), ("words", 32, None))

# Full-width digits and punctuation, as a Japanese or Chinese keyboard types them
WIDE = [
    ("ヨハネ３：１６", "ja_bungo", ("ヨハネ", 3, 16, 16)),
    ("ヨハネ 3：16", "ja_bungo", ("ヨハネ", 3, 16, 16)),
    ("ヨハネ３：１６－１８", "ja_bungo", ("ヨハネ", 3, 16, 18)),
    ("ヨハネ3:16～18", "ja_bungo", ("ヨハネ", 3, 16, 18)),
    ("ヨハネ3:16〜18", "ja_bungo", ("ヨハネ", 3, 16, 18)),
    ("ヨハネ\u3000３．１６", "ja_bungo", ("ヨハネ", 3, 16, 16)),  # ideographic space
    ("約翰福音３：１６", "en_kjv", ("John", 3, 16, 16)),
    ("John 3：16", "en_kjv", ("John", 3, 16, 16)),
]
for q, t, want in WIDE:
    check(f"full-width {q!r} [{t}]", vs.parse_reference(q, t), want)
kind, res, passage = vs.find("ヱホバ", "ja_bungo", limit=100000)
check("Japanese words are still a word search", (kind, len(res)), ("words", len(vs.search_words("ヱホバ", "ja_bungo", 100000))))
check("full-width letters still find words", len(vs.search_words("ＬＯＶＥ", "en_kjv", 100000)),
      len(vs.search_words("love", "en_kjv", 100000)))

# Passage text for a parsed reference
ref, text = vs.get_passage("en_kjv", "John", 3, 16, 16)
check("passage ref", ref, "John 3:16")
check("passage text", text.startswith("For God so loved the world"), True)

# find(): reference vs words
kind, res, passage = vs.find("John 11:35", "en_kjv")
check("find reference passage", (kind, passage[:2]), ("reference", ("John 11:35", "Jesus wept.")))
check("find reference lists the whole chapter", len(res), 57)
kind, res, passage = vs.find("Proverbs 30:4", "en_kjv")
check("Proverbs 30:4 lists all 33 verses", [r[2] for r in res], list(range(1, 34)))
check("Proverbs 30:4 passage", passage[0], "Proverbs 30:4")
kind, res, passage = vs.find("John 3:16-18", "en_kjv")
check("range passage keeps its verses", (passage[0], passage[2], passage[3], len(res)), ("John 3:16-18", 16, 18, 36))
kind, res, passage = vs.find("faith hope charity", "en_kjv")
check("words have no passage", passage, None)
check("find words kind", kind, "words")
check("find words hit 1 Cor 13:13", any(r[0] == "1 Corinthians 13:13" for r in res), True)

# Word search counts and timing (first run builds the cache, then repeat runs)
t0 = time.perf_counter(); r1 = vs.search_words("faith hope charity", "en_kjv"); first_ms = (time.perf_counter() - t0) * 1000
times = []
for q in ("faith hope charity", "love", "shepherd", "living water", "jesus wept"):
    t0 = time.perf_counter(); n = len(vs.search_words(q, "en_kjv", limit=10000)); times.append(((time.perf_counter() - t0) * 1000, q, n))
check("'love' prefix matches 'loved' in John 3:16",
      any(r == "John 3:16" for r, _ in vs.search_words("loved world", "en_kjv")), True)
check("accent-insensitive search (corazon)", len(vs.search_words("corazon", "es_rvr")) > 0, True)
check("Japanese substring search", len(vs.search_words("愛", "ja_bungo")) > 0, True)
check("empty search", vs.search_words("   ", "en_kjv"), [])
# Indic scripts keep their virama and vowel signs when matching: they change the word
param = vs.search_words("परम", "hi_irv", 100000)
check("Hindi: param does not also find prem", sum("परम" not in t for _, t in param), 0)
check("Hindi: prem is found", len(vs.search_words("प्रेम", "hi_irv", 100000)) > 300, True)
check("Tamil: a misspelling finds nothing", len(vs.search_words("அனபு", "ta_irv", 100000)), 0)
check("Tamil: the word is found", len(vs.search_words("அன்பு", "ta_irv", 100000)) > 50, True)
check("Hindi highlight keeps the letter whole", vs.match_spans("प्रे", "उसने प्रेम रखा"), [(5, 9)])
# A vowel sign or virama is part of the word, so the letter after it is not a word start
def starts_a_word(word, text):
    f, w = vs._fold(text), vs._fold(word)
    return any(i == 0 or not (f[i - 1].isalnum() or unicodedata.category(f[i - 1])[0] == "M" or f[i - 1] == "\u200d")
               for i in range(len(f)) if f.startswith(w, i))


for abbr, word in (("hi_irv", "रेम"), ("hi_irv", "र"), ("ta_irv", "பு"), ("ta_irv", "ம")):
    found = vs.search_words(word, abbr, 100000)
    check(f"{abbr}: {word} only matches at a word start", sum(not starts_a_word(word, t) for _, t in found), 0)
check("Hindi: रेम is not highlighted inside प्रेम", vs.match_spans("रेम", "उसने प्रेम रखा"), [])
check("Tamil: பு is not highlighted inside அன்பு", vs.match_spans("பு", "அன்பு பும"), [(6, 8)])
check("Hindi: a letter after a zero-width joiner is mid-word", vs.match_spans("ष", "क्\u200dष ष"), [(5, 6)])
check("accents still ignored: eternel finds Éternel", len(vs.search_words("eternel", "fr_lsg", 100000)) > 1000, True)
check("Hebrew finds a word", len(vs.search_words("אהב", "he_delitzsch", 100000)) > 0, True)
check("Japanese finds a word mid-sentence", len(vs.search_words("ヱホバ", "ja_bungo", 100000)) > 1000, True)

# Stores in a temp folder
d = tempfile.mkdtemp(dir=TMP)
fav = vs.VerseList(os.path.join(d, "favorites.json"))
fav.add("John 3:16", "For God...", "en_kjv")
fav.add("Psalms 23:1", "The LORD is my shepherd...", "en_kjv")
fav.add("John 3:16", "For God...", "en_kjv")  # re-adding moves it to the top, no duplicate
check("favorites order", [e["ref"] for e in fav.entries], ["John 3:16", "Psalms 23:1"])
check("favorites reload", [e["ref"] for e in vs.VerseList(fav.path).entries], ["John 3:16", "Psalms 23:1"])
fav.remove("John 3:16", "en_kjv")
check("favorites remove", vs.VerseList(fav.path).contains("John 3:16", "en_kjv"), False)
hist = vs.VerseList(os.path.join(d, "history.json"), cap=100)
for i in range(130):
    hist.add(f"Genesis 1:{i + 1}", "x", "en_kjv", unique=False)
check("history capped at 100", len(vs.VerseList(hist.path, cap=100).entries), 100)
check("history newest first", hist.entries[0]["ref"], "Genesis 1:130")
open(os.path.join(d, "bad.json"), "w").write("{not json")
check("corrupt file gives empty list", vs.VerseList(os.path.join(d, "bad.json")).entries, [])
check("no tmp file left behind", [f for f in os.listdir(d) if f.endswith(".tmp")], [])
# Saved by an editor that adds a byte order mark (PowerShell 5.1, older Notepad): still read
bom = os.path.join(d, "bom.json")
with open(bom, "w", encoding="utf-8-sig") as f:
    json.dump([{"ref": "Juan 3:16", "text": "Porque de tal manera...", "translation": "es_rvr", "at": ""}], f,
              ensure_ascii=False)
check("a file with a byte order mark is read", [e["ref"] for e in vs.VerseList(bom).entries], ["Juan 3:16"])
check("and is not set aside as damaged", [f for f in os.listdir(d) if "damaged" in f and "bom" in f], [])
# bibles/index.json edited by hand and saved with a byte order mark still names the translations
import bible_loader as bl
real_dir, real_index = bl._BIBLES_DIR, bl._INDEX
bibles = os.path.join(d, "bibles"); os.makedirs(bibles)
with open(os.path.join(bibles, "index.json"), "w", encoding="utf-8-sig") as f:
    json.dump([{"language": "English", "versions": [{"name": "My Translation", "abbreviation": "en_mine"}]}], f)
bl._BIBLES_DIR, bl._INDEX = bibles, None
try:
    index = bl._get_index()
finally:
    bl._BIBLES_DIR, bl._INDEX = real_dir, real_index
check("index.json with a byte order mark is read", [v["name"] for g in index for v in g["versions"]], ["My Translation"])

# A verse numbered with a superscript digit is skipped, not the whole file ("²".isdigit() is True)
check("a superscript verse number skips just that verse",
      bl._normalize_bible({"Genesis": {"1": {"1": "In the beginning", "\u00b2": "x"}}}), {"Genesis": {1: {"1": "In the beginning"}}})
# The Greek psalm-title step runs before brackets are removed, as it always did
check("Greek: escaped marks next to a bracket", bl.clean_text("&gt;{&gt;", "el_greek"), ">>")
# The verse of the day is picked exactly as before (a list of every verse, then choice())
import random, datetime


def old_pick(abbr, day):
    rnd = random.Random(day.isoformat())
    starts = [(b, int(c), v) for b, chs in bl._load_data(abbr).items() for c, vs in chs.items()
              for v in sorted(int(x) for x in vs)]
    return rnd.choice(starts)


def new_pick(abbr, day):
    rnd = random.Random(day.isoformat())
    starts = bl._get_all_starts(abbr)
    return bl._start_at(starts, rnd.randrange(starts[0]))


days = [datetime.date(2026, 1, 1) + datetime.timedelta(days=n) for n in range(366)]
same = all(old_pick(a, d) == new_pick(a, d) for a in ("en_kjv", "la_vulgate", "he_delitzsch") for d in days)
check("the verse of the day is the same as before on 366 days in 3 Bibles", same, True)
check("verse positions are kept per chapter, not per verse", len(bl._get_all_starts("en_kjv")[1]), 1189)
# A file that cannot be loaded is tried once, not on every verse change
calls = []
real_load_file = bl._load_file
bl._load_file = lambda path, abbr="": (calls.append(abbr), {})[1]
bl._ABBREVIATIONS.append("xx_broken")
try:
    bl._load_data("xx_broken"); bl._load_data("xx_broken")
finally:
    bl._load_file = real_load_file
    bl._ABBREVIATIONS.remove("xx_broken"); bl._FAILED.discard("xx_broken")
check("a broken Bible file is read once", calls, ["xx_broken"])
check("the book name index is built once", vs._book_index() is vs._book_index(), True)

# Japanese voicing marks spell a different sound (ガ ga, カ ka), so they count in a search
ga, ka = (len(vs.search_words(q, "ja_bungo", limit=10 ** 6)) for q in ("ガ", "カ"))
R.check("ガ and カ are different letters in a search", ga != ka and ga > 0 and ka > 0, (ga, ka))
R.check("half-width ｶﾞ finds the same as ガ", len(vs.search_words("ｶﾞ", "ja_bungo", limit=10 ** 6)) == ga)

# ----- Numbered books, everyday names, short forms -----
canonical = bl._get_book_names()["canonical"]


def own(abbr, english):
    """This Bible's name for an English book name."""
    return bl.localize_reference(f"{english} 1:1", abbr).rsplit(" ", 1)[0]


for query, abbr, english, ch, v in (
        ("1 Jana 1:9", "pl_gdanska", "1 John", 1, 9), ("1 Koryntian 13:4", "pl_gdanska", "1 Corinthians", 13, 4),
        ("2 Piotra 1:1", "pl_gdanska", "2 Peter", 1, 1), ("1 Giăng 1:9", "vi_vietnamese", "1 John", 1, 9),
        ("1 Ιωάννου 1:9", "el_greek", "1 John", 1, 9), ("1 يوحنا 1:9", "ar_svd", "1 John", 1, 9),
        ("1 שמואל 3:1", "he_delitzsch", "1 Samuel", 3, 1), ("1 یوحنا 1:9", "fa_opv", "1 John", 1, 9),
        ("1ヨハネ 1:9", "ja_bungo", "1 John", 1, 9), ("2ペテロ 1:1", "ja_bungo", "2 Peter", 1, 1),
        ("I Jana 1:9", "pl_gdanska", "1 John", 1, 9), ("Иоанна 3:16", "ru_synodal", "John", 3, 16),
        ("Матфея 5:3", "ru_synodal", "Matthew", 5, 3), ("Мф 5:3", "ru_synodal", "Matthew", 5, 3),
        ("Ин 3:16", "ru_synodal", "John", 3, 16), ("1 Ин 1:9", "ru_synodal", "1 John", 1, 9),
        ("Jo 3:16", "en_kjv", "John", 3, 16), ("Php 4:13", "en_kjv", "Philippians", 4, 13),
        ("Jnh 2:2", "en_kjv", "Jonah", 2, 2), ("Mr 1:1", "en_kjv", "Mark", 1, 1), ("Jg 6:12", "en_kjv", "Judges", 6, 12),
        ("SS 2:1", "en_kjv", "Song of Solomon", 2, 1), ("Jb 1:1", "en_kjv", "Job", 1, 1),
        ("Jó 1:1", "pt_almeida", "Job", 1, 1), ("Isaías 53:5", "es_rvr", "Isaiah", 53, 5)):
    got = vs.parse_reference(query, abbr)
    check(f"{query!r} in {abbr}", got and got[:3], (own(abbr, english), ch, v))

# One-chapter books with just a verse, verse and chapter ranges, a range from a missing verse
check("Jude 3", vs.parse_reference("Jude 3", "en_kjv"), ("Jude", 1, 3, 3))
check("Jude 3-5", vs.parse_reference("Jude 3-5", "en_kjv"), ("Jude", 1, 3, 5))
check("3 John 4", vs.parse_reference("3 John 4", "en_kjv"), ("3 John", 1, 4, 4))
check("Philemon 6", vs.parse_reference("Philemon 6", "en_kjv"), ("Philemon", 1, 6, 6))
check("Obadiah 4", vs.parse_reference("Obadiah 4", "en_kjv"), ("Obadiah", 1, 4, 4))
check("Jude 1 is the chapter", vs.parse_reference("Jude 1", "en_kjv"), ("Jude", 1, 1, 5))
check("John 3:16-4:2 runs to the end of John 3", vs.parse_reference("John 3:16-4:2", "en_kjv"), ("John", 3, 16, 36))
check("John 3:16-3:18", vs.parse_reference("John 3:16-3:18", "en_kjv"), ("John", 3, 16, 18))
check("John 3-4 opens John 3", vs.parse_reference("John 3-4", "en_kjv"), ("John", 3, 1, 5))
hu_john = own("hu_karoli", "John")
first = min(int(v) for v in bl._load_data("hu_karoli")[hu_john][21])
check("a range that starts on a verse the file lacks starts at the next one",
      vs.parse_reference(f"{hu_john} 21:1-3", "hu_karoli"), (hu_john, 21, first, 3))
check("a book name on its own, five words long", vs.parse_reference(own("vi_vietnamese", "Deuteronomy"), "vi_vietnamese"),
      (own("vi_vietnamese", "Deuteronomy"), 1, 1, 5))

# Pasted right-to-left text carries invisible direction marks
check("a reference with a direction mark", vs.parse_reference("\u200fيوحنا 3:16", "ar_svd")[1:3], (3, 16))
check("a direction mark after it", vs.parse_reference("John 3:16\u200f", "en_kjv"), ("John", 3, 16, 16))

# Very long input stays fast and never fails
t0 = time.perf_counter()
check("20,000 digits are not a reference", vs.parse_reference("1" * 20000 + "x", "en_kjv"), None)
check("a 5,000-digit chapter is not a reference", vs.parse_reference("John " + "9" * 5000, "en_kjv"), None)
long_words = vs.search_words(" ".join(["love"] * 2000), "en_kjv")
R.check("very long input is handled in under half a second", time.perf_counter() - t0 < 0.5,
        f"{time.perf_counter() - t0:.2f} s")

# ----- Searches typed the way keyboards type them -----
def hits(q, abbr):
    return len(vs.search_words(q, abbr, limit=10 ** 6))


R.check("Vietnamese without accents finds as much as with them",
        hits("Duc Chua Troi", "vi_vietnamese") == hits("Đức Chúa Trời", "vi_vietnamese") > 3000,
        (hits("Duc Chua Troi", "vi_vietnamese"), hits("Đức Chúa Trời", "vi_vietnamese")))
R.check("Japanese modern kanji find the old forms: 天国 = 天國", hits("天国", "ja_bungo") == hits("天國", "ja_bungo") > 0,
        (hits("天国", "ja_bungo"), hits("天國", "ja_bungo")))
R.check("国 = 國, 声 = 聲", hits("国", "ja_bungo") == hits("國", "ja_bungo") > 1000 and hits("声", "ja_bungo") == hits("聲", "ja_bungo") > 0,
        (hits("国", "ja_bungo"), hits("國", "ja_bungo"), hits("声", "ja_bungo"), hits("聲", "ja_bungo")))
zwnj = hits("می\u200cکند", "fa_opv")
R.check("Persian typed without the zero-width non-joiner", hits("میکند", "fa_opv") == zwnj > 0, (hits("میکند", "fa_opv"), zwnj))
R.check("...and a word after it still starts a word", hits("کند", "fa_opv") >= zwnj, (hits("کند", "fa_opv"), zwnj))
R.check("Persian yeh finds the Arabic Bible's: یسوع = يسوع", hits("یسوع", "ar_svd") == hits("يسوع", "ar_svd") > 0,
        (hits("یسوع", "ar_svd"), hits("يسوع", "ar_svd")))
R.check("Arabic yeh finds the Persian Bible's: عيسى = عیسی", hits("عيسى", "fa_opv") == hits("عیسی", "fa_opv") > 0,
        (hits("عيسى", "fa_opv"), hits("عیسی", "fa_opv")))
R.check("Persian kaf finds the Arabic: ملک = ملك", hits("ملک", "ar_svd") == hits("ملك", "ar_svd") > 0,
        (hits("ملک", "ar_svd"), hits("ملك", "ar_svd")))
spans = vs.match_spans("Duc", "Đức Chúa Trời")
check("bold marks the accented word", spans, [(0, 3)])
check("a search with a direction mark", hits("\u200fيسوع", "ar_svd"), hits("يسوع", "ar_svd"))

# ----- Round 4: typed the way people type -----
if not bl._ABBREVIATIONS:
    bl._discover()
# Clean-up leaves no space before punctuation, and no translator's note
check("stars before a full stop", bl._clean_text("abc***.", "ar_svd"), "abc ….")
check("stars between words", bl._clean_text("abc *** def", "ar_svd"), "abc … def")
check("a direction mark removed before a full stop", bl._clean_text("abc " + chr(0x200E) + ".", "ar_svd"), "abc.")
for book, chapter, verse in (("Isaiah", 54, "13"), ("Jeremiah", 49, "4"), ("James", 2, "16"), ("Ezekiel", 23, "43")):
    t = bl._clean_text(bl._load_data("ar_svd")[own("ar_svd", book)][chapter][verse], "ar_svd")
    R.check(f"ar_svd {book} {chapter}:{verse} has no space before its full stop", not t.endswith(" ."), t[-12:])
for chapter, verse in ((17, "36"), (10, "22")):
    t = bl._clean_text(bl._load_data("en_kjv")["Luke"][chapter][verse], "en_kjv")
    R.check(f"KJV Luke {chapter}:{verse} shows no translator's note", "copies" not in t, t[-60:])
# Apostrophes: a typed ' finds the printed ’ (and the other way round)
R.check("l'Éternel finds l’Éternel", hits("l'Éternel", "fr_lsg") == hits("l’Éternel", "fr_lsg") > 5000,
        (hits("l'Éternel", "fr_lsg"), hits("l’Éternel", "fr_lsg")))
R.check("dell'Eterno finds dell’Eterno", hits("dell'Eterno", "it_riveduta") == hits("dell’Eterno", "it_riveduta") > 1000,
        (hits("dell'Eterno", "it_riveduta"), hits("dell’Eterno", "it_riveduta")))
R.check("God's = God’s", hits("God's", "en_asv") == hits("God’s", "en_asv") > 0 and hits("God's", "en_ylt") > 0,
        (hits("God's", "en_asv"), hits("God’s", "en_asv"), hits("God's", "en_ylt")))
# Words in front of a name, typed or not
for query, abbr, english in (("К Римлянам 1:1", "ru_synodal", "Romans"), ("К Евреям 1:1", "ru_synodal", "Hebrews"),
                             ("Послание к Римлянам 1:1", "ru_synodal", "Romans"), ("До Римлян 1:1", "uk_kulish", "Romans"),
                             ("Księga Rodzaju 1:1", "pl_gdanska", "Genesis"), ("Sędziów 1:1", "pl_gdanska", "Judges"),
                             ("Yakobo 1:1", "sw_ulb", "James"), ("Waraka wa Yakobo 1:1", "sw_ulb", "James")):
    got = vs.parse_reference(query, abbr)
    check(f"{query!r} in {abbr}", got and got[0], own(abbr, english))
# The Greek numeral sign typed as a tonos, an acute accent or an oxia
for sign in (0x0384, 0x00B4, 0x1FFD, 0x0374, 0x2019, 0x27):
    got = vs.parse_reference("Α" + chr(sign) + " Ιωάννου 1:1", "el_greek")
    check(f"Α{chr(sign)} Ιωάννου (U+{sign:04X})", got and got[0], own("el_greek", "1 John"))
# English short forms open the English book in every Bible, before another language's name
for abbr in ("ar_svd", "el_greek", "fa_opv", "he_delitzsch", "hi_irv", "ja_bungo", "ru_synodal", "ta_irv", "uk_kulish",
             "zh_cuv", "ko_krv"):  # (in a Latin-script Bible its own names come first: Polish Ro is Rodzaju)
    if abbr not in bl._ABBREVIATIONS:
        continue
    for query, english in (("Dan 7:13", "Daniel"), ("Ro 1:1", "Romans"), ("Mat 1:1", "Matthew"), ("Heb 1:1", "Hebrews"),
                           ("Col 1:1", "Colossians"), ("Jer 1:1", "Jeremiah")):
        got = vs.parse_reference(query, abbr)
        check(f"{query!r} in {abbr}", got and got[0], own(abbr, english))
check("Ис 1:1 is Isaiah (Synodal short form)", vs.parse_reference("Ис 1:1", "ru_synodal")[0], own("ru_synodal", "Isaiah"))
check("Нав 1:1 is Joshua", (vs.parse_reference("Нав 1:1", "ru_synodal") or [None])[0], own("ru_synodal", "Joshua"))
check("Исх 1:1 is still Exodus", vs.parse_reference("Исх 1:1", "ru_synodal")[0], own("ru_synodal", "Exodus"))
# A book name that is also a common word of that Bible, on its own: a word search
for word, abbr in (("יהודה", "he_delitzsch"), ("יעקב", "he_delitzsch"), ("ויקרא", "he_delitzsch"), ("يهوذا", "ar_svd"),
                   ("یهودا", "fa_opv"), ("Ιούδα", "el_greek"), ("Giuda", "it_riveduta"), ("Kutoka", "sw_ulb")):
    kind, rows, _ = vs.find(word, abbr)
    R.check(f"{word} on its own searches {abbr}", kind == "words" and len(rows) >= 100, (kind, len(rows)))
    got = vs.parse_reference(word + " 1:1", abbr)
    R.check(f"...and {word} 1:1 still opens the book", got is not None and got[1:3] == (1, 1), got)
for name in bl._load_data("en_kjv"):
    if len(name.split()) == 1:
        kind, _, passage = vs.find(name, "en_kjv")
        if kind != "reference" or not passage[0].startswith(name):
            R.check(f"English book name {name} on its own opens the book", False, (kind, passage))
# Verse ranges in one-chapter books
check("Jude 1-3", vs.parse_reference("Jude 1-3", "en_kjv"), ("Jude", 1, 1, 3))
check("Obadiah 1-4", vs.parse_reference("Obadiah 1-4", "en_kjv"), ("Obadiah", 1, 1, 4))
check("Jude 1:1-3", vs.parse_reference("Jude 1:1-3", "en_kjv"), ("Jude", 1, 1, 3))
# find() reports the verse it shows, which is in the chapter list (not a verse that is only "׃")
for query, abbr in (("Matthew 5:37", "he_delitzsch"), ("1 Samuel 13:1", "en_bbe"), ("3 John 1:1", "ar_svd")):
    kind, rows, passage = vs.find(query, abbr)
    shown = [n for _, _, n in rows]
    R.check(f"{query} in {abbr}: the verse shown is in the list", passage[2] in shown and passage[3] in shown,
            (passage[2:], shown[:5]))
for abbr in ("he_delitzsch", "en_bbe", "ar_svd"):
    bible = bl._load_data(abbr)
    for book, chapters in bible.items():
        for chapter, verses in chapters.items():
            first = min(int(n) for n in verses)
            if not bl.has_words(bl._clean_text(verses[str(first)], abbr)):
                got = vs.parse_reference(f"{book} {chapter}", abbr)
                R.check(f"{abbr} {book} {chapter} opens on a verse with words", got and bl.has_words(
                    bl._clean_text(verses[str(got[2])], abbr)), got)
# Bold covers the accent marks on the last letter (Arabic shadda)
text = bl._clean_text(bl._load_data("ar_svd")[own("ar_svd", "1 Kings")][22]["9"], "ar_svd")
cut = [(s, e) for s, e in vs.match_spans("الي", text) if e < len(text) and unicodedata.combining(text[e])]
R.check("bold never stops before a mark on its last letter", not cut and vs.match_spans("الي", text), cut)
# Hindi written with and without the zero-width joiner
zwj = chr(0x200D)
hindi = sorted({w for chapters in bl._load_data("hi_irv").values() for verses in chapters.values()
                for t in verses.values() if zwj in t for w in bl._clean_text(t, "hi_irv").split() if zwj in w})
missed = [w for w in hindi[:40] if hits(w.replace(zwj, ""), "hi_irv") != hits(w, "hi_irv") or not hits(w, "hi_irv")]
R.check(f"Hindi words found with or without the joiner ({len(hindi[:40])} words)", hindi and not missed, missed[:3])
# A favorites file nested too deep to read is kept aside, not a crash
deep_dir = tempfile.mkdtemp(dir=TMP)
deep = os.path.join(deep_dir, "deep.json")
with open(deep, "w") as f:
    f.write("[" * 100000)
try:
    entries = vs.VerseList(deep).entries
except RecursionError:
    entries = "RecursionError"
check("a favorites file nested 100,000 deep gives an empty list", entries, [])
R.check("...and is kept as .damaged", not os.path.exists(deep) and any(n.startswith("deep.json.damaged") for n in os.listdir(deep_dir)))
# Book names: spaced, spelled and capitalised as in print, and found the ways people write them
for abbr in bl._ABBREVIATIONS:
    for name in bl._load_data(abbr):
        if re.search(r"\d(?=[^\W\d])|\s\d+$", name) or (name.isupper() and len(name) > 1):
            R.check(f"{abbr} book name {name!r} is written as in print", False)
for query, abbr, english in (("2 Corinthiërs 1:1", "nl_sv1917", "2 Corinthians"), ("Numeri 1:1", "nl_sv1917", "Numbers"),
                             ("Richteren 1:1", "nl_sv1917", "Judges"), ("1 Kongebog 3:5", "da_1871", "1 Kings"),
                             ("Første Kongebog 3:5", "da_1871", "1 Kings"), ("1 Krønikebog 1:1", "da_1871", "1 Chronicles"),
                             ("Salmerne 23:1", "da_1871", "Psalms"), ("Kolossenserne 1:1", "da_1871", "Colossians"),
                             ("ペテロの第一の手紙 1:1", "ja_bungo", "1 Peter"), ("ヨハネの第一の手紙 1:1", "ja_bungo", "1 John"),
                             ("コリント前書 1:1", "ja_bungo", "1 Corinthians"), ("コリント人への後の書 1:1", "ja_bungo", "2 Corinthians"),
                             ("ヨハネ傳福音書 3:16", "ja_bungo", "John"), ("列王紀略上 1:1", "ja_bungo", "1 Kings"),
                             ("歴代志略下 1:1", "ja_bungo", "2 Chronicles"), ("民數紀略 1:1", "ja_bungo", "Numbers"),
                             ("エレミヤ記 1:1", "ja_bungo", "Jeremiah"), ("ルツ記 1:1", "ja_bungo", "Ruth"),
                             ("使徒行傳 1:1", "ja_bungo", "Acts"), ("ロマ人への書 1:1", "ja_bungo", "Romans"),
                             ("ピレモンへの書 1:1", "ja_bungo", "Philemon"), ("ヨハネの默示録 1:1", "ja_bungo", "Revelation"),
                             ("1 Yohana 1:1", "sw_ulb", "1 John"), ("1 Samweli 1:1", "sw_ulb", "1 Samuel")):
    got = vs.parse_reference(query, abbr)
    check(f"{query!r} in {abbr}", got and got[0], own(abbr, english))
# Every Bible's own book names, with a verse and on their own, open that book
for abbr in bl._ABBREVIATIONS:
    bible = bl._load_data(abbr)
    words = {vs._book_key(n) for n in vs._WORD_NAMES.get(abbr.split("_")[0], ())}
    for name in bible:
        got = vs.parse_reference(f"{name} 1:1", abbr)
        alone = vs.parse_reference(name, abbr)
        if (got or [None])[0] != name or (vs._book_key(name) not in words and (alone or [None])[0] != name):
            R.check(f"{abbr} {name} opens {name}", False, (got, alone))

print(json.dumps({"parser_cases": len(CASES), "search_first_ms": round(first_ms, 1),
                  "search_ms": [(round(ms, 1), q, n) for ms, q, n in times]}, ensure_ascii=False))
R.finish()
