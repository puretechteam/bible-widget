"""`BibleWidget.exe --self-test [report.json]`: exercise the app offscreen and report.

Used to prove a build works on its own. Settings go to a temp folder, so the user's files are
never touched. Exit code 0 when every check passes."""

import os
import sys
import json
import shutil
import tempfile
import traceback


def report_path(argv):
    """Where --self-test writes its report: the first argument after it that is not an option
    (--network may come before it), or None for the console."""
    rest = argv[argv.index("--self-test") + 1:] if "--self-test" in argv else []
    return next((a for a in rest if not a.startswith("-")), None)


def run():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)

    import colors
    import widget_window as ww
    import bible_loader as bl
    import verses
    from prayer_window import PrayerWindow
    from paths import FROZEN
    from version import VERSION

    tmp = tempfile.mkdtemp(prefix="BibleWidget-selftest-")
    colors._colors_path = lambda: os.path.join(tmp, "colors.txt")
    ww.APP_DIR = tmp
    ww.BibleWidget._repair_startup = lambda self: None

    checks = []

    def check(name, fn):
        try:
            ok = bool(fn())
            checks.append({"name": name, "ok": ok})
        except Exception:
            checks.append({"name": name, "ok": False, "error": traceback.format_exc(limit=3)})

    translations = bl.get_available_translations()
    check("34 translations found", lambda: len(translations) >= 34)  # more if the user added some
    for abbr, _, _ in translations:
        check(f"verse of the day: {abbr}", lambda a=abbr: bl.get_verse_of_the_day(a)[0] != "Error")
    def prayers():
        from prayer_window import get_prayers_list
        windows = [PrayerWindow("en_kjv", p["id"], "en") for p in get_prayers_list()]
        return len(windows) == 6 and all(win.text_label.text() for win in windows)
    check("6 prayers load", prayers)

    w = ww.BibleWidget()
    w.show()
    app.processEvents()
    check("widget shows a verse", lambda: bool(w.ref_label.text()) and bool(w._verse_text))
    check("colours dialog opens", lambda: (w._open_color_settings(), w._color_dialog.isVisible())[1])
    check("find by reference lists the chapter", lambda: (
        lambda r: r[2][0] == "John 3:16" and len(r[1]) == 36)(verses.find("John 3:16", "en_kjv")))
    check("find by words", lambda: len(verses.search_words("living water", "en_kjv")) > 0)
    check("verses window opens", lambda: (w._open_verses("find"), w._verses_window.isVisible())[1])
    check("about window opens", lambda: (w._open_about(), w._about_window.isVisible())[1])
    check("history records verses", lambda: len(w._history.entries) >= 1)

    def share():
        from share_image import render_card
        image = render_card("John 11:35", "Jesus wept.", "King James Version", colors.get_colors())
        return image.width() >= 1600 and image.height() >= 900
    check("share image renders", share)

    def share_unique():
        from share_image import render_card, MIN_CONTRAST
        a, b = (render_card("John 11:35", "Jesus wept.", "", colors.get_colors()) for _ in range(2))
        readable = all(float(i.text("Contrast")) >= MIN_CONTRAST for i in (a, b))
        return a.text("Background") != b.text("Background") and a != b and readable
    check("share image backgrounds are new each time and readable", share_unique)

    def qt_wording():
        # Qt's own translations ship with the build: Qt's German differs from the app's own strings
        # ("Anwenden", not "Übernehmen"; "Voreinstellungen", not "Auf Standard zurücksetzen")
        from menu_strings import get_string
        return (get_string("Apply", "de"), get_string("Reset to Defaults", "de")) == ("Anwenden", "Voreinstellungen")
    check("Qt's translations of the standard buttons load", qt_wording)

    def crash_figures():
        # widget.pid records the memory and handles every 10 minutes, for a run that ends unexpectedly
        import crash_log
        found = crash_log.resources()
        return sys.platform != "win32" or (found.get("memory_mb", 0) > 0 and found.get("handles", 0) > 0)
    check("crash logging reads memory and handles", crash_figures)

    if FROZEN:
        def shipped_list():
            # The next update reads this to keep the files you added or edited
            from paths import APP_DIR
            from updater import MANIFEST, _read_manifest
            files = _read_manifest(os.path.join(APP_DIR, "_internal", MANIFEST))
            return files is not None and "BibleWidget.exe" in files and "bibles/en_kjv.json" in files
        check("the list of shipped files is there", shipped_list)

    network_result = []
    if "--network" in sys.argv:
        def https_update_check():
            from PySide6.QtCore import QEventLoop, QTimer
            outcome = []
            loop = QEventLoop()
            w._updater.found.connect(lambda r: (outcome.append("found"), loop.quit()))
            w._updater.up_to_date.connect(lambda: (outcome.append("up_to_date"), loop.quit()))
            w._updater.failed.connect(lambda e: (outcome.append("failed: " + e), loop.quit()))
            timeout = QTimer()
            timeout.setSingleShot(True)
            timeout.timeout.connect(loop.quit)
            timeout.start(25000)
            w._updater.check(manual=True)
            loop.exec()
            timeout.stop()
            network_result.extend(outcome)
            return bool(outcome) and not outcome[0].startswith("failed")
        check("update check over HTTPS", https_update_check)

    failed = [c for c in checks if not c["ok"]]
    report = {"version": VERSION, "frozen": FROZEN, "python": sys.version.split()[0],
              "passed": len(checks) - len(failed), "failed": len(failed), "checks": checks,
              "update_check_result": network_result}
    shutil.rmtree(tmp, ignore_errors=True)
    text = json.dumps(report, indent=1)
    path = report_path(sys.argv)
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    elif sys.stdout is not None:
        print(text)
    return 0 if not failed else 1
