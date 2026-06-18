# Changelog

## v1.1.1

### Fixed
- **Startup now survives folder renames** — the `BibleWidget.vbs` file no longer hardcodes a launcher filename. It runs `widget_window.py` directly from the current folder location, so renaming the project folder for GitHub won't break startup.
- **Translation preference persists across restarts** — your selected Bible is saved to `translation.txt` and restored on launch. No more defaulting to "All (Random)" every time.
- **Tray menu checkmarks reflect saved preference** — the correct translation shows as checked when you open the menu.

### Changed
- **Startup repair logic** — if an old stale `.vbs` is detected, the widget silently rewrites it with the correct current path on launch.

---

## v1.1.0-testing-deepseek-v4-flash

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