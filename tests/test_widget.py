"""The widget and the Verses window, offscreen: history and Back, favorites, Find, the menus,
notifications, Copy, Save as Image, waking from sleep and the read-only folder warning."""
import os
import json
import time
import tempfile
from support import Results, TMP, app, isolate_widget, pictures

R = Results()
ww = isolate_widget()
qt = app()
from PySide6.QtWidgets import QApplication, QPushButton, QMessageBox
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
import verses as vs
import share_image as si

w = ww.BibleWidget(); w.show(); qt.processEvents()
toasts = []
real_notify = w._notify
w._notify = lambda message, on_click=None: (toasts.append(message), real_notify(message, on_click))


def wait_for(condition, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qt.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


# ----- History and Back -----
R.check("startup verse recorded", len(w._history.entries) == 1)
refs = [w.ref_label.text()]
for _ in range(3):
    w.show_new_verse(manual=True); refs.append(w.ref_label.text())
R.check("history has 4", len(w._history.entries) == 4, len(w._history.entries))
R.check("history newest first", [e["ref"] for e in w._history.entries] == refs[::-1])
w._go_back(); R.check("Back shows the previous verse", w.ref_label.text() == refs[2])
w._go_back(); R.check("Back again", w.ref_label.text() == refs[1])
R.check("Back does not record", len(w._history.entries) == 4)
w._go_back(); w._go_back()
R.check("Back stops at the oldest", w.ref_label.text() == refs[0] and not w._can_go_back())
w.show_new_verse(manual=True)
R.check("a new verse resets Back", w._history_pos == 0 and len(w._history.entries) == 5)

# ----- Favorites -----
ref, text, abbr = w._current()
w._toggle_favorite(); R.check("favorite added", w._favorites.contains(ref, abbr))
R.check("favorites saved", vs.VerseList(os.path.join(TMP, "favorites.json")).contains(ref, abbr))
w._toggle_favorite(); R.check("favorite removed", not w._favorites.contains(ref, abbr))
R.check("history saved", len(vs.VerseList(os.path.join(TMP, "history.json")).entries) == 5)

# ----- Copy Verse -----
w.show_passage("John 11:35", "Jesus wept.", "en_kjv")
toasts.clear()
w._copy_verse()
R.check("Copy Verse adds the translation", QApplication.clipboard().text() == "Jesus wept.\nJohn 11:35 (KJV)",
        repr(QApplication.clipboard().text()))
R.check("Copy Verse says it was copied", toasts == ["Verse copied"], toasts)
copy_action = next(a for a in w._menu.actions() if a.text() == "Copy Verse")
QApplication.clipboard().clear()
copy_action.trigger()  # the tray action passes Qt's "checked" flag; it must still copy
R.check("tray Copy Verse works", QApplication.clipboard().text().endswith("(KJV)"))

# ----- Verses window: Find -----
w._open_verses("find"); qt.processEvents()
vw = w._verses_window
R.check("Verses window opens", vw is not None and vw.isVisible())
vw.translation.setCurrentIndex(vw.translation.findData("en_kjv"))
vw.query.setText("Proverbs 30:4"); vw.search(); qt.processEvents()
R.check("a reference lists its chapter", vw.find_tree.topLevelItemCount() == 33, vw.find_tree.topLevelItemCount())
R.check("the verse searched for is selected", vw.find_tree.currentItem().text(0) == "Proverbs 30:4")
bold = [vw.find_tree.topLevelItem(i).text(0) for i in range(33) if vw.find_tree.topLevelItem(i).font(0).bold()]
R.check("only the verse searched for is bold", bold == ["Proverbs 30:4"], bold)
R.check("the widget shows it", w.ref_label.text() == "Proverbs 30:4")
R.check("the status names the chapter", vw.find_status.text().startswith("Proverbs 30"), vw.find_status.text())
vw.query.setText("John 11:35"); vw.search(); qt.processEvents()
R.check("a reference's status counts its whole chapter", "57 verses found" in vw.find_status.text(),
        vw.find_status.text())
vw.query.setText("living water"); vw.search()
n = vw.find_tree.topLevelItemCount()
R.check("word search fills the list", n == len(vs.search_words("living water", "en_kjv")) and n > 0, n)


def buttons(page_index):
    page = vw.tabs.widget(page_index)
    return [b.text() for b in page.findChildren(QPushButton)]


R.check("Find buttons", buttons(0) == ["Search", "Show on Widget", "Add to Favorites", "Copy Verse", "Save as Image"],
        buttons(0))
R.check("Favorites buttons", buttons(1) == ["Show on Widget", "Copy Verse", "Save as Image", "Remove"], buttons(1))
R.check("History buttons", buttons(2) == ["Clear History", "Show on Widget", "Add to Favorites", "Copy Verse",
                                          "Save as Image"], buttons(2))
R.check("no button takes Enter", not any(b.autoDefault() or b.isDefault() for b in vw.findChildren(QPushButton)))

# Keyboard: Enter shows the selected verse, Ctrl+C copies it
vw.activateWindow(); QTest.qWaitForWindowActive(vw)
vw.find_tree.setFocus()
vw.find_tree.setCurrentItem(vw.find_tree.topLevelItem(1))
picked = vw.find_tree.currentItem().text(0)
QTest.keyClick(vw.find_tree, Qt.Key_Return); qt.processEvents()
R.check("Enter shows the selected verse", w.ref_label.text() == picked, (w.ref_label.text(), picked))
QApplication.clipboard().clear()
QTest.keyClick(vw.find_tree, Qt.Key_C, Qt.ControlModifier); qt.processEvents()
R.check("Ctrl+C copies the selected verse", QApplication.clipboard().text().endswith(f"{picked} (KJV)"),
        repr(QApplication.clipboard().text()[-40:]))

# Right-click menu on a row
vw._row_menu(vw.find_tree, "find", vw.find_tree.visualItemRect(vw.find_tree.topLevelItem(0)).center())
qt.processEvents()  # let the menu open, as it does before anyone can click it
labels = [a.text() for a in vw._menu.actions()]
vw._menu.close(); qt.processEvents()
R.check("the window is active again after the menu", QApplication.activeWindow() is vw)
R.check("right-click menu on Find", labels == ["Show on Widget", "Add to Favorites", "Copy Verse", "Save as Image"],
        labels)

# Add to favorites from Find, then Delete removes it on the Favorites tab
vw._favorite(vw.find_tree.currentItem())
R.check("add a favorite from Find", len(w._favorites.entries) == 1)
vw.show_tab("favorites"); qt.processEvents()
R.check("Favorites tab lists it", vw.favorites_tree.topLevelItemCount() == 1)
R.check("History tab lists all", vw.history_tree.topLevelItemCount() == len(w._history.entries))
vw.favorites_tree.setFocus()
QTest.keyClick(vw.favorites_tree, Qt.Key_Delete); qt.processEvents()
R.check("Delete removes the favorite", len(w._favorites.entries) == 0 and vw.favorites_tree.topLevelItemCount() == 0)

# Ctrl+F goes back to Find with the search box ready
QTest.keyClick(vw.favorites_tree, Qt.Key_F, Qt.ControlModifier); qt.processEvents()
R.check("Ctrl+F opens Find", vw.tabs.currentIndex() == 0 and vw.query.hasFocus())
w._open_verses("history"); R.check("reopening reuses the window", w._verses_window is vw)


# Clear History asks first; Cancel (the default) keeps everything
def answer(button_text):
    def click():
        box = QApplication.activeModalWidget()
        if isinstance(box, QMessageBox):
            asked.append(box.text())
            next(b for b in box.buttons() if b.text() == button_text).click()
    QTimer.singleShot(50, click)


asked = []
before = len(w._history.entries)
answer("Cancel"); vw._clear_history()
R.check("Clear History asks first", asked == ["Remove every verse from History? This can't be undone."], asked)
R.check("Cancel keeps History", len(w._history.entries) == before and before > 0)
answer("Clear History"); vw._clear_history()
R.check("confirming clears History", len(w._history.entries) == 0 and vw.history_tree.topLevelItemCount() == 0)
asked.clear()
vw._clear_history()
R.check("an empty History is not asked about", asked == [])

# ----- The widget's right-click menu -----
w.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(10, 10), w.mapToGlobal(QPoint(10, 10))))
qt.processEvents()
menu = w._context_menu
labels = [a.text().replace("&&", "&") for a in menu.actions() if not a.isSeparator()]
R.check("right-click menu items", labels == ["Back", "Next Verse", "Add to Favorites", "Copy Verse", "Save as Image",
                                             "Find a Verse...", "Favorites & History..."], labels)
R.check("Back disabled with an empty history", not menu.actions()[0].isEnabled())
menu.close()
# The verse changes while the menu is open (the timer): Copy Verse still copies the one it was opened on
w._display("John 11:35", "Jesus wept.", "en_kjv", record=False)
w.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(10, 10), w.mapToGlobal(QPoint(10, 10))))
w._display("Genesis 1:1", "In the beginning God created the heaven and the earth.", "en_kjv", record=False)
copy_action = next(a for a in w._context_menu.actions() if a.text() == "Copy Verse")
QApplication.clipboard().clear()
copy_action.trigger()
w._context_menu.close()
R.check("right-click Copy Verse copies the verse the menu was opened on",
        QApplication.clipboard().text() == "Jesus wept.\nJohn 11:35 (KJV)", repr(QApplication.clipboard().text()))
R.check("tray menu has Verses...", "Verses..." in [a.text() for a in w._menu.actions()])

# ----- Notifications run their own action only -----
calls = []
w._notify("update", lambda: calls.append("update"))
w._notify("saved", lambda: calls.append("open image"))
w._on_toast_clicked()
w._notify("You're up to date")
w._on_toast_clicked()
R.check("a notification click runs only its own action", calls == ["open image"], calls)

# ----- Waking from sleep -----
before = w._quote_count
w._due = time.time() - 60
w._check_overdue()
R.check("an overdue verse changes at once", w._quote_count == before + 1 and w._timer.isActive())
before = w._quote_count
w._check_overdue()
R.check("not overdue: nothing changes", w._quote_count == before)

# ----- Save as Image: the file is written off the UI thread -----
w.show_passage("John 11:35", "Jesus wept.", "en_kjv")
toasts.clear()
t0 = time.perf_counter()
thread = w._save_image()
returned_ms = (time.perf_counter() - t0) * 1000
R.check("Save as Image hands the file to a worker thread", thread is not None and thread.name == "save-image")
thread.join(30)
R.check("the saved notification arrives", wait_for(lambda: any(t.startswith("Saved image to") for t in toasts)),
        toasts)
saved = sorted(os.listdir(pictures()))
data = open(os.path.join(pictures(), saved[-1]), "rb").read() if saved else b""
R.check("the PNG is complete", data.startswith(b"\x89PNG") and data.endswith(b"IEND\xaeB`\x82"), saved)
R.check("the image is on the clipboard", QApplication.clipboard().image().width() == 3200)
print(f"   Save as Image returned to the UI after {returned_ms:.0f} ms")

# Two saves in the same second get two files
first = set(os.listdir(pictures()))
threads = [w._save_image(), w._save_image()]
for t in threads:
    t.join(30)
new = sorted(set(os.listdir(pictures())) - first)
R.check("two saves at once make two files", len(new) == 2, new)

# Quitting while an image is being written: the app waits for the file before it shuts down
slow_save = si.save_card
si.save_card = lambda image, ref, folder=None: (time.sleep(0.8), slow_save(image, ref, folder))[1]
before = set(os.listdir(pictures()))
thread = w._save_image()
QApplication.instance().aboutToQuit.emit()  # what Exit (or Windows shutting down) sends
R.check("quitting waits for the image file", not thread.is_alive()
        and len(set(os.listdir(pictures())) - before) == 1, sorted(set(os.listdir(pictures())) - before))
si.save_card = slow_save
qt.processEvents()

# Save from the Verses window's History and Find tabs
w._open_verses("history"); qt.processEvents()
vw.history_tree.setCurrentItem(vw.history_tree.topLevelItem(0))
count = len(os.listdir(pictures()))
vw._save_image(vw.history_tree.currentItem())
R.check("Save as Image from History", wait_for(lambda: len(os.listdir(pictures())) == count + 1))

# The folder can't be written: the image is still on the clipboard
real_save = si.save_card
si.save_card = lambda image, ref, folder=None: (_ for _ in ()).throw(OSError("read-only"))
toasts.clear()
QApplication.clipboard().clear()
w._save_image().join(30)
R.check("save fails: the notification says it is on the clipboard",
        wait_for(lambda: toasts == ["The image is on the clipboard, but it could not be saved"]), toasts)
R.check("save fails: the image is still on the clipboard", QApplication.clipboard().image().width() == 3200)
si.save_card = real_save

# ----- Error state: nothing to keep -----
w._display("Error", "No Bible data loaded.", "")
w.contextMenuEvent(type("E", (), {"globalPos": lambda self: QPoint(0, 0)})())
labels = {a.text(): a.isEnabled() for a in w._context_menu.actions() if not a.isSeparator()}
w._context_menu.close()
R.check("error state disables Favorite, Copy and Save",
        not labels["Add to Favorites"] and not labels["Copy Verse"] and not labels["Save as Image"], labels)
n_fav = len(w._favorites.entries)
w._toggle_favorite(("Error", "x", ""))
R.check("an error can't be a favorite", len(w._favorites.entries) == n_fav)
R.check("Save as Image does nothing on an error", w._save_image() is None)
QApplication.clipboard().setText("unchanged")
w._copy_verse()
R.check("Copy Verse does nothing on an error", QApplication.clipboard().text() == "unchanged")

# ----- A folder settings can't be saved in -----
toasts.clear()
R.check("a writable folder gives no warning", w._warn_if_read_only() is False and toasts == [])
ww.APP_DIR = os.path.join(TMP, "missing", "folder")
R.check("a folder that can't be written is reported", w._warn_if_read_only() is True and len(toasts) == 1, toasts)
R.check("the warning names the folder problem", "can't be saved" in toasts[-1])
ww.APP_DIR = TMP

# ----- A damaged favorites file is kept, not overwritten -----
d = tempfile.mkdtemp(dir=TMP)
path = os.path.join(d, "favorites.json")
open(path, "w").write('[{"ref": "John 3:16", "text": "For God so loved",')  # cut off half way
lst = vs.VerseList(path)
lst.add("Psalm 23:1", "The LORD is my shepherd", "en_kjv")
kept = [n for n in os.listdir(d) if n.startswith("favorites.json.damaged-")]
R.check("a damaged favorites file is kept aside", len(kept) == 1
        and "John 3:16" in open(os.path.join(d, kept[0])).read() and len(json.load(open(path))) == 1, kept)

# ----- Translations taken out in 2.1.0 -----
import bible_loader as bl
for old, new in (("pt_nvi", "pt_almeida"), ("fi_pr", "fi_finnish"), ("ko_ko", "en_kjv"),
                 ("zh_cuv", "en_kjv"), ("ro_cornilescu", "en_kjv")):  # no free Chinese, Korean or Romanian Bible
    with open(w._translation_path, "w", encoding="utf-8") as f:
        f.write(old)
    w._translation = "en_kjv"
    w._load_translation_preference()
    R.check(f"a saved {old} moves to {new}", w._translation == new, w._translation)
R.check("an old favorite keeps its label", bl.get_short_name("fr_apee") == "Épée"
        and bl.get_translation_name("pt_nvi") == "Nova Versão Internacional")
R.check("a removed Bible's file is gone", "pt_nvi" not in {a for a, _, _ in bl.get_available_translations()})
# Someone who puts their own copy back (a file of that name) keeps it, with its own label
real_available, real_abbreviations = ww.get_available_translations, list(bl._ABBREVIATIONS)
ww.get_available_translations = lambda: real_available() + [("ko_ko", "My Korean Bible", "Korean")]
bl._ABBREVIATIONS.append("ko_ko")
try:
    with open(w._translation_path, "w", encoding="utf-8") as f:
        f.write("ko_ko")
    w._load_translation_preference()
    R.check("a Bible you put back yourself stays chosen", w._translation == "ko_ko", w._translation)
    R.check("...and is not labelled as the one taken out", bl.get_short_name("ko_ko") == "KO", bl.get_short_name("ko_ko"))
finally:
    ww.get_available_translations = real_available
    bl._ABBREVIATIONS[:] = real_abbreviations
    w._translation = "en_kjv"

# ----- Arabic text gets no letter spacing (it pulls joined letters apart and breaks الله) -----
w._display("يوحنا 3:16", "لانه هكذا احب الله العالم", "ar_svd", record=False)
arabic = (w.verse_font.letterSpacing(), w.ref_font.letterSpacing())
w._display("John 11:35", "Jesus wept.", "en_kjv", record=False)
latin = (w.verse_font.letterSpacing(), w.ref_font.letterSpacing())
R.check("Arabic verses and references have no letter spacing, others keep theirs",
        arabic == (0, 0) and latin == (0.5, 1.5), (arabic, latin))

# ----- Right-to-left menu languages -----
w._set_language("he"); qt.processEvents()
R.check("a Hebrew menu runs right to left", QApplication.layoutDirection() == Qt.RightToLeft)
w._set_language("fa"); qt.processEvents()
R.check("a Persian menu runs right to left", QApplication.layoutDirection() == Qt.RightToLeft)
w._set_language("en"); qt.processEvents()
R.check("an English menu runs left to right again", QApplication.layoutDirection() == Qt.LeftToRight)
from menu_strings import get_available_languages
names = [n for _, n in get_available_languages()]
R.check("29 menu languages, sorted ignoring accents", len(names) == 29 and names.index("Čeština") < names.index("Dansk"),
        names[:3])

# ----- Menu wording from human-made sources -----
from menu_strings import get_string, get_translated_language_name
# Qt's wording, which differs from the app's own strings: "Anwenden" (not "Übernehmen"), "Voreinstellungen"
R.check("Qt's own wording for the standard buttons", (get_string("Apply", "de"), get_string("Reset to Defaults", "de"),
        get_string("Reset to Defaults", "ko")) == ("Anwenden", "Voreinstellungen", "기본값 복원"))
R.check("a language Qt does not cover keeps its own wording", get_string("Cancel", "hi") not in ("", "Cancel"))
R.check("book names inside menu text come from that language's Bible",
        (get_string("Acts 4:24-26", "it"), get_string("Acts 4:24-26", "he")) == ("Atti 4:24-26", "מעשי השליחים 4:24-26")
        and "Jana 3:16" in get_string("Type a reference (John 3:16) or words", "pl"))
R.check("language names come from Unicode CLDR", (get_translated_language_name("German", "fr"),
        get_translated_language_name("Polish", "pl"), get_translated_language_name("Hebrew", "ja"))
        == ("Allemand", "polski", "ヘブライ語"))
w._set_language("de"); qt.processEvents()
w._open_color_settings(); qt.processEvents()
names = sorted(b.text() for b in w._color_dialog.findChildren(QPushButton) if b.text())
w._color_dialog.close()
R.check("the colors dialog's buttons speak German", {"OK", "Abbrechen", "Anwenden"} <= set(names), names)
from PySide6.QtGui import QAction


def notes():
    # Found through the menu's own children (a submenu fetched with QAction.menu() after a
    # rebuild can come back as a stale PySide wrapper at a reused address)
    return [a for a in w._menu.findChildren(QAction) if "suggest a fix" in a.text()]


R.check("a machine-translated menu says so, with a way to suggest a fix", len(notes()) == 1)
w._set_language("en"); qt.processEvents()
R.check("the English menu has no such note", notes() == [])

# ----- An update check does not rebuild the menu under the user's pointer -----
w._menu.popup(QPoint(0, 0)); qt.processEvents()
open_menu = w._menu
w._rebuild_menu()
R.check("the open menu is left alone", w._menu is open_menu and open_menu.isVisible())
open_menu.hide(); qt.processEvents(); qt.processEvents()
R.check("and rebuilt once it closes", w._menu is not open_menu)

# ----- Find starts in a translation that still exists -----
if w._verses_window is not None:
    w._verses_window.close(); qt.processEvents()
w._translation, w._shown_translation = None, "pt_nvi"
w._open_verses("find"); qt.processEvents()
vw = w._verses_window
R.check("Find opens on the replacement of a translation taken out", vw.translation.currentData() == "pt_almeida",
        vw.translation.currentData())

# ----- A failure while measuring puts the widget's own passage back -----
w._translation = "en_kjv"
w.show_new_verse(manual=True); qt.processEvents()
shown = w.ref_label.text()
real_find = vs.find


def failing_find(text, abbr, fits=None, limit=200):
    fits("Trial 1:1", "trial text that must not stay")
    raise RuntimeError("test")


vs.find = failing_find
vw.query.setText("John 3:16")
try:
    vw.search()
finally:
    vs.find = real_find
R.check("a failed Find leaves the widget showing its own verse", w.ref_label.text() == shown
        and "trial" not in w._verse_text, w.ref_label.text())
real_random = ww.get_random_passage
ww.get_random_passage = lambda *a, **k: (k["fits"]("Trial 2:2", "more trial text"), 1 / 0)
try:
    w.show_new_verse(manual=True)
except ZeroDivisionError:
    pass
finally:
    ww.get_random_passage = real_random
R.check("a failed verse change leaves the widget showing its own verse", w.ref_label.text() == shown
        and "trial" not in w._verse_text, w.ref_label.text())
R.check("Copy Verse still copies the verse on show", w._current()[0] == shown)

# ----- Next to an older version (2.0.2 takes no lock, it only answers on its pipe) -----
from PySide6.QtNetwork import QLocalServer
pipe = f"BibleWidget-test-{os.getpid()}"  # not the real name, so a widget you run is never asked
older = QLocalServer()
older.listen(pipe)
asked_older = []
older.newConnection.connect(lambda: asked_older.append(older.nextPendingConnection()))
R.check("a running older version keeps a new copy from starting", ww._claim_single_instance(pipe) is None)
R.check("the older version is asked to show itself", wait_for(lambda: bool(asked_older)), asked_older)
older.close()
lock = ww._claim_single_instance(pipe)
R.check("with no other copy running, the new one starts", lock is not None)
lock.unlock()
# The temp folder (where the lock file goes) is missing: still starts, still finds a running copy
real_env = {k: os.environ.get(k) for k in ("TMP", "TEMP")}
os.environ["TMP"] = os.environ["TEMP"] = os.path.join(TMP, "no-such-temp-folder")
try:
    lock = ww._claim_single_instance(pipe + "-2")
    R.check("a lock file that can't be made does not stop the widget starting", lock is not None)
    older = QLocalServer()
    older.listen(pipe + "-2")
    R.check("...and a running copy is still found", ww._claim_single_instance(pipe + "-2") is None)
    older.close()
finally:
    for k, v in real_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

# ----- Run on Startup when the launcher starts another copy (in a temp APPDATA) -----
real_appdata = os.environ.get("APPDATA")
temp_appdata = os.environ["APPDATA"] = tempfile.mkdtemp(prefix="bw-appdata-")
try:
    other = tempfile.mkdtemp(prefix="bw-other-copy-")
    open(os.path.join(other, "widget_window.py"), "w").close()
    def launcher(content=None):
        path = w._startup_file_path()
        if content is not None:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-16", newline="") as f:
                f.write(content)
        with open(path, encoding="utf-16", newline="") as f:
            return f.read()
    ours = w._startup_content("silent")
    theirs = ours.replace(ww.APP_DIR, other)
    launcher(theirs)
    R.check("a launcher that starts another copy shows Run on Startup as off", w._startup_mode() is None)
    ww.real_repair_startup(w)
    R.check("...and is left as it is", launcher() == theirs)
    w._set_startup(None)  # "Off", which shows as already chosen
    R.check("Off leaves another copy's launcher alone", os.path.exists(w._startup_file_path()) and launcher() == theirs)
    launcher(ours)
    R.check("a launcher that starts this copy shows Run on Startup as on", w._startup_mode() == "silent")
    w._set_startup(None)
    R.check("Off removes this copy's launcher", not os.path.exists(w._startup_file_path()))
    launcher(ours)
    launcher(ours.replace(ww.APP_DIR, other + "-moved-away"))
    ww.real_repair_startup(w)
    R.check("a launcher whose copy is gone is pointed at this one, same mode", launcher() == ours, launcher()[-120:])
finally:
    if real_appdata is None:
        os.environ.pop("APPDATA", None)
    else:
        os.environ["APPDATA"] = real_appdata
    import shutil
    for folder in (temp_appdata, other):
        shutil.rmtree(folder, ignore_errors=True)

# ----- Exit while an update is being unpacked: it waits until it's clear how the install went -----
import updater
from PySide6.QtWidgets import QApplication as QApp
quits = []
real_quit, real_start, real_can = QApp.quit, updater.start_install, updater.can_self_update
def failing_install(path, version, *a):
    time.sleep(0.8)
    return False
QApp.quit = staticmethod(lambda: quits.append("quit"))
updater.start_install, updater.can_self_update = failing_install, (lambda folder=None: True)
try:
    w._available_update = {"tag": "v9.9.9", "version": "9.9.9", "notes": "", "page": "",
                           "zip_url": "https://example.invalid/x.zip", "sha_url": "https://example.invalid/x.zip.sha256"}
    w._open_update_window()
    win = w._update_window
    with open(w._pid_path, "w") as f:
        f.write(str(os.getpid()))
    states = []
    QTimer.singleShot(200, lambda: (w._exit_app(), states.append((w._tray_icon.isVisible(), os.path.exists(w._pid_path), quits[:]))))
    download = tempfile.mkdtemp(prefix=updater.DOWNLOAD_PREFIX, dir=TMP)
    win._on_downloaded(os.path.join(download, "x.zip"))
    qt.processEvents()
    R.check("Exit while installing waits: tray icon and pid file stay, no quit yet",
            states == [(True, True, [])], states)
    R.check("...and quits once the install has failed", quits == ["quit"], quits)
    R.check("a failed install leaves no download behind", not os.path.exists(download))
finally:
    QApp.quit, updater.start_install, updater.can_self_update = real_quit, real_start, real_can
if w._update_window is not None:
    w._update_window.close()
qt.processEvents()

# ----- Settings files saved with a byte order mark (PowerShell 5.1, older Notepad) -----
before = (w._menu_lang, w._mode, w._translation, w._snap_corner)
for name, value in (("language.txt", "de"), ("mode.txt", "daily"), ("translation.txt", "de_luther"),
                    ("corner.txt", "bl\n\non")):
    with open(os.path.join(TMP, name), "w", encoding="utf-8-sig") as f:
        f.write(value)
w._load_language_preference(); w._load_mode(); w._load_translation_preference(); w._load_snap_corner()
got = (w._menu_lang, w._mode, w._translation, w._snap_corner)
R.check("language, mode, translation and corner with a byte order mark are read",
        got == ("de", "daily", "de_luther", "bl"), got)
w._menu_lang, w._mode, w._translation, w._snap_corner = before
w._save_language_preference(); w._save_mode(); w._save_translation_preference(); w._save_snap_corner()

# ----- Update checks -----
from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QNetworkReply


class FakeReply(QObject):
    finished = Signal()
    def __init__(self, tag):
        super().__init__()
        self.tag = tag
    def error(self): return QNetworkReply.NoError
    def errorString(self): return ""
    def readAll(self): return json.dumps({"tag_name": self.tag, "assets": []}).encode()


replies = []
w._updater._net.get = lambda request: (replies.append(FakeReply("v0.0.1")), replies[-1])[1]
real_auto = w._update_settings.auto
w._update_settings.auto = True
w._open_about()
w._check_for_updates(manual=True)   # Check for Updates in About, on a slow network...
w._check_for_updates(manual=False)  # ...while the daily check comes due
for reply in list(replies):
    reply.finished.emit()
qt.processEvents()
R.check("an automatic check during Check for Updates: About still gets its answer",
        w._about_window.status.text() == "You're up to date", (w._about_window.status.text(), len(replies)))
R.check("...and no check is left running", not w._updater.checking())

rel = lambda v: {"tag": "v" + v, "version": v, "notes": "", "page": "", "zip_url": None, "sha_url": None}
w._available_update = rel("9.1.0")
w._open_update_window()
w._manual_check = False
w._on_update_found(rel("9.2.0"))  # a newer release came out while the window was open
w._open_update_window()
qt.processEvents()
R.check("the Update window offers the newest release, not the one it first showed",
        w._update_window is not None and w._update_window._release["tag"] == "v9.2.0",
        w._update_window and w._update_window._release["tag"])
w._on_update_result(True)  # the release was withdrawn: the latest is no longer newer
R.check("a withdrawn release is no longer offered in the menu", w._available_update is None
        and not any("9.2.0" in a.text() for a in w._menu.actions()))
if w._update_window is not None:
    w._update_window.close()
w._update_settings.auto = real_auto
qt.processEvents()

# ----- Windows: a prayer opens once; a new menu language reaches every open window -----
from menu_strings import get_string
w._open_prayer("magnificat"); w._open_prayer("magnificat"); qt.processEvents()
R.check("opening the same prayer twice shows one window",
        sum(p._prayer_id == "magnificat" for p in w._prayer_windows) == 1, len(w._prayer_windows))
w._open_color_settings(); qt.processEvents()
w._set_language("de"); qt.processEvents()
R.check("a new menu language: About is shown in it", w._about_window is not None
        and w._about_window.windowTitle() == get_string("About Bible Widget", "de"),
        w._about_window and w._about_window.windowTitle())
R.check("...and Customize Colors", w._color_dialog is not None
        and w._color_dialog.windowTitle() == get_string("Customize Colors", "de"),
        w._color_dialog and w._color_dialog.windowTitle())
R.check("...and the open prayer", [p._lang for p in w._prayer_windows] == ["de"]
        and w._prayer_windows[0].amen_button.text() == get_string("Amen", "de"),
        [(p._lang, p.amen_button.text()) for p in w._prayer_windows])
w._set_language("en"); qt.processEvents()
for win in [w._about_window, w._color_dialog] + list(w._prayer_windows):
    if win is not None:
        win.close()
qt.processEvents()
R.check("closed windows are forgotten", w._about_window is None and w._color_dialog is None
        and not w._prayer_windows, (w._about_window, w._color_dialog, w._prayer_windows))

# Two windows on the same prayer (one reached with the arrows): both come back in the new language
a = w._open_prayer("lords-prayer", "en_kjv"); qt.processEvents(); a.move(100, 100)
b = w._open_prayer("jonahs-prayer", "en_kjv"); qt.processEvents(); b.move(700, 100)
b._prayer_id = "lords-prayer"; b._load_current_prayer()
places = sorted(p.pos().toTuple() for p in (a, b))
w._set_language("de"); qt.processEvents(); qt.sendPostedEvents(None, 0); qt.processEvents()
shown = sorted((p._prayer_id, p._lang, p.pos().toTuple()) for p in w._prayer_windows if p.isVisible())
R.check("two windows on the same prayer both come back in the new language, where they were",
        shown == [("lords-prayer", "de", places[0]), ("lords-prayer", "de", places[1])], (shown, places))
w._set_language("en"); qt.processEvents()
for p in list(w._prayer_windows):
    p.close()
qt.processEvents()

# The language changes while Clear History is asking: nothing breaks, the question still works
w._open_verses("history"); qt.processEvents()
vw = w._verses_window
before_clear = len(w._history.entries)
outcome = []
def change_language_then_answer():
    box = QApplication.activeModalWidget()
    outcome.append(type(box).__name__)
    w._set_language("de")
    qt.processEvents()
    box = QApplication.activeModalWidget()
    if box is not None:
        box.reject()  # "No"
QTimer.singleShot(200, change_language_then_answer)
try:
    vw._clear_history()
    outcome.append("returned")
except Exception as e:
    outcome.append(f"{type(e).__name__}: {e}")
qt.processEvents()
R.check("changing the language while Clear History asks raises nothing", outcome == ["QMessageBox", "returned"], outcome)
R.check("...and No keeps the history", len(w._history.entries) == before_clear, (len(w._history.entries), before_clear))
w._set_language("en"); qt.processEvents()
if w._verses_window is not None:
    w._verses_window.close()
qt.processEvents()

# A huge number in a hand-edited corner.txt is ignored, not a crash at every start
with open(os.path.join(TMP, "corner.txt"), "w", encoding="utf-8") as f:
    f.write("tl\n\noff\n99999999999,5")
before_pos = w._free_pos
try:
    w._load_snap_corner()
    loaded = "ok"
except Exception as e:
    loaded = repr(e)
R.check("a corner.txt with a huge position is ignored", loaded == "ok" and w._free_pos == before_pos, (loaded, w._free_pos))
w._save_snap_corner()

# ----- No Bible could be loaded: the card says so in the menu language -----
w._menu_lang = "de"
w._display("Error", "No Bible data loaded.", "")
R.check("the error card is in the menu language", w._verse_text == get_string("No verses found", "de"), w._verse_text)
w._set_language("fr")
R.check("...and follows a change of language", w._verse_text == get_string("No verses found", "fr"), w._verse_text)
w._set_language("en")
w._menu_lang = "en"
w.show_new_verse(manual=True)

# ----- The tray icon follows the taskbar turning light or dark on its own -----
import tray_icon
real_light = ww.taskbar_is_light
icons = []
real_set_icon = w._tray_icon.setIcon
w._tray_icon.setIcon = lambda icon: (icons.append(icon), real_set_icon(icon))
ww.taskbar_is_light = lambda: not w._tray_light
w._refresh_tray_icon()
ww.taskbar_is_light = lambda: w._tray_light
w._refresh_tray_icon()
ww.taskbar_is_light = real_light
R.check("the tray icon is redrawn when the taskbar changes, only then", len(icons) == 1, len(icons))

# Windows shutting down or signing out: noted in widget.pid, so the next start reports no crash
if os.name == "nt":
    import ctypes
    from ctypes import wintypes
    import crash_log
    saved = dict(crash_log._state)
    crash_log._state.update(app_dir=TMP, started="2026-11-11T09:00:00", ended=False)
    try:
        msg = wintypes.MSG()
        msg.message, msg.wParam = 0x0016, 1  # WM_ENDSESSION, the session is ending
        base = type(w).__mro__[1]
        real_native = base.nativeEvent
        base.nativeEvent = lambda self, event_type, message: (False, 0)  # Qt's own takes only its own messages
        try:
            w.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg))
        finally:
            base.nativeEvent = real_native
        pid_text = open(os.path.join(TMP, "widget.pid"), encoding="utf-8").read()
        R.check("Windows ending the session is noted in widget.pid",
                "ended=Windows is shutting down or signing out" in pid_text, pid_text)
    finally:
        crash_log._state.clear()
        crash_log._state.update(saved)

R.finish()
