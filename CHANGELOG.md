# Changelog

## v2.1.0 (2026-11-12)

### A correction and an apology
Versions 1.1.0 through 2.0.2 included Bible translations we did not have the right to share, and our license said every Bible text was public domain. That was wrong. Four of them are copyrighted, and their publishers do not allow copying: the Nova Versão Internacional, the Almeida Corrigida Fiel, the New Chinese Version and the Finnish Kirkkoraamattu of 1992 (shipped as Pyhä Raamattu). Six more are claimed by their publishers or still protected in some countries: the Almeida Revisada Imprensa Bíblica, La Bible de l'Épée, Schlachter 1951, the Korean Revised Version of 1961, the Chinese Union Version in its 1988 New Punctuation edition and Cornilescu 1924.

We are sorry: to the translators and publishers of those Bibles, and to everyone who downloaded them trusting that they were free to share. We should have checked each text's history before shipping it, and we did not.

What we have done about it:
- All ten are removed from the app, and the releases that contained them are taken down.
- Every Bible the app ships was checked against its own history (its publisher, its translators and the dates), not only against the site it came from.
- Each one now has its license, year and source recorded in `bibles/index.json` and listed in LICENSE.
- The build and the tests refuse any Bible without that record, or with a license other than public domain or CC BY-SA 4.0.

### Added
- **34 Bible translations in 27 languages** (was 25 in 14). New languages: Czech (Kralická 1613), Danish (1871/1907), Dutch (Statenvertaling, 1917 printing), Hebrew (with the Delitzsch New Testament), Hindi and Tamil (Indian Revised Version), Hungarian (Károli 1908), Italian (Riveduta 1927), Japanese (Bungo-yaku), Latin (Clementine Vulgate), Persian (Old Persian Version), Polish (Biblia Gdańska 1881), Swahili (Unlocked Literal Bible), Swedish (1917), Tagalog (Ang Biblia 1905) and Ukrainian (Kulish 1905). Also new: Lutherbibel 1912, Louis Segond 1910 and Almeida 1911. All 6 prayers are in every translation (Job's Prayer used to be missing from one), and references work in each language, such as "Giovanni 3:16", "יוחנן 3:16" or "ヨハネ 3:16". On the real screen, 0 of 2,200 random passages from the new and re-sourced Bibles were cut off.
- **Menu in 29 languages** (was 14): Czech, Danish, Dutch, Hebrew, Hindi, Hungarian, Italian, Japanese, Persian, Polish, Swahili, Swedish, Tagalog, Tamil and Ukrainian are new. Arabic, Hebrew and Persian menus and windows now read from right to left; the widget and saved images look exactly the same either way (0 pixels differ). Where human-made wording exists, it is used: language names come from the Unicode CLDR project (870 of them, written and reviewed by native speakers), and OK, Cancel, Apply, Close and Reset to Defaults use Qt's own translations in the 20 menu languages Qt covers. Bible book names in the menus come from the book name lists of that language's Bibles. The rest of the menu text in languages other than English is machine translated; the Menu Language menu says so, with a link to suggest a better wording.
- **No install needed**: download `BibleWidget-<version>-win64.zip`, unzip, run `BibleWidget.exe`. No Python, no PySide6, no `dependencies.bat`. The download is 67 MB, with all 34 Bibles (unused Qt and Python parts are left out, which saved 24 MB). The build behaves the same as running from source: the same self-test checks pass on both, and a fresh unzip passes with Python removed from the PATH. It opens in about half a second, a little faster than v2.0.2 from source in the same test (0.50 s against 0.53 s), and uses the same memory (76 MB).
- **Updates from inside the app**: the app checks GitHub shortly after it starts and then once a day (or when you choose Check for Updates) and offers new versions with their release notes. Update Now downloads the new version, verifies its SHA-256 checksum, and lets the new version install itself, so each release brings its own installer. Checking and unpacking the download happen in the background, so the window keeps responding. The swap and restart take 2 to 3 seconds. Your settings, favorites, history and any Bibles you added are never touched, and the names you gave added Bibles in `bibles/index.json` are kept. If anything goes wrong (a file in use, or a new version that fails to start), every file is put back and the version you had starts again. If the running version hangs instead of closing for the update, it is ended after a minute so the update can go on. A window left open while the update installs (Stats, a confirmation, the color picker) is closed so the app can hand over at once, instead of holding it up until the installer ends the app. Files held for a moment by antivirus or OneDrive are retried while installing and while putting files back, and if the old version could ever not be fully put back, its files are kept in `.update-backup` instead of starting a broken app. A shipped file or folder marked read-only, hidden or system (by you or a sync tool) is updated too, and a file another program holds open the whole time is left as it was while the update is undone, with the old version started again. Tested end to end against real builds: 12 of 12 scenarios pass (successful update, bad checksum refused, failed start rolled back, installer that cannot start, offline, Skip This Version, read-only folder, short temp paths with an install folder whose name has brackets and an apostrophe, a locked file midway, a file held for 2 seconds, which is retried and then installs, files you added or edited, and an old version that hangs instead of closing). Automatic checks can be turned off in About Bible Widget. Updates replace the Bible and prayer files that ship with the app and remove the ones a new version no longer includes; if you edited one, your version is kept next to it as `<name>.edited-<date>`, and a file you added is never replaced, even by a new file with the same name.
- **Crash logging**: if the widget ever ends without being closed, the next start says so in `widget.log`, with when the run started and was last seen running (recorded every 10 minutes), its memory and handles at that time, the Python stack of every thread at the moment of a crash, and Windows' own crash or hang report for it, found by its process number. Errors in background threads and during clean-up are logged too, and so are Windows ending the app (shutting down, signing out, or closing the console it was started from) and a start with Windows' crash reports turned off. Before, a crash left nothing: no log line, and a `widget.pid` that only gave a process number. Tested by ending the real app 7 ways (Exit, ended from outside, an error in another thread, an access violation, Qt's fatal error, Ctrl+Break in its console, and an old `widget.pid`): 24 of 24 checks pass, against 8 of 24 before.
- **About Bible Widget**: shows the version number, which also appears in the tray tooltip, Stats and the exe's file properties.
- **Find a verse**: type a reference such as "John 3:16", "Jn 3:16-18", "1 Cor 13", "Jude 3", or a book name in any of the Bibles' languages ("Juan 3:16", "Giovanni 3:16", "Иоанна 3:16", "Мф 5:3"), and the whole chapter is listed with your verses highlighted and shown on the widget (Proverbs 30:4 lists all 33 verses of Proverbs 30). Numbered books can be typed with a number however the Bible writes them: "1 Jana" finds the Polish "I Jana", and the same works in Greek, Arabic, Hebrew, Persian, Vietnamese and Japanese. A range that runs into the next chapter ("John 3:16-4:2") shows the first chapter's part. A word on its own, with no chapter, counts as a book name only in the translation's language or in English, so "Judas" or "esta" search the text instead of opening a book. So does a book name that is mostly another word in its own Bible: the Hebrew "יהודה" is Judah in 612 verses as well as the name of Jude, so on its own it is searched for ("יהודה 1" opens Jude), and the same goes for 26 such names in 14 languages. Numbers typed with a Japanese or Chinese keyboard (ヨハネ３：１６) work too. Names are found with or without the words in front of them ("К Римлянам", "Послание к Римлянам", "До Римлян", "Księga Rodzaju", "Waraka wa Yakobo"), in older forms ("Første Kongebog", and the Bungo-yaku's own "コリント前書", "ヨハネ傳福音書" and "列王紀略上"), and with any accent on the Greek numeral sign ("Α΄ Ιωάννου"). English short forms open the English book in every Bible: "Dan 7:13" opened Numbers in 10 of them (through the Vietnamese "Dân Số Ký"), and "Ro 1:1" opened Genesis. In a one-chapter book, "Jude 1-3" shows verses 1 to 3 (it showed 1 to 5). Or search by words across the whole Bible, with the matching words shown in bold: about 11 ms per search, and 0.15 s for the first search in a translation (0.4 s in Hindi). Words are found as keyboards type them: Vietnamese without accents ("Duc Chua Troi" finds all 3,647 verses with "Đức Chúa Trời", not 9), modern kanji in the Japanese Bible, printed in the old forms ("天国" finds the 33 verses with "天國", not 0), Persian without the zero-width non-joiner (544 verses, not 0), Hindi with or without the zero-width joiner, any kind of apostrophe ("l'Éternel" finds the 5,544 verses with "l’Éternel", not 0, and "dell'Eterno" 1,513), and the Arabic and Persian keyboards' different yeh and kaf. Searches match the start of words, in Hindi and Tamil too, where the marks that spell a word count ("परम" does not find "प्रेम") while accents elsewhere are ignored, and Japanese ガ and カ count as different letters. Arabic results line up from the right, so each verse's start is visible. Show any result on the widget, add it to your favorites, copy it or save it as an image.
- **Favorites and History**: save verses you love and look back at the last 100 verses the widget showed, in the new Verses window. Every list can show, copy or save the selected verse as an image, from its buttons or a right-click menu, and has keys: Enter shows the verse, Ctrl+C copies it, Delete removes a favorite, Ctrl+F jumps to Find and Esc closes the window. Clear History asks before it removes anything. If the favorites or history file is ever damaged, it is kept as `favorites.json.damaged-<date>` instead of being overwritten.
- **Back**: bring back the verse that just changed.
- **Save as Image**: turns a verse into a 3200x1800 card image in your colors, saved to `Pictures\Bible Widget` and copied to the clipboard. No two images are ever alike: each one paints a new background in one of 7 styles (starry night, aurora, sunrise, ocean, heavenly light, nebula, bokeh) from its own 256-bit random seed (a repeat is about 1 in 4×10³⁸ even if all 8 billion people saved one image every second for 100 years), with no watermark, just the translation name. In testing, 70 of 70 images were all different. The text is checked against the actual background behind it: the verse reaches at least 4.5:1 contrast and the reference and translation name at least 3:1 (the WCAG AA levels for normal and large text), tested on 140 cards. Readable custom colors are kept; colors that would be hard to read on a given background get another background, or the default colors. On a bright sky the translation name gets a soft dark backing. Click the notification to open the image. If the Pictures folder cannot be written, the image is still copied to the clipboard. The file is written in the background, so the widget no longer freezes while it saves: writing the PNG takes about 0.2 s, and the widget kept responding throughout (its longest pause during the write was under 1 ms). Quitting while an image is being written waits for the file to finish.
- **Right-click menu on the widget**: Back, Next Verse, Add to Favorites, Copy Verse, Save as Image, Find a Verse, Favorites & History. It opened and ran the chosen action 8 times out of 8 in real-click tests.

### Changed
- **Bibles taken out**: the ten translations above are replaced where a free one exists: Almeida 1911 for the three Portuguese ones, Lutherbibel 1912 for Schlachter, Louis Segond 1910 for La Bible de l'Épée and the Finnish Bible of 1776 for Pyhä Raamattu. We have not yet found a Chinese, Korean or Romanian text whose free status we could confirm, so the others have no replacement yet (a Korean text labeled "1910" turned out to be the 1961 Korean Revised Version, so it is not included). If you had chosen one of them, the widget and Find switch to its replacement (or the default) by themselves; favorites and history you saved from them keep their verses.
- **License**: LICENSE lists every Bible with its status and source: 30 are public domain and 4 (Hindi, Tamil, Swahili and the Wycliffe transcription) are under CC BY-SA 4.0. It also covers the language names (Unicode License) and the software the download is built with: Python (PSF License) and Qt with PySide6 (LGPL v3), with the third-party code inside Qt; their license texts come in the download's `licenses` folder.
- **Sharper tray icon**: the white cross is drawn for each display scale instead of being stretched, so at 200% scaling it has 16 soft edge pixels instead of 104, and it adds a faint warm glow. It stays white whatever Verse Text color you pick, and gets a dark edge on light taskbars, where the old icon was nearly invisible (it switches as soon as you change the Windows theme, or only the taskbar's). Windows such as Stats and Verses now show the cross as their icon.
- **Startup launcher**: two copies of the app (for example the exe and a source folder) no longer take over each other's Run on Startup entry, and Run on Startup shows as on only when it starts this copy. Choosing Off then leaves the other copy's entry alone.
- **Moving from 2.0.2**: while 2.0.2 is still running, starting the new version brings 2.0.2 forward instead of opening a second widget. The README says which five settings files to copy into the new folder to keep your settings.
- **Copy Verse** adds the translation after the reference, for example "John 11:35 (KJV)", and a notification confirms the copy.
- **A folder that can't be written**: if the app sits in a folder it can't write to (such as Program Files), a notification now says your settings can't be saved there; clicking it opens the folder. Before, settings were silently lost at every restart.
- **Running from source**: packages are listed in `requirements.txt`, which `dependencies.bat` now installs. The tests are included: `python tests/run_tests.py` runs 772 checks in about two minutes without touching your settings.
- **Less memory, same speed**: the verse of the day needs 0.5 MB of memory per Bible instead of 2.3 MB, with the same verse each day. Bibles load as fast as in 2.0.2 (the 13 that are unchanged: 325 ms together, against 328 ms) even though each verse's text is now cleaned up as it loads (see Fixed).
- **Wycliffe Bible**: now the transcription from Wikisource (through CrossWire), shared under CC BY-SA 4.0 as its license asks.
- **README screenshots** show the new menus with all 34 translations and 29 languages, the right-click menu, the Verses window and the current Customize Colors window. They come in the download too, so its README shows them.

### Fixed
- **Leftovers from the source files in the verse text**: 40,605 of the 403,387 verses in the 13 Bibles kept from 2.0.2 showed things that were never meant to be read: square brackets ("darkness [was] upon" in Webster), italics codes ("darkness <FI>is<Fi> on" in Young's Literal), backquotes, other numberings' verse numbers ("(H13:1)" in the Finnish Bible, "(14:55)" and "(75-)" in the Synodal), footnotes ("(a) Spelta eli Turkin kaura."), HTML codes ("&lt;&lt;" around the Greek psalm titles), invisible direction marks in the Arabic, missing spaces ("YetGod" in the ASV, "diris:Jen" in the Esperanto), margin notes in the KJV ("make...; or, fulfil"), 44 Vietnamese letters garbled into "@" or "»" ("Tr»i" for "Trời"), stars marking a gap in the Arabic and the Bible in Basic English (now an ellipsis) and a few typos ("Ela0d", ",,"). Darby, which had 3,681 missing spaces ("In the beginningGod"), now comes from eBible.org's edition. Two verse endings in the Arabic Bible (1 Timothy 6:21 and 3 John 1:14) had stray brackets and a reference in them; they now read as in the printed Van Dyck Bible. A scan of all 1,057,582 verses now finds 0 leftovers.
- **The King James Version was missing 6 verses** (Herod's order in Matthew 2:16 among them) and had split 4 others in two, so 146 verses showed under the wrong number: Find "Matthew 22:37" showed verse 38. It now has all 31,102 verses, numbered as printed, and every chapter has as many verses as Webster's revision of it.
- **Long verses cut off on small screens**: on a 1366 x 768 laptop at 125% scaling, 109 of the KJV's verses lost their ending (Esther 8:9 by 265 pixels). The widget now grows wider as well as taller for such a verse: 0 of 31,102 are cut off on that screen, or at 1280 x 720. It is also sized for the screen it is on: moved to another monitor, or after a change of resolution or scaling, it kept the size of the first screen (on a laptop, 40% of its width instead of 20%).
- **Verses that are only punctuation** ("..." in 19 verses of the Bible in Basic English, where the source lost the words or joined them to the verse before) no longer show as a passage. Find opens the next verse instead and highlights that one in the chapter list (before, nothing in the list was highlighted). The 11 such verses in the Hebrew New Testament ("׃") and the Arabic 3 John 1:1 (":") now have their words.
- **Verses lost, merged or empty in 13 Bibles**: where a source file fitted an edition's verses into another numbering, the extra verses were glued onto the verse before (Job 39:30 held nine verses in the Geneva, Danish, Polish and Swedish Bibles), and elsewhere verses were lost or left empty. They were repaired from other public domain copies of the same editions (listed in LICENSE): 459 verses are back under their own number (107 Danish, 100 Polish, 98 Swedish, 45 Hungarian, 41 Vietnamese, 29 Geneva, 26 Wycliffe, 8 Finnish, 5 Czech, Persian and Japanese), and 187 Vietnamese verses that had lost words in the middle are whole again. Checked chapter by chapter: no letter of the text was lost, the repairs only moved verse breaks or put back missing words. The Vietnamese and Finnish Bibles now have all 31,102 verses.
- **Words run together in the American Standard Version**: 644 verses had words joined where the source dropped its italics ("Godisfor us, whoisagainst us" in Romans 8:31, "Davidmade"). They are now spaced as printed, which also makes this Bible's clean-up 59% faster (142 ms to 58 ms for the whole Bible, the same for the Geneva Bible).
- **Translator's notes in the King James Version**: Luke 17:36 ended with "this verse is not found in most of the Greek copies", and Luke 10:22 with a note on other copies. Both are gone.
- **Typing errors from the source files**: a number inside a German verse ("gerechtet 518heeft", Judges 11:25), a zero for a letter in the Finnish ("kuka 0n", Proverbs 30:4), "×" for "ł" in the Polish, stray signs in the Persian and the Japanese ("／" in 24 verses, and "モ−セ" for "モーセ", so a search for Moses missed 2 verses), a Latin "w" for a Hebrew letter in 2 verses, ",." and ".," in 18 Swahili, Tamil and Polish verses, and 169 missing spaces after a full stop or semicolon (141 in the Synodal: "Симовых;Ханаан"). Clean-up no longer leaves a space before a full stop where it removes the Arabic Bible's invisible marks or gap stars (4 verses), or glues two sentences where it removes another numbering's verse number (2 psalm titles in the Synodal).
- **Book names**: the Swahili Bible showed 1 John as "1Yohana 1 3:16", and three more numbered books had no space; the Danish showed Ruth and Job in capitals and misspelled Colossians; the Dutch had "Numberi" and "2 Corinthiër". They now read as printed, and Find also takes "1 Kongebog", "Salmerne", "Richteren", "Sędziów" and "Yakobo".
- **Bold in search results** now covers the marks on a word's last letter (an Arabic shadda was left out of the bold).
- **A favorites or history file nested too deeply** (100,000 brackets) stopped the app at startup. It is now kept aside as damaged, like any other file that can't be read.
- **OK and Cancel in Customize Colors** were in English whatever the menu language. They now follow it.
- **A new menu language** now reaches the windows that are open (About, Customize Colors and prayers, which keep the colors you picked but did not apply yet). Before, they stayed in the old language. A message that no Bible could be loaded is shown in the menu language too.
- **Prayers**: choosing a prayer that is already open brings its window forward instead of opening a second one on top of it, and prayer windows open on the widget's screen instead of the main one.
- **A Bible file you add** with a superscript digit as a verse number now loses only that verse instead of being skipped whole, and a verse that holds only another numbering's verse number, such as "(H40:19)", is left out instead of showing as an empty passage.
- **Arabic text on the widget** was drawn with letter spacing, which pulls joined letters apart and broke ligatures such as الله. Arabic, Hebrew and Persian verses and references now have none, on the widget, in the prayer window and in saved images.
- **The verse timer could stop for good**: if showing one verse failed, no new verse came until a restart. The timer now always carries on.
- **Daily mode and changing translation**: switching translations in Daily mode showed a random verse instead of the verse of the day. It now keeps the verse of the day.
- **Damaged Bible files**: a Bible file with bad data no longer stops the widget; it is skipped and noted in `widget.log`.
- **Prayer window keys**: the arrow keys and Esc now work even after clicking into the prayer text.
- **Dragging the widget**: each snap no longer leaves a used animation behind (100 drags left 100; now 1).
- **Two copies at once**: starting the widget twice at the same moment could leave both running. A lock file now keeps it to one.
- **Waking from sleep**: if the PC slept past midnight (Daily mode) or past the next change, the new verse could come late. The widget now compares the clock every 30 seconds and changes the verse straight away.
- **stop_widget.bat**: after a crash it could stop an unrelated program that had been given the widget's old process number, even another Python program. It now checks by the process's command line that it is the widget, and a `widget.pid` holding anything but a number is ignored.
- **Running from source with two versions of Python**: `dependencies.bat` could install PySide6 into one while `start_widget.vbs` started the widget with the other, which then failed without a message. Both now use the same one (the newest Python 3 the py launcher knows, or else the one on the PATH).
- **Files saved with a byte order mark** (by PowerShell or some versions of Notepad): `bibles/index.json` lost every translation's display name, and `translation.txt`, `language.txt`, `mode.txt` and `corner.txt` were ignored, so those settings went back to their defaults. They are now read either way.
- **Customize Colors sometimes did nothing**: if the colors window had been minimized (Win+D minimizes it), choosing Customize Colors again left it minimized and invisible. It now comes back every time: 3 of 3 test runs, up from 0 of 3.
- **A hand-edited `bibles/index.json` saved in ANSI** (as older editors do, for example with "Português" in it) stopped the app at startup, as did one of the wrong shape. It is now read either way, and an entry it can't use is skipped. The same goes for `book_names.json`, `prayers.json` and `colors.txt`, which also keeps a comment written in ANSI intact when a color is saved. On Japanese, Chinese or Korean Windows, a byte that the system's code page can't read in `colors.txt` or `updates.txt` no longer stops the app starting.
- **Settings could be lost**: if the app was ended while saving (on a crash or power cut), the translation, menu language, mode, colors or position could be left empty and go back to their defaults. Each is now replaced in one step, so the file holds either the old setting or the new one. Saving a color also keeps comments and anything else you wrote in `colors.txt`.

---

## v2.0.2 (2026-10-30)

### Changed
- **The widget now matches the prayer window**: the reference is shown in small caps above a single fading line, and the verse has more line spacing (the extra line above the reference is gone). On the real screen, 0 of 30 verse changes leave stale pixels and 0 of 300 passages are cut off, same as v2.0.1. The extra spacing shortens slightly more long passages to fit: 59 of 300, up from 44, for an average of 1.84 verses instead of 1.92.
- **README screenshots** updated to the new look.

---

## v2.0.1 (2026-10-30)

### Fixed
- **Dark bands on the widget after a verse change**: the drop shadow was drawn with a Qt effect that Windows could not update on a see-through window, so old pixels were left behind (most visible as a dark bar under the reference). The shadow is now painted directly. In testing, 11 of 30 verse changes left stale pixels before (27,544 wrong pixels); now 0 of 30.
- **Long passages cut off at the bottom**: 103 of 300 random passages (34%) did not fit the card, overflowing by up to 326 px. Now 0 of 300. The text is measured with its real letter spacing, the font can shrink to 10 pt, and if a passage still does not fit its last verses are dropped (15% of passages, 2.13 to 1.92 verses on average). A single verse that is too long on its own, like Esther 8:9, makes the widget slightly taller for that verse only.
- **Widget resizing itself**: the layout could force the window taller than its normal size (for example 324 to 377 px), out of line with its corner. The widget now controls its own size.
- **Prayer window updates**: Windows rejected every prayer window repaint (18 of 18 in testing, logged as `UpdateLayeredWindowIndirect failed`). Now 0.
- **Prayer window redesigned**: it now matches the widget's look, with the reference above a clear title, borderless text with comfortable line spacing that no longer runs off the edge, a slim scrollbar only for long prayers, and round arrow buttons around an Amen button. References use the Bible's own book names (e.g. "Mateo 6:9-13"), Arabic prayers are right-aligned, and Esc or the arrow keys close the window or switch prayers.
- **Jonah's Prayer (KJV)** no longer includes leftover translator footnotes.

---

## v2.0.0

### Added
- **Color customization**: pick your own colors for the verse text, background, and separator line. Right-click the tray icon → "Customize Colors..." to open a settings dialog with a color swatch and picker for each element. Click "Reset to Defaults" to restore the original dark style.
- **Smart corner snapping**: drag the widget anywhere on screen and release; it smoothly animates to the nearest screen corner (top-left, top-right, bottom-left, or bottom-right) with a 20px margin. The snap uses a 200ms animated ease-out.
- **Snap to Corners toggle**: right-click the tray icon → "Snap to Corners" to turn the corner-snapping behavior on or off. Your preference is saved and remembered.
- **Persistent corner + screen**: your chosen corner and the monitor it's anchored to are saved to `corner.txt`. The widget reopens in the same spot next launch, and falls back to your primary monitor if the saved one is disconnected.
- **Snap respects taskbar**: bottom corners snap above the taskbar, not behind it.
- **Show Widget button**: if the widget ever goes missing (e.g. after Win+D or a fullscreen app), right-click the tray icon → "Show Widget" to bring it back instantly.
- **Segoe UI font**: the widget now uses the Windows system font (Segoe UI) with Medium weight for both the verse and citation, giving a clean modern look that stays readable on translucent backgrounds.
- **Card shadow**: a soft drop shadow makes the widget look like a floating card on your desktop.
- **Gradient separator**: the line between the citation and the verse fades to transparent at the edges for a more polished look.

### Changed
- **Removed theme toggle**: the old dark/light theme switcher is gone. Use the new color customization to set any colors you want.
- **Removed `theme.py` and `theme.txt`**: replaced by the new `colors.py` module and `colors.txt` file.
- **`prayer_window.py`**: updated to use the new color system.

### Fixed
- **Widget sizing**: long verses no longer stretch the widget off-screen. The widget keeps a constant size and the font automatically shrinks to fit the text.
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
- **6 new Bible translations**: 19 → 25 total. American Standard Version (ASV), Darby Translation, Young's Literal Translation (YLT), Webster's Bible, Geneva Bible, and Wycliffe Bible, all public domain English translations from scrollmapper/bible_databases
- **6 prayers**: scrollable prayer window now includes: The Lord's Prayer, Jonah's Prayer, Mary's Magnificat, Job's Prayer, Acts 4:24-26, and Solomon's Prayer (1 Kings 8:22-24), each available in all 25 translations
- **Prayer navigation**: ◀ and ▶ buttons in the prayer window to cycle between prayers without closing
- **QScrollArea**: long prayers (e.g. Mary's Magnificat) are now scrollable; non-long prayers display normally
- **Translated prayer names**: all 6 prayer names translated into all 14 menu languages
- **Copy Verse tray action**: copies the current reference and text to the clipboard from the tray menu
- **Stats tray action**: shows uptime, verse count, mode, and next refresh in a popup, removing the need to launch with a terminal
- **bibles/index.json**: updated with 6 new English translation entries

### Fixed
- **Window positioning on startup**: the widget now anchors its position before loading the first verse, preventing the window from jumping when verses resize with larger fonts or longer text. It opens at a fixed size in the top-right corner.
- **Prayer window constant size**: the prayer window no longer resizes itself when switching prayers; it keeps a fixed size and the prayer text scrolls within it via the scroll area
- **Constant widget size**: the main widget now uses a fixed size in the top-right corner; long verses shrink the font to fit instead of growing the window or moving it
- **Copy Verse separator**: copied verses now include a dash between the reference and text so they don't run together when pasted

### Changed
- **prayer_window.py**: completely rewritten: accepts `prayer_id` parameter to select any prayer, added QScrollArea for the text, added prev/next navigation buttons, retains drag and Amen button
- **widget_window.py**: Prayers submenu now lists all 6 prayers individually instead of just "The Lord's Prayer"
- **Removed Psalm 51**: dropped the Psalm 51 prayer along with its tray menu entry and all 14 translation strings; 6 prayers remain
- **menu_strings.py**: added 6 new string keys per language for the additional prayer names
- **README.md**: updated translation count, prayer features, and file descriptions
- **Launcher cleanup**: deleted `start_widget.bat` (terminal stats launch is now redundant since Stats live in the tray menu) and renamed `start_widget_no_terminal.vbs` → `start_widget.vbs`. Startup detection now keys off the `pythonw` silent run

---

## v1.2.0

### Added
- **Prayers submenu**: "The Lord's Prayer" opens a dedicated overlay with Amen button
- **Menu Language submenu**: 14-language tray menu translation, fully independent from Bible Translation
- **menu_strings.py**: centralized translation dictionary for all tray menu text
- **Menu language persistence**: saved to `language.txt` and restored on launch
- **Change Quote**: moved to the top section (under Daily Mode) for faster access
- **Lord's Prayer in all 19 translations**: prayers/prayers.json covers every available Bible

### Fixed
- **Prayer window sizing**: full prayer text now renders without being cut off at the top or bottom
- **Prayer window layout**: removed alignment that squished labels into a narrow column

### Changed
- **Menu order**: Translation → Menu Language → Prayers → Run on Startup → Exit
- **Language and Translation are independent**: you can read the Bible in one language while keeping the tray menu in another

---

## v1.1.1

### Fixed
- **Startup now survives folder renames**: the `BibleWidget.vbs` file no longer hardcodes a launcher filename. It runs `widget_window.py` directly from the current folder location, so renaming the project folder for GitHub won't break startup.
- **Translation preference persists across restarts**: your selected Bible is saved to `translation.txt` and restored on launch. No more defaulting to "All (Random)" every time.
- **Tray menu checkmarks reflect saved preference**: the correct translation shows as checked when you open the menu.

### Changed
- **Startup repair logic**: if an old stale `.vbs` is detected, the widget silently rewrites it with the correct current path on launch.

---

## v1.1.0

### Added
- **19 Bible translations** (14 languages): Arabic, Chinese (×2), German, Greek, English (×2), Esperanto, Spanish, Finnish (×2), French, Korean, Portuguese (×3), Romanian, Russian, Vietnamese
- **Translation picker**: right-click the tray icon to choose a specific Bible, or "All (Random)" to shuffle across all 19
- **`bibles/` folder**: 19 JSON files (~75 MB) for fully offline use, plus `index.json` for proper display names
- **`bible_loader.py` fully rewritten**: auto-discovers Bibles, normalizes file formats, supports mixed schemas
- **README.md updated** with multi-translation features, adding new translations guide, and file descriptions

### Fixed
- **Long verses display correctly on first load**: widget auto-grows vertically to fit wrapped text
- **Citations properly centered**: no more left-aligned references after verse changes
- **Clean citation format**: `John 3:16` instead of `John 3:16 (en_kjv)`
- **Verse counter accurate**: stats now count actual verses, not chapters
- **UTF-8 BOM handling**: files with byte-order marks load correctly
- **Arabic Bible format supported**: array-format JSON normalized to standard structure
- **Mixed key type compatibility**: chapter/verse lookups work with both string and integer keys
- **Widget won't collapse**: minimum width guard prevents unusable text areas

### Removed
- **Window size presets** (Small/Medium/Large): replaced with auto-sizing
- **Unused `QGraphicsDropShadowEffect` import**
- **Dead `_calc_font_size()` method**: orphaned from earlier refactor
- **Dead `translation` parameter** from citation formatter

### Changed
- **`dependencies.bat`**: restores auto-install for PySide6 (only Python must be pre-installed)
- **`_fit_text_size()`**: now uses `setFixedWidth()` + `boundingRect()` for precise word-wrap measurement
- **Verse span weighting**: 1 verse = 40%, 2 = 25%, 3 = 18%, 4 = 12%, 5 = 5%
- **Citation format**: clean `Book Chapter:Verse` with no translation suffix

---

## v1.0.0

- Initial release
- Single KJV Bible
- Hourly and daily modes
- Transparent frameless window
- Drag-to-move with smart anchoring
- System tray integration
- Startup launcher