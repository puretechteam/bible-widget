# Bible Widget

A transparent desktop widget that displays Bible verses on your screen. It sits on top of everything, stays out of the way, and gives you a new verse every hour (or daily if you prefer).

![screenshot](screenshots/screenshot.png)
![translation menu](screenshots/translation-menu-ss.png)

## Features

- **Transparent overlay** — blends into your desktop, just shows the verse
- **Drag anywhere** — click and drag to move it wherever you want
- **Smart anchoring** — drag it where you want, and the window stays centered there even when the verse changes size
- **19 Bible translations** — 14 languages included: Arabic, Chinese (×2), German, Greek, English (×2), Esperanto, Spanish, Finnish (×2), French, Korean, Portuguese (×3), Romanian, Russian, Vietnamese
- **Translation picker** — right-click the tray icon to pick a specific Bible, or leave it on "All (Random)"
- **Hourly mode** — shows a random passage every hour
- **Daily mode** — shows the same verse all day (changes at midnight)
- **Change Quote** — instantly get a new verse from the tray menu
- **Run on Startup** — toggle in the tray menu to auto-launch when you log in. Survives folder renames — no broken paths.
- **Translation saves automatically** — your Bible selection is remembered between launches
- **Stats for Nerds** — double-click `start_widget.bat` to see uptime, verse count, and other stats in a terminal
- **Works offline** — all Bible data bundled locally, no internet needed after setup

## Requirements

- **Windows** (7, 10, or 11)
- **Python 3.7+** installed with "Add Python to PATH" checked
- **PySide6** (run `dependencies.bat` to install it automatically)

## Quick Start

1. Run `dependencies.bat` — this installs PySide6 if you don't have it
2. Double-click `start_widget_no_terminal.vbs` to launch the widget (no terminal window)
3. Right-click the cross icon in your system tray to change modes or exit

### Alternative launch

- `start_widget.bat` — launches with a terminal showing stats
- `stop_widget.bat` — kills the widget if needed

## Files

| File | What it does |
|------|-------------|
| `dependencies.bat` | Check/install PySide6 |
| `start_widget_no_terminal.vbs` | Launch widget silently |
| `start_widget.bat` | Launch widget with stats terminal |
| `stop_widget.bat` | Stop the widget |
| `widget_window.py` | The main widget code |
| `bible_loader.py` | Loads Bible data and picks verses |
| `bibles/` | All 19 Bible JSON files + index.json (~75 MB) |

## How It Works

The widget loads all 19 translations at startup (~75 MB in memory). Each time a new verse is requested, it picks a random book, chapter, and starting verse, then grabs 1-5 consecutive verses. The window automatically resizes to fit the text — long verses get smaller fonts and wrap to multiple lines.

In daily mode, the verse is seeded by the current date so everyone gets the same verse on the same day.

## Adding a New Translation

Place a Bible JSON file in the `bibles/` folder. The widget auto-discovers it on next launch. The file should follow one of these formats:

**Standard format (most Bibles):**
```json
{
  "Genesis": {
    "1": {
      "1": "In the beginning...",
      "2": "And the earth..."
    }
  }
}
```

**Array format (like the Arabic Bible):**
```json
[
  {
    "name": "Genesis",
    "chapters": [
      ["In the beginning...", "And the earth..."],
      [...]
    ]
  }
]
```

If you add a new file, also add its info to `bibles/index.json` for proper display names:
```json
{
  "language": "English",
  "versions": [
    { "name": "My Translation", "abbreviation": "my_trans" }
  ]
}
```

## License

<a href="https://github.com/puretechteam/bible-widget">Bible Widget</a> by <a href="https://github.com/puretechteam">Pure Tech</a> is marked <a href="https://creativecommons.org/publicdomain/zero/1.0/">CC0 1.0 Universal</a><img src="https://mirrors.creativecommons.org/presskit/icons/cc.svg" alt="" style="max-width: 1em;max-height:1em;margin-left: .2em;"><img src="https://mirrors.creativecommons.org/presskit/icons/zero.svg" alt="" style="max-width: 1em;max-height:1em;margin-left: .2em;">

All Bible texts are public domain. JSON data sourced from [thiagobodruk/bible](https://github.com/thiagobodruk/bible) (CC0).