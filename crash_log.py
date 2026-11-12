"""What ended the app, written to widget.log so it can be found afterwards.

The widget runs for days without a console, so an ending that is not a normal quit would leave no
trace. This records:
- Python errors in any thread and during clean-up, with their tracebacks (and Qt's own errors,
  set up in widget_window._setup_logging)
- fatal errors in Qt or Windows code, such as an access violation, with the Python stack of every
  thread: in crash.log, which faulthandler writes to directly (widget.log is renamed when it
  rotates, which a file held open would block)
- Windows ending the app: shutdown, signing out, or the console it was started from closing
- every 10 minutes, in widget.pid, that it is still running and the memory and handles it uses

At the next start, a widget.pid that is still there means the last run never got to quit. Then
widget.log gets what is known about it: when it started and was last seen running, its memory and
handles at that time, what crash.log holds, and the crash or hang report Windows made for it, if
any."""

import os
import sys
import time
import logging
import datetime
import threading
import faulthandler
import subprocess
import re
import html

from paths import read_text, write_text

log = logging.getLogger("bible_widget")

HEARTBEAT_MS = 10 * 60 * 1000  # how often widget.pid is brought up to date
SUMMARY_EVERY_S = 6 * 3600  # how often widget.log gets a "still running" line
PID_FILE = "widget.pid"
CRASH_FILE = "crash.log"

_state = {"app_dir": None, "crash_file": None, "started": None, "last_summary": None, "ended": False}
_console_handler = None  # kept so the callback is not freed while Windows can call it


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


# ----- Windows process facts (all None elsewhere or if Windows refuses) -----

def _kernel32():
    import ctypes
    return ctypes.WinDLL("kernel32", use_last_error=True)


def resources():
    """This process's memory (MB) and handles: {"memory_mb", "handles", "gdi", "user"}."""
    if sys.platform != "win32":
        return {}
    try:
        return _resources()
    except (OSError, AttributeError, ValueError, TypeError):  # only figures: never stop the app for them
        return {}


def _resources():
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    kernel32 = _kernel32()
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    kernel32.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    process = kernel32.GetCurrentProcess()
    found = {}
    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    if kernel32.K32GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
        found["memory_mb"] = round(counters.WorkingSetSize / 2 ** 20)
        found["private_mb"] = round(counters.PagefileUsage / 2 ** 20)
    count = wintypes.DWORD()
    if kernel32.GetProcessHandleCount(process, ctypes.byref(count)):
        found["handles"] = count.value
    user32 = ctypes.WinDLL("user32")
    user32.GetGuiResources.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    found["gdi"] = user32.GetGuiResources(process, 0)
    found["user"] = user32.GetGuiResources(process, 1)
    return found


def _describe_resources(found):
    parts = []
    if "memory_mb" in found:
        parts.append(f"{found['memory_mb']} MB memory ({found.get('private_mb', '?')} MB private)")
    for key, name in (("handles", "handles"), ("gdi", "GDI objects"), ("user", "window objects")):
        if key in found:
            parts.append(f"{found[key]} {name}")
    return ", ".join(parts) or "no figures"


def how_started():
    """The parent program and whether there is a console window, which ends the app when closed."""
    if sys.platform != "win32":
        return ""
    import ctypes
    parent = None
    try:
        import updater
        parent_pid = _parent_pid(os.getpid())
        parent = updater._process_exe(parent_pid) if parent_pid else None
    except Exception:  # only a description: never stop the start for it
        parent = None
    console = bool(_kernel32().GetConsoleWindow())
    started_by = f"started by {os.path.basename(parent)}" if parent else "parent unknown"
    return started_by + (", with a console window (closing it ends the widget)" if console else ", no console")


def _parent_pid(pid):
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]
    kernel32 = _kernel32()
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        return None
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(Entry)
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            if entry.th32ProcessID == pid:
                return entry.th32ParentProcessID
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return None


# ----- Recording -----

def install(app_dir):
    """Record Python and fatal errors from now on. Call first thing, before Qt starts."""
    _state["app_dir"] = app_dir
    try:
        crash_file = open(os.path.join(app_dir, CRASH_FILE), "ab")
        faulthandler.enable(file=crash_file, all_threads=True)
        _state["crash_file"] = crash_file
    except OSError:  # a folder that can't be written: no crash.log
        if sys.stderr is not None:
            faulthandler.enable(all_threads=True)

    def thread_hook(args):
        if args.exc_type is SystemExit:
            return
        log.error("Unhandled exception in thread %s:", getattr(args.thread, "name", "?"),
                  exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    threading.excepthook = thread_hook

    def unraisable_hook(unraisable):
        log.warning("Ignored exception (%s):", unraisable.err_msg or "during clean-up",
                    exc_info=(unraisable.exc_type, unraisable.exc_value, unraisable.exc_traceback))
    sys.unraisablehook = unraisable_hook
    _install_console_handler()


_CONSOLE_EVENTS = {0: "Ctrl+C was pressed in its console", 1: "Ctrl+Break was pressed in its console",
                   2: "the console window it was started from was closed", 5: "Windows is signing out",
                   6: "Windows is shutting down"}


def _install_console_handler():
    """Windows ends a program started from a console when that console closes, or at sign-out,
    without a crash report. Log it first. (Windows waits for this to return.)"""
    global _console_handler
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
    def on_event(kind):
        reason = _CONSOLE_EVENTS.get(kind, f"console event {kind}")
        if kind == 0:  # Python handles Ctrl+C itself; the widget keeps running
            log.info("%s", reason)
        else:
            mark_ended(reason)
        return False  # let Windows and Python go on as they would
    if _kernel32().SetConsoleCtrlHandler(on_event, True):
        _console_handler = on_event


def start_run():
    """Once this copy is the one running: report how the last run ended if it never quit, then
    write widget.pid. Returns the report text (None if the last run quit normally)."""
    app_dir = _state["app_dir"]
    path = os.path.join(app_dir, PID_FILE)
    report = None
    try:
        previous = read_text(path)
        written = datetime.datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="seconds")
    except FileNotFoundError:
        previous = written = None
    except OSError:
        previous, written = "", None
    crash_text = _take_crash_text()
    if previous is not None:
        report = _report_previous(previous, crash_text, written)
    elif crash_text:
        log.warning("crash.log held a report from an earlier run:\n%s", crash_text)
    _state["started"] = _now()
    _state["last_summary"] = time.monotonic()
    log.info("Running on Python %s, %s; %s", sys.version.split()[0], _qt_versions(), how_started())
    if sys.platform == "win32":
        mode = _kernel32().GetErrorMode()
        if mode & 0x2:  # SEM_NOGPFAULTERRORBOX, inherited from the program that started this one
            log.warning("Windows crash reports are off for this run (error mode 0x%x, from the program that "
                        "started it): a crash will show only in crash.log", mode)
    heartbeat()
    return report


def _qt_versions():
    try:
        import PySide6
        from PySide6 import QtCore
        return f"PySide6 {PySide6.__version__}, Qt {QtCore.qVersion()}"
    except Exception:
        return "PySide6 unknown"


def _take_crash_text():
    """What faulthandler wrote in crash.log, which is then emptied."""
    crash_file = _state["crash_file"]
    path = os.path.join(_state["app_dir"], CRASH_FILE)
    try:
        with open(path, "rb") as f:
            text = f.read().decode("utf-8", "replace").strip()
        if text and crash_file is not None:
            crash_file.truncate(0)
        return text
    except OSError:
        return ""


def _parse_pid_file(text):
    lines = text.splitlines()
    facts = {}
    if lines and lines[0].strip().isdigit():
        facts["pid"] = int(lines[0].strip())
    for line in lines[1:]:
        key, _, value = line.partition("=")
        if key.strip():
            facts[key.strip()] = value.strip()
    return facts


def _report_previous(previous, crash_text, written=None):
    facts = _parse_pid_file(previous)
    pid = facts.get("pid")
    if facts.get("ended"):
        log.info("The last run (pid %s) was ended at %s: %s", pid, facts.get("ended_at", "?"), facts["ended"])
        if crash_text:
            log.warning("crash.log:\n%s", crash_text)
        return None
    lines = [f"The last run (pid {pid if pid else '?'}) ended without quitting: it crashed, hung or was ended "
             "from outside."]
    if "started" in facts:
        lines.append(f"Started {facts['started']}, last seen running {facts.get('alive', '?')} "
                     f"({facts.get('resources', 'no figures')}).")
    else:
        lines.append(f"It was started by a version that did not record when it was last seen running "
                     f"(widget.pid was written {written or '?'}).")
    if crash_text:
        lines.append("crash.log:\n" + crash_text)
    else:
        lines.append("crash.log is empty: no fatal error inside the app was caught.")
    report = "\n".join(lines)
    log.warning("%s", report)
    if pid:
        # Windows' own crash or hang report, found by the process number; looked up in the
        # background, since reading the event log can take a second
        threading.Thread(target=_log_windows_report, args=(pid, facts.get("started") or written), daemon=True,
                         name="windows-report").start()
    return report


def heartbeat():
    """Write widget.pid: this process's number, then when it started and was last seen running,
    with its memory and handles. Every 6 hours the same figures go to widget.log."""
    if _state["ended"] or _state["app_dir"] is None:
        return
    found = resources()
    described = _describe_resources(found)
    try:
        write_text(os.path.join(_state["app_dir"], PID_FILE),
                   f"{os.getpid()}\nstarted={_state['started']}\nalive={_now()}\nresources={described}\n")
    except OSError:
        pass
    if time.monotonic() - _state["last_summary"] >= SUMMARY_EVERY_S:
        _state["last_summary"] = time.monotonic()
        log.info("Still running: %s", described)


def mark_ended(reason):
    """Windows is ending the app (shutdown, sign-out, its console closing): log it, and note it in
    widget.pid, so the next start does not report a crash."""
    log.warning("Ending: %s", reason)
    if _state["app_dir"] is None or _state["ended"]:
        return
    try:
        write_text(os.path.join(_state["app_dir"], PID_FILE),
                   f"{os.getpid()}\nstarted={_state['started']}\nended_at={_now()}\nended={reason}\n")
    except OSError:
        pass


def end_run(reason, app_dir=None):
    """A normal quit: log why (once), and remove widget.pid."""
    if not _state["ended"]:
        log.info("Stopping: %s", reason)
    _state["ended"] = True
    app_dir = app_dir or _state["app_dir"]
    if app_dir is None:
        return
    try:
        os.remove(os.path.join(app_dir, PID_FILE))
    except OSError:
        pass


# ----- Windows Error Reporting -----

# Read with patterns, not an XML parser: that would add 340 KB to the download for this alone
_EVENT_RE = re.compile(r"<Event[ >].*?</Event>", re.S)
_DATA_RE = re.compile(r"<Data Name=['\"]([^'\"]+)['\"]\s*(?:/>|>(.*?)</Data>)", re.S)
_EVENT_ID_RE = re.compile(r"<EventID[^>]*>(\d+)</EventID>")
_TIME_RE = re.compile(r"<TimeCreated SystemTime=['\"]([^'\"]+)['\"]")


def windows_reports(pid, days=14, runner=None):
    """Windows' crash (event 1000) and hang (1002) reports for a process number, newest first:
    [{"kind", "time", "app", "module", "code", ...}]."""
    if sys.platform != "win32" and runner is None:
        return []
    query = ("*[System[(EventID=1000 or EventID=1002) and "
             f"TimeCreated[timediff(@SystemTime) <= {days * 86400 * 1000}]]]")
    command = ["wevtutil", "qe", "Application", f"/q:{query}", "/f:xml", "/rd:true", "/c:200"]
    try:
        if runner is not None:
            out = runner(command)
        else:
            out = subprocess.run(command, capture_output=True, timeout=30,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError):
        return []
    found = []
    for event in _EVENT_RE.findall(out or ""):
        data = {name: html.unescape(value or "") for name, value in _DATA_RE.findall(event)}
        try:
            event_pid = int(data.get("ProcessId", ""), 16)
        except ValueError:
            continue
        if event_pid != pid:
            continue
        event_id = _EVENT_ID_RE.search(event)
        created = _TIME_RE.search(event)
        found.append({"kind": "crash" if event_id and event_id.group(1) == "1000" else "hang",
                      "time": created.group(1) if created else "",
                      "app": data.get("AppName", ""), "module": data.get("ModuleName", ""),
                      "code": data.get("ExceptionCode", ""), "offset": data.get("FaultingOffset", ""),
                      "path": data.get("AppPath") or data.get("ExeFileName", "")})
    return found


def _log_windows_report(pid, started=None):
    reports = windows_reports(pid)
    if started:  # a reused process number from before this run is someone else's
        reports = [r for r in reports if r["time"][:19] >= _utc(started)]
    if not reports:
        log.info("Windows made no crash or hang report for pid %s (it was ended from outside, or ended itself "
                 "without a fault).", pid)
        return
    for r in reports[:3]:
        if r["kind"] == "crash":
            log.warning("Windows crash report for pid %s at %s UTC: %s failed in %s, exception code 0x%s at "
                        "offset 0x%s", pid, r["time"][:19], r["app"], r["module"], r["code"], r["offset"])
        else:
            log.warning("Windows hang report for pid %s at %s UTC: %s stopped responding and was closed",
                        pid, r["time"][:19], r["app"])


def _utc(local_iso):
    """A local time written by this module, as the UTC text the event log uses."""
    try:
        moment = datetime.datetime.fromisoformat(local_iso).astimezone(datetime.timezone.utc)
        return moment.strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return ""
