# Changelog

## v2.0.0

### Added
- **Color customization** — pick your own colors for the verse text, background, and separator line. Right-click the tray icon → "Customize Colors..." to open a settings dialog with a color swatch and picker for each element. Click "Reset to Defaults" to restore the original dark style.
- **Smart corner snapping** — drag the widget anywhere on screen and release; it smoothly animates to the nearest screen corner (top-left, top-right, bottom-left, or bottom-right) with a 20px margin. The snap uses a 200ms animated ease-out.
- **Snap to Corners toggle** — right-click the tray icon → "Snap to Corners" to turn the corner-snapping behavior on or off. Your preference is saved and remembered.
- **Persistent corner + screen** — your chosen corner and the monitor it's anchored to are saved to `corner.txt`. The widget reopens in the same spot next launch, and falls back to your primary monitor if the saved one is disconnected.
- **Snap respects taskbar** — bottom corners snap above the taskbar, not behind it.
- **Show Widget button** — if the widget ever goes missing (e.g. after Win+D or a fullscreen app), right-click the tray icon → "Show Widget" to bring it back instantly.
- **Segoe UI font** — the widget now uses the Windows system font (Segoe UI) with Medium weight for both the verse and citation, giving a clean modern look that stays readable on translucent backgrounds.
- **Card shadow** — a soft drop shadow makes the widget look like a floating card on your desktop.
- **Gradient separator** — the line between the citation and the verse fades to transparent at the edges for a more polished look.

### Changed
- **Removed theme toggle** — the old dark/light theme switcher is gone. Use the new color customization to set any colors you want.
- **Removed `theme.py` and `theme.txt`** — replaced by the new `colors.py` module and `colors.txt` file.
- **`prayer_window.py`** — updated to use the new color system.

### Fixed
- **Widget sizing** — long verses no longer stretch the widget off-screen. The widget keeps a constant size and the font automatically shrinks to fit the text.
- **Customize Colors never opened**: the dialog class was defined after the app started, so clicking the menu item failed silently (with only a beep). It now opens every time.
- **Colors keep their transparency**: the color picker has an alpha slider, and partly transparent text and separator colors are respected instead of turning solid.
- **Prayer window opened blank**: the first prayer now loads straight away instead of only after pressing a navigation arrow. Opening a second prayer no longer closes the first.
- **Win+D (Show Desktop)**: the widget no longer re-parents itself into the desktop window (which made it jump, shrink, or land off-screen on multi-monitor setups). It now sits at the bottom of the window stack and rises above the desktop whenever the desktop is in focus, including after Win+D.
- **Dragging between monitors**: the widget no longer snaps back mid-drag. On release it snaps to the nearest corner of the monitor it was dropped on, and that monitor is remembered.
- **Widget slowly grew wider**: a margin miscalculation added 10 px of width every time the text was refit.
- **Translation menu**: the checkmark now stays on the chosen translation, and "All (Random)" is remembered after a restart.
- **Run on Startup**: added an "Off" option, "With console" now really opens a console (with live stats), and the launcher is no longer rewritten on every start.
- **Stats**: verse and book counts are for the current translation, and "Next refresh" shows when the timer will actually fire.
- **Daily mode** now changes at local midnight (it used to count 24 hours from when it was turned on) and the chosen mode is remembered.
- **Verse text cleanup**: KJV translator footnotes are removed, Portuguese (AA) asides show in parentheses, Chinese text no longer has a space between every character, Esperanto shows real letters (ĉ, ĝ, ŝ, ŭ) instead of "cx" spellings, broken characters in the Chinese and Esperanto texts are repaired, and placeholder verses in the Chinese Union Version are skipped.
- **Book names in each language**: references now show native book names (e.g. "Josué 15:42", "約書亞記" in Chinese) and English book names are consistent across translations ("1 Timothy", "Revelation").
- **Missing menu text**: "Show Widget", "Customize Colors...", "Snap to Corners" and the 5 newer prayer names are now translated in all 14 menu languages.
- **French translation name** in the menu now reads "La Bible de l'Épée".
- **Prayer fallback**: a prayer missing from the chosen translation now falls back to another Bible in the same language, then KJV, instead of Arabic.

### Added
- **Random Mode**: a new verse every 15 minutes.
- **Error log**: problems are written to `widget.log` in the app folder (capped at 512 KB), since the widget runs without a console.
- **Single instance**: launching the widget again brings the running one forward instead of opening a second copy.
- **Click the tray icon** to bring the widget forward for a few seconds.
- **Free position is remembered** when corner snapping is turned off.

### Changed
- **Lower memory use**: translations are loaded on demand (the current one plus a couple of recent ones) instead of all 25 at startup, cutting memory use from roughly 224 MB to well under 100 MB and making startup faster.
- **No taskbar flash**: the widget's window type is set before it is first shown.

---

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