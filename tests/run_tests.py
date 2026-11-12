"""Run every test file, one after another, and print the totals.

    python tests/run_tests.py            all of them (about a minute)
    python tests/run_tests.py widget     only files whose name contains "widget"

Everything runs offscreen with its files in a temp folder: your settings, favorites, history
and Pictures folder are never touched."""

import os
import re
import sys
import time
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))


def main(argv):
    names = sorted(n for n in os.listdir(HERE) if n.startswith("test_") and n.endswith(".py"))
    if argv:
        names = [n for n in names if any(a in n for a in argv)]
    total_passed = total_failed = 0
    broken = []
    for name in names:
        t0 = time.monotonic()
        run = subprocess.run([sys.executable, "-B", os.path.join(HERE, name)], cwd=HERE,
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
        seconds = time.monotonic() - t0
        found = re.findall(r"^(\d+) passed, (\d+) failed$", run.stdout, re.M)
        if found:
            passed, failed = map(int, found[-1])
        else:
            passed, failed = 0, 1
            broken.append(name)
        total_passed += passed
        total_failed += failed
        print(f"{name:<24} {passed:>4} passed {failed:>3} failed  {seconds:5.1f} s", flush=True)
        for line in run.stdout.splitlines():
            if line.startswith(("FAILED", "   ")):
                print("    " + line.strip())
        if run.returncode != 0 and (failed == 0 or name in broken):
            print(run.stderr[-3000:])
    print(f"\nTotal: {total_passed} passed, {total_failed} failed")
    return 1 if total_failed or broken else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
