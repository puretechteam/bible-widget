"""Where the app's files live.

Running from source, that is this folder. In the standalone build (BibleWidget.exe), it is the
folder holding the exe, so bibles/, prayers/ and the settings files sit next to it and stay
editable."""

import os
import sys
import json
import time

FROZEN = getattr(sys, "frozen", False)
APP_DIR = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
_ANSI = "mbcs" if sys.platform == "win32" else "latin-1"  # Windows' own code page


def app_path(*parts):
    return os.path.join(APP_DIR, *parts)


def write_text(path, text, encoding="utf-8", newline=None):
    """Replace a file's contents in one step: if the app is ended midway, the file holds the
    old contents or the new ones, never an empty or half-written file. (If another program keeps
    the file open for over a second, it is written in place instead.) Raises OSError."""
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding=encoding, newline=newline) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(10):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                # Another program has the file open (a backup or sync tool, a viewer): it usually
                # lets go within a moment. If not, write it in place rather than lose the save.
                if attempt == 9:
                    with open(path, "w", encoding=encoding, newline=newline) as f:
                        f.write(text)
                    os.remove(tmp)
                    return
                time.sleep(0.1)
    except BaseException:  # any failure: the old file stays and no temporary file is left
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def read_text(path):
    """A file people may edit by hand: UTF-8 with or without a byte order mark, or else Windows'
    own code page (what older editors save, e.g. "Português" in ANSI). A byte that code page
    can't read either (possible on Japanese, Chinese or Korean Windows) becomes U+FFFD instead of
    stopping the app. Raises OSError."""
    with open(path, "rb") as f:
        raw = f.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode(_ANSI, errors="replace")


def read_json(path):
    """A JSON file people may edit by hand (see read_text). Raises OSError if it can't be read
    and ValueError if it isn't JSON."""
    return json.loads(read_text(path))


def folder_writable(folder=None):
    """True if a file can be created in `folder` (the app folder by default). Settings live
    there, so a folder that can't be written (such as Program Files) can't keep them.
    (Not tempfile: on Windows it retries "access denied" almost endlessly, and would hang here.)"""
    probe = os.path.join(folder or APP_DIR, f".write-test-{os.getpid()}")
    try:
        with open(probe, "w"):
            pass
    except OSError:
        return False
    try:
        os.remove(probe)
    except OSError:
        pass
    return True
