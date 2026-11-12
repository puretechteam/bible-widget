"""Build the standalone Windows release: dist/BibleWidget/ and BibleWidget-<version>-win64.zip.

Needs requirements-dev.txt (PyInstaller). Users of the build need nothing installed.
Run: python build.py"""

import os
import sys
import time
import shutil
import re
import json
import hashlib
import zipfile
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "build")
DIST = os.path.join(ROOT, "dist")
ASSETS = os.path.join(BUILD, "assets")
sys.path.insert(0, ROOT)

from version import VERSION, version_tuple  # noqa: E402

MANIFEST = "shipped.json"  # the same name updater.MANIFEST reads

VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Pure Tech'),
      StringStruct('FileDescription', 'Bible Widget'),
      StringStruct('FileVersion', '{v}'),
      StringStruct('InternalName', 'BibleWidget'),
      StringStruct('LegalCopyright', 'Pure Tech, CC0 1.0'),
      StringStruct('OriginalFilename', 'BibleWidget.exe'),
      StringStruct('ProductName', 'Bible Widget'),
      StringStruct('ProductVersion', '{v}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def make_assets():
    os.makedirs(ASSETS, exist_ok=True)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # noqa: F841 (needed for painting)
    from tray_icon import write_ico
    write_ico(os.path.join(ASSETS, "BibleWidget.ico"))
    numbers = tuple(version_tuple(VERSION)[:3]) + (0,)
    with open(os.path.join(ASSETS, "version_info.txt"), "w", encoding="utf-8") as f:
        f.write(VERSION_INFO.format(t=numbers, v=VERSION))


def run_pyinstaller():
    subprocess.run([sys.executable, "-m", "PyInstaller", "BibleWidget.spec", "--noconfirm", "--clean",
                    "--distpath", DIST, "--workpath", os.path.join(BUILD, "pyinstaller")],
                   cwd=ROOT, check=True)


# What the download takes from each data folder (not Thumbs.db, notes, or a Bible kept aside as
# en_kjv.json.edited-<date>): bibles/ and prayers/ sit next to the exe so users can add
# translations, and the README's screenshots come along so it reads the same as on GitHub
SHIPPED_DATA = {"bibles": ".json", "prayers": ".json", "screenshots": ".png"}


def data_files():
    """(folder, file name) of every data file the download ships."""
    for folder, ext in SHIPPED_DATA.items():
        for name in sorted(os.listdir(os.path.join(ROOT, folder))):
            # Exactly ".json": the app loads only those, and the license check looks only at those
            if name.endswith(ext) and os.path.isfile(os.path.join(ROOT, folder, name)):
                yield folder, name


def add_data(app_dir):
    for folder, name in data_files():
        os.makedirs(os.path.join(app_dir, folder), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, folder, name), os.path.join(app_dir, folder, name))
    for name in ("README.md", "CHANGELOG.md", "LICENSE"):
        if os.path.exists(os.path.join(ROOT, name)):
            shutil.copy2(os.path.join(ROOT, name), app_dir)
    add_licenses(app_dir)


def add_licenses(app_dir):
    """The licenses of the software inside the download, which they require to travel with it:
    Qt, PySide6 and Shiboken6 (LGPL v3, which builds on the GPL v3), Python and the libraries it
    lists (libffi among them), and the Unicode License for the CLDR language names."""
    out = os.path.join(app_dir, "licenses")
    os.makedirs(out, exist_ok=True)
    for name in ("LGPL-3.0.txt", "GPL-3.0.txt", "Qt-third-party.txt", "Unicode-3.0.txt"):
        shutil.copy2(os.path.join(ROOT, "licenses", name), out)
    python_license = os.path.join(sys.base_prefix, "LICENSE.txt")
    if not os.path.exists(python_license):
        raise SystemExit(f"Not building: Python's license file is missing ({python_license}). "
                         "Build with the python.org installer's Python, which has it.")
    shutil.copy2(python_license, os.path.join(out, "Python.txt"))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_manifest(app_dir):
    """_internal/shipped.json lists every file the download puts outside _internal, with its
    SHA-256. The next update uses it to tell files you added or edited from untouched ones."""
    files = {}
    for root, dirs, names in os.walk(app_dir):
        dirs[:] = [d for d in dirs if not (root == app_dir and d == "_internal")]
        for name in names:
            full = os.path.join(root, name)
            files[os.path.relpath(full, app_dir).replace(os.sep, "/")] = sha256_file(full)
    with open(os.path.join(app_dir, "_internal", MANIFEST), "w", encoding="utf-8") as f:
        json.dump({"version": VERSION, "files": files}, f, indent=1, sort_keys=True)
    return len(files)


def make_zip(app_dir):
    zip_path = os.path.join(DIST, f"BibleWidget-{VERSION}-win64.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, _, files in os.walk(app_dir):
            for name in files:
                full = os.path.join(root, name)
                z.write(full, os.path.join("BibleWidget", os.path.relpath(full, app_dir)))
    with open(zip_path + ".sha256", "w", encoding="ascii") as f:
        f.write(f"{sha256_file(zip_path)}  {os.path.basename(zip_path)}\n")
    return zip_path


def folder_size(path):
    return sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(path) for f in fs)


# Standard library packages the app never imports (not in any test or self-test run on Python
# 3.13), left out of the download. Only those this Python does not import when loading the app are
# left out: on Python 3.11, for example, pathlib imports urllib at startup, so urllib stays.
NEVER_IMPORTED = ("email", "smtplib", "http", "urllib", "ipaddress", "tarfile", "gzip", "csv", "calendar",
                  "_strptime", "pprint", "tracemalloc", "stringprep", "py_compile", "quopri", "getopt",
                  "_pydatetime", "dataclasses", "_threading_local", "_py_abc")
APP_MODULES = ("widget_window", "updater", "verses", "verses_window", "share_image", "backgrounds",
               "about_window", "prayer_window", "tray_icon", "selftest", "menu_strings", "bible_loader")


def modules_to_leave_out():
    """NEVER_IMPORTED minus anything this Python imports when the app's modules load."""
    code = ("import sys, json\nsys.path.insert(0, sys.argv[1])\n"
            f"for m in {APP_MODULES!r}: __import__(m)\n"
            "print(json.dumps(sorted({n.split('.')[0] for n in sys.modules})))")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    out = subprocess.run([sys.executable, "-B", "-c", code, ROOT], capture_output=True, text=True, env=env, check=True)
    imported = set(json.loads(out.stdout.strip().splitlines()[-1]))
    return [m for m in NEVER_IMPORTED if m not in imported]


# The only licenses a shipped Bible may have. Anything else (or no record at all) stops the build.
ALLOWED_LICENSES = ("Public Domain", "CC BY-SA 4.0")


def check_bible_licenses():
    """Every Bible in bibles/ needs a record in index.json (license, year, source) with an allowed
    license, and must be listed in LICENSE, under that license. Returns a list of problems (empty
    when all is well)."""
    folder = os.path.join(ROOT, "bibles")
    with open(os.path.join(folder, "index.json"), encoding="utf-8-sig") as f:
        records = {v["abbreviation"]: v for g in json.load(f) for v in g["versions"]}
    with open(os.path.join(ROOT, "LICENSE"), encoding="utf-8") as f:
        license_text = f.read()
    # LICENSE lists the public domain Bibles first, then those under CC BY-SA 4.0
    cc_start = license_text.find("Under the Creative Commons Attribution-ShareAlike 4.0")
    if cc_start < 0:
        return ["LICENSE: the CC BY-SA 4.0 section is missing"]
    problems = []
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith(".json") and not name.endswith(".json"):
            problems.append(f"{name}: name it with a lowercase .json (the app only loads those)")
            continue
        if not name.endswith(".json") or name in ("index.json", "book_names.json"):
            continue
        abbr = name[:-len(".json")]
        record = records.get(abbr)
        if record is None:
            problems.append(f"{abbr}: no record in bibles/index.json")
            continue
        if record.get("license") not in ALLOWED_LICENSES:
            problems.append(f"{abbr}: license {record.get('license')!r} is not one of {ALLOWED_LICENSES}")
        if not record.get("year") or not str(record.get("source", "")).startswith("https://"):
            problems.append(f"{abbr}: needs a year and an https source in bibles/index.json")
        row = re.search(rf"^\| `{re.escape(abbr)}` \|(.*)$", license_text, re.M)
        if row is None:
            problems.append(f"{abbr}: not listed in LICENSE")
        else:
            listed_as = "CC BY-SA 4.0" if row.start() > cc_start else "Public Domain"
            if record.get("license") != listed_as:
                problems.append(f"{abbr}: index.json says {record.get('license')}, LICENSE lists it as {listed_as}")
            # The year in index.json and the one LICENSE gives must be the same edition
            for year in re.findall(r"\d{4}", str(record.get("year", ""))):
                if year not in row.group(1):
                    problems.append(f"{abbr}: index.json says {year}, LICENSE does not")
    shipped = {n[:-len(".json")] for n in os.listdir(folder) if n.endswith(".json")}
    for listed in sorted(set(re.findall(r"^\| `([a-z]{2}_[a-z0-9]+)` \|", license_text, re.M)) - shipped):
        problems.append(f"{listed}: listed in LICENSE but not shipped")
    return problems


def check_software_versions():
    """LICENSE names the Python and PySide6 the download is built with: they must be these."""
    import PySide6
    with open(os.path.join(ROOT, "LICENSE"), encoding="utf-8") as f:
        text = f.read()
    problems = []
    python = f"Python {sys.version_info.major}.{sys.version_info.minor},"
    if python not in text:
        problems.append(f"LICENSE does not name {python.rstrip(',')}, which this build uses")
    if f"PySide6 and Shiboken6 {PySide6.__version__})" not in text:
        problems.append(f"LICENSE does not name PySide6 {PySide6.__version__}, which this build uses")
    return problems


def main():
    start = time.time()
    problems = check_bible_licenses()
    if problems:
        raise SystemExit("Not building: a Bible's license is not recorded.\n  " + "\n  ".join(problems))
    problems = check_software_versions()
    if problems:
        raise SystemExit("Not building: LICENSE names other software versions.\n  " + "\n  ".join(problems))
    shutil.rmtree(os.path.join(DIST, "BibleWidget"), ignore_errors=True)
    make_assets()
    run_pyinstaller()
    app_dir = os.path.join(DIST, "BibleWidget")
    add_data(app_dir)
    shipped = write_manifest(app_dir)
    zip_path = make_zip(app_dir)
    mb = 1024 * 1024
    print(f"Built Bible Widget {VERSION} in {time.time() - start:.0f}s")
    print(f"  folder: {app_dir} ({folder_size(app_dir) / mb:.1f} MB, {shipped} files listed in {MANIFEST})")
    print(f"  zip:    {zip_path} ({os.path.getsize(zip_path) / mb:.1f} MB)")


if __name__ == "__main__":
    main()
