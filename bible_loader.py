import json
import random
import os
import datetime

_BIBLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bibles")
_DATA = {}  # {abbreviation: bible_dict}
_ABBREVIATIONS = []  # ordered list of loaded abbreviations
_ALL_STARTS = {}  # {abbreviation: [(book, chapter, verse), ...]}
_LANGUAGE_NAMES = {}  # {abbreviation: {"lang": "English", "name": "King James Version"}}

_INDEX = None


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


def _normalize_bible(data):
    """Normalize different Bible JSON formats into {book: {chapter: {verse: text}}."""
    if isinstance(data, dict):
        # Already in expected format: check first book
        first_book = next(iter(data.values()), None)
        if isinstance(first_book, dict):
            first_chap = next(iter(first_book.values()), None)
            if isinstance(first_chap, dict):
                return data  # Standard format
    if isinstance(data, list):
        # Array format: [{abbrev, chapters: [[v1,v2,...], ...]}, ...]
        normalized = {}
        for book_entry in data:
            if not isinstance(book_entry, dict):
                continue
            book_name = book_entry.get("name") or book_entry.get("abbrev", "Unknown")
            chapters = book_entry.get("chapters", [])
            book_dict = {}
            for chap_idx, verse_list in enumerate(chapters, start=1):
                if not isinstance(verse_list, list):
                    continue
                chap_dict = {}
                for v_idx, text in enumerate(verse_list, start=1):
                    if text:
                        chap_dict[str(v_idx)] = text
                if chap_dict:
                    book_dict[chap_idx] = chap_dict
            if book_dict:
                normalized[book_name] = book_dict
        return normalized
    return {}


def _load_file(filepath):
    """Load a single JSON Bible file."""
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return _normalize_bible(data)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[WARNING] Could not load {os.path.basename(filepath)}: {e}")
        return {}


def _load_data(translation=None):
    """Load all Bible data from the bibles/ directory.
    If translation is specified, only load that one.
    Returns the full _DATA dict.
    """
    global _DATA, _ABBREVIATIONS, _ALL_STARTS

    # Build language names cache
    _build_language_names()

    # If no bibles loaded yet, discover and load all
    if not _DATA:
        if not os.path.isdir(_BIBLES_DIR):
            print(f"[ERROR] Bibles directory not found: {_BIBLES_DIR}")
            return {}

        for fname in sorted(os.listdir(_BIBLES_DIR)):
            if not fname.endswith(".json") or fname == "index.json":
                continue
            abbr = fname.replace(".json", "")
            filepath = os.path.join(_BIBLES_DIR, fname)
            bible = _load_file(filepath)
            if bible:
                _DATA[abbr] = bible
                _ABBREVIATIONS.append(abbr)

    if translation is not None:
        # Return just the one translation's data
        return _DATA.get(translation, {})
    return _DATA


def _get_all_starts(translation):
    """Build and cache the flattened list of all verse starting positions
    for a specific translation."""
    global _ALL_STARTS
    if translation in _ALL_STARTS:
        return _ALL_STARTS[translation]

    bible = _load_data(translation)
    if not bible:
        return []

    all_starts = []
    for book_name, chapters in bible.items():
        for chap_num_str, verses in chapters.items():
            verse_nums = sorted(int(v) for v in verses.keys())
            for v in verse_nums:
                all_starts.append((book_name, int(chap_num_str), v))
    _ALL_STARTS[translation] = all_starts
    return all_starts


def _clean_text(text):
    """Remove KJV/Peshitta/etc curly braces like {are} → are."""
    text = text.replace("{", "").replace("}", "")
    return " ".join(text.split())


def _build_passage(chapter, start_idx, end_idx, verse_nums):
    verses_text = []
    for i in range(start_idx, end_idx + 1):
        verses_text.append(_clean_text(chapter[str(verse_nums[i])]))
    return " ".join(verses_text)


def _format_reference(book, chapter_num, start_verse, end_verse):
    ref = f"{book} {chapter_num}:{start_verse}"
    if start_verse != end_verse:
        ref += f"-{end_verse}"
    return ref


def get_available_translations():
    """Returns a list of (abbreviation, display_name, language) tuples."""
    _load_data()
    _build_language_names()
    result = []
    for abbr in _ABBREVIATIONS:
        info = _LANGUAGE_NAMES.get(abbr, {"lang": "Unknown", "name": abbr})
        result.append((abbr, info["name"], info["lang"]))
    return result


def get_random_passage(translation=None):
    """Returns (reference, text) for 1-5 consecutive verses.
    If translation is None, picks a random one from loaded bibles."""
    _load_data()
    if not _DATA:
        return "Error", "No Bible data loaded."

    if translation is None:
        translation = random.choice(_ABBREVIATIONS) if _ABBREVIATIONS else ""

    bible = _DATA.get(translation, {})
    if not bible:
        return "Error", f"Translation '{translation}' not loaded."

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

    text = _build_passage(chapter, start_idx, end_idx, verse_nums)
    reference = _format_reference(book, chapter_num, start_verse, end_verse)

    return reference, text


def get_verse_of_the_day(translation=None):
    """Returns a deterministic (reference, text) based on the current date.
    If translation is None, picks a random one based on the date."""
    _load_data()
    if not _DATA:
        return "Error", "No Bible data loaded."

    today = datetime.date.today()
    local_random = random.Random(today.isoformat())

    if translation is None:
        translation = local_random.choice(_ABBREVIATIONS) if _ABBREVIATIONS else ""

    all_starts = _get_all_starts(translation)
    if not all_starts:
        return "Error", f"No verses found for '{translation}'."

    book_name, chapter_num, start_verse = local_random.choice(all_starts)
    bible = _DATA.get(translation, {})
    book_data = bible[book_name]
    chapter = book_data.get(str(chapter_num)) or book_data.get(chapter_num)
    verse_nums = sorted(int(v) for v in chapter.keys())
    start_idx = verse_nums.index(start_verse)

    span = local_random.choices([1, 2, 3, 4, 5], weights=[40, 25, 18, 12, 5])[0]
    end_idx = min(start_idx + span - 1, len(verse_nums) - 1)
    end_verse = verse_nums[end_idx]

    text = _build_passage(chapter, start_idx, end_idx, verse_nums)
    reference = _format_reference(book_name, chapter_num, start_verse, end_verse)

    return reference, text


if __name__ == "__main__":
    print("=== Available Translations ===")
    for abbr, name, lang in get_available_translations():
        print(f"  {abbr}: {name} ({lang})")

    print("\n=== Random Passages ===")
    for i in range(5):
        ref, text = get_random_passage()
        print(f"  {ref}: {text[:80]}...")

    print("\n=== Verse of the Day (English KJV) ===")
    ref, text = get_verse_of_the_day("en_kjv")
    print(f"  {ref}: {text[:80]}...")

    print("\n=== Verse of the Day (Random) ===")
    ref, text = get_verse_of_the_day()
    print(f"  {ref}: {text[:80]}...")