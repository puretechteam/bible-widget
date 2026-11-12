"""Crash logging, with the real app in a child process (crash_driver.py: offscreen, its files in a
temp folder, a user name of its own, so a widget you run is never involved): however a run ends,
widget.log says how, and the next start reports a run that never quit, with the crash."""
import os
import re
import sys
import time
import shutil
import signal
import tempfile
import subprocess
from support import Results, ROOT

R = Results()
DRIVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash_driver.py")
FOLDER = tempfile.mkdtemp(prefix="bw-crash-")
ENV = dict(os.environ, USERNAME=f"bw-crash-test-{os.getpid()}", BIBLE_WIDGET_TEST_APP=ROOT)
LOG = os.path.join(FOLDER, "widget.log")
PID = os.path.join(FOLDER, "widget.pid")
STARTED = os.path.join(FOLDER, "started.txt")


def start(action, **popen):
    if os.path.exists(STARTED):
        os.remove(STARTED)
    p = subprocess.Popen([sys.executable, "-B", DRIVER, FOLDER, action], env=ENV, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, **popen)
    end = time.monotonic() + 30
    while time.monotonic() < end and not os.path.exists(STARTED) and p.poll() is None:
        time.sleep(0.1)
    return p


def finish(p, timeout=40):
    try:
        return p.wait(timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        return "hung"


def log_since(mark):
    text = open(LOG, encoding="utf-8", errors="replace").read() if os.path.exists(LOG) else ""
    return text[mark:]


def log_size():
    return len(open(LOG, encoding="utf-8", errors="replace").read()) if os.path.exists(LOG) else 0


def report_after(action):
    """Start again (and quit): what the new start writes about the run before it."""
    mark = log_size()
    finish(start("quit"))
    return log_since(mark)


# Windows' crash and hang records, as wevtutil prints them: matched by process number
import crash_log
SAMPLE = ("<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System><EventID>1000</EventID>"
          "<TimeCreated SystemTime='2026-11-10T20:47:51.58Z'/></System><EventData><Data Name='AppName'>python.exe</Data>"
          "<Data Name='ModuleName'>Qt6Core.dll</Data><Data Name='ExceptionCode'>c0000409</Data>"
          "<Data Name='FaultingOffset'>1be08</Data><Data Name='ProcessId'>0x1c4c0</Data><Data Name='Empty'/>"
          "</EventData></Event><Event xmlns='x'><System><EventID>1002</EventID><TimeCreated SystemTime='2026-11-11T09:08:50Z'/>"
          "</System><EventData><Data Name='AppName'>A &amp; B.exe</Data><Data Name='ProcessId'>0x10</Data></EventData></Event>")
crash = crash_log.windows_reports(0x1c4c0, runner=lambda command: SAMPLE)
hang = crash_log.windows_reports(16, runner=lambda command: SAMPLE)
R.check("a Windows crash record is read: module, code, time", [(r["kind"], r["module"], r["code"], r["time"]) for r in crash]
        == [("crash", "Qt6Core.dll", "c0000409", "2026-11-10T20:47:51.58Z")], crash)
R.check("...a hang record too, and only the asked-for process's", [(r["kind"], r["app"]) for r in hang] == [("hang", "A & B.exe")], hang)
R.check("...and nothing for another process", crash_log.windows_reports(99, runner=lambda command: SAMPLE) == [])

try:
    # 1. A normal Exit: logged, widget.pid removed, and the next start reports nothing
    mark = log_size()
    p = start("quit")
    code = finish(p)
    text = log_since(mark)
    R.check("Exit: the app ends normally", code == 0, code)
    R.check("...widget.log says why it stopped", "Stopping: Exit was chosen" in text, text[-300:])
    R.check("...and how it was started, with versions", re.search(r"Running on Python \d+\.\d+.*PySide6", text), text[-400:])
    R.check("...and widget.pid is removed", not os.path.exists(PID))
    text = report_after("quit")
    R.check("after a normal Exit, the next start reports nothing", "ended without quitting" not in text, text[-300:])

    # 2. Ended from outside (as Task Manager or a crash with no report would): widget.pid kept it alive
    p = start("run")
    time.sleep(1.5)
    heartbeat = open(PID, encoding="utf-8").read() if os.path.exists(PID) else ""
    R.check("while running, widget.pid says when it was last seen and its memory",
            re.search(r"^\d+\nstarted=.+\nalive=.+\nresources=\d+ MB memory", heartbeat), heartbeat)
    stop_widget_style = heartbeat.splitlines()[0].isdigit() if heartbeat else False
    R.check("...with the process number alone on the first line (stop_widget.bat reads that)", stop_widget_style)
    p.kill()
    p.wait()
    text = report_after("run")
    R.check("killed: the next start reports the run that never quit", f"The last run (pid {p.pid}) ended without quitting" in text,
            text[-500:])
    R.check("...with when it was last seen running and its memory",
            re.search(r"last seen running \d{4}-\d\d-\d\dT[\d:]+ \(\d+ MB memory", text), text[-500:])
    R.check("...and that Windows made no crash report for it", f"no crash or hang report for pid {p.pid}" in text, text[-400:])

    # 3. An error in another thread is logged with its traceback, and the app keeps going
    mark = log_size()
    code = finish(start("thread-error"))
    text = log_since(mark)
    R.check("an error in another thread is logged", "Unhandled exception in thread test-thread" in text
            and "ZeroDivisionError: a test error in another thread" in text, text[-500:])
    R.check("...and the app carries on to a normal Exit", code == 0 and "Stopping: Exit was chosen" in text, code)

    # 4. A fatal error in native code: the Python stack of every thread, and Windows' crash report
    p = start("segfault")
    code = finish(p)
    R.check("an access violation ends the app", code not in (0, "hung"), code)
    text = report_after("segfault")
    R.check("...the next start reports it with the stack it happened in",
            "Windows fatal exception: access violation" in text and "crash_driver.py" in text, text[-800:])
    R.check("...and Windows' own crash report, found by its process number",
            re.search(rf"Windows crash report for pid {p.pid} .* exception code 0xc0000005", text), text[-500:])
    crash_file = os.path.join(FOLDER, "crash.log")
    R.check("...and crash.log is emptied once reported", os.path.exists(crash_file) and os.path.getsize(crash_file) == 0)

    # 5. Qt's fatal error (what a crash inside Qt looks like): its message, and Windows' report
    p = start("qt-fatal")
    code = finish(p)
    text = report_after("qt-fatal")
    R.check("Qt's fatal error ends the app", code not in (0, "hung"), code)
    whole = log_since(0)
    R.check("...its message is in widget.log", "Qt: a test fatal error" in whole and "CRITICAL Qt:" in whole,
            whole[-400:])
    R.check("...and the next start reports the run that never quit, with Windows' report",
            f"The last run (pid {p.pid}) ended without quitting" in text
            and re.search(rf"Windows crash report for pid {p.pid} .* exception code 0x", text), text[-600:])

    # 6. Ctrl+Break in its console ends it: logged as it happens, and not reported as a crash
    p = start("run", creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    time.sleep(1)
    os.kill(p.pid, signal.CTRL_BREAK_EVENT)
    code = finish(p)
    text = report_after("run")
    whole = log_since(0)
    R.check("Ctrl+Break in its console is logged as it ends the app",
            "Ending: Ctrl+Break was pressed in its console" in whole, whole[-300:])
    R.check("...and the next start says so instead of reporting a crash",
            f"The last run (pid {p.pid}) was ended at" in text and "ended without quitting" not in text, text[-400:])

    # 7. A widget.pid from a version before this one (only a number) is still reported
    with open(PID, "w") as f:
        f.write("4000000")
    text = report_after("run")
    R.check("an old widget.pid (a number alone) is reported as a run that never quit",
            "The last run (pid 4000000) ended without quitting" in text and "did not record when" in text, text[-400:])

    # 8. Started by a program that turned Windows' crash reports off: said at the start
    env = dict(ENV, BW_TEST_ERROR_MODE="3")
    mark = log_size()
    p = subprocess.Popen([sys.executable, "-B", DRIVER, FOLDER, "quit"], env=env, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    finish(p)
    text = log_since(mark)
    R.check("crash reports turned off by the program that started it are noted",
            "Windows crash reports are off for this run" in text, text[-400:])
    text = report_after("quit")
    R.check("...and not with them on", "crash reports are off" not in text, text[-300:])
finally:
    shutil.rmtree(FOLDER, ignore_errors=True)

R.finish()
