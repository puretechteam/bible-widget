"""Updates: version numbers, settings, download checks, and the installer's file swap and
rollback, run on a fake app folder in a temp directory (no exe is started, nothing is downloaded)."""
import os
import sys
import types
import zipfile
import hashlib
import time
import subprocess
from support import Results, TMP, ROOT, app

R = Results()
app()
import updater
import paths
from version import version_tuple, VERSION

# ----- Version numbers -----
R.check("v2.1.0 parses", version_tuple("v2.1.0") == (2, 1, 0, 0))
R.check("2.1 is 2.1.0", version_tuple("2.1") == (2, 1, 0, 0))
R.check("a pre-release sorts before the release", version_tuple("v2.1.0-rc1") < version_tuple("v2.1.0"))
R.check("2.10 is newer than 2.9", version_tuple("2.10.0") > version_tuple("2.9.9"))
R.check("garbage is lowest", version_tuple("latest") < version_tuple("0.0.1"))
R.check("this version parses", version_tuple(VERSION)[:3] != (0, 0, 0), VERSION)
R.check("zip name", updater.zip_name("2.1.0") == "BibleWidget-2.1.0-win64.zip")

# ----- Settings -----
folder = os.path.join(TMP, "settings"); os.makedirs(folder)
s = updater.UpdateSettings(folder)
R.check("updates are on by default", s.auto is True and s.skip == "")
s.auto, s.skip = False, "v9.9.9"; s.save()
s2 = updater.UpdateSettings(folder)
R.check("settings are remembered", s2.auto is False and s2.skip == "v9.9.9")

# ----- Downloads -----
R.check("HTTPS downloads are allowed", updater._allowed_download("https://github.com/x.zip"))
R.check("plain HTTP is refused", not updater._allowed_download("http://github.com/x.zip"))
R.check("an empty link is refused", not updater._allowed_download(""))
blob = os.path.join(TMP, "blob.bin")
open(blob, "wb").write(os.urandom(3_000_000))
R.check("sha256 matches hashlib", updater.sha256_of(blob) == hashlib.sha256(open(blob, "rb").read()).hexdigest())
R.check("running from source never installs itself", updater.can_self_update(TMP) is False)
R.check("a writable folder is writable", paths.folder_writable(TMP))
R.check("a missing folder is not writable", not paths.folder_writable(os.path.join(TMP, "no", "such")))

# A real folder Windows refuses to write to (write denied for this user, then allowed again).
# Run in a child process with a time limit: the check once hung for good on such a folder.
if sys.platform == "win32":
    locked = os.path.join(TMP, "locked"); os.makedirs(locked)
    user = os.environ.get("USERNAME", "")
    subprocess.run(["icacls", locked, "/deny", f"{user}:(W,AD)"], capture_output=True)
    try:
        probe = [sys.executable, "-B", "-c", "import sys, paths; print(paths.folder_writable(sys.argv[1]))", locked]
        try:
            out = subprocess.run(probe, cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip()
        except subprocess.TimeoutExpired:
            out = "hung"
    finally:
        subprocess.run(["icacls", locked, "/remove:d", user], capture_output=True)
    R.check("a write-denied folder is reported quickly", out == "False", out)
    R.check("the check leaves no file behind", os.listdir(locked) == [])

# Unpacking finds the exe inside the zip's folder, and refuses a zip without one
z = os.path.join(TMP, "update.zip")
with zipfile.ZipFile(z, "w") as f:
    f.writestr("BibleWidget/BibleWidget.exe", b"new")
    f.writestr("BibleWidget/_internal/lib.dll", b"new")
R.check("unpacking finds BibleWidget.exe", os.path.basename(updater.extract(z, os.path.join(TMP, "x1"))) == "BibleWidget")
bad = os.path.join(TMP, "bad.zip")
with zipfile.ZipFile(bad, "w") as f:
    f.writestr("readme.txt", b"no exe")
try:
    updater.extract(bad, os.path.join(TMP, "x2")); R.check("a zip without the exe is refused", False)
except FileNotFoundError:
    R.check("a zip without the exe is refused", True)
R.check("the installer needs a folder", updater.install_main(["--install-update"]) == 2)


# ----- Swap and rollback on a fake install -----
def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(data)


def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else None


def fake_install(name):
    app_dir, source = os.path.join(TMP, name, "app"), os.path.join(TMP, name, "new")
    for rel in ("BibleWidget.exe", "_internal/lib.dll", "_internal/old_only.dll", "bibles/en_kjv.json"):
        write(os.path.join(app_dir, rel), "old " + rel)
    write(os.path.join(app_dir, "favorites.json"), "my favorites")  # the user's own file
    for rel in ("BibleWidget.exe", "_internal/lib.dll", "_internal/new_only.dll", "bibles/en_kjv.json", "NEW.txt"):
        write(os.path.join(source, rel), "new " + rel)
    return app_dir, updater._Installer(app_dir, source, "9.9.9", os.path.join(app_dir, "update.log"))


app_dir, inst = fake_install("swap")
inst.swap()
j = lambda *p: os.path.join(app_dir, *p)
R.check("swap: new program files", read(j("BibleWidget.exe")) == "new BibleWidget.exe"
        and read(j("bibles", "en_kjv.json")) == "new bibles/en_kjv.json")
R.check("swap: _internal replaced whole", read(j("_internal", "new_only.dll")) is not None
        and read(j("_internal", "old_only.dll")) is None)
R.check("swap: your files are kept", read(j("favorites.json")) == "my favorites")
R.check("swap: a backup exists", os.path.isdir(inst.backup))
inst.rollback()
R.check("rollback: old program files", read(j("BibleWidget.exe")) == "old BibleWidget.exe"
        and read(j("bibles", "en_kjv.json")) == "old bibles/en_kjv.json")
R.check("rollback: old _internal", read(j("_internal", "old_only.dll")) is not None
        and read(j("_internal", "new_only.dll")) is None)
R.check("rollback: files the update added are gone", read(j("NEW.txt")) is None)
R.check("rollback: your files are kept", read(j("favorites.json")) == "my favorites")
R.check("rollback: the backup is removed", not os.path.exists(inst.backup))

# A Bible you added keeps its name: the update's index.json is merged with yours
import json
real_sleep_for_tests = updater.time.sleep
MINE = [{"language": "English", "versions": [
    {"name": "King James Version", "abbreviation": "en_kjv"},
    {"name": "My Translation", "abbreviation": "en_mine"}]},
    {"language": "Latin", "versions": [{"name": "Vulgata", "abbreviation": "la_vul"}]}]
NEW = [{"language": "English", "versions": [{"name": "King James Version (1769)", "abbreviation": "en_kjv"},
                                            {"name": "World English Bible", "abbreviation": "en_web"}]}]
app_dir, inst = fake_install("index")
with open(os.path.join(app_dir, "bibles", "index.json"), "w", encoding="utf-8-sig") as f:
    json.dump(MINE, f)  # saved with a byte order mark, as some editors do
write(os.path.join(inst.source, "bibles", "index.json"), json.dumps(NEW))
inst.swap()
merged = json.load(open(os.path.join(app_dir, "bibles", "index.json"), encoding="utf-8"))
names = {v["abbreviation"]: v["name"] for g in merged for v in g["versions"]}
R.check("update: your added Bibles stay in index.json", names.get("en_mine") == "My Translation"
        and names.get("la_vul") == "Vulgata", names)
R.check("update: the new index.json's entries win", names.get("en_kjv") == "King James Version (1769)"
        and names.get("en_web") == "World English Bible")
R.check("update: a Bible is listed once", sum(len(g["versions"]) for g in merged) == 4)
inst.rollback()
R.check("rollback: your index.json is back as it was",
        json.load(open(os.path.join(app_dir, "bibles", "index.json"), encoding="utf-8-sig")) == MINE)

# A file held for a moment (antivirus, OneDrive) is retried instead of failing the update
app_dir, inst = fake_install("held")
real_copy2, fails = updater.shutil.copy2, {"n": 0}


def flaky_copy2(src, dst, *a, **k):
    if os.path.basename(dst) == "BibleWidget.exe" and fails["n"] < 2:
        fails["n"] += 1
        raise PermissionError(32, "being used by another process")
    return real_copy2(src, dst, *a, **k)


updater.shutil.copy2, updater.time.sleep = flaky_copy2, (lambda s: None)
try:
    inst.swap(); held_ok = True
except OSError as e:
    held_ok = e
finally:
    updater.shutil.copy2, updater.time.sleep = real_copy2, real_sleep_for_tests
R.check("swap: a briefly held file is retried", held_ok is True and fails["n"] == 2, held_ok)
R.check("swap: and then updated", read(os.path.join(app_dir, "BibleWidget.exe")) == "new BibleWidget.exe")

# A backup kept by an earlier failed restore is never deleted by a later update
app_dir, inst = fake_install("kept")
write(os.path.join(inst.backup, "BibleWidget.exe"), "the version that could not be put back")
inst.swap()
kept = [n for n in os.listdir(app_dir) if n.startswith(".update-backup-")]
R.check("swap: an earlier backup is kept aside", len(kept) == 1 and read(os.path.join(
    app_dir, kept[0], "BibleWidget.exe")) == "the version that could not be put back", os.listdir(app_dir))
inst.rollback()
R.check("rollback: the earlier backup is still there", all(os.path.isdir(os.path.join(app_dir, k)) for k in kept))
R.check("rollback: the program is back", read(os.path.join(app_dir, "BibleWidget.exe")) == "old BibleWidget.exe")

# Files you added or edited are never lost: the old download's shipped.json tells them apart
MANIFEST = getattr(updater, "MANIFEST", "shipped.json")
def h(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


app_dir, inst = fake_install("yours")
old_list = {rel: h("old " + rel) for rel in ("BibleWidget.exe", "bibles/en_kjv.json")}
write(os.path.join(app_dir, "_internal", MANIFEST), json.dumps({"version": "2.1.0", "files": old_list}))
write(os.path.join(app_dir, "NEW.txt"), "my own notes")          # yours; the update ships a NEW.txt too
write(os.path.join(app_dir, "bibles", "en_kjv.json"), "my edited kjv")  # a shipped file you edited
new_list = {rel: h("new " + rel) for rel in ("BibleWidget.exe", "bibles/en_kjv.json", "NEW.txt")}
write(os.path.join(inst.source, "_internal", MANIFEST), json.dumps({"version": "9.9.9", "files": new_list}))
inst.swap()
edited = [n for n in os.listdir(os.path.join(app_dir, "bibles")) if n.startswith("en_kjv.json.edited-")]
R.check("update: a file you added is kept, even with the same name as a new one",
        read(os.path.join(app_dir, "NEW.txt")) == "my own notes")
R.check("update: a shipped file you edited is updated, with your version kept beside it",
        read(os.path.join(app_dir, "bibles", "en_kjv.json")) == "new bibles/en_kjv.json" and len(edited) == 1
        and read(os.path.join(app_dir, "bibles", edited[0])) == "my edited kjv", edited)
R.check("update: the edited copy is not loaded as a Bible", all(not n.endswith(".json") for n in edited))
listed = json.load(open(os.path.join(app_dir, "_internal", MANIFEST), encoding="utf-8"))["files"]
R.check("update: the new list does not claim your file", "NEW.txt" not in listed and "bibles/en_kjv.json" in listed)
R.check("update: untouched files are replaced as usual", read(j("BibleWidget.exe")) is not None
        and read(os.path.join(app_dir, "BibleWidget.exe")) == "new BibleWidget.exe")
inst.rollback()
R.check("rollback: your edited file is back and the extra copy is gone",
        read(os.path.join(app_dir, "bibles", "en_kjv.json")) == "my edited kjv"
        and not [n for n in os.listdir(os.path.join(app_dir, "bibles")) if ".edited-" in n])
R.check("rollback: your added file is untouched", read(os.path.join(app_dir, "NEW.txt")) == "my own notes")

# A file the old release shipped and the new one does not (a withdrawn Bible) goes, unless you edited it
INDEX = lambda abbrs: json.dumps([{"language": "English", "versions": [{"abbreviation": a} for a in abbrs]}])
app_dir, inst = fake_install("withdrawn")
b = lambda *p: os.path.join(app_dir, "bibles", *p)
write(b("en_gone.json"), "old en_gone")        # shipped, untouched: removed
write(b("en_edited.json"), "my edited copy")    # shipped, then edited by you: kept aside
write(b("en_added.json"), "my own Bible")       # yours: never touched
write(os.path.join(app_dir, "README.txt"), "old readme")
write(os.path.join(app_dir, "extras", "notes", "old.txt"), "old notes")  # alone in its folders
old_index = INDEX(["en_kjv", "en_gone", "en_edited", "en_added"])
write(b("index.json"), old_index)
old_list = {rel: h("old " + rel) for rel in ("BibleWidget.exe", "bibles/en_kjv.json")}
old_list.update({"bibles/en_gone.json": h("old en_gone"), "bibles/en_edited.json": h("original en_edited"),
                 "README.txt": h("old readme"), "extras/notes/old.txt": h("old notes"), "bibles/index.json": h(INDEX(["en_kjv", "en_gone", "en_edited"]))})
write(os.path.join(app_dir, "_internal", MANIFEST), json.dumps({"version": "2.1.0", "files": old_list}))
write(os.path.join(inst.source, "bibles", "index.json"), INDEX(["en_kjv"]))
write(os.path.join(inst.source, "_internal", MANIFEST), json.dumps({"version": "9.9.9", "files": {}}))
inst.swap()
kept_aside = [n for n in os.listdir(b()) if n.startswith("en_edited.json.edited-")]
abbrs = [v["abbreviation"] for g in json.load(open(b("index.json"), encoding="utf-8")) for v in g["versions"]]
R.check("update: a Bible the new release withdrew is removed", read(b("en_gone.json")) is None)
R.check("update: so is any other withdrawn file you did not change", read(j("README.txt")) is None)
R.check("update: a withdrawn file you edited is kept aside", read(b("en_edited.json")) is None
        and len(kept_aside) == 1 and read(b(kept_aside[0])) == "my edited copy", os.listdir(b()))
R.check("update: a Bible you added stays", read(b("en_added.json")) == "my own Bible")
R.check("update: folders a withdrawn file leaves empty are removed", not os.path.exists(os.path.join(app_dir, "extras")))
R.check("update: withdrawn Bibles leave index.json, yours stay", abbrs == ["en_kjv", "en_added"], abbrs)
inst.rollback()
R.check("rollback: withdrawn files are back", read(b("en_gone.json")) == "old en_gone"
        and read(b("en_edited.json")) == "my edited copy" and read(j("README.txt")) == "old readme")
R.check("rollback: a withdrawn file's folders come back with it",
        read(os.path.join(app_dir, "extras", "notes", "old.txt")) == "old notes")
R.check("rollback: the kept-aside copy is gone", not [n for n in os.listdir(b()) if ".edited-" in n])
R.check("rollback: index.json is back as it was", read(b("index.json")) == old_index)
R.check("rollback: your Bible is untouched", read(b("en_added.json")) == "my own Bible")

# Without the old list nothing can be told apart, so nothing is removed
app_dir, inst = fake_install("withdrawn-nolist")
write(os.path.join(app_dir, "bibles", "en_gone.json"), "old en_gone")
write(os.path.join(app_dir, "bibles", "index.json"), INDEX(["en_kjv", "en_gone"]))
write(os.path.join(inst.source, "bibles", "index.json"), INDEX(["en_kjv"]))
inst.swap()
abbrs = [v["abbreviation"] for g in json.load(open(os.path.join(app_dir, "bibles", "index.json"), encoding="utf-8"))
         for v in g["versions"]]
R.check("update without a list: nothing is removed", read(os.path.join(app_dir, "bibles", "en_gone.json")) == "old en_gone"
        and abbrs == ["en_kjv", "en_gone"], abbrs)

# A file the new release only renamed in case (Windows folders ignore case) is not "withdrawn",
# and a list entry that points off the program folder (a drive-relative path) is ignored
app_dir, inst = fake_install("withdrawn-case")
write(os.path.join(app_dir, "Readme.md"), "old readme")
write(os.path.join(inst.source, "README.md"), "new readme")
old_list = {"Readme.md": h("old readme"), "C:stray.txt": h("x"), "bibles/en_kjv.json": h("old bibles/en_kjv.json")}
write(os.path.join(app_dir, "_internal", MANIFEST), json.dumps({"version": "2.1.0", "files": old_list}))
inst.swap()
names = [n for n in os.listdir(app_dir) if n.lower() == "readme.md"]
R.check("update: a file renamed only in case is installed, not removed",
        len(names) == 1 and read(os.path.join(app_dir, names[0])) == "new readme", names)
R.check("update: a list entry off the program folder is never touched", inst.replaced == [] or
        all(not os.path.splitdrive(r)[0] for r in inst.replaced), inst.replaced)

# Rollback also removes the folders the update made for its new files
app_dir, inst = fake_install("rollback-folders")
write(os.path.join(inst.source, "fonts", "sub", "f.ttf"), "font")
inst.swap()
made = os.path.isdir(os.path.join(app_dir, "fonts", "sub"))
inst.rollback()
R.check("rollback: folders the update made are gone again", made and not os.path.exists(os.path.join(app_dir, "fonts")))

# A shipped file marked read-only (by you, or a sync tool) is still updated, and still removed
# when the new release withdraws it
import stat
app_dir, inst = fake_install("read-only")
write(os.path.join(app_dir, "README.md"), "old readme")
write(os.path.join(app_dir, "bibles", "en_gone.json"), "old en_gone")
write(os.path.join(inst.source, "README.md"), "new readme")
old_list = {"README.md": h("old readme"), "bibles/en_gone.json": h("old en_gone"),
            "bibles/en_kjv.json": h("old bibles/en_kjv.json")}
write(os.path.join(app_dir, "_internal", MANIFEST), json.dumps({"version": "2.1.0", "files": old_list}))
for rel in ("README.md", os.path.join("bibles", "en_gone.json")):
    os.chmod(os.path.join(app_dir, rel), stat.S_IREAD)
real_retry = updater._retry
updater._retry = lambda func, *a, **k: real_retry(func, *a, tries=2, delay=0)
try:
    inst.swap()
    swapped = "ok"
except OSError as e:
    swapped = repr(e)
finally:
    updater._retry = real_retry
R.check("update: a read-only shipped file is updated", swapped == "ok" and read(os.path.join(app_dir, "README.md")) == "new readme", swapped)
R.check("update: a read-only withdrawn file is removed", not os.path.exists(os.path.join(app_dir, "bibles", "en_gone.json")))
inst.rollback()
R.check("rollback: both are back", read(os.path.join(app_dir, "README.md")) == "old readme"
        and read(os.path.join(app_dir, "bibles", "en_gone.json")) == "old en_gone")

# A shipped folder marked read-only (Windows does that to a folder given a custom icon), and a
# shipped file marked hidden or system, don't block the update either
if sys.platform == "win32":
    app_dir, inst = fake_install("attributes")
    write(os.path.join(app_dir, "extras", "gone.txt"), "old gone")
    write(os.path.join(app_dir, "README.md"), "old readme")
    write(os.path.join(app_dir, "LICENSE"), "old license")
    write(os.path.join(inst.source, "README.md"), "new readme")
    write(os.path.join(inst.source, "LICENSE"), "new license")
    old_list = {"extras/gone.txt": h("old gone"), "README.md": h("old readme"), "LICENSE": h("old license"),
                "bibles/en_kjv.json": h("old bibles/en_kjv.json")}
    write(os.path.join(app_dir, "_internal", MANIFEST), json.dumps({"version": "2.1.0", "files": old_list}))
    subprocess.run(["attrib", "+R", os.path.join(app_dir, "extras")], capture_output=True)
    subprocess.run(["attrib", "+H", os.path.join(app_dir, "README.md")], capture_output=True)
    subprocess.run(["attrib", "+S", os.path.join(app_dir, "LICENSE")], capture_output=True)
    real_retry = updater._retry
    updater._retry = lambda func, *a, **k: real_retry(func, *a, tries=2, delay=0)
    try:
        inst.swap()
        swapped = "ok"
    except OSError as e:
        swapped = repr(e)
    finally:
        updater._retry = real_retry
    R.check("update: a read-only folder a withdrawn file leaves empty is removed",
            swapped == "ok" and not os.path.exists(os.path.join(app_dir, "extras")), swapped)
    R.check("update: hidden and system shipped files are updated", read(os.path.join(app_dir, "README.md")) == "new readme"
            and read(os.path.join(app_dir, "LICENSE")) == "new license", swapped)
    inst.rollback()
    R.check("rollback: all three are back", read(os.path.join(app_dir, "extras", "gone.txt")) == "old gone"
            and read(os.path.join(app_dir, "README.md")) == "old readme" and read(os.path.join(app_dir, "LICENSE")) == "old license")

# A list entry for _internal in other letters ("_Internal/lib.dll"), or with a trailing dot,
# is _internal itself on Windows: never touched (the new _internal is installed whole)
app_dir, inst = fake_install("internal-case")
old_list = {"_Internal/lib.dll": h("old _internal/lib.dll"), "_internal./lib.dll": h("x"),
            "bibles/en_kjv.json": h("old bibles/en_kjv.json")}
write(os.path.join(app_dir, "_internal", MANIFEST), json.dumps({"version": "2.1.0", "files": old_list}))
try:
    inst.swap()
    swapped = "ok"
except OSError as e:
    swapped = repr(e)
R.check("update: _internal in other letters or with a trailing dot is never touched",
        swapped == "ok" and read(os.path.join(app_dir, "_internal", "lib.dll")) == "new _internal/lib.dll", swapped)
try:
    inst.rollback()
    rolled = "ok"
except OSError as e:
    rolled = str(e)
R.check("rollback: and the old _internal comes back", rolled == "ok"
        and read(os.path.join(app_dir, "_internal", "lib.dll")) == "old _internal/lib.dll", rolled)

# A file another program holds open the whole time can't be updated: the update is undone, and
# rollback succeeds (the file was never changed), so the old version restarts as usual
app_dir, inst = fake_install("held-throughout")
write(os.path.join(app_dir, "README.md"), "old readme")
write(os.path.join(inst.source, "README.md"), "new readme")
held = os.path.normcase(os.path.join(app_dir, "README.md"))
real_retry, real_copy2 = updater._retry, updater.shutil.copy2
def held_copy2(src, dst, *a, **k):
    if os.path.normcase(dst) == held:
        raise PermissionError(32, "in use by another program", dst)
    return real_copy2(src, dst, *a, **k)
updater._retry = lambda func, *a, **k: real_retry(func, *a, tries=2, delay=0)
updater.shutil.copy2 = held_copy2
try:
    try:
        inst.swap()
        swapped = "ok"
    except OSError:
        swapped = "failed"
    try:
        inst.rollback()
        rolled = "ok"
    except OSError as e:
        rolled = str(e)
finally:
    updater._retry, updater.shutil.copy2 = real_retry, real_copy2
R.check("update: a file held throughout makes the update fail", swapped == "failed", swapped)
R.check("rollback: an unchanged held file is not an error", rolled == "ok", rolled)
R.check("rollback: everything is the old version", read(os.path.join(app_dir, "README.md")) == "old readme"
        and read(os.path.join(app_dir, "BibleWidget.exe")) == "old BibleWidget.exe")
R.check("rollback: and the backup is removed", not os.path.exists(inst.backup))

# A list entry rooted at the drive ("\Users\...") is off the program folder too (Python 3.13
# no longer calls it absolute)
app_dir, inst = fake_install("rooted-key")
victim = os.path.join(TMP, "rooted-victim.txt")
write(victim, "not the app's")
rooted = os.path.splitdrive(victim)[1].replace(os.sep, "/")
old_list = {rooted: h("not the app's"), "bibles/en_kjv.json": h("old bibles/en_kjv.json")}
write(os.path.join(app_dir, "_internal", MANIFEST), json.dumps({"version": "2.1.0", "files": old_list}))
try:
    inst.swap()
    swapped = "ok"
except OSError as e:
    swapped = repr(e)
R.check("update: a drive-rooted list entry is ignored", swapped == "ok" and read(victim) == "not the app's"
        and not any(r.lstrip("\\/").lower() == rooted.lstrip("/").replace("/", os.sep).lower() for r in inst.replaced), swapped)

# A finished install's backup that can't be deleted (a file in it held) is marked done, and the
# next update deletes it instead of keeping it as "an earlier backup"
app_dir, inst = fake_install("backup-held")
inst.swap()
real_retry, real_rmtree = updater._retry, updater.shutil.rmtree
updater._retry = lambda func, *a, **k: real_retry(func, *a, tries=2, delay=0)
updater.shutil.rmtree = lambda path, *a, **k: (_ for _ in ()).throw(PermissionError(13, "in use", path))
try:
    inst.discard_backup()
finally:
    updater.shutil.rmtree = real_rmtree
    updater._retry = real_retry
left = sorted(n for n in os.listdir(app_dir) if n.startswith(".update-backup"))
R.check("update: a backup that can't be deleted is marked done", len(left) == 1 and "-done-" in left[0], left)
_, nxt = fake_install("backup-held")
nxt.swap()
left = sorted(n for n in os.listdir(app_dir) if n.startswith(".update-backup"))
R.check("update: the next update deletes it, and keeps no 'earlier backup'", left == [".update-backup"]
        and "Kept an earlier backup" not in (read(os.path.join(app_dir, "update.log")) or ""), left)

# updates.txt as people may save it: a byte order mark, spaces, capitals
for raw in (b"\xef\xbb\xbfauto=off\n", b"auto = Off\n", "auto=off\nskip=v9.9.9\n".encode("cp1252")):
    folder = os.path.join(TMP, "settings-forms")
    write(os.path.join(folder, updater.SETTINGS_FILE), "")
    with open(os.path.join(folder, updater.SETTINGS_FILE), "wb") as f:
        f.write(raw)
    R.check(f"update settings: {raw[:14]!r} turns automatic checks off", updater.UpdateSettings(folder).auto is False)

sys.path.insert(0, ROOT)
import build
R.check("the build and the installer use the same list name", build.MANIFEST == MANIFEST)

# The old app hangs instead of quitting: the installer ends it, but only if it is this app's exe
close = getattr(updater, "_close_old_app", None)
hung = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
try:
    other = close(hung.pid, os.path.join(TMP, "swap", "app", "BibleWidget.exe"), 0.5) if close else None
    R.check("a hung process that is not this app is left alone", other is False and hung.poll() is None, other)
    said = []
    ended = close(hung.pid, sys.executable, 0.5, said.append) if close else None
    R.check("a hung old app is ended so the update can go on", ended is True and hung.poll() is not None, ended)
    R.check("and update.log says so", any("ending it" in m for m in said), said)
finally:
    if hung.poll() is None:
        hung.kill()

# Anything unexpected in the installer still leaves the user with a running widget
app_dir, inst = fake_install("unexpected")
real_wait, starts = updater._wait_for_exit, []
real_start = updater._Installer.start_app
updater._wait_for_exit = lambda pid, timeout: (_ for _ in ()).throw(RuntimeError("something new went wrong"))
updater._Installer.start_app = lambda self, *a: starts.append(self.app_dir)
try:
    code = updater.install_main(["--install-update", app_dir, "--wait-pid", "1", "--version", "9.9.9"])
except Exception as e:
    code = repr(e)
finally:
    updater._wait_for_exit, updater._Installer.start_app = real_wait, real_start
R.check("an unexpected installer error still starts the app", code == 1 and len(starts) == 1, code)
R.check("and it is written to update.log", "Unexpected problem" in (read(os.path.join(app_dir, "update.log")) or ""))

# A restore that can't finish keeps the backup and does not start the app
app_dir, inst = fake_install("stuck")
inst.swap()
os.remove(os.path.join(inst.backup, "BibleWidget.exe"))  # this file can't be put back
real_sleep = updater.time.sleep
updater.time.sleep = lambda s: None  # skip the retry waits
started = []
inst.start_app = lambda *a: started.append(a)
try:
    updater._restore_and_restart(inst)
finally:
    updater.time.sleep = real_sleep
R.check("failed restore: the backup is kept", os.path.isdir(inst.backup))
R.check("failed restore: the app is not started", started == [])
R.check("failed restore: the rest is still put back", read(os.path.join(app_dir, "_internal", "old_only.dll")) is not None)
R.check("failed restore: the log says where the backup is", "kept in" in read(os.path.join(app_dir, "update.log")))

# Leftovers older than an hour are cleaned up, newer ones are left (in a temp folder of our own)
scratch = os.path.join(TMP, "temp"); os.makedirs(scratch)
for name in ("BibleWidget-update-old", "BibleWidget-update-new", "SomethingElse-old"):
    os.makedirs(os.path.join(scratch, name))
for name in ("BibleWidget-update-old", "SomethingElse-old"):
    os.utime(os.path.join(scratch, name), (0, 0))
real_tempfile = updater.tempfile
updater.tempfile = types.SimpleNamespace(gettempdir=lambda: scratch)
try:
    updater.clean_leftovers()
finally:
    updater.tempfile = real_tempfile
R.check("old update leftovers are removed, others kept",
        sorted(os.listdir(scratch)) == ["BibleWidget-update-new", "SomethingElse-old"], os.listdir(scratch))
# ----- Slow update steps run off the UI thread, and the newest check wins -----
import threading
from PySide6.QtCore import QTimer
ticks = []
tick = QTimer(); tick.setInterval(10); tick.timeout.connect(lambda: ticks.append(1)); tick.start()
worker_threads = []
result = updater.run_in_background(lambda: (worker_threads.append(threading.current_thread().name), time.sleep(0.4), 42)[2])
tick.stop()
R.check("a slow update step runs on a worker thread", result == 42 and worker_threads == ["update-work"], worker_threads)
R.check("and the app keeps responding meanwhile", len(ticks) >= 15, f"{len(ticks)} timer ticks in 0.4 s")
try:
    updater.run_in_background(lambda: 1 / 0); error = None
except ZeroDivisionError as e:
    error = e
R.check("an error in the slow step reaches the caller", isinstance(error, ZeroDivisionError))
# A dialog opened while the installer starts (Stats, say) does not hold the app up once the
# installer has taken over; when the install did not start, the dialog is left alone
from PySide6.QtWidgets import QMessageBox
for started, want_closed in ((True, True), (False, False)):
    boxes = []
    def open_box():
        box = QMessageBox(QMessageBox.Information, "Stats", "open while installing")
        boxes.append(box)
        QTimer.singleShot(3000, box.accept)  # the user closes it after 3 s
        box.exec()
    QTimer.singleShot(50, open_box)
    t0 = time.monotonic()
    updater.run_in_background(lambda s=started: (time.sleep(0.3), s)[1], close_dialogs_when=bool)
    took = time.monotonic() - t0
    if want_closed:
        R.check("a dialog opened during the install is closed once the installer has taken over",
                took < 1.5 and boxes and not boxes[0].isVisible(), f"{took:.2f} s")
    else:
        R.check("...and left open when the install did not start (the user closes it)", took >= 2.5, f"{took:.2f} s")


class FakeReply:
    def __init__(self, tag):
        self.body = json.dumps({"tag_name": tag, "assets": []}).encode()
    def deleteLater(self): pass
    def error(self): return updater.QNetworkReply.NoError
    def readAll(self): return self.body


checker = updater.UpdateChecker(updater.UpdateSettings(os.path.join(TMP, "settings2")))
seen = []
checker.found.connect(lambda r: seen.append(("found", r["tag"])))
checker.up_to_date.connect(lambda: seen.append(("up to date",)))
checker._check_number = 2  # check 1 (automatic) is still running when check 2 (manual) starts
checker._on_checked(FakeReply("v9.0.0"), False, 1)
R.check("an older check's answer is ignored once a newer check started", seen == [], seen)
checker._on_checked(FakeReply("v9.0.0"), True, 2)
R.check("the newest check's answer is reported, once", seen == [("found", "v9.0.0")], seen)


# ----- The end of a download always reports success or failure -----
class DoneReply:
    def deleteLater(self): pass
    def readAll(self): return b""
    def error(self): return updater.QNetworkReply.NoError
    def errorString(self): return ""
    def abort(self): pass


class FullDisk:  # the last buffered bytes can't be written: close() raises
    def __init__(self, path): self.f = open(path, "wb")
    def write(self, data): self.f.write(data)
    def close(self): self.f.close(); raise OSError(28, "No space left on device")


class Quarantined:  # antivirus takes the zip away as soon as it is closed
    def __init__(self, path): self.f, self.path = open(path, "wb"), path
    def write(self, data): self.f.write(data)
    def close(self): self.f.close(); os.remove(self.path)


def finish_download(opener, data=b"zip bytes", expected=None, cancel=False):
    folder = updater.tempfile.mkdtemp(prefix="BibleWidget-download-", dir=TMP)
    path = os.path.join(folder, "BibleWidget-9.9.9-win64.zip")
    out = opener(path); out.write(data)
    c = updater.UpdateChecker(updater.UpdateSettings(os.path.join(TMP, "settings2")))
    events = []
    c.downloaded.connect(lambda p: events.append(("downloaded", p)))
    c.download_failed.connect(lambda m: events.append(("failed", m)))
    c._reply = DoneReply()  # what _on_sha leaves set while the zip downloads
    if cancel:
        c.cancel()  # the window closed while the finished zip was being checked
    try:
        c._on_zip(DoneReply(), out, path, expected or hashlib.sha256(data).hexdigest()); escaped = None
    except Exception as e:
        escaped = e
    return events, escaped, c.busy(), folder, path


events, escaped, busy, folder, path = finish_download(FullDisk)
R.check("download: a full disk at the end is reported as a failure", escaped is None and len(events) == 1
        and events[0][0] == "failed" and "space" in events[0][1], (escaped, events))
R.check("download: and the checker is free again", busy is False)
R.check("download: and the partial file and its folder are removed", not os.path.exists(folder), os.path.exists(path))
events, escaped, busy, folder, path = finish_download(Quarantined)
R.check("download: a zip removed by antivirus is reported as a failure", escaped is None and len(events) == 1
        and events[0][0] == "failed", (escaped, events))
R.check("download: and the checker is free again ", busy is False)
R.check("download: and its folder is removed", not os.path.exists(folder))
events, escaped, busy, folder, path = finish_download(lambda p: open(p, "wb"), expected="0" * 64)
R.check("download: a wrong checksum is a failure, with nothing left behind", escaped is None
        and events == [("failed", "The download did not match its checksum.")] and not os.path.exists(folder)
        and busy is False, (escaped, events))
events, escaped, busy, folder, path = finish_download(lambda p: open(p, "wb"))
R.check("download: a good download is reported and kept", escaped is None and events == [("downloaded", path)]
        and os.path.exists(path) and busy is False, (escaped, events))
events, escaped, busy, folder, path = finish_download(lambda p: open(p, "wb"), cancel=True)
R.check("download: one cancelled at the very end is not reported as downloaded", escaped is None
        and [e[0] for e in events] == ["failed"] and not os.path.exists(folder) and busy is False, (escaped, events))


# ----- The Update window: Esc stops its download, and only the window that started one installs it -----
import about_window
from PySide6.QtCore import QObject, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


class FakeWidget(QObject):
    def __init__(self):
        super().__init__()
        self._update_settings = updater.UpdateSettings(os.path.join(TMP, "settings2"))
        self._updater = updater.UpdateChecker(self._update_settings, self)
    def _s(self, text): return text
    def _clear_update(self): pass
    def _exit_app(self, reason="Exit was chosen"):
        # As QApplication.quit() does: every open window is asked to close, and one that refuses stops the quit
        refused = [w for w in QApplication.topLevelWidgets()
                   if isinstance(w, about_window.UpdateWindow) and w.isVisible() and not w.close()]
        installs.append("exit" if not refused else "quit refused")


class PendingReply(DoneReply):  # a download in progress; abort() ends it the way Qt does
    def __init__(self, checker): self.checker = checker
    def abort(self): aborts.append(1); self.checker._fail("Operation canceled")


installs, aborts = [], []
widget = FakeWidget()
checker = widget._updater
checker.download = lambda release, folder: setattr(checker, "_reply", PendingReply(checker))
release = {"tag": "v9.9.9", "version": "9.9.9", "notes": "", "page": "",
           "zip_url": "https://example.invalid/x.zip", "sha_url": "https://example.invalid/x.zip.sha256"}
real_self_update, real_start_install, real_mkdtemp = updater.can_self_update, updater.start_install, about_window.tempfile
updater.can_self_update = lambda folder=None: True  # (the real check writes a probe file into the app folder)
updater.start_install = lambda path, version, *a: (installs.append(path), False)[1]
about_window.tempfile = types.SimpleNamespace(mkdtemp=lambda prefix: updater.tempfile.mkdtemp(prefix=prefix, dir=TMP))


def open_window():
    window = about_window.UpdateWindow(widget, release)
    window.setAttribute(Qt.WA_DeleteOnClose)
    window.show(); QApplication.processEvents()
    return window


def flush():
    for _ in range(3):
        QApplication.processEvents(); QApplication.sendPostedEvents(None, 0)


try:
    first = open_window()
    first.go.click()
    R.check("window: Update Now starts the download", checker.busy())
    QTest.keyClick(first, Qt.Key_Escape); flush()
    R.check("window: Esc stops its download", aborts == [1] and not checker.busy(), (aborts, checker.busy()))
    checker._reply = None
    second = open_window()
    other = updater.tempfile.mkdtemp(prefix="BibleWidget-download-", dir=TMP)
    checker.downloaded.emit(os.path.join(other, "a.zip"))  # a download this window did not start
    checker.download_failed.emit("someone else's download")
    flush()
    R.check("window: a download it did not start is not installed", installs == [], installs)
    R.check("window: nor shown as its failure", second.go.text() == "Update Now" and second.go.isEnabled()
            and second.message.text() == "", (second.go.text(), second.message.text()))
    second.go.click()
    checker._reply = None
    checker.downloaded.emit(os.path.join(other, "b.zip"))  # its own download
    flush()
    R.check("window: its own download is installed", installs == [os.path.join(other, "b.zip")], installs)
    second.close(); flush()

    # While the update is being unpacked, Esc and closing are ignored (the app restarts in a moment);
    # if it then fails, the window is still there to say so
    from PySide6.QtCore import QTimer
    def slow_install(path, version, *a):
        time.sleep(0.6)
        return False
    updater.start_install = slow_install
    third = open_window()
    third.go.click()
    checker._reply = None
    QTimer.singleShot(150, lambda: (QTest.keyClick(third, Qt.Key_Escape), third.close()))
    checker.downloaded.emit(os.path.join(other, "c.zip"))
    flush()
    R.check("window: Esc and close are ignored while installing, and a failure is still shown",
            third.isVisible() and "could not be installed" in third.message.text(), third.message.text())
    third.close(); flush()

    # Once the installer has started, the app quits at once: the window must not hold the quit up
    updater.start_install = lambda path, version, *a: True
    installs.clear()
    fourth = open_window()
    fourth.go.click()
    checker._reply = None
    checker.downloaded.emit(os.path.join(other, "d.zip"))
    flush()
    R.check("window: after handing over to the installer, the app can quit", installs == ["exit"], installs)
finally:
    updater.can_self_update, updater.start_install, about_window.tempfile = real_self_update, real_start_install, real_mkdtemp

# The real app, in its own process: once the installer has taken over, it really quits
import subprocess
probe = subprocess.run([sys.executable, "-X", "utf8", "-B", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                          "quit_after_handover.py")],
                       capture_output=True, text=True, encoding="utf-8", timeout=60,
                       env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
R.check("the real app quits at once after handing over to the installer",
        probe.returncode == 0 and "exit code 0" in probe.stdout, (probe.returncode, probe.stdout.strip()[-80:]))

R.finish()
