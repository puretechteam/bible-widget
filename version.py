"""The app version: the one place it is set. Used by the app, the build and the update check."""

import re

VERSION = "2.1.0"
REPO = "puretechteam/bible-widget"
RELEASES_URL = f"https://github.com/{REPO}/releases"


def version_tuple(text):
    """'v2.1.0' or '2.1.0' -> (2, 1, 0, 0). A pre-release such as 'v2.1.0-rc1' -> (2, 1, 0, -1),
    so it ranks just below the release it leads up to. Anything unparsable -> (0, 0, 0, -1)."""
    m = re.match(r"\s*[vV]?(\d+(?:\.\d+)*)(.*)$", text or "")
    if not m:
        return (0, 0, 0, -1)
    numbers = [int(n) for n in m.group(1).split(".")][:3]
    numbers += [0] * (3 - len(numbers))
    return tuple(numbers) + ((0,) if not m.group(2).strip() else (-1,))
