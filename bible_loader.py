import json
import random
import logging
import re
import os
import datetime
from collections import OrderedDict
from paths import app_path, read_json

_BIBLES_DIR = app_path("bibles")
_CACHE = OrderedDict()  # {abbreviation: bible_dict}, least recently used first
_CACHE_SIZE = 3
_ABBREVIATIONS = []  # ordered list of available abbreviations (files on disk)
_ALL_STARTS = {}  # {abbreviation: (verse count, [(first index, book, chapter, sorted verses), ...])}
_FAILED = set()  # translations whose file could not be loaded (tried once per run)
_LANGUAGE_NAMES = {}  # {abbreviation: {"lang": "English", "name": "King James Version"}}

_INDEX = None
_BOOK_NAMES = None

# Short labels shown after the reference, e.g. "John 3:16 (KJV)"
_SHORT_NAMES = {
    "ar_svd": "SVD",
    "cs_kralicka": "Kralická",
    "da_1871": "1871/1907",
    "de_luther": "Luther",
    "el_greek": "Greek",
    "en_asv": "ASV",
    "en_bbe": "BBE",
    "en_darby": "Darby",
    "en_geneva": "Geneva",
    "en_kjv": "KJV",
    "en_webster": "Webster",
    "en_wycliffe": "Wycliffe",
    "en_ylt": "YLT",
    "eo_esperanto": "Esperanto",
    "es_rvr": "RVR",
    "fa_opv": "OPV",
    "fi_finnish": "Finnish",
    "fr_lsg": "LSG",
    "he_delitzsch": "Delitzsch",
    "hi_irv": "IRV",
    "hu_karoli": "Károli",
    "it_riveduta": "Riveduta",
    "ja_bungo": "文語訳",
    "la_vulgate": "Vulgata",
    "nl_sv1917": "SV 1917",
    "pl_gdanska": "Gdańska",
    "pt_almeida": "Almeida",
    "ru_synodal": "Synodal",
    "sv_1917": "1917",
    "sw_ulb": "ULB",
    "ta_irv": "IRV",
    "tl_angbiblia": "Ang Biblia",
    "uk_kulish": "Kulish",
    "vi_vietnamese": "Vietnamese",
}

# Translations taken out in 2.1.0 (not free to share) and the one that takes each one's place,
# so a saved choice, favorite or history entry still works. "" means none in that language:
# the widget then uses its default. One you put back yourself (a file of that name) is used as is.
REPLACED = {
    "pt_nvi": "pt_almeida", "pt_acf": "pt_almeida", "pt_aa": "pt_almeida",
    "fi_pr": "fi_finnish", "fr_apee": "fr_lsg", "de_schlachter": "de_luther", "ko_ko": "",
    "zh_ncv": "", "zh_cuv": "", "ro_cornilescu": "",
}

# Their labels, for favorites and history saved before 2.1.0 (those keep their own text)
_RETIRED = {
    "pt_nvi": ("NVI", "Nova Versão Internacional"), "pt_acf": ("ACF", "Almeida Corrigida Fiel"),
    "pt_aa": ("AA", "Almeida Revisada Imprensa Bíblica"), "zh_ncv": ("NCV", "New Chinese Version"),
    "fi_pr": ("PR", "Pyhä Raamattu"), "fr_apee": ("Épée", "La Bible de l'Épée"),
    "de_schlachter": ("Schlachter", "Schlachter"), "ko_ko": ("Korean", "Korean Version"),
    "zh_cuv": ("CUV", "Chinese Union Version"),
    "ro_cornilescu": ("Cornilescu", "Versiunea Dumitru Cornilescu"),
}

# Written without spaces between words, so verses are joined without one
_NO_SPACE_SCRIPTS = ("zh", "ja")

# Characters lost to encoding errors in the source files, repaired by context
_TEXT_FIXES = {
    "eo_esperanto": [("�", "'"), ("Joram*", "Joram")],
    "vi_vietnamese": [("Ð", "Đ"),  # Icelandic eth used in place of Vietnamese D-stroke
                      (",;", ";")],
    # Doubled punctuation and empty brackets in the source files
    "en_geneva": [(",,", ",")],
    "sw_ulb": [(",,", ","), (",;", ";")],
    "ta_irv": [(",,", ",")],
    "pl_gdanska": [(", ( ),", ","), (",;", ";")],
    "fi_finnish": [(";,", ";"), (", ,", ",")],
    "it_riveduta": [("..;", ";")],
    # A zero typed for theta, and for nothing
    "el_greek": [("δυναμε0α", "δυναμεθα"), ("πλη0η", "πληθη"), ("εμα0ον", "εμαθον")],
    "es_rvr": [("Ela0d", "Elad")],
    "sv_1917": [(" >2 Krön 24,1 f.", "")],  # a cross reference left at the end of 2 Kings 12:1
    # Young's Literal opens quotes with a backquote: `Let light be;'
    "en_ylt": [("`", "‘"), ("'", "’")],
    "en_wycliffe": [("`", ""), ("dnA Y", "And Y")],  # ` marks a phrase that renders one Latin word
    # Young's Literal's italics codes: darkness <FI>is<Fi> on the face
}

# Per Bible: (pattern, replacement) rules for leftovers in the source files
_REGEX_FIXES = {
    # Italics codes
    "en_ylt": [(re.compile(r"</?F[Ii]>"), "")],
    # Footnote letters and the footnotes after the verse: "kaura (a) ... (a) Spelta eli Turkin kaura."
    "fi_finnish": [(re.compile(r"(?<=[.!?:;])\s*\([a-z]\)\s.*$"), ""), (re.compile(r"\s*\([a-z]\)"), ""),
                   (re.compile(r"\s*1 Aika K\. 11: 22\.$"), "")],
    # The psalm's number in another numbering: "Psalom.(75-)"
    "ru_synodal": [(re.compile(r"\s*\(\d+-\)"), "")],
    # A space after a colon: "diris:Jen" -> "diris: Jen". An x after a letter that already has
    # its hat: "ĉxar" (the source wrote the x-system on top of the real letter)
    "eo_esperanto": [(re.compile(r":(?=[^\W\d_])"), ": "), (re.compile(r"(?<=[ĉĝĥĵŝŭĈĜĤĴŜŬ])[xX]"), "")],
    # Letters whose UTF-8 bytes were garbled, repaired from the byte that survived. À, ê, ó (0xC3
    # first) with that byte turned into "@": "ch@\xa0ng" is "chàng" (by then the no-break space is a
    # plain one). Ờ, ứ, ặ (0xE1 0xBB or 0xE1 0xBA first) with those turned into "»" or "Ṁ", "º" or
    # "Ḁ": "Tr»\x9di" is "Trời", "giº·c" is "giặc". Đ (0xC4) and ư (0xC6) as "\x80" and "Ā".
    "vi_vietnamese": [(re.compile("@([ \u00a1-\u00bf])|([\u00bb\u1e40\u00ba\u1e00\u0080\u0100])+([\u0080-\u00bf])"),
                       lambda m: _vi_letter(m))],
}
# Run a Bible's rules only on verses that have one of these characters (most verses have none)
_REGEX_NEEDS = {"vi_vietnamese": lambda t: ("@" in t or "\u00bb" in t or "\u00ba" in t or "\u1e40" in t
                                             or "\u1e00" in t or "\u0080" in t or "\u0100" in t)}
_VI_LEAD = {"\u00bb": b"\xe1\xbb", "\u1e40": b"\xe1\xbb", "\u00ba": b"\xe1\xba", "\u1e00": b"\xe1\xba",
            "\u0080": b"\xc4", "\u0100": b"\xc6"}


def _vi_letter(m):
    if m.group(1) is not None:
        return bytes([0xC3, 0xA0 if m.group(1) == " " else ord(m.group(1))]).decode("utf-8")
    return (_VI_LEAD[m.group(2)] + bytes([ord(m.group(3))])).decode("utf-8")


# A gap in the text marked with stars ("*****" in the Arabic, "***" in the Bible in Basic English,
# where the Hebrew is unclear), shown as an ellipsis
_STARS_RE = re.compile(r"\s*\*{3,}\s*")
_PUNCTUATION = ".,;:!?\u060c\u061b\u061f)\u00bb\u201d\u2019"


def _ellipsis(m):
    """The stars as an ellipsis, with no space between it and punctuation after it."""
    return " \u2026" if m.string[m.end():m.end() + 1] in tuple(_PUNCTUATION) else " \u2026 "


_INVISIBLE = "\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff\u00ad"
_ANY_INVISIBLE_RE = re.compile(f"[{_INVISIBLE}]")
# A mark right before punctuation goes with the space before it: "كثيرا \u200e." is "كثيرا."
_INVISIBLE_RE = re.compile(rf"\s*[{_INVISIBLE}]+(?=[.,;:!?\u060c\u061b\u061f])|[{_INVISIBLE}]")

# Another numbering's verse left in the text: (14:55), (H13:1), (H 39:1), (H26-34)
_ALT_NUMBER_RE = re.compile(r"\s*\((?:[HG] ?)?\d+[:-]\d+\)(?=(\w?))")
# Esperanto x-system (cx -> ĉ, ux -> ŭ) used by the Esperanto source
_EO_X_RE = re.compile(r"([cghjsuCGHJSU])[xX]")
_EO_X_MAP = dict(zip("cghjsuCGHJSU", "ĉĝĥĵŝŭĈĜĤĴŜŬ"))

_CJK = r"⺀-鿿豈-﫿＀-￯"
_CJK_SPACE_RE = re.compile(rf"(?<=[{_CJK}])\s+|\s+(?=[{_CJK}])")
# Translator footnotes in braces, as in the KJV source: {shew...: Heb. uncover mine ear}. Most have
# a colon; the rest give a Hebrew or Greek reading or an "or" alternative: {make...; or, fulfil}.
# Two say what other copies have: {this verse is not found in most of the Greek copies}. The KJV's
# supplied words are in braces too ({was}), and never contain these.
_FOOTNOTE_RE = re.compile(r"\s*\{[^{}]*:[^{}]*\}")
_NOTE_RE = re.compile(r"\s*\{[^{}]*(?:\.\.\.|\bHeb\.|\bGr\.|\bor,|\bcopies\b)[^{}]*\}")


def _get_index():
    """Load and cache the index.json data for display names."""
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    path = os.path.join(_BIBLES_DIR, "index.json")
    try:
        data = read_json(path)  # users edit this file by hand
    except FileNotFoundError:
        data = []
    except (OSError, ValueError) as e:
        logging.getLogger("bible_widget").warning("Could not read bibles/index.json: %s", e)
        data = []
    if not isinstance(data, list):
        logging.getLogger("bible_widget").warning("bibles/index.json is not a list of languages; ignoring it")
        data = []
    # Keep only entries shaped as expected: {"language": ..., "versions": [{...}, ...]}
    _INDEX = [{**group, "versions": [v for v in group.get("versions", []) if isinstance(v, dict)]}
              for group in data if isinstance(group, dict) and isinstance(group.get("versions", []), list)]
    return _INDEX


def _get_book_names():
    """Load and cache book_names.json (native book names and English aliases)."""
    global _BOOK_NAMES
    if _BOOK_NAMES is not None:
        return _BOOK_NAMES
    path = os.path.join(_BIBLES_DIR, "book_names.json")
    try:
        data = read_json(path)
    except (OSError, ValueError) as e:
        logging.getLogger("bible_widget").warning("Could not read bibles/book_names.json: %s", e)
        data = {}
    _BOOK_NAMES = data if isinstance(data, dict) else {}
    return _BOOK_NAMES


def _build_language_names():
    """Populate _LANGUAGE_NAMES from the index."""
    if _LANGUAGE_NAMES:
        return
    idx = _get_index()
    for entry in idx:
        lang = entry.get("language", "Unknown")
        for ver in entry.get("versions", []):
            abbr = ver.get("abbreviation", "")
            name = ver.get("name", abbr)
            if abbr:
                _LANGUAGE_NAMES[abbr] = {"lang": lang, "name": name}


def _discover():
    """Find the translation files on disk without loading them."""
    if _ABBREVIATIONS or not os.path.isdir(_BIBLES_DIR):
        return
    for fname in sorted(os.listdir(_BIBLES_DIR)):
        if not fname.endswith(".json") or fname in ("index.json", "book_names.json"):
            continue
        _ABBREVIATIONS.append(fname[:-len(".json")])


def _native_names(abbr):
    """Return the list of 66 native book names for a translation, or None."""
    names = _get_book_names().get("names", {})
    return names.get(abbr) or names.get(abbr.split("_")[0])


def _normalize_bible(data, abbr=""):
    """Normalize different Bible JSON formats into {book: {chapter: {verse: text}}."""
    if isinstance(data, dict):
        # Dict format: {book: {chapter: {verse: text}}}; unify English book names
        aliases = _get_book_names().get("aliases", {})
        normalized = {}
        for book_name, chapters in data.items():
            if not isinstance(chapters, dict):
                continue
            book_dict = {}
            for chap, verses in chapters.items():
                if not isinstance(verses, dict) or not _is_number(chap):
                    continue
                # The same checks as _is_number and _is_real_verse, inline: this runs for every verse.
                # Fast path for plain verse numbers ("16"); any chapter where it drops a verse is
                # redone in full, which also reads "016", " 16" or other digits (Arabic-Indic, etc.)
                chap_dict = {v: t for v, t in verses.items()
                             if isinstance(t, str) and type(v) is str and v.isascii() and v.isdecimal() and v[0] != "0"
                             and t.strip() not in _NOT_VERSES}
                if len(chap_dict) != len(verses):
                    chap_dict = {str(int(v)): t for v, t in verses.items()
                                 if isinstance(t, str) and t.strip() not in _NOT_VERSES and str(v).strip().isdecimal()}
                if chap_dict:
                    book_dict[int(chap)] = chap_dict
            if book_dict:
                normalized[aliases.get(book_name, book_name)] = book_dict
        return normalized
    if isinstance(data, list):
        # Array format: [{abbrev, chapters: [[v1,v2,...], ...]}, ...]
        native = _native_names(abbr)
        if native is not None and len(native) != len(data):
            native = None
        normalized = {}
        for book_idx, book_entry in enumerate(data):
            if not isinstance(book_entry, dict):
                continue
            book_name = book_entry.get("name") or book_entry.get("abbrev", "Unknown")
            if native is not None:
                book_name = native[book_idx]
            chapters = book_entry.get("chapters", [])
            book_dict = {}
            for chap_idx, verse_list in enumerate(chapters, start=1):
                if not isinstance(verse_list, list):
                    continue
                chap_dict = {}
                for v_idx, text in enumerate(verse_list, start=1):
                    if isinstance(text, str) and text.strip() not in _NOT_VERSES:  # _is_real_verse, inline
                        chap_dict[str(v_idx)] = text
                if chap_dict:
                    book_dict[chap_idx] = chap_dict
            if book_dict:
                normalized[book_name] = book_dict
        return normalized
    return {}


def _is_number(key):
    # isdecimal, not isdigit: "²".isdigit() is True, but int("²") fails
    return str(key).strip().isdecimal()


# Some sources mark verses merged into the previous one with a lone "a"
# ("[]": an empty verse the source keeps for numbering, e.g. Basic English Matthew 17:21)
_NOT_VERSES = ("", "a", "[]")


def _is_real_verse(text):
    return isinstance(text, str) and text.strip() not in _NOT_VERSES


# "[ (Job 35:17) text ]" inside a verse: a verse the source file tucked onto the one before it
_EMBEDDED_VERSE = re.compile(r"\s*\[\s*\([^()\[\]]*?\s(\d+):(\d+)\)\s*([^\[\]]*?)\s*\]")
_EMBEDDED_START = re.compile(r"\[\s*\(")  # how every such verse starts: a quick test before the full one
# "( [ (I Timothy 6:22) ) text ]": the same, but the source wraps the marker in parentheses to say
# the text belongs to the verse it follows (as in the printed Arabic Bible): keep it there
_WRAPPED_VERSE = re.compile(r"\s*\(\s*\[\s*\([^()\[\]]*?\s\d+:\d+\)\s*\)\s*([^\[\]]*?)\s*\]")


def _split_embedded_verses(bible):
    """Some source files (for example a Korean Bible in 18 places) append
    whole verses to the last verse of a chapter as "[ (Book c:v) text ]". Give each its own
    verse number, so a passage never carries dozens of verses (Korean Job 35:16 held 32)."""
    for chapters in bible.values():
        for chapter, verses in chapters.items():
            if not _EMBEDDED_START.search("".join(verses.values())):  # one pass in C for the chapter
                continue
            changed = False
            for verse in list(verses):
                text = verses[verse]
                if not _EMBEDDED_START.search(text):
                    continue
                unwrapped = _WRAPPED_VERSE.sub(lambda m: " " + m.group(1), text).strip()
                if unwrapped != text:
                    verses[verse] = text = unwrapped
                    changed = True
                parts = [m for m in _EMBEDDED_VERSE.finditer(text)
                         if int(m.group(1)) == chapter and m.group(2) not in verses and m.group(3)]
                if not parts:
                    continue
                for m in reversed(parts):
                    text = text[:m.start()] + text[m.end():]
                    verses[m.group(2)] = m.group(3)
                verses[verse] = text.strip()
                changed = True
            if changed:
                chapters[chapter] = dict(sorted(verses.items(), key=lambda kv: int(kv[0])))
    return bible


def _load_file(filepath, abbr=""):
    """Load a single JSON Bible file."""
    try:
        return _split_embedded_verses(_normalize_bible(read_json(filepath), abbr))
    except (OSError, ValueError, TypeError, AttributeError) as e:
        # Unreadable, not UTF-8, not JSON, or not shaped like a Bible: skip this file
        logging.getLogger("bible_widget").warning("Could not load %s: %s", os.path.basename(filepath), e)
        return {}


def _load_data(translation=None):
    """Load one translation on demand (keeping a few recent ones cached).
    Returns {} if it is unknown or cannot be loaded."""
    _build_language_names()
    _discover()

    if translation in _CACHE:
        _CACHE.move_to_end(translation)
        return _CACHE[translation]
    if translation not in _ABBREVIATIONS or translation in _FAILED:
        return {}

    bible = _load_file(os.path.join(_BIBLES_DIR, f"{translation}.json"), translation)
    if not bible:
        _FAILED.add(translation)
        return {}
    _CACHE[translation] = bible
    while len(_CACHE) > _CACHE_SIZE:
        evicted, _ = _CACHE.popitem(last=False)
        _ALL_STARTS.pop(evicted, None)
    return bible


def _get_all_starts(translation):
    """Every verse of a translation in Bible order, counted by chapter: (total, chapters), where
    each chapter is (index of its first verse, book, chapter, its verse numbers in order).
    Kept per chapter rather than per verse: about 1,200 entries instead of 31,000."""
    if translation in _ALL_STARTS:
        return _ALL_STARTS[translation]

    bible = _load_data(translation)
    if not bible:
        return 0, []

    total, chapters_list = 0, []
    for book_name, chapters in bible.items():
        for chap_num, verses in chapters.items():
            verse_nums = sorted(int(v) for v in verses.keys())
            chapters_list.append((total, book_name, int(chap_num), verse_nums))
            total += len(verse_nums)
    _ALL_STARTS[translation] = (total, chapters_list)
    return _ALL_STARTS[translation]


def _start_at(starts, index):
    """The verse at a position counted from Genesis 1:1: (book, chapter, verse)."""
    import bisect
    total, chapters = starts
    i = bisect.bisect_right([first for first, _, _, _ in chapters], index) - 1
    first, book, chapter, verse_nums = chapters[i]
    return book, chapter, verse_nums[index - first]


def _clean_text(text, translation=""):
    """Tidy verse text: drop translator footnotes, unwrap supplied words,
    remove spacing between Chinese characters and repair broken characters."""
    # Each step runs only when the characters it looks for are there (this runs for every verse)
    if "{" in text:
        if ":" in text:
            text = _FOOTNOTE_RE.sub("", text)
        if "..." in text or "Heb." in text or "Gr." in text or "or," in text or "copies" in text:
            text = _NOTE_RE.sub("", text)
    if "(" in text:
        text = _ALT_NUMBER_RE.sub(lambda m: " " if m.group(1) else "", text)  # "Давида. (54:2)Ус": a space
    if not text.isascii():
        # Invisible marks left in some files (direction marks in the Arabic, byte order marks,
        # soft hyphens). Not U+200C: Persian needs that one to spell words correctly.
        if _ANY_INVISIBLE_RE.search(text):
            text = _INVISIBLE_RE.sub("", text)
    if translation == "el_greek":
        # The psalm titles were stored HTML-escaped: &lt;&lt;Ψαλμος του Δαβιδ.&gt;&gt;
        text = text.replace("&lt;&lt;", "\u00ab").replace("&gt;&gt;", "\u00bb")
        text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    # Supplied words, e.g. KJV {was} or Darby [land]; bracketed psalm titles and Selah
    for mark in "{}[]":
        if mark in text:
            text = text.replace(mark, "")
    text = " ".join(text.split())
    if translation.startswith(_NO_SPACE_SCRIPTS):
        text = _CJK_SPACE_RE.sub("", text)
    elif translation.startswith("eo"):
        text = _EO_X_RE.sub(lambda m: _EO_X_MAP[m.group(1)], text)
    for bad, good in _TEXT_FIXES.get(translation, []):
        text = text.replace(bad, good)
    needs = _REGEX_NEEDS.get(translation)
    if needs is None or needs(text):
        for pattern, good in _REGEX_FIXES.get(translation, []):
            text = pattern.sub(good, text)
    if "**" in text:
        text = _STARS_RE.sub(_ellipsis, text).strip()
    return text.replace("�", "") if "�" in text else text


def has_words(text):
    """False for a verse that is only markup or punctuation ("(H40:19)", "...", the Hebrew "׃"):
    its words were lost in the source file or merged into the verse before."""
    return any(ch.isalnum() for ch in text)


def clean_text(text, translation=""):
    """Public form of _clean_text, for text from other sources such as prayers."""
    return _clean_text(text, translation)


def _build_passage(chapter, start_idx, end_idx, verse_nums, translation=""):
    verses_text = []
    for i in range(start_idx, end_idx + 1):
        text = _clean_text(chapter[str(verse_nums[i])], translation)
        if has_words(text):  # a verse that is only markup or "..." adds nothing
            verses_text.append(text)
    sep = "" if translation.startswith(_NO_SPACE_SCRIPTS) else " "
    return sep.join(verses_text)


def _format_reference(book, chapter_num, start_verse, end_verse):
    ref = f"{book} {chapter_num}:{start_verse}"
    if start_verse != end_verse:
        ref += f"-{end_verse}"
    return ref


def get_short_name(translation):
    """Short label for a translation, e.g. 'en_kjv' -> 'KJV'."""
    if not translation:
        return ""
    _discover()
    if translation in _RETIRED and translation not in _ABBREVIATIONS:
        return _RETIRED[translation][0]
    return _SHORT_NAMES.get(translation, translation.split("_")[-1].upper())


def get_translation_name(translation):
    """Full name of a translation, including ones taken out since (for old favorites)."""
    _build_language_names()
    if translation in _LANGUAGE_NAMES:
        return _LANGUAGE_NAMES[translation]["name"]
    if translation in _RETIRED:
        return _RETIRED[translation][1]
    return translation


def localize_reference(reference, translation):
    """Show an English reference with the translation's own book name,
    e.g. 'Matthew 6:9-13' -> 'Mateo 6:9-13' for es_rvr."""
    book, _, verses = reference.rpartition(" ")
    canonical = _get_book_names().get("canonical", [])
    bible = _load_data(translation)
    if book not in canonical:
        return reference
    index = canonical.index(book)
    native = _native_names(translation) or []
    for name in ([native[index]] if index < len(native) else []) + [book]:
        if name in bible:
            return f"{name} {verses}"
    if len(bible) == len(canonical):
        return f"{list(bible)[index]} {verses}"
    return reference


def get_translation_info(translation):
    """Returns (book_count, verse_count) for one translation."""
    bible = _load_data(translation)
    verses = sum(len(c) for book in bible.values() for c in book.values())
    return len(bible), verses


def get_available_translations():
    """Returns a list of (abbreviation, display_name, language) tuples."""
    _build_language_names()
    _discover()
    result = []
    for abbr in _ABBREVIATIONS:
        info = _LANGUAGE_NAMES.get(abbr, {"lang": "Unknown", "name": abbr})
        result.append((abbr, info["name"], info["lang"]))
    return result


def get_random_passage(translation=None, with_translation=False, fits=None):
    """Returns (reference, text) for 1-5 consecutive verses.
    If translation is None, picks a random one from the available bibles.
    With with_translation=True, returns (reference, text, translation).
    fits(reference, text) -> bool, if given, drops trailing verses until the passage fits."""
    _discover()
    if not _ABBREVIATIONS:
        return _result("Error", "No Bible data loaded.", "", with_translation)

    if translation is None:
        translation = _first_loadable(random.sample(_ABBREVIATIONS, len(_ABBREVIATIONS)))

    bible = _load_data(translation)
    if not bible:
        return _result("Error", f"Translation '{translation}' not loaded.", "", with_translation)

    book = random.choice(list(bible.keys()))
    chapters = bible[book]
    chapter_num = random.choice(list(chapters.keys()))
    chapter = chapters[chapter_num]
    verse_nums = sorted(int(v) for v in chapter.keys())

    start_idx = random.randint(0, len(verse_nums) - 1)
    span = random.choices([1, 2, 3, 4, 5], weights=[40, 25, 18, 12, 5])[0]
    end_idx = min(start_idx + span - 1, len(verse_nums) - 1)

    reference, text = _passage_that_fits(book, chapter_num, chapter, start_idx, end_idx, verse_nums, translation, fits)
    return _result(reference, text, translation, with_translation)


def get_verse_of_the_day(translation=None, with_translation=False, fits=None):
    """Returns a deterministic (reference, text) based on the current date.
    If translation is None, picks a random one based on the date.
    With with_translation=True, returns (reference, text, translation).
    fits(reference, text) -> bool, if given, drops trailing verses until the passage fits."""
    _discover()
    if not _ABBREVIATIONS:
        return _result("Error", "No Bible data loaded.", "", with_translation)

    today = datetime.date.today()
    local_random = random.Random(today.isoformat())

    if translation is None:
        order = list(_ABBREVIATIONS)
        local_random.shuffle(order)
        translation = _first_loadable(order)

    all_starts = _get_all_starts(translation)
    if not all_starts[0]:
        return _result("Error", f"No verses found for '{translation}'.", "", with_translation)

    # randrange(n) draws exactly as choice() over a list of n did, so each day keeps its verse
    book_name, chapter_num, start_verse = _start_at(all_starts, local_random.randrange(all_starts[0]))
    chapter = _load_data(translation)[book_name][chapter_num]
    verse_nums = sorted(int(v) for v in chapter.keys())
    start_idx = verse_nums.index(start_verse)

    span = local_random.choices([1, 2, 3, 4, 5], weights=[40, 25, 18, 12, 5])[0]
    end_idx = min(start_idx + span - 1, len(verse_nums) - 1)

    reference, text = _passage_that_fits(book_name, chapter_num, chapter, start_idx, end_idx, verse_nums,
                                         translation, fits)
    return _result(reference, text, translation, with_translation)


def _passage_that_fits(book, chapter_num, chapter, start_idx, end_idx, verse_nums, translation, fits):
    """Build the longest passage from start_idx up to end_idx that fits() accepts.
    A single verse is always returned whole."""
    # Never start on a verse that is only markup or punctuation: it would show as an empty passage
    words = lambda i: has_words(_clean_text(chapter[str(verse_nums[i])], translation))
    first = start_idx
    while start_idx < len(verse_nums) - 1 and not words(start_idx):
        start_idx += 1
    if not words(start_idx):  # the rest of the chapter is empty: the verse before, then
        start_idx = first
        while start_idx > 0 and not words(start_idx):
            start_idx -= 1
    end_idx = max(end_idx, start_idx)

    def build(end):
        return (_format_reference(book, chapter_num, verse_nums[start_idx], verse_nums[end]),
                _build_passage(chapter, start_idx, end, verse_nums, translation))
    if fits is None or end_idx == start_idx or fits(*build(end_idx)):
        return build(end_idx)
    # More verses never fit better, so search for the last one that fits: about 8 checks
    # for Psalm 119:1-176 instead of 175, each a full text layout on the UI thread
    best, lo, hi = start_idx, start_idx + 1, end_idx - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if fits(*build(mid)):
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    return build(best)


def _first_loadable(candidates):
    """The first translation in `candidates` that loads (a broken file is skipped)."""
    for abbr in candidates:
        if _load_data(abbr):
            return abbr
    return candidates[0] if candidates else ""


def _result(reference, text, translation, with_translation):
    if with_translation:
        return reference, text, translation
    return reference, text


if __name__ == "__main__":
    print("=== Available Translations ===")
    for abbr, name, lang in get_available_translations():
        print(f"  {abbr}: {name} ({lang})")

    print("\n=== Random Passages ===")
    for i in range(5):
        ref, text, abbr = get_random_passage(with_translation=True)
        print(f"  {ref} ({get_short_name(abbr)}): {text[:80]}...")

    print("\n=== Verse of the Day (English KJV) ===")
    ref, text = get_verse_of_the_day("en_kjv")
    print(f"  {ref}: {text[:80]}...")

    print("\n=== Verse of the Day (Random) ===")
    ref, text = get_verse_of_the_day()
    print(f"  {ref}: {text[:80]}...")
