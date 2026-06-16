# Bible Widget

A transparent desktop widget that displays Bible verses on your screen. It sits on top of everything, stays out of the way, and gives you a new verse every hour (or daily if you prefer).

![screenshot](screenshot.png)

## Features

- **Transparent overlay** — blends into your desktop, just shows the verse
- **Drag anywhere** — click and drag to move it wherever you want
- **Smart anchoring** — drag it where you want, and the window stays centered there even when the verse changes size
- **Hourly mode** — shows a random passage every hour
- **Daily mode** — shows the same verse all day (changes at midnight)
- **Change Quote** — instantly get a new verse from the tray menu
- **Run on Startup** — toggle in the tray menu to auto-launch when you log in
- **Stats for Nerds** — double-click `start_widget.bat` to see uptime, verse count, and other stats in a terminal

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
| `bible_loader.py` | Loads the Bible data and picks verses |
| `kjv.json` | The King James Version Bible (public domain) |
| `screenshot.png` | Github screenshot image |

## License

<a href="https://github.com/puretechteam/bible-widget">Bible Widget</a> by <a href="https://github.com/puretechteam">Pure Tech</a> is marked <a href="https://creativecommons.org/publicdomain/zero/1.0/">CC0 1.0 Universal</a><img src="https://mirrors.creativecommons.org/presskit/icons/cc.svg" alt="" style="max-width: 1em;max-height:1em;margin-left: .2em;"><img src="https://mirrors.creativecommons.org/presskit/icons/zero.svg" alt="" style="max-width: 1em;max-height:1em;margin-left: .2em;">

The KJV Bible text is public domain. The JSON data is from [thiagobodruk/bible](https://github.com/thiagobodruk/bible) (CC0).