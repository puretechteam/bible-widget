"""Finding verses (by reference or by words) and the favorites / history lists."""

import os
import re
import json
import logging
import datetime
import unicodedata
import bible_loader as bl
from paths import read_json, write_text

log = logging.getLogger("bible_widget")

# Common abbreviations people type. These win over the source files' short codes, where "jn"
# means Jonah, and over full names in other languages ("Jo" is John, not the Portuguese "Jó").
_ENGLISH_ABBREVIATIONS = {
    "jn": "John", "jhn": "John", "jo": "John", "mat": "Matthew", "mrk": "Mark", "mr": "Mark",
    "luk": "Luke", "jdg": "Judges", "jdgs": "Judges", "jg": "Judges", "jb": "Job", "jnh": "Jonah",
    "sos": "Song of Solomon", "sng": "Song of Solomon", "ss": "Song of Solomon",
    "song": "Song of Solomon", "songofsongs": "Song of Solomon", "canticles": "Song of Solomon",
    "psa": "Psalms", "pss": "Psalms", "psalm": "Psalms", "qoh": "Ecclesiastes",
    "ezk": "Ezekiel", "php": "Philippians", "phm": "Philemon", "phlm": "Philemon", "jas": "James",
    "1jn": "1 John", "2jn": "2 John", "3jn": "3 John", "1pt": "1 Peter", "2pt": "2 Peter",
    "rv": "Revelation", "revelations": "Revelation", "rev": "Revelation",
    # Russian ones that are not the start of the name (Мф is Матфея)
    "мф": "Matthew", "мк": "Mark", "лк": "Luke", "ин": "John", "флп": "Philippians", "флм": "Philemon",
    "1ин": "1 John", "2ин": "2 John", "3ин": "3 John", "ис": "Isaiah", "нав": "Joshua",
}
# Words in front of a name that people type or leave out: "От Иоанна", "К Римлянам", "Послание к
# Римлянам", "До Римлян", "Księga Rodzaju", "Waraka wa Yakobo" (written as _fold gives them)
_NAME_PREFIXES = ("от", "к", "до", "від", "послание", "послания", "евангелие", "книга", "ksiega", "waraka wa",
                  "kitabu cha")

# Matched after NFKC, which turns full-width "３：１６－１８" into "3:16-18" and "～" into "~".
# "John 3:16-18", "John 3:16-4:2" (end in another chapter), "John 3-4" or "Jude 3-5" (no colon)
_DASH = r"\s*[-–—‐−~〜]\s*"
_REFERENCE_RE = re.compile(
    r"^\s*(?P<book>.+?)\s*(?P<chapter>\d{1,4})"
    rf"(?:\s*[:.,]\s*(?P<start>\d{{1,4}})(?:{_DASH}(?P<end>\d{{1,4}})(?:\s*[:.,]\s*(?P<end_verse>\d{{1,4}}))?)?"
    rf"|{_DASH}(?P<chapter_end>\d{{1,4}}))?\s*$"
)
_MAX_REFERENCE = 100  # longer than any reference: not one (and never slow to try)
_MAX_SEARCH_WORDS = 32
# Invisible marks that pasted right-to-left text carries
_INVISIBLE_RE = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069\u061c\ufeff\u00ad]")
# Apostrophes, and the Greek numeral sign, are typed and printed many ways (l'Éternel and l’Éternel,
# Α' and Α΄ Ιωάννου): all are matched as '. Replaced before NFKC, which would turn the tonos into a
# space and an accent.
_APOSTROPHES = "\u2019\u2018\u02bc\u0384\u00b4\u1ffd\u02b9\u0374"
_APOSTROPHE_TABLE = str.maketrans(dict.fromkeys(_APOSTROPHES, "'"))
_CJK_RE = re.compile(r"[⺀-鿿가-힯豈-﫿]")
_CHAPTER_PREVIEW = 5  # verses shown when only a chapter is given


def is_rtl(text):
    """True when the first strong character is right-to-left (Arabic, Hebrew)."""
    for ch in text:
        direction = unicodedata.bidirectional(ch)
        if direction in ("R", "AL"):
            return True
        if direction == "L":
            return False
    return False


# Letters typed one way and printed another, matched as one. Latin letters with a stroke, which
# have no accent to drop (Vietnamese đ, Polish ł). Persian and Arabic keyboards' yeh and kaf. The
# old kanji the Japanese Bungo-yaku is printed in, and the modern ones keyboards type (國 and 国).
_SAME_LETTER = {"đ": "d", "ł": "l", "ø": "o", "ı": "i", "ħ": "h",
                "ی": "ي", "ى": "ي", "ک": "ك"}
_SAME_LETTER.update(zip(
    "國聲體學會來爲與舊實惡戰靈傳從歸萬禮氣權齒圖團壽將對專晝盡數擧據處號變讀賣寶豫獨樂藥醫鹽劍險驗檢儉圓廣擴鑛經輕莖戀蠻灣亞壓圍壹隱營榮衞驛奧應歐毆櫻假價畫壞懷繪覺嶽渴卷陷寬歡觀關顏龜僞戲犧峽狹曉區驅勳徑惠揭溪繼鷄藝擊缺縣圈獻顯嚴效恆黑濟碎齋劑雜參慘棧蠶贊殘絲兒辭濕舍寫釋收澁獸縱肅敍稱涉燒證奬條狀乘淨剩疊孃讓釀觸寢愼眞粹醉隨髓樞靜齊攝竊淺踐錢潛纖禪雙壯爭莊搜插巢總聰藏臟屬續墮帶滯臺瀧擇澤單擔膽彈斷癡遲蟲鑄廳徵聽敕鎭遞鐵轉點黨盜燈當鬭德屆繩貳惱腦霸廢拜麥發髮拔晚祕濱甁拂佛竝邊辨瓣辯舖步豐襃沒飜每滿默餠譯餘譽搖樣謠賴亂覽龍兩獵綠壘淚勵隸齡爐勞樓錄黃卽旣槪晉",
    "国声体学会来為与旧実悪戦霊伝従帰万礼気権歯図団寿将対専昼尽数挙拠処号変読売宝予独楽薬医塩剣険験検倹円広拡鉱経軽茎恋蛮湾亜圧囲壱隠営栄衛駅奥応欧殴桜仮価画壊懐絵覚岳渇巻陥寛歓観関顔亀偽戯犠峡狭暁区駆勲径恵掲渓継鶏芸撃欠県圏献顕厳効恒黒済砕斎剤雑参惨桟蚕賛残糸児辞湿舎写釈収渋獣縦粛叙称渉焼証奨条状乗浄剰畳嬢譲醸触寝慎真粋酔随髄枢静斉摂窃浅践銭潜繊禅双壮争荘捜挿巣総聡蔵臓属続堕帯滞台滝択沢単担胆弾断痴遅虫鋳庁徴聴勅鎮逓鉄転点党盗灯当闘徳届縄弐悩脳覇廃拝麦発髪抜晩秘浜瓶払仏並辺弁弁弁舗歩豊褒没翻毎満黙餅訳余誉揺様謡頼乱覧竜両猟緑塁涙励隷齢炉労楼録黄即既概晋"))


class _FoldTable(dict):
    """Each character's folded form, worked out the first time it is seen (str.translate table)."""

    def __missing__(self, code):
        if chr(code) in _APOSTROPHES:
            self[code] = "'"
            return "'"
        # Invisible marks, and the zero-width joiner, which Hindi writes in some words and not others
        if chr(code) == "\u200d" or _INVISIBLE_RE.match(chr(code)):
            self[code] = ""
            return ""
        decomposed = unicodedata.normalize("NFKD", chr(code).casefold())
        # Marks are accents in Latin, Greek, Cyrillic, Hebrew and Arabic, so they are ignored. In
        # Indic and Southeast Asian scripts (Hindi, Tamil, Thai...) the virama and vowel signs
        # spell the word, so they are kept: without them प्रेम (prem) would match परम (param).
        # So are the Japanese voicing marks: ガ (ga) is not カ (ka).
        folded = self[code] = "".join(_SAME_LETTER.get(ch, ch) for ch in decomposed if not unicodedata.combining(ch)
                                      or 0x0900 <= ord(ch) <= 0x109F or ch in "\u3099\u309a")
        return folded


_FOLD_TABLE = _FoldTable()


def _fold(text):
    """Case- and accent-insensitive form used for matching."""
    if text.isascii():
        return text.lower()
    # Put Korean syllables back together afterwards (NFKD splits them into letters)
    return unicodedata.normalize("NFC", text.translate(_FOLD_TABLE))


# Numbered books written another way than "1 John": I Jana, Α' Ιωάννου, يوحنا الأولى, יוחנן א,
# اول یوحنا, ヨハネ第一, 歴代誌上. Each is read as its number in front ("1jana"), so typing either works.
_ORDINAL_RULES = [
    (re.compile(r"^(iii|ii|i)\s+"), {"i": "1", "ii": "2", "iii": "3"}, "prefix"),
    (re.compile(r"^([αβγ])\s*'\s*"), {"α": "1", "β": "2", "γ": "3"}, "prefix"),
    (re.compile(r"^(forste|forsta|anden|andra|tredje)\s+"),
     {"forste": "1", "forsta": "1", "anden": "2", "andra": "2", "tredje": "3"}, "prefix"),  # Første Kongebog
    (re.compile(r"\s+(الاولي|الاول|الثانيه|الثانية|الثاني|الثالثه|الثالثة|الثالث)$"),
     {"الاولي": "1", "الاول": "1", "الثانيه": "2", "الثانية": "2", "الثاني": "2",
      "الثالثه": "3", "الثالثة": "3", "الثالث": "3"}, "suffix"),
    (re.compile(r"\s+([אבג])$"), {"א": "1", "ב": "2", "ג": "3"}, "suffix"),
    (re.compile(r"^(اول|دوم|سوم)\s+"), {"اول": "1", "دوم": "2", "سوم": "3"}, "prefix"),
    (re.compile(r"\s*第([一二三])(?:の)?"), {"一": "1", "二": "2", "三": "3"}, "inside"),
    (re.compile(r"([前後后])(?:の)?[書书]"), {"前": "1", "後": "2", "后": "2"}, "inside"),  # コリント前書, 哥林多前書
    (re.compile(r"([上下])$"), {"上": "1", "下": "2"}, "suffix"),
]


def _numbered(folded):
    if not (" " in folded or "\u7b2c" in folded or "'" in folded or folded.endswith(("\u4e0a", "\u4e0b"))
            or "\u524d" in folded or "\u5f8c" in folded or "\u540e" in folded):
        return folded  # every rule needs a space, 第, a Greek numeral sign, a final 上 or 下, or 前/後
    for pattern, numbers, _ in _ORDINAL_RULES:
        m = pattern.search(folded)
        if m:
            return numbers[m.group(1)] + folded[:m.start()] + folded[m.end():]
    return folded


# Japanese and Chinese names are written with and without "letter", "book", "gospel" and their
# particles, in old and new characters: ペテロの第一の手紙 = ペテロ第一, ヨハネ傳福音書 = ヨハネ,
# 列王紀略上 = 列王記第一, ロマ人への書 = ローマ人への手紙. The keys leave those out.
_CJK_NAME_RE = re.compile(r"(?:による|伝)?福音書|人?への|[の之略]|手紙")
_CJK_LAST_RE = re.compile(r"[書记記书]$")
_CJK_SAME = str.maketrans("紀纪志", "記记誌")


def _book_key(text):
    key = re.sub(r"[\s.']", "", _numbered(_fold(text).strip()))
    if _CJK_RE.search(key):
        key = _CJK_LAST_RE.sub("", _CJK_NAME_RE.sub("", key.translate(_CJK_SAME)))
    return key


def _without_prefix(folded):
    """A folded name without the words in front of it: "послание к римлянам" -> "римлянам"."""
    shorter = True
    while shorter:
        shorter = False
        for prefix in _NAME_PREFIXES:
            if folded.startswith(prefix + " ") and folded[len(prefix) + 1:].strip():
                folded, shorter = folded[len(prefix) + 1:].strip(), True
    return folded


def _name_keys(name):
    """The keys a book name is found by: itself, and without the words in front of it."""
    return {_book_key(name), _book_key(_without_prefix(_fold(name).strip()))}


# Book names that are also common words of their Bible: typed on their own, they are a word search.
# Hebrew יהודה is Judah (612 verses) as well as Jude, יעקב is Jacob as well as James, ויקרא is "and he
# called" as well as Leviticus. Each is a word at least 100 times outside its book, and 10 times as
# often as in it (English names are left out: every Bible is opened by them). With a chapter they
# open the book: "יהודה 1".
_WORD_NAMES = {"ar": ("اللاويين", "متى", "يعقوب", "يهوذا"), "da": ("Jakob", "Judas"), "el": ("Ιούδα",),
               "eo": ("Levidoj",), "es": ("Hechos",), "fa": ("لاویان", "یعقوب", "یهودا"),
               "he": ("ויקרא", "יעקב", "יהודה"), "hi": ("याकूब", "यहूदा"), "hu": ("Zsidók",), "it": ("Giuda",),
               "ru": ("Иакова",), "sw": ("Mwanzo", "Kutoka", "Yuda"), "ta": ("யாக்கோபு", "யூதா"), "uk": ("Якова",)}


_BOOK_INDEX = {}


def _book_index():
    """Every known way to name each canonical book: {canonical_index: set(keys)},
    plus the short codes and English abbreviations as separate tiers. Built once."""
    names = bl._get_book_names()
    if id(names) in _BOOK_INDEX:
        return _BOOK_INDEX[id(names)]
    _BOOK_INDEX.clear()
    _BOOK_INDEX[id(names)] = _build_book_index(names)
    return _BOOK_INDEX[id(names)]


def _build_book_index(names):
    canonical = names.get("canonical", [])
    full = {i: {_book_key(n)} for i, n in enumerate(canonical)}
    for alias, target in names.get("aliases", {}).items():
        if target in canonical:
            full[canonical.index(target)].add(_book_key(alias))
    for native in names.get("names", {}).values():
        for i, n in enumerate(native[:len(canonical)]):
            full[i] |= _name_keys(n)
    english = {_book_key(k): canonical.index(v) for k, v in _ENGLISH_ABBREVIATIONS.items() if v in canonical}
    codes = {_book_key(c): i for i, c in enumerate(names.get("codes", []))}
    # For a book name on its own: the English names and aliases, and each language's names
    # ("de" and "de_luther" are both German), {key: lowest canonical index}
    def add(index, key, i):
        index[key] = min(i, index.get(key, i))

    english_names = {}
    for alias, target in [(n, n) for n in canonical] + list(names.get("aliases", {}).items()):
        if target in canonical:
            add(english_names, _book_key(alias), canonical.index(target))
    languages = {}
    for key, native in names.get("names", {}).items():
        lang = languages.setdefault(key.split("_")[0], {})
        for i, n in enumerate(native[:len(canonical)]):
            for k in _name_keys(n):
                add(lang, k, i)
    return canonical, full, english, codes, english_names, languages


def _translation_book(bible, translation, index, canonical):
    """The book name a translation uses for a canonical book index."""
    if canonical[index] in bible:
        return canonical[index]
    native = bl._native_names(translation)
    if native and len(native) == len(canonical) and native[index] in bible:
        return native[index]
    books = list(bible)
    if len(books) == len(canonical):
        return books[index]
    return None


def _resolve_book(query, bible, translation, exact_only=False):
    """Match what the user typed to a book of this translation, or None.
    exact_only: only a full book name counts (no abbreviations or prefixes)."""
    folded = _fold(query).strip()
    shorter = _without_prefix(folded)
    for text in (folded, shorter) if shorter != folded else (folded,):
        book = _resolve_key(_book_key(text), bible, translation, exact_only)
        if book is not None:
            return book
    return None


def _resolve_key(q, bible, translation, exact_only):
    if not q:
        return None
    canonical, full, english, codes, english_names, languages = _book_index()
    own = {_book_key(b): b for b in bible}

    def by_index(i):
        return _translation_book(bible, translation, i, canonical)

    # 1. Exact full name: this translation's own names, then common abbreviations, then any
    # language's names. A name on its own (exact_only) counts only in this Bible's language or
    # English: in English "Judas" is a word.
    if q in own:
        return own[q]
    if exact_only:
        found = [i for i in (english_names.get(q), languages.get(translation.split("_")[0], {}).get(q))
                 if i is not None]
        return by_index(min(found)) if found else None
    if q in english:
        return by_index(english[q])
    for i in sorted(full):
        if q in full[i]:
            return by_index(i)
    # 2. The source files' short codes
    if q in codes:
        return by_index(codes[q])
    # 3. Prefix of a name: this translation's own names, then the English names ("Dan" is Daniel,
    # not the Vietnamese "Dân Số Ký"), then this language's, then any language's, each in Bible order
    if len(q) >= 2:
        for key, book in own.items():
            if key.startswith(q):
                return book
        for names in (english_names, languages.get(translation.split("_")[0], {})):
            found = [i for key, i in names.items() if key.startswith(q)]
            if found:
                return by_index(min(found))
        for i in sorted(full):
            if any(name.startswith(q) for name in full[i]):
                return by_index(i)
    return None


def parse_reference(text, translation):
    """'John 3:16', 'jn 3:16-18', 'Juan 3', '1co13:4' -> (book, chapter, start, end) in this
    translation, or None. A chapter on its own gives its first few verses."""
    # Full-width digits and ：from CJK keyboards; direction marks from pasted right-to-left text
    text = _INVISIBLE_RE.sub("", unicodedata.normalize("NFKC", (text or "").translate(_APOSTROPHE_TABLE))).strip()
    if len(text) > _MAX_REFERENCE:
        return None
    m = _REFERENCE_RE.match(text)
    bible = bl._load_data(translation)
    start = end = None
    if not m:
        # A book name on its own ("1 John") opens chapter 1. Only a full name counts, so short
        # words that start a book name ("gen", "is", "ex") stay word searches.
        if len(text.split()) > 6 or _book_key(text) in {_book_key(n) for n in _WORD_NAMES.get(translation.split("_")[0], ())}:
            return None
        book = _resolve_book(text, bible, translation, exact_only=True)
        if book is None:
            return None
        chapter = min(bible[book])
    else:
        book = _resolve_book(m.group("book"), bible, translation)
        if book is None:
            return None
        chapter = int(m.group("chapter"))
        if m.group("start") is not None:
            start = int(m.group("start"))
            end = int(m.group("end") or start)
            if m.group("end_verse") is not None:  # John 3:16-4:2
                if end < chapter:
                    return None
                # Ending in a later chapter: to the end of this one (a passage is one chapter)
                end = int(m.group("end_verse")) if end == chapter else 10 ** 4
        elif len(bible[book]) == 1 and (chapter not in bible[book] or m.group("chapter_end")):
            # A one-chapter book with just verses: Jude 3 is Jude 1:3, Jude 1-3 is Jude 1:1-3
            start, end = chapter, int(m.group("chapter_end") or chapter)
            chapter = min(bible[book])
    verses = bible[book].get(chapter)
    if not verses:
        return None
    nums = sorted(int(v) for v in verses)

    def shown(n):  # not a verse that is only markup or "׃": the passage and the list leave it out
        return bl.has_words(bl._clean_text(verses[str(n)], translation))
    if start is None:
        preview = []
        for n in nums:
            if shown(n):
                preview.append(n)
                if len(preview) == _CHAPTER_PREVIEW:
                    break
        return (book, chapter, preview[0], preview[-1]) if preview else None
    if end < start:
        return None
    # A verse the file lacks (lost from its source) is skipped: the range starts at the next one
    inside = [n for n in nums if start <= n <= end]
    if not inside:
        return None
    first = next((n for n in inside if shown(n)), None)
    if first is None:  # only verses without words: the next verse that has some, else the one before
        first = next((n for n in nums if n > end and shown(n)), None) or next(
            (n for n in reversed(nums) if n < start and shown(n)), None)
        return None if first is None else (book, chapter, first, first)
    return book, chapter, first, next(n for n in reversed(inside) if shown(n))


def get_passage(translation, book, chapter, start, end, fits=None):
    """(reference, text) for a verse range; fits() may drop trailing verses, as elsewhere."""
    verses = bl._load_data(translation)[book][chapter]
    nums = sorted(int(v) for v in verses)
    return bl._passage_that_fits(book, chapter, verses, nums.index(start), nums.index(end), nums,
                                 translation, fits)


_SEARCH_CACHE = {}  # {translation: [(book, chapter, verse, folded_text)]}


def _search_rows(translation):
    if translation not in _SEARCH_CACHE:
        _SEARCH_CACHE.clear()  # one translation at a time keeps memory small
        rows = []
        for book, chapters in bl._load_data(translation).items():
            for chapter, verses in chapters.items():
                for v, text in verses.items():
                    rows.append((book, chapter, int(v), _fold(bl._clean_text(text, translation))))
        _SEARCH_CACHE[translation] = rows
    return _SEARCH_CACHE[translation]


def search_words(query, translation, limit=200):
    """Verses containing every word of the query (case and accents ignored).
    Words match at the start of a word, so 'love' finds 'loved'; Chinese, Japanese and
    Korean words match anywhere. Returns [(reference, text)] in Bible order."""
    patterns = _search_patterns(query)
    if not patterns:
        return []
    results = []
    bible = bl._load_data(translation)
    for book, chapter, v, folded in _search_rows(translation):
        if all(p.search(folded) for p in patterns):
            text = bl._clean_text(bible[book][chapter][str(v)], translation)
            results.append((bl._format_reference(book, chapter, v, v), text))
            if len(results) >= limit:
                break
    return results


def chapter_verses(translation, book, chapter):
    """Every verse of a chapter as [(reference, text, verse_number)]."""
    verses = bl._load_data(translation)[book][chapter]
    rows = [(bl._format_reference(book, chapter, v, v), bl._clean_text(verses[str(v)], translation), v)
            for v in sorted(int(n) for n in verses)]
    return [row for row in rows if bl.has_words(row[1])]  # not one that is only markup or "..."


_IN_WORD = None  # regex class of what continues a word, built on first use


def _in_word():
    """Letters and digits, plus every combining mark and the zero-width joiner: a Hindi or Tamil
    vowel sign or virama is part of the word, so the letter after it does not start a new one."""
    global _IN_WORD
    if _IN_WORD is None:
        ranges = []  # marks are all below U+30000 or in the U+E0000 block (variation selectors)
        for c in (*range(0x30000), *range(0xE0000, 0xE1000)):
            if unicodedata.category(chr(c))[0] == "M":
                if ranges and ranges[-1][1] == c - 1:
                    ranges[-1][1] = c
                else:
                    ranges.append([c, c])
        _IN_WORD = r"[\w\u200d" + "".join(rf"\U{a:08x}-\U{b:08x}" for a, b in ranges) + "]"
    return _IN_WORD


_ARABIC_SCRIPT_RE = re.compile(r"[\u0600-\u06ff]")


def _search_patterns(query):
    words = [w for w in _fold(query or "").split() if w][:_MAX_SEARCH_WORDS]
    patterns = []
    for w in words:
        if _CJK_RE.search(w):
            patterns.append(re.compile(re.escape(w)))
        elif _ARABIC_SCRIPT_RE.search(w):
            # Persian writes some words with an invisible non-joiner inside (mi-\u200c-konad), which keyboards
            # often leave out: it may be there or not between any two letters
            letters = [re.escape(c) for c in w.replace("\u200c", "")]
            patterns.append(re.compile(f"(?<!{_in_word()})" + "\u200c?".join(letters)))
        else:
            # Word start: the lookbehind goes after the word, so the regex scans for the word itself (fast)
            patterns.append(re.compile(f"{re.escape(w)}(?<!{_in_word()}{re.escape(w)})"))
    return patterns


def match_spans(query, text):
    """Where the words of a search appear in `text`, as merged (start, end) character ranges,
    matched the same way search_words matches (case and accents ignored)."""
    folded, owner = [], []  # folded text, and for each folded character the original index
    for i, ch in enumerate(text):
        piece = _fold(ch)
        folded.append(piece)
        owner.extend([i] * len(piece))
    folded = "".join(folded)
    spans = []
    for pattern in _search_patterns(query):
        for m in pattern.finditer(folded):
            if m.end() > m.start():
                end = owner[m.end() - 1] + 1
                while end < len(text) and unicodedata.combining(text[end]):
                    end += 1  # the accents on the last letter, which folding drops (Arabic shadda)
                spans.append((owner[m.start()], end))
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def find(query, translation, fits=None, limit=200):
    """A reference if the query looks like one, otherwise a word search.
    Returns (kind, results, passage):
    - 'reference': results is every verse of the chapter, as [(reference, text, verse)], and
      passage is (reference, text, start, end) for exactly what was asked for.
    - 'words': results is [(reference, text, None)] and passage is None."""
    parsed = parse_reference(query, translation)
    if parsed is not None:
        book, chapter, start, end = parsed
        ref, text = get_passage(translation, book, chapter, start, end, fits=fits)
        return "reference", chapter_verses(translation, book, chapter), (ref, text, start, end)
    return "words", [(ref, text, None) for ref, text in search_words(query, translation, limit)], None


class VerseList:
    """A saved list of passages (favorites or history), newest first, stored as JSON.
    Each entry: {"ref", "text", "translation", "at"}."""

    def __init__(self, path, cap=None):
        self.path = path
        self.cap = cap
        self.entries = self._load()

    def _load(self):
        try:
            data = read_json(self.path)  # also with a byte order mark, or saved in ANSI
            if isinstance(data, list):
                return [e for e in data if isinstance(e, dict)
                        and all(isinstance(e.get(k), str) for k in ("ref", "text", "translation"))]
            self._keep_damaged()
        except FileNotFoundError:
            pass
        except (ValueError, RecursionError):  # RecursionError: nested too deep to read
            log.exception("Could not read %s", os.path.basename(self.path))
            self._keep_damaged()
        except OSError:
            log.exception("Could not read %s; starting with an empty list", os.path.basename(self.path))
        return []

    def _keep_damaged(self):
        """Move an unreadable file aside before the next save would overwrite it, so the saved
        verses in it can still be recovered by hand."""
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        kept = f"{self.path}.damaged-{stamp}"
        try:
            os.replace(self.path, kept)
            log.warning("Kept the unreadable %s as %s; starting with an empty list",
                        os.path.basename(self.path), os.path.basename(kept))
        except OSError:
            log.exception("Could not keep a copy of %s", os.path.basename(self.path))

    def _save(self):
        try:
            # In one step: a crash never leaves a half-written file
            write_text(self.path, json.dumps(self.entries, ensure_ascii=False, indent=1))
        except OSError:
            log.exception("Could not save %s", os.path.basename(self.path))

    def find_index(self, ref, translation):
        for i, e in enumerate(self.entries):
            if e["ref"] == ref and e["translation"] == translation:
                return i
        return -1

    def contains(self, ref, translation):
        return self.find_index(ref, translation) >= 0

    def add(self, ref, text, translation, unique=True):
        if unique:
            i = self.find_index(ref, translation)
            if i >= 0:
                del self.entries[i]
        self.entries.insert(0, {"ref": ref, "text": text, "translation": translation,
                                "at": datetime.datetime.now().isoformat(timespec="seconds")})
        if self.cap is not None:
            del self.entries[self.cap:]
        self._save()

    def remove(self, ref, translation):
        i = self.find_index(ref, translation)
        if i >= 0:
            del self.entries[i]
            self._save()

    def clear(self):
        self.entries = []
        self._save()
