# Changelog

## v1.3.0

### Added
- **6 new Bible translations** — 19 → 25 total. American Standard Version (ASV), Darby Translation, Young's Literal Translation (YLT), Webster's Bible, Geneva Bible, and Wycliffe Bible — all public domain English translations from scrollmapper/bible_databases
- **6 prayers** — scrollable prayer window now includes: The Lord's Prayer, Jonah's Prayer, Mary's Magnificat, Job's Prayer, Acts 4:24-26, and Solomon's Prayer (1 Kings 8:22-24) — each available in all 25 translations
- **Prayer navigation** — ◀ and ▶ buttons in the prayer window to cycle between prayers without closing
- **QScrollArea** — long prayers (e.g. Mary's Magnificat) are now scrollable; non-long prayers display normally
- **Translated prayer names** — all 6 prayer names translated into all 14 menu languages
- **Copy Verse tray action** — copies the current reference and text to the clipboard from the tray menu
- **Stats tray action** — shows uptime, verse count, mode, and next refresh in a popup, removing the need to launch with a terminal
- **bibles/index.json** — updated with 6 new English translation entries

### Fixed
- **Window positioning on startup** — the widget now anchors its position before loading the first verse, preventing the window from jumping when verses resize with larger fonts or longer text. It opens at a fixed size in the top-right corner.
- **Prayer window constant size** — the prayer window no longer resizes itself when switching prayers; it keeps a fixed size and the prayer text scrolls within it via the scroll area
- **Constant widget size** — the main widget now uses a fixed size in the top-right corner; long verses shrink the font to fit instead of growing the window or moving it
- **Copy Verse separator** — copied verses now include a "—" separator between the reference and text so they don't run together when pasted

### Changed
- **prayer_window.py** — completely rewritten: accepts `prayer_id` parameter to select any prayer, added QScrollArea for the text, added prev/next navigation buttons, retains drag and Amen button
- **widget_window.py** — Prayers submenu now lists all 6 prayers individually instead of just "The Lord's Prayer"
- **Removed Psalm 51** — dropped the Psalm 51 prayer along with its tray menu entry and all 14 translation strings; 6 prayers remain
- **menu_strings.py** — added 6 new string keys per language for the additional prayer names
- **README.md** — updated translation count, prayer features, and file descriptions
- **Launcher cleanup** — deleted `start_widget.bat` (terminal stats launch is now redundant since Stats live in the tray menu) and renamed `start_widget_no_terminal.vbs` → `start_widget.vbs`. Startup detection now keys off the `pythonw` silent run

---

## v1.2.0

### Added
- **Prayers submenu** — "The Lord's Prayer" opens a dedicated overlay with Amen button
- **Menu Language submenu** — 14-language tray menu translation, fully independent from Bible Translation
- **menu_strings.py** — centralized translation dictionary for all tray menu text
- **Menu language persistence** — saved to `language.txt` and restored on launch
- **Change Quote** — moved to the top section (under Daily Mode) for faster access
- **Lord's Prayer in all 19 translations** — prayers/prayers.json covers every available Bible

### Fixed
- **Prayer window sizing** — full prayer text now renders without being cut off at the top or bottom
- **Prayer window layout** — removed alignment that squished labels into a narrow column

### Changed
- **Menu order** — Translation → Menu Language → Prayers → Run on Startup → Exit
- **Language and Translation are independent** — you can read the Bible in one language while keeping the tray menu in another

---

## v1.1.1

### Fixed
- **Startup now survives folder renames** — the `BibleWidget.vbs` file no longer hardcodes a launcher filename. It runs `widget_window.py` directly from the current folder location, so renaming the project folder for GitHub won't break startup.
- **Translation preference persists across restarts** — your selected Bible is saved to `translation.txt` and restored on launch. No more defaulting to "All (Random)" every time.
- **Tray menu checkmarks reflect saved preference** — the correct translation shows as checked when you open the menu.

### Changed
- **Startup repair logic** — if an old stale `.vbs` is detected, the widget silently rewrites it with the correct current path on launch.

---

## v1.1.0

### Added
- **19 Bible translations** (14 languages): Arabic, Chinese (×2), German, Greek, English (×2), Esperanto, Spanish, Finnish (×2), French, Korean, Portuguese (×3), Romanian, Russian, Vietnamese
- **Translation picker** — right-click the tray icon to choose a specific Bible, or "All (Random)" to shuffle across all 19
- **`bibles/` folder** — 19 JSON files (~75 MB) for fully offline use, plus `index.json` for proper display names
- **`bible_loader.py` fully rewritten** — auto-discovers Bibles, normalizes file formats, supports mixed schemas
- **README.md updated** with multi-translation features, adding new translations guide, and file descriptions

### Fixed
- **Long verses display correctly on first load** — widget auto-grows vertically to fit wrapped text
- **Citations properly centered** — no more left-aligned references after verse changes
- **Clean citation format** — `John 3:16` instead of `John 3:16 (en_kjv)`
- **Verse counter accurate** — stats now count actual verses, not chapters
- **UTF-8 BOM handling** — files with byte-order marks load correctly
- **Arabic Bible format supported** — array-format JSON normalized to standard structure
- **Mixed key type compatibility** — chapter/verse lookups work with both string and integer keys
- **Widget won't collapse** — minimum width guard prevents unusable text areas

### Removed
- **Window size presets** (Small/Medium/Large) — replaced with auto-sizing
- **Unused `QGraphicsDropShadowEffect` import**
- **Dead `_calc_font_size()` method** — orphaned from earlier refactor
- **Dead `translation` parameter** from citation formatter

### Changed
- **`dependencies.bat`** — restores auto-install for PySide6 (only Python must be pre-installed)
- **`_fit_text_size()`** — now uses `setFixedWidth()` + `boundingRect()` for precise word-wrap measurement
- **Verse span weighting** — 1 verse = 40%, 2 = 25%, 3 = 18%, 4 = 12%, 5 = 5%
- **Citation format** — clean `Book Chapter:Verse` with no translation suffix

---

## v1.0.0

- Initial release
- Single KJV Bible
- Hourly and daily modes
- Transparent frameless window
- Drag-to-move with smart anchoring
- System tray integration
- Startup launcher