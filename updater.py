"""Update checks against GitHub releases, and installing an update in place.

Checking sends one anonymous request to the public GitHub API. Installing (standalone exe only):
1. The running app downloads the release zip, verifies its SHA-256 and unpacks it to a temp folder.
2. It starts the NEW BibleWidget.exe from there with --install-update, waits until that installer
   reports it is running, then quits.
3. The installer (the new version's own code, so every release brings its own) waits for the old
   app to exit, swaps the program files with a full rollback on any error, starts the installed
   version and waits for it to confirm it started; if it does not, everything is put back and the
   old version is started again.
Only files that ship in the zip are replaced, and files the old release shipped that the new one
does not are removed (kept aside if the user edited them). Settings, favorites, history and any
Bibles the user added are never touched."""

import os
import re
import sys
import json
import time
import stat
import shutil
import hashlib
import logging
import secrets
import tempfile
import zipfile
import datetime
import subprocess
from PySide6.QtCore import QObject, Signal, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from paths import APP_DIR, FROZEN, folder_writable, read_json, read_text, write_text
from version import VERSION, REPO, version_tuple

log = logging.getLogger("bible_widget")

# The override exists only so tests can point a source run at a local server; the exe ignores it.
_TEST_URL = None if FROZEN else os.environ.get("BIBLE_WIDGET_UPDATE_URL")
API_URL = _TEST_URL or f"https://api.github.com/repos/{REPO}/releases/latest"
SETTINGS_FILE = "updates.txt"
CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000
FIRST_CHECK_DELAY_MS = 15 * 1000
INSTALLER_START_TIMEOUT_S = 20   # the old app waits this long for the installer to report in
OLD_APP_EXIT_TIMEOUT_S = 60      # the installer waits this long for the old app to close
NEW_APP_START_TIMEOUT_S = 60     # and this long for the new version to confirm it started
STARTED_ENV = "BIBLE_WIDGET_STARTED_FILE"
MANIFEST = "shipped.json"  # in _internal: the files a download put next to the exe, with their SHA-256
NEVER_KEEP = {"BibleWidget.exe", "bibles/index.json"}  # always replaced (index.json is merged instead)
STAGING_PREFIX = "BibleWidget-update-"
DOWNLOAD_PREFIX = "BibleWidget-download-"  # a download's own temp folder
EXE_NAME = "BibleWidget.exe"


def zip_name(version):
    return f"BibleWidget-{version}-win64.zip"


class UpdateSettings:
    """auto=on|off and skip=<tag>, kept in updates.txt next to the other settings."""

    def __init__(self, folder=None):
        self.path = os.path.join(folder or APP_DIR, SETTINGS_FILE)
        self.auto = True
        self.skip = ""
        try:
            lines = read_text(self.path).splitlines()  # also with a byte order mark, or in ANSI
        except OSError:  # none yet, or unreadable: the defaults
            lines = []
        for line in lines:
            key, _, value = line.partition("=")
            key, value = key.strip().lower(), value.strip()
            if key == "auto":
                self.auto = value.lower() != "off"
            elif key == "skip":
                self.skip = value

    def save(self):
        try:
            write_text(self.path, f"auto={'on' if self.auto else 'off'}\nskip={self.skip}\n")
        except OSError:
            log.exception("Could not save update settings")


def can_self_update(folder=None):
    """Only the standalone exe updates itself, and only where it may write its own folder."""
    if not FROZEN and not os.environ.get("BIBLE_WIDGET_UPDATE_TEST"):
        return False
    return folder_writable(folder or APP_DIR)


def _allowed_download(url):
    """Release files must come over HTTPS (a local test server is allowed only in tests)."""
    return bool(url) and (url.startswith("https://") or bool(_TEST_URL))


class UpdateChecker(QObject):
    """Emits found(release) when a newer, not-skipped release exists; up_to_date() or
    failed(message) otherwise. `release` is a dict: tag, version, notes, page, zip_url, sha_url."""

    found = Signal(dict)
    up_to_date = Signal()
    failed = Signal(str)
    progress = Signal(int, int)
    downloaded = Signal(str)
    download_failed = Signal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._net = QNetworkAccessManager(self)
        self._reply = None
        self._cancelled = False
        self._write_error = None
        self._check_number = 0
        self._check_pending = False

    def _request(self, url):
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.UserAgentHeader, f"BibleWidget/{VERSION}")
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setTransferTimeout(30000)
        return request

    def check(self, manual=False):
        # A newer check replaces one still running (an automatic one, then Check for Updates)
        self._check_number += 1
        self._check_pending = True
        number = self._check_number
        reply = self._net.get(self._request(API_URL))
        reply.finished.connect(lambda: self._on_checked(reply, manual, number))

    def _on_checked(self, reply, manual, number=None):
        reply.deleteLater()
        if number is not None and number != self._check_number:
            return  # replaced by a newer check: only its result is reported
        self._check_pending = False
        if reply.error() != QNetworkReply.NoError:
            log.info("Update check failed: %s", reply.errorString())
            self.failed.emit(reply.errorString())
            return
        try:
            data = json.loads(bytes(reply.readAll()).decode("utf-8"))
            tag = data["tag_name"]
        except (ValueError, KeyError, TypeError):
            log.warning("Update check: unexpected reply")
            self.failed.emit("unexpected reply")
            return
        if version_tuple(tag) <= version_tuple(VERSION) or (not manual and tag == self.settings.skip):
            log.info("Update check: up to date (latest %s)", tag)
            self.up_to_date.emit()
            return
        version = tag.lstrip("vV")
        assets = {a.get("name"): a.get("browser_download_url") for a in data.get("assets", [])}
        release = {
            "tag": tag, "version": version, "notes": data.get("body") or "",
            "page": data.get("html_url") or "",
            "zip_url": assets.get(zip_name(version)), "sha_url": assets.get(zip_name(version) + ".sha256"),
        }
        log.info("Update available: %s", tag)
        self.found.emit(release)

    # ----- Downloading -----

    def checking(self):
        """True while a check for a new release is waiting for GitHub's answer."""
        return self._check_pending

    def busy(self):
        return self._reply is not None

    def download(self, release, folder):
        """Download the release zip and its checksum into `folder`, then verify it."""
        if self.busy():
            return  # one download at a time
        self._cancelled = False
        zip_url, sha_url = release.get("zip_url"), release.get("sha_url")
        if not (_allowed_download(zip_url) and _allowed_download(sha_url)):
            self._fail("This release has no Windows download.", folder)
            return
        sha_reply = self._net.get(self._request(sha_url))
        self._reply = sha_reply
        sha_reply.finished.connect(lambda: self._on_sha(sha_reply, release, folder))

    def _on_sha(self, reply, release, folder):
        reply.deleteLater()
        if reply.error() != QNetworkReply.NoError:
            self._fail(reply.errorString(), folder)
            return
        text = bytes(reply.readAll()).decode("utf-8-sig", "replace")
        match = re.search(r"\b[0-9a-fA-F]{64}\b", text)
        if not match:
            self._fail("The checksum file could not be read.", folder)
            return
        expected = match.group(0).lower()
        path = os.path.join(folder, zip_name(release["version"]))
        try:
            out = open(path, "wb")
        except OSError as e:
            self._fail(str(e), folder)
            return
        zip_reply = self._net.get(self._request(release["zip_url"]))
        self._reply = zip_reply
        self._write_error = None

        def write_chunk():
            try:
                out.write(bytes(zip_reply.readAll()))
            except (OSError, ValueError) as e:
                self._write_error = str(e)  # reported instead of "Operation canceled"
                zip_reply.abort()

        zip_reply.readyRead.connect(write_chunk)
        zip_reply.downloadProgress.connect(lambda got, total: self.progress.emit(int(got), int(total)))
        zip_reply.finished.connect(lambda: self._on_zip(zip_reply, out, path, expected))

    def _on_zip(self, reply, out, path, expected):
        # Every way out of here ends in downloaded or download_failed, or the window would wait forever
        reply.deleteLater()
        error = self._write_error
        try:
            try:
                out.write(bytes(reply.readAll()))
            finally:
                out.close()  # can fail too: a full disk, or antivirus holding the file
            if error is None and reply.error() != QNetworkReply.NoError:
                error = reply.errorString()
            if error is None and run_in_background(sha256_of, path) != expected:
                log.error("Update download failed verification")
                error = "The download did not match its checksum."
            if error is None and self._cancelled:
                error = "Cancelled"  # cancelled while the checksum was being checked
        except Exception as e:
            error = error or str(e) or repr(e)
        if error is not None:
            self._fail(error, os.path.dirname(path), path)  # never leave a partial or unverified file behind
            return
        self._reply = None
        self.downloaded.emit(path)

    def _fail(self, message, folder=None, path=None):
        self._reply = None
        if path:
            _remove(path)
        if folder and os.path.basename(os.path.normpath(folder)).startswith(DOWNLOAD_PREFIX):
            _remove(folder)  # the download's own temp folder
        log.info("Update download failed: %s", message)
        self.download_failed.emit(message)

    def cancel(self):
        if self._reply is not None:
            self._cancelled = True
            self._reply.abort()


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _retry(func, *args, tries=10, delay=0.5):
    """Call func(*args), retrying on OSError for about tries * delay seconds."""
    for attempt in range(tries):
        try:
            return func(*args)
        except OSError:
            if attempt == tries - 1:
                raise
            time.sleep(delay)


_READ_ONLY, _HIDDEN, _SYSTEM = 0x1, 0x2, 0x4  # Windows file attributes


def _writable(path):
    """Clear a file's or folder's read-only, hidden and system marks (set by you, a sync tool, or
    Windows when a folder gets a custom icon): on Windows a read-only file or folder can't be
    deleted, and a hidden or system file can't be overwritten, so the update would fail on it for
    no good reason."""
    try:
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetFileAttributesW.restype = ctypes.c_uint32
            attrs = kernel32.GetFileAttributesW(str(path))
            if attrs != 0xFFFFFFFF and attrs & (_READ_ONLY | _HIDDEN | _SYSTEM):
                kernel32.SetFileAttributesW(str(path), attrs & ~(_READ_ONLY | _HIDDEN | _SYSTEM))
        elif os.path.exists(path) and not os.access(path, os.W_OK):
            os.chmod(path, os.stat(path).st_mode | stat.S_IWRITE)
    except (OSError, AttributeError):
        pass
    return path


def _rmtree(path):
    """shutil.rmtree that also deletes read-only files (a backup keeps their read-only mark)."""
    def clear_and_retry(func, failed, *_):
        _writable(failed)
        func(failed)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=clear_and_retry)
    else:
        shutil.rmtree(path, onerror=clear_and_retry)


def _read_manifest(path):
    """{relative path: sha256} from a shipped.json, or None if there is none (or it can't be read)."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            files = json.load(f).get("files")
        return files if isinstance(files, dict) else None
    except (OSError, ValueError, AttributeError):
        return None


def _merge_index(old_path, new_path, withdrawn=()):
    """bibles/index.json names the translations. An update ships its own; keep the entries
    for Bibles the user added (any abbreviation the new file does not list), but not for
    the `withdrawn` ones: Bibles the old release shipped that the new one does not."""
    try:
        old = read_json(old_path)  # the user's, possibly saved by an editor in ANSI
        new = read_json(new_path)
        known = {v.get("abbreviation") for g in new for v in g.get("versions", [])}
        added = 0
        for group in old:
            for version in group.get("versions", []):
                if version.get("abbreviation") in known or version.get("abbreviation") in withdrawn:
                    continue
                target = next((g for g in new if g.get("language") == group.get("language")), None)
                if target is None:
                    target = {"language": group.get("language", ""), "versions": []}
                    new.append(target)
                target["versions"].append(version)
                known.add(version.get("abbreviation"))
                added += 1
    except (OSError, ValueError, TypeError, AttributeError):
        return  # an unreadable index: the new one stands as it is
    if added:
        with open(new_path, "w", encoding="utf-8") as f:
            json.dump(new, f, ensure_ascii=False, indent=4)


def _remove(path):
    try:
        if os.path.isdir(path):
            try:
                _rmtree(path)
            except OSError:
                shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(_writable(path))
    except OSError:
        pass


# ----- Handing over to the installer (runs in the old app) -----

def run_in_background(fn, *args, close_dialogs_when=None):
    """Run fn(*args) on a worker thread while Qt keeps the app's windows responsive, and return
    its result (or raise its error). For the slow steps of an update: checking the download's
    SHA-256, unpacking it and waiting for the installer.

    A dialog the user opens meanwhile (Stats, say) runs its own event loop, and this one can only
    return once it closes. If close_dialogs_when(result) is true (the installer has taken over and
    the app must quit), such dialogs are closed so the app is not held up."""
    import threading
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
    result = {}

    def work():
        try:
            result["value"] = fn(*args)
        except BaseException as e:  # handed back to the caller below
            result["error"] = e

    thread = threading.Thread(target=work, name="update-work", daemon=True)
    thread.start()
    if QCoreApplication.instance() is not None:
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(20)
        from PySide6.QtWidgets import QApplication
        before = QApplication.activeModalWidget() if isinstance(QCoreApplication.instance(), QApplication) else None

        def check():
            if thread.is_alive():
                return
            loop.quit()
            if close_dialogs_when is not None and "error" not in result and close_dialogs_when(result.get("value")):
                modal = QApplication.activeModalWidget()
                if modal is not None and modal is not before:
                    modal.reject() if hasattr(modal, "reject") else modal.close()
        timer.timeout.connect(check)
        timer.start()
        if thread.is_alive():
            loop.exec()
        timer.stop()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


def extract(zip_path, staging):
    """Unpack the release zip; returns the folder that holds BibleWidget.exe."""
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(staging)
    for root, _, files in os.walk(staging):
        if EXE_NAME in files:
            return root
    raise FileNotFoundError(f"{EXE_NAME} not found in the update")


def _detached_flags():
    """No console, not tied to this process's job (so it survives this app quitting)."""
    if sys.platform != "win32":
        return []
    base = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW
    return [base | 0x01000000, base]  # first try with CREATE_BREAKAWAY_FROM_JOB


def start_install(zip_path, version, app_dir=None, pid=None):
    """Unpack the update and start its installer. Returns True once the installer reports that
    it is running; the caller must then quit. Returns False (and changes nothing) otherwise."""
    app_dir = os.path.realpath(app_dir or APP_DIR)
    staging_root = os.path.realpath(tempfile.mkdtemp(prefix=STAGING_PREFIX))
    try:
        staging = extract(zip_path, staging_root)
    except (OSError, zipfile.BadZipFile) as e:
        log.error("Could not unpack the update: %s", e)
        _remove(staging_root)
        return False
    download = (os.path.dirname(zip_path) if os.path.basename(os.path.dirname(zip_path)).startswith(DOWNLOAD_PREFIX)
                else zip_path)
    marker = os.path.join(staging_root, "installer.started")
    args = [os.path.join(staging, EXE_NAME), "--install-update", app_dir, "--wait-pid", str(pid or os.getpid()),
            "--version", version, "--marker", marker]
    process = None
    for flags in _detached_flags() or [0]:
        try:
            process = subprocess.Popen(args, cwd=staging, creationflags=flags, close_fds=True)
            break
        except OSError as e:
            log.warning("Could not start the installer with flags %#x: %s", flags, e)
    if process is None:
        _remove(staging_root)
        return False
    deadline = time.monotonic() + INSTALLER_START_TIMEOUT_S
    while time.monotonic() < deadline:
        if os.path.exists(marker):
            log.info("Installer for %s is running", version)
            _remove(download)  # only now: if the installer had failed, the download could be tried again
            return True
        if process.poll() is not None:
            break
        time.sleep(0.1)
    log.error("The installer for %s did not start (exit code %s)", version, process.poll())
    if process.poll() is None:
        process.kill()
    _remove(staging_root)
    return False


# ----- The installer (runs as the NEW version, from the temp folder) -----

class _Installer:
    def __init__(self, app_dir, source, version, log_path):
        self.app_dir = app_dir
        self.source = source
        self.version = version
        self.log_path = log_path
        self.backup = os.path.join(app_dir, ".update-backup")
        self.moved_internal = False
        self.made_backup = False  # only a backup this install made is ever deleted
        self.replaced = []   # files that existed and were backed up, then overwritten
        self.kept_yours = []  # files you added that share a name with one the update ships
        self.created = []    # files the update added (removed again on rollback)
        self.made_dirs = []  # folders the update made for them (removed again on rollback, if empty)

    def say(self, message):
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {message}\n")
        except OSError:
            pass

    def swap(self):
        """Put the new program files in place. Raises on any problem; rollback() undoes it.
        Each file step is retried for a few seconds (antivirus often holds files briefly)."""
        for name in os.listdir(self.app_dir):
            if name.startswith(os.path.basename(self.backup) + "-done-"):
                _remove(os.path.join(self.app_dir, name))  # from a finished install: not needed
        if os.path.exists(self.backup):
            # Left by an earlier restore that could not finish: it may be the only good copy
            kept = f"{self.backup}-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
            _retry(os.replace, self.backup, kept)
            self.say(f"Kept an earlier backup as {os.path.basename(kept)}")
        os.makedirs(self.backup)
        self.made_backup = True
        internal = os.path.join(self.app_dir, "_internal")
        shipped = _read_manifest(os.path.join(internal, MANIFEST))  # what the old version installed
        # Looked up ignoring case, as Windows finds files: "Readme.md" then "README.md" is one file
        shipped_any_case = {k.lower(): v for k, v in shipped.items()} if shipped is not None else None
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        if os.path.isdir(internal):
            _retry(os.replace, internal, os.path.join(self.backup, "_internal"))  # one atomic rename
            self.moved_internal = True
        shutil.copytree(os.path.join(self.source, "_internal"), internal,
                        copy_function=lambda src, dst: _retry(shutil.copy2, src, dst))
        ships = set()  # what the new release puts outside _internal
        merge_index = None
        for root, dirs, files in os.walk(self.source):
            rel_root = os.path.relpath(root, self.source)
            if rel_root == "_internal" or rel_root.startswith("_internal" + os.sep):
                continue
            for name in files:
                rel = os.path.normpath(os.path.join(rel_root, name))
                dest = os.path.join(self.app_dir, rel)
                folder = os.path.dirname(dest)
                new_dirs = []
                while not os.path.isdir(folder):
                    new_dirs.append(folder)
                    folder = os.path.dirname(folder)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                self.made_dirs.extend(reversed(new_dirs))  # outermost first
                saved = None
                key = rel.replace(os.sep, "/")
                ships.add(key)
                if os.path.exists(dest) and shipped is not None and key not in NEVER_KEEP:
                    if key.lower() not in shipped_any_case:
                        # Not something an earlier download put here: it is yours. Keep it.
                        self.kept_yours.append(key)
                        self.say(f"Kept your {key}; the update's file of that name was not installed")
                        continue
                    if _retry(sha256_of, dest) != shipped_any_case[key.lower()]:
                        # You edited a shipped file: keep your version next to the new one
                        mine = f"{rel}.edited-{stamp}"
                        _retry(shutil.copy2, dest, os.path.join(self.app_dir, mine))
                        self.created.append(mine)
                        self.say(f"You had edited {key}; your version is kept as {os.path.basename(mine)}")
                if os.path.exists(dest):
                    saved = os.path.join(self.backup, rel)
                    os.makedirs(os.path.dirname(saved), exist_ok=True)
                    _retry(shutil.copy2, dest, saved)
                    self.replaced.append(rel)
                else:
                    self.created.append(rel)
                _retry(shutil.copy2, os.path.join(root, name), _writable(dest))
                if saved and rel == os.path.join("bibles", "index.json"):
                    merge_index = (saved, dest)  # once the withdrawn Bibles are known
        withdrawn = self._remove_withdrawn(shipped, ships, stamp) if shipped is not None else set()
        if merge_index:
            _merge_index(*merge_index, withdrawn=withdrawn)
        if self.kept_yours:
            # The new list must not claim your files, or the next update would treat them as edited
            path = os.path.join(internal, MANIFEST)
            new = _read_manifest(path)
            if new is not None:
                for key in self.kept_yours:
                    new.pop(key, None)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"version": self.version, "files": new}, f, indent=1, sort_keys=True)

    def _remove_withdrawn(self, shipped, ships, stamp):
        """Remove the files the old release shipped that the new one does not (a withdrawn Bible,
        say), backed up so rollback() puts them back. One you edited is kept as <name>.edited-<date>.
        Returns the abbreviations of the withdrawn Bibles, which leave index.json."""
        bibles = set()
        ships_any_case = {k.lower() for k in ships} | {k.lower() for k in NEVER_KEEP}
        for key in sorted(set(shipped)):
            if key.lower() in ships_any_case:
                continue  # still shipped, perhaps renamed only in case (Windows folders ignore case)
            rel = os.path.normpath(key)
            parts = rel.split(os.sep)
            if (os.path.isabs(rel) or os.path.splitdrive(rel)[0] or rel.startswith(("\\", "/"))
                    or parts[0] == ".." or parts[0].lower() == "_internal"
                    # Windows drops trailing dots and spaces: "_internal." is _internal too
                    or any(p != p.rstrip(". ") for p in parts)):
                continue  # never outside the program folder, and _internal is replaced whole
            folder, name = os.path.split(rel)
            if folder == "bibles" and name.endswith(".json") and name != "book_names.json":
                bibles.add(name[:-len(".json")])
            dest = os.path.join(self.app_dir, rel)
            if not os.path.isfile(dest):
                continue
            saved = os.path.join(self.backup, rel)
            os.makedirs(os.path.dirname(saved), exist_ok=True)
            _retry(shutil.copy2, dest, saved)
            self.replaced.append(rel)
            if _retry(sha256_of, dest) != shipped[key]:
                mine = f"{rel}.edited-{stamp}"
                _retry(shutil.copy2, dest, os.path.join(self.app_dir, mine))
                self.created.append(mine)
                self.say(f"You had edited {key}, which this version no longer includes; "
                         f"your version is kept as {os.path.basename(mine)}")
            else:
                self.say(f"Removed {key}; this version no longer includes it")
            _retry(os.remove, _writable(dest))
            # A folder left empty goes too (rollback() makes it again)
            parent = os.path.dirname(dest)
            while os.path.normcase(parent) != os.path.normcase(self.app_dir) and not os.listdir(parent):
                _retry(os.rmdir, _writable(parent))
                parent = os.path.dirname(parent)
        return bibles

    def rollback(self):
        """Put the previous version back. Each step is retried for a few seconds (antivirus often
        holds freshly written files), and a failed step does not stop the others. Raises OSError
        if anything could not be restored; the backup is then kept, and deleted only on success."""
        errors = []
        internal = os.path.join(self.app_dir, "_internal")
        if self.moved_internal:
            try:
                if os.path.isdir(internal):
                    _retry(_rmtree, internal)
                _retry(os.replace, os.path.join(self.backup, "_internal"), internal)
                self.moved_internal = False
            except OSError as e:
                errors.append(f"_internal: {e}")
        for rel in self.replaced:
            dest, saved = os.path.join(self.app_dir, rel), os.path.join(self.backup, rel)
            try:
                if os.path.isfile(dest) and sha256_of(dest) == sha256_of(saved):
                    continue  # never changed (it could not be written): nothing to put back
            except OSError:
                pass
            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                _retry(shutil.copy2, saved, _writable(dest))
            except OSError as e:
                errors.append(f"{rel}: {e}")
        for rel in self.created:
            _remove(os.path.join(self.app_dir, rel))
        for folder in reversed(self.made_dirs):  # deepest first; one that holds anything stays
            try:
                os.rmdir(folder)
            except OSError:
                pass
        if errors:
            raise OSError("; ".join(errors[:5]))
        if self.made_backup:
            self.discard_backup()

    def discard_backup(self):
        """Delete this install's backup once it is no longer needed (retried: antivirus may hold a
        file in it). If it still can't go, rename it so the next update knows it is safe to delete,
        instead of keeping it as possibly the only good copy."""
        try:
            _retry(_rmtree, self.backup)
        except OSError:
            done = f"{self.backup}-done-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
            try:
                _retry(os.replace, self.backup, done)
            except OSError:
                log.warning("Could not remove the update backup %s", self.backup)

    def start_app(self, started_file=None):
        env = dict(os.environ)
        env.pop(STARTED_ENV, None)
        if started_file:
            env[STARTED_ENV] = started_file
        flags = _detached_flags()
        for f in flags or [0]:
            try:
                return subprocess.Popen([os.path.join(self.app_dir, EXE_NAME)], cwd=self.app_dir, env=env,
                                        creationflags=f, close_fds=True)
            except OSError:
                continue
        return None


def _wait_for_exit(pid, timeout):
    """True once the process has exited (or does not exist)."""
    if sys.platform != "win32":
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except OSError:
                return True
            time.sleep(0.2)
        return False
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not handle:
        return True
    try:
        return kernel32.WaitForSingleObject(handle, int(timeout * 1000)) == 0
    finally:
        kernel32.CloseHandle(handle)


def _process_exe(pid):
    """The full path of a running process's program, or None."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return None
        return buf.value
    finally:
        kernel32.CloseHandle(handle)


def _close_old_app(pid, exe, timeout, say=lambda message: None):
    """Wait for the old app to quit. If it hangs, end it, but only if that process really is
    this install's BibleWidget.exe. True once it is gone."""
    if _wait_for_exit(pid, timeout):
        return True
    running = _process_exe(pid)
    if not running or os.path.normcase(os.path.realpath(running)) != os.path.normcase(os.path.realpath(exe)):
        return False
    say(f"The running app did not close within {timeout:g} s; ending it")
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
    if handle:
        try:
            kernel32.TerminateProcess(handle, 1)
        finally:
            kernel32.CloseHandle(handle)
    return _wait_for_exit(pid, 10)


def install_main(argv):
    """Entry point for `BibleWidget.exe --install-update <app_dir> --wait-pid N --version V --marker F`."""
    def arg(name, default=None):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default

    if not arg("--install-update"):
        return 2
    app_dir = os.path.realpath(arg("--install-update"))
    version = arg("--version", "?")
    inst = _Installer(app_dir, os.path.realpath(os.path.dirname(sys.executable)), version,
                      os.path.join(app_dir, "update.log"))
    marker = arg("--marker")
    if marker:
        try:
            with open(marker, "w") as f:
                f.write(str(os.getpid()))
        except OSError:
            pass
    inst.say(f"Installing {version}")
    try:
        return _install(inst, arg("--wait-pid", "0"), version)
    except Exception as e:
        # Never leave the user without a widget, whatever went wrong
        inst.say(f"Unexpected problem ({e!r}); restoring the previous version")
        if inst.made_backup:
            _restore_and_restart(inst)
        else:
            inst.start_app()
        return 1


def _install(inst, wait_pid, version):
    app_dir = inst.app_dir
    if not _close_old_app(int(wait_pid), os.path.join(app_dir, EXE_NAME), OLD_APP_EXIT_TIMEOUT_S, inst.say):
        inst.say("The running app did not close and could not be ended; nothing was changed")
        return 1
    try:
        inst.swap()
    except Exception as e:
        inst.say(f"Install failed ({e}); restoring the previous version")
        _restore_and_restart(inst)
        return 1

    started = os.path.join(app_dir, f".update-started-{secrets.token_hex(8)}")
    process = inst.start_app(started)
    deadline = time.monotonic() + NEW_APP_START_TIMEOUT_S
    ok = False
    while process is not None and time.monotonic() < deadline:
        if os.path.exists(started):
            ok = True
            break
        if process.poll() is not None:
            break
        time.sleep(0.25)
    if ok:
        _remove(started)
        inst.discard_backup()
        inst.say(f"Update to {version} finished")
        return 0
    inst.say(f"Version {version} did not start; restoring the previous version")
    if process is not None and process.poll() is None:
        process.kill()
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            pass
    _remove(started)
    _restore_and_restart(inst)
    return 1


def _restore_and_restart(inst):
    """Roll back, then start the previous version, but only if it was fully restored: a
    half-restored app would not start, and the backup folder is what is needed to repair it."""
    try:
        inst.rollback()
    except Exception as e:
        inst.say(f"Restore problem: {e}. The previous version's files are kept in {inst.backup}; "
                 f"download Bible Widget again from the website to repair this folder.")
        return
    inst.start_app()
    inst.say("Rolled back")


def confirm_started():
    """Called by a freshly installed version once it is up: tells the installer it started."""
    path = os.environ.pop(STARTED_ENV, None)
    if path:
        try:
            with open(path, "w") as f:
                f.write(VERSION)
        except OSError:
            pass


def clean_leftovers():
    """Remove unpacked updates and downloads left in the temp folder by earlier updates."""
    temp = tempfile.gettempdir()
    try:
        names = os.listdir(temp)
    except OSError:
        return
    cutoff = time.time() - 3600
    for name in names:
        if name.startswith((STAGING_PREFIX, DOWNLOAD_PREFIX, "BibleWidget-selftest-")):
            path = os.path.join(temp, name)
            try:
                if os.path.getmtime(path) < cutoff:
                    _remove(path)
            except OSError:
                pass
