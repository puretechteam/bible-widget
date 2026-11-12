# PyInstaller spec for the standalone Windows build. Run it through build.py, which also
# creates the icon and version resource this file refers to.
# One-folder build: starts fast (nothing to unpack per launch) and trips antivirus less often.
import os

EXCLUDES = [
    "tkinter", "unittest", "pydoc", "numpy",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel", "PySide6.QtMultimedia", "PySide6.QtPdf",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.Qt3DCore", "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtSvg", "PySide6.QtSvgWidgets",
    "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSerialPort", "PySide6.QtDesigner",
    # Python modules only reachable through logging.handlers' mail and event-log handlers, or
    # optional ones (decimal, bz2, lzma): the app never uses them. Networking goes through Qt.
    "ssl", "_ssl", "_hashlib", "decimal", "_decimal", "_pydecimal", "bz2", "_bz2", "lzma", "_lzma",
    "win32evtlogutil", "win32api", "win32con", "pywintypes", "win32evtlog", "pythoncom", "win32",
] + __import__("build").modules_to_leave_out()  # never imported by the app on this Python (about 480 KB)

# Qt and Python files the app never uses: software OpenGL, the touch keyboard (and the Qt
# Quick/QML it needs), PDF and SVG, image formats other than PNG (built in), extra platform and
# touch plugins, and OpenSSL. HTTPS uses Windows' own TLS (Qt's schannel backend), and hashlib
# falls back to Python's built-in SHA-256 without libcrypto.
UNUSED_BINARIES = ("opengl32sw", "qtvirtualkeyboard", "qt6virtualkeyboard", "qt6quick", "qt6qml",
                   "qpdf", "qt6pdf", "qopensslbackend", "libssl-3", "libcrypto-3", "qt6opengl",
                   "qdirect2d", "qminimal", "qtuiotouchplugin", "qt6svg", "qsvg", "qjpeg", "qwebp",
                   "qtiff", "qgif", "qico", "qicns", "qtga", "qwbmp",
                   # TLS through Windows' own schannel only; the app never asks for network status
                   "qcertonlybackend", "qnetworklistmanager")

a = Analysis(
    ["widget_window.py"],
    pathex=["."],
    hiddenimports=["selftest", "share_image", "backgrounds", "about_window", "verses_window", "tray_icon"],
    excludes=EXCLUDES,
    noarchive=False,
)
a.binaries = [b for b in a.binaries if not any(u in os.path.basename(b[0]).lower() for u in UNUSED_BINARIES)]
# Qt's own UI translations (.qm): only qtbase for the menu languages Qt covers, which give the
# human-made wording of OK, Cancel, Apply, Close and Restore Defaults (see menu_strings.py)
from menu_strings import QT_TRANSLATION_FILES
a.datas = [d for d in a.datas if "translations" not in d[0].replace("\\", "/").split("/")[:2]
           or os.path.basename(d[0]) in QT_TRANSLATION_FILES]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BibleWidget",
    console=False,
    icon="build/assets/BibleWidget.ico",
    version="build/assets/version_info.txt",
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="BibleWidget", upx=False)
