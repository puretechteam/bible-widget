"""The scripts for running from source, each run from a copy in a temp folder with a stand-in
widget_window.py (never the real widget, its settings or the real pid file): stop_widget.bat
stops only the widget, start_widget.vbs starts it with the Python dependencies.bat installs into."""
import os
import sys
import time
import shutil
import tempfile
import subprocess
from support import Results, ROOT

R = Results()
if sys.platform != "win32":
    print("Windows only: skipped")
    R.finish()

folder = tempfile.mkdtemp(prefix="bw-scripts-")
for name in ("stop_widget.bat", "start_widget.vbs", "dependencies.bat"):
    shutil.copy2(os.path.join(ROOT, name), folder)
marker = os.path.join(folder, "started.txt")
with open(os.path.join(folder, "widget_window.py"), "w", encoding="utf-8") as f:
    f.write("import sys, time\n"
            f"open({marker!r}, 'w').write(sys.executable)\n"
            "time.sleep(30)\n")
pid_file = os.path.join(folder, "widget.pid")


def stop(pid):
    with open(pid_file, "w") as f:
        f.write(str(pid))
    subprocess.run(["cmd", "/c", os.path.join(folder, "stop_widget.bat")], capture_output=True, timeout=60)


procs = []
try:
    # Another Python program that was given the widget's old process number is left alone
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    procs.append(other)
    stop(other.pid)
    time.sleep(0.5)
    R.check("stop_widget.bat leaves another Python program alone", other.poll() is None)
    R.check("...and removes the stale widget.pid", not os.path.exists(pid_file))
    # The widget itself is stopped
    widget = subprocess.Popen([sys.executable, os.path.join(folder, "widget_window.py")])
    procs.append(widget)
    stop(widget.pid)
    try:
        widget.wait(10)
    except subprocess.TimeoutExpired:
        pass
    R.check("stop_widget.bat stops the widget", widget.poll() is not None)
    # widget.pid as the running app keeps it (the process number, then when it was last seen running)
    widget = subprocess.Popen([sys.executable, os.path.join(folder, "widget_window.py")])
    procs.append(widget)
    with open(pid_file, "w") as f:
        f.write("\n".join([str(widget.pid), "started=2026-11-11T09:00:00", "alive=2026-11-11T09:10:00",
                           "resources=80 MB memory", ""]))
    subprocess.run(["cmd", "/c", os.path.join(folder, "stop_widget.bat")], capture_output=True, timeout=60)
    try:
        widget.wait(10)
    except subprocess.TimeoutExpired:
        pass
    R.check("...also with the times and memory the app writes after the number", widget.poll() is not None)
    # Anything but a number in widget.pid is ignored
    with open(pid_file, "w") as f:
        f.write("1 & echo hacked > hacked.txt")
    subprocess.run(["cmd", "/c", os.path.join(folder, "stop_widget.bat")], capture_output=True, timeout=60, cwd=folder)
    R.check("a widget.pid that is not a number runs nothing", not os.path.exists(os.path.join(folder, "hacked.txt"))
            and not os.path.exists(pid_file))

    # start_widget.vbs starts widget_window.py next to it
    subprocess.run(["wscript", "//nologo", os.path.join(folder, "start_widget.vbs")], timeout=30)
    end = time.monotonic() + 20
    while time.monotonic() < end and not os.path.exists(marker):
        time.sleep(0.2)
    started_with = open(marker, encoding="utf-8").read() if os.path.exists(marker) else None
    R.check("start_widget.vbs starts the widget", started_with is not None)

    # dependencies.bat installs into that same Python (here an empty requirements.txt: nothing to install)
    open(os.path.join(folder, "requirements.txt"), "w").close()
    run = subprocess.run(["cmd", "/c", os.path.join(folder, "dependencies.bat")], capture_output=True, text=True,
                         stdin=subprocess.DEVNULL, timeout=120)
    R.check("dependencies.bat finishes", "All dependencies are ready" in run.stdout, run.stdout[-300:])
    py = shutil.which("py")
    if started_with:
        expected = subprocess.run([py, "-3", "-c", "import sys; print(sys.executable)"], capture_output=True,
                                  text=True).stdout.strip() if py else ""
        expected = expected or shutil.which("python") or started_with
        R.check("start_widget.vbs uses the Python dependencies.bat installs into",
                os.path.normcase(started_with) == os.path.normcase(expected), (started_with, expected))
    # Stop it again before the next part
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*" + folder.replace("'", "''")
                    + "*widget_window.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                   capture_output=True, timeout=60)
    os.remove(marker) if os.path.exists(marker) else None

    # A py launcher that can't run Python (left behind when Python was uninstalled): both scripts
    # use the python on the PATH instead
    real_python = shutil.which("python")
    if real_python:
        fake_bin = os.path.join(folder, "fake-bin")
        os.makedirs(fake_bin)
        shutil.copy2(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "timeout.exe"),
                     os.path.join(fake_bin, "py.exe"))  # exits with an error, like a broken launcher
        env = dict(os.environ, PATH=fake_bin + os.pathsep + os.path.dirname(real_python) + os.pathsep
                   + os.environ.get("PATH", ""))
        run = subprocess.run(["cmd", "/c", os.path.join(folder, "dependencies.bat")], capture_output=True, text=True,
                             stdin=subprocess.DEVNULL, timeout=120, env=env)
        R.check("with a broken py launcher, dependencies.bat uses python", "Using: python" in run.stdout, run.stdout[:200])
        subprocess.run(["wscript", "//nologo", os.path.join(folder, "start_widget.vbs")], timeout=30, env=env)
        end = time.monotonic() + 20
        while time.monotonic() < end and not os.path.exists(marker):
            time.sleep(0.2)
        R.check("...and so does start_widget.vbs, so the widget starts", os.path.exists(marker))

    # A widget of another copy (another folder) that was given this copy's old process number is
    # left alone
    other_folder = os.path.join(folder, "other copy")
    os.makedirs(other_folder)
    shutil.copy2(os.path.join(folder, "widget_window.py"), other_folder)
    theirs = subprocess.Popen([sys.executable, os.path.join(other_folder, "widget_window.py")])
    procs.append(theirs)
    time.sleep(0.5)
    stop(theirs.pid)
    time.sleep(0.5)
    R.check("stop_widget.bat leaves another copy's widget alone", theirs.poll() is None)
finally:
    for p in procs:
        if p.poll() is None:
            p.kill()
    # The widget start_widget.vbs started: found by its marker's Python, ended by its command line
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*" + folder.replace("'", "''")
                    + "*widget_window.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                   capture_output=True, timeout=60)
    time.sleep(0.5)
    shutil.rmtree(folder, ignore_errors=True)

R.finish()
