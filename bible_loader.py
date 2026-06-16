import json
import random
import os
import datetime

_DATA = None
_ALL_STARTS = None


def _load_data():
    global _DATA
    if _DATA is not None:
        return _DATA
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kjv.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            _DATA = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[ERROR] Could not load Bible data: {e}")
        _DATA = {}
    return _DATA


def _get_all_starts():
    """Build and cache the flattened list of all verse starting positions."""
    global _ALL_STARTS
    if _ALL_STARTS is not None:
        return _ALL_STARTS
    bible = _load_data()
    all_starts = []
    for book_name, chapters in bible.items():
        for chap_num_str, verses in chapters.items():
            verse_nums = sorted(int(v) for v in verses.keys())
            for v in verse_nums:
                all_starts.append((book_name, int(chap_num_str), v))
    _ALL_STARTS = all_starts
    return _ALL_STARTS


def _clean_text(text):
    """Remove KJV curly braces like {are} → are, keeping the words intact."""
    text = text.replace("{", "").replace("}", "")
    return " ".join(text.split())


def _build_passage(chapter, start_idx, end_idx, verse_nums):
    """Build joined verse text from chapter data."""
    verses_text = []
    for i in range(start_idx, end_idx + 1):
        verses_text.append(_clean_text(chapter[str(verse_nums[i])]))
    return " ".join(verses_text)


def _format_reference(book, chapter_num, start_verse, end_verse):
    """Format a Bible reference string."""
    if start_verse == end_verse:
        return f"{book} {chapter_num}:{start_verse}"
    return f"{book} {chapter_num}:{start_verse}-{end_verse}"


def get_random_passage():
    """Returns (reference, text) for 1-5 consecutive verses from a random location."""
    bible = _load_data()
    if not bible:
        return "Error", "Could not load Bible data."
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


def get_verse_of_the_day():
    """Returns a deterministic (reference, text) based on the current date.
    Same logic as get_random_passage but seeded by date."""
    bible = _load_data()
    if not bible:
        return "Error", "Could not load Bible data."

    today = datetime.date.today()
    local_random = random.Random(today.isoformat())

    # Pick starting point from cached list
    all_starts = _get_all_starts()
    book_name, chapter_num, start_verse = local_random.choice(all_starts)

    # Find how many verses are in this chapter from this point
    chapter = bible[book_name][str(chapter_num)]
    verse_nums = sorted(int(v) for v in chapter.keys())
    start_idx = verse_nums.index(start_verse)

    span = local_random.choices([1, 2, 3, 4, 5], weights=[40, 25, 18, 12, 5])[0]
    end_idx = min(start_idx + span - 1, len(verse_nums) - 1)
    end_verse = verse_nums[end_idx]

    text = _build_passage(chapter, start_idx, end_idx, verse_nums)
    reference = _format_reference(book_name, chapter_num, start_verse, end_verse)

    return reference, text


if __name__ == "__main__":
    print("=== Random Passage (multi-verse) ===")
    for i in range(5):
        ref, text = get_random_passage()
        print(f"  {ref}: {text[:80]}...")

    print("\n=== Verse of the Day ===")
    ref, text = get_verse_of_the_day()
    print(f"  {ref}: {text[:80]}...")