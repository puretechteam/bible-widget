"""The About window (version, link, update settings) and the Update Available window."""

import os
import tempfile
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QTextBrowser,
    QProgressBar, QApplication
)
from PySide6.QtGui import QFont, QDesktopServices
from PySide6.QtCore import Qt, QUrl
from version import VERSION, REPO, RELEASES_URL
import updater


class AboutWindow(QDialog):
    def __init__(self, widget):
        super().__init__()
        self._widget = widget
        tr = widget._s
        self.setWindowTitle(tr("About Bible Widget"))
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(8)
        top = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(QApplication.windowIcon().pixmap(56, 56))
        top.addWidget(icon)
        title = QVBoxLayout()
        name = QLabel("Bible Widget")
        font = QFont("Segoe UI", 16)
        font.setWeight(QFont.DemiBold)
        name.setFont(font)
        title.addWidget(name)
        title.addWidget(QLabel(tr("Version {version}").format(version=VERSION)))
        top.addLayout(title, 1)
        layout.addLayout(top)

        link = QLabel(f'<a href="https://github.com/{REPO}">github.com/{REPO}</a> &nbsp;·&nbsp; Pure Tech')
        link.setOpenExternalLinks(True)
        layout.addWidget(link)
        layout.addSpacing(6)

        self.auto = QCheckBox(tr("Check for updates automatically"))
        self.auto.setChecked(widget._update_settings.auto)
        self.auto.toggled.connect(widget._set_auto_update)
        layout.addWidget(self.auto)

        self.status = QLabel()
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        check = QPushButton(tr("Check for Updates"))
        check.clicked.connect(lambda: widget._check_for_updates(manual=True))
        buttons.addWidget(check)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.close)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def set_status(self, text):
        self.status.setText(text)


class UpdateWindow(QDialog):
    def __init__(self, widget, release):
        super().__init__()
        self._widget = widget
        self._release = release
        tr = widget._s
        self._tr = tr
        self.setWindowTitle(tr("Update Available"))
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.resize(520, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        heading = QLabel(tr("Bible Widget {version} is available").format(version=release["version"]))
        font = QFont("Segoe UI", 13)
        font.setWeight(QFont.DemiBold)
        heading.setFont(font)
        layout.addWidget(heading)
        layout.addWidget(QLabel(tr("You have version {version}.").format(version=VERSION)))

        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(release["notes"] or "")
        layout.addWidget(notes, 1)

        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)

        buttons = QHBoxLayout()
        self.skip = QPushButton(tr("Skip This Version"))
        self.skip.clicked.connect(self._skip_version)
        buttons.addWidget(self.skip)
        buttons.addStretch(1)
        self.later = QPushButton(tr("Later"))
        self.later.clicked.connect(self.close)
        buttons.addWidget(self.later)
        self.self_update = updater.can_self_update() and bool(release.get("zip_url")) and bool(release.get("sha_url"))
        self.go = QPushButton(tr("Update Now") if self.self_update else tr("Open Download Page"))
        self.go.setDefault(True)
        self.go.clicked.connect(self._update_now if self.self_update else self._open_page)
        buttons.addWidget(self.go)
        layout.addLayout(buttons)

        # Esc and Later end in finished() without a closeEvent: both stop this window's download
        self._downloading = False
        self._installing = False
        self.quit_when_done = False  # Exit was chosen while installing: quit once that is over
        self.finished.connect(self._stop_download)

    def closeEvent(self, event):
        if self._installing:  # the update is being unpacked: the app restarts in a moment
            event.ignore()
            return
        self._stop_download()  # closing the window stops a download in progress
        super().closeEvent(event)

    def reject(self):
        if not self._installing:  # Esc, the same as closing
            super().reject()

    def _listen(self, on):
        # Only the window that started a download hears how it ended (the checker is shared)
        if on == self._downloading:
            return
        checker = self._widget._updater
        for signal, slot in ((checker.progress, self._on_progress), (checker.downloaded, self._on_downloaded),
                             (checker.download_failed, self._on_failed)):
            if on:
                signal.connect(slot)
            else:
                signal.disconnect(slot)
        self._downloading = on

    def _stop_download(self):
        if self._downloading:
            self._listen(False)
            self._widget._updater.cancel()

    def _open_page(self):
        QDesktopServices.openUrl(QUrl(self._release.get("page") or RELEASES_URL))

    def _skip_version(self):
        self._widget._update_settings.skip = self._release["tag"]
        self._widget._update_settings.save()
        if (self._widget._available_update or {}).get("tag") == self._release["tag"]:
            self._widget._clear_update()  # not a newer release found since this window opened
        self.close()

    def _update_now(self):
        if self._widget._updater.busy():
            return
        for b in (self.go, self.later, self.skip):
            b.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.message.setText(self._tr("Downloading update..."))
        try:
            folder = tempfile.mkdtemp(prefix=updater.DOWNLOAD_PREFIX)
        except OSError as e:  # the temp drive is full, say
            self._on_failed(str(e))
            return
        self._listen(True)
        self._widget._updater.download(self._release, folder)

    def _on_progress(self, got, total):
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(got)

    def _on_downloaded(self, path):
        self._listen(False)
        self.message.setText(self._tr("Installing update..."))
        self._installing = True
        QApplication.processEvents()
        try:
            # Unpacking takes a few seconds: on a worker thread, so the window stays responsive
            started = updater.run_in_background(updater.start_install, path, self._release["version"],
                                                close_dialogs_when=bool)
        except Exception:
            updater.log.exception("Could not start the update")
            started = False
        self._installing = False  # quitting closes every window: this one must let it
        if not started:
            # Nothing will use the download now (a new try downloads again): don't leave 66 MB in temp
            folder = os.path.dirname(path)
            updater._remove(folder if os.path.basename(folder).startswith(updater.DOWNLOAD_PREFIX) else path)
        if started or self.quit_when_done:
            self._widget._exit_app("closing for the update" if started else "Exit was chosen during the update")
        else:
            self._on_failed(None)

    def _on_failed(self, error):
        self._listen(False)
        self.progress.hide()
        if error is None:
            self.message.setText(self._tr("The update could not be installed. Your current version keeps running."))
        else:
            self.message.setText(self._tr("The update could not be downloaded: {error}").format(error=error))
        for b in (self.later, self.skip):
            b.setEnabled(True)
        self.go.setEnabled(True)
        self.go.setText(self._tr("Open Download Page"))
        self.go.clicked.disconnect()
        self.go.clicked.connect(self._open_page)
