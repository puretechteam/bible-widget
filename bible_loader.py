import json
import random
import re
import os
import datetime
from collections import OrderedDict

_BIBLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bibles")
_CACHE = OrderedDict()  # {abbreviation: bible_dict}, least recently used first
_CACHE_SIZE = 3
_ABBREVIATIONS = []  # ordered list of available abbreviations (files on disk)
_ALL_STARTS = {}  # {abbreviation: [(book, chapter, verse), ...]}
_LANGUAGE_NAMES = {}  # {abbreviation: {"lang": "English", "name": "King James Version"}}

_INDEX = None
_BOOK_NAMES = None

# Short labels shown after the reference, e.g. "John 3:16 (KJV)"
_SHORT_NAMES = {
    "ar_svd": "SVD",
    "zh_cuv": "CUV",
    "zh_ncv": "NCV",
    "de_schlachter": "Schlachter",
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
    "fi_finnish": "Finnish",
    "fi_pr": "PR",
    "fr_apee": "Épée",
    "ko_ko": "Korean",
    "pt_aa": "AA",
    "pt_acf": "ACF",
    "pt_nvi": "NVI",
    "ro_cornilescu": "Cornilescu",
    "ru_synodal": "Synodal",
    "vi_vietnamese": "Vietnamese",
}

# Characters lost to encoding errors in the source files, repaired by context
_TEXT_FIXES = {
    "zh_cuv": [
        ("那�生", "那裡生"),
        ("能�壞", "能蛀壞"),
        ("我�面", "我裡面"),
        ("長了�", "長了鏽"),
        ("那�要", "那鏽要"),
    ],
    "eo_esperanto": [("�", "'")],
    "vi_vietnamese": [("Ð", "Đ")],  # Icelandic eth used in place of Vietnamese D-stroke
}

# Esperanto x-system (cx -> ĉ, ux -> ŭ) used by the Esperanto source
_EO_X_RE = re.compile(r"([cghjsuCGHJSU])[xX]")
_EO_X_MAP = dict(zip("cghjsuCGHJSU", "ĉĝĥĵŝŭĈĜĤĴŜŬ"))

_CJK = r"⺀-鿿豈-﫿＀-￯"
_CJK_SPACE_RE = re.compile(rf"(?<=[{_CJK}])\s+|\s+(?=[{_CJK}])")
_FOOTNOTE_RE = re.compile(r"\s*\{[^{}]*:[^{}]*\}")


def _get_index():
    """Load and cache the index.json data for display names."""
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    path = os.path.join(_BIBLES_DIR, "index.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            _INDEX = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _INDEX = []
    return _INDEX


def _get_book_names():
    """Load and cache book_names.json (native book names and English aliases)."""
    global _BOOK_NAMES
    if _BOOK_NAMES is not None:
        return _BOOK_NAMES
    path = os.path.join(_BIBLES_DIR, "book_names.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            _BOOK_NAMES = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _BOOK_NAMES = {}
    return _BOOK_NAMES


def _build_language_names():
    """Populate _LANGUAGE_NAMES from the index."""
    global _LANGUAGE_NAMES
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
                if not isinstance(verses, dict):
                    continue
                chap_dict = {str(v): t for v, t in verses.items() if _is_real_verse(t)}
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
                    if _is_real_verse(text):
                        chap_dict[str(v_idx)] = text
                if chap_dict:
                    book_dict[chap_idx] = chap_dict
            if book_dict:
                normalized[book_name] = book_dict
        return normalized
    return {}


def _is_real_verse(text):
    # Some sources mark verses merged into the previous one with a lone "a"
    return isinstance(text, str) and text.strip() not in ("", "a")


def _load_file(filepath, abbr=""):
    """Load a single JSON Bible file."""
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return _normalize_bible(data, abbr)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[WARNING] Could not load {os.path.basename(filepath)}: {e}")
        return {}


def _load_data(translation=None):
    """Load one translation on demand (keeping a few recent ones cached).
    With no translation, returns the dict of currently cached translations.
    """
    _build_language_names()
    _discover()

    if translation is None:
        return dict(_CACHE)
    if translation in _CACHE:
        _CACHE.move_to_end(translation)
        return _CACHE[translation]
    if translation not in _ABBREVIATIONS:
        return {}

    bible = _load_file(os.path.join(_BIBLES_DIR, f"{translation}.json"), translation)
    if not bible:
        return {}
    _CACHE[translation] = bible
    while len(_CACHE) > _CACHE_SIZE:
        evicted, _ = _CACHE.popitem(last=False)
        _ALL_STARTS.pop(evicted, None)
    return bible


def _get_all_starts(translation):
    """Build and cache the flattened list of all verse starting positions
    for a specific translation."""
    if translation in _ALL_STARTS:
        return _ALL_STARTS[translation]

    bible = _load_data(translation)
    if not bible:
        return []

    all_starts = []
    for book_name, chapters in bible.items():
        for chap_num, verses in chapters.items():
            verse_nums = sorted(int(v) for v in verses.keys())
            for v in verse_nums:
                all_starts.append((book_name, int(chap_num), v))
    _ALL_STARTS[translation] = all_starts
    return all_starts


def _clean_text(text, translation=""):
    """Tidy verse text: drop translator footnotes, unwrap supplied words,
    remove spacing between Chinese characters and repair broken characters."""
    text = _FOOTNOTE_RE.sub("", text)
    if translation == "pt_aa":
        # Parenthetical remarks were stored in braces
        text = text.replace("{", "(").replace("}", ")")
    else:
        # KJV supplied words, e.g. {was} -> was
        text = text.replace("{", "").replace("}", "")
    text = " ".join(text.split())
    if translation.startswith("zh"):
        text = _CJK_SPACE_RE.sub("", text)
    elif translation.startswith("eo"):
        text = _EO_X_RE.sub(lambda m: _EO_X_MAP[m.group(1)], text)
    for bad, good in _TEXT_FIXES.get(translation, []):
        text = text.replace(bad, good)
    return text.replace("�", "")


def clean_text(text, translation=""):
    """Public form of _clean_text, for text from other sources such as prayers."""
    return _clean_text(text, translation)


def _build_passage(chapter, start_idx, end_idx, verse_nums, translation=""):
    verses_text = []
    for i in range(start_idx, end_idx + 1):
        verses_text.append(_clean_text(chapter[str(verse_nums[i])], translation))
    sep = "" if translation.startswith("zh") else " "
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
    return _SHORT_NAMES.get(translation, translation.split("_")[-1].upper())


def localize_reference(reference, translation):
    """Show an English reference with the translation's own book name,
    e.g. 'Matthew 6:9-13' -> 'Mateo 6:9-13' for es_rvr."""
    book, _, verses = reference.rpartition(" ")
    canonical = _get_book_names().get("canonical", [])
    bible = _load_data(translation)
    if book in canonical and len(bible) == len(canonical):
        return f"{list(bible)[canonical.index(book)]} {verses}"
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


def get_random_passage(translation=None, with_translation=False):
    """Returns (reference, text) for 1-5 consecutive verses.
    If translation is None, picks a random one from the available bibles.
    With with_translation=True, returns (reference, text, translation)."""
    _discover()
    if not _ABBREVIATIONS:
        return _result("Error", "No Bible data loaded.", "", with_translation)

    if translation is None:
        translation = random.choice(_ABBREVIATIONS)

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

    start_verse = verse_nums[start_idx]
    end_verse = verse_nums[end_idx]

    text = _build_passage(chapter, start_idx, end_idx, verse_nums, translation)
    reference = _format_reference(book, chapter_num, start_verse, end_verse)

    return _result(reference, text, translation, with_translation)


def get_verse_of_the_day(translation=None, with_translation=False):
    """Returns a deterministic (reference, text) based on the current date.
    If translation is None, picks a random one based on the date.
    With with_translation=True, returns (reference, text, translation)."""
    _discover()
    if not _ABBREVIATIONS:
        return _result("Error", "No Bible data loaded.", "", with_translation)

    today = datetime.date.today()
    local_random = random.Random(today.isoformat())

    if translation is None:
        translation = local_random.choice(_ABBREVIATIONS)

    all_starts = _get_all_starts(translation)
    if not all_starts:
        return _result("Error", f"No verses found for '{translation}'.", "", with_translation)

    book_name, chapter_num, start_verse = local_random.choice(all_starts)
    chapter = _load_data(translation)[book_name][chapter_num]
    verse_nums = sorted(int(v) for v in chapter.keys())
    start_idx = verse_nums.index(start_verse)

    span = local_random.choices([1, 2, 3, 4, 5], weights=[40, 25, 18, 12, 5])[0]
    end_idx = min(start_idx + span - 1, len(verse_nums) - 1)
    end_verse = verse_nums[end_idx]

    text = _build_passage(chapter, start_idx, end_idx, verse_nums, translation)
    reference = _format_reference(book_name, chapter_num, start_verse, end_verse)

    return _result(reference, text, translation, with_translation)


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
