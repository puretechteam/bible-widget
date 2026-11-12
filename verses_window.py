"""The Verses window: Find a verse, Favorites and History, in three tabs."""

import html
import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLineEdit, QComboBox, QPushButton,
    QTreeWidget, QTreeWidgetItem, QLabel, QHeaderView, QAbstractItemView, QApplication,
    QStyledItemDelegate, QStyle, QStyleOptionViewItem, QMenu, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QFont, QTextDocument, QTextOption, QPalette, QAbstractTextDocumentLayout, QKeySequence, QShortcut
)
from bible_loader import get_available_translations, get_short_name, REPLACED
import verses

log = logging.getLogger("bible_widget")

ROLE = Qt.UserRole  # each row carries (ref, text, translation)
MARKED_ROLE = Qt.UserRole + 1  # the verse as HTML with the searched words marked


class MarkedTextDelegate(QStyledItemDelegate):
    """Draws a cell's MARKED_ROLE HTML (search matches in bold, in the link colour)."""

    def paint(self, painter, option, index):
        marked = index.data(MARKED_ROLE)
        if not marked:
            return super().paint(painter, option, index)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        widget = opt.widget
        style = widget.style() if widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)
        selected = opt.state & QStyle.State_Selected
        color = opt.palette.color(QPalette.HighlightedText if selected else QPalette.Text)
        mark = opt.palette.color(QPalette.HighlightedText if selected else QPalette.Link)
        rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, widget)
        doc = QTextDocument()
        doc.setDefaultFont(opt.font)
        doc.setDocumentMargin(0)
        if verses.is_rtl(index.data(Qt.DisplayRole) or ""):
            # Arabic starts at the right: one right-aligned line the width of the cell, so the
            # beginning of the verse is what shows (laid out from the left, only its end did)
            text_option = QTextOption(Qt.AlignRight)
            text_option.setTextDirection(Qt.RightToLeft)
            text_option.setWrapMode(QTextOption.NoWrap)
            doc.setDefaultTextOption(text_option)
            doc.setTextWidth(rect.width())
        marked = marked.replace("<b>", '<b style="color:%s">' % mark.name())
        doc.setHtml('<span style="color:%s">%s</span>' % (color.name(), marked))
        painter.save()
        painter.setClipRect(rect)
        painter.translate(rect.left(), rect.top() + (rect.height() - doc.size().height()) / 2)
        doc.documentLayout().draw(painter, QAbstractTextDocumentLayout.PaintContext())
        painter.restore()


def _marked_html(query, text):
    """The verse as HTML with the words of `query` in bold."""
    out, last = [], 0
    for start, end in verses.match_spans(query, text):
        out.append(html.escape(text[last:start]))
        out.append(f"<b>{html.escape(text[start:end])}</b>")
        last = end
    out.append(html.escape(text[last:]))
    return "".join(out)


class VersesWindow(QWidget):
    TABS = ("find", "favorites", "history")

    def __init__(self, widget):
        """`widget` is the BibleWidget: it shows passages and owns the favorites/history lists."""
        super().__init__()
        self._widget = widget
        tr = widget._s
        self._tr = tr
        self.setWindowTitle(f"Bible Widget - {tr('Verses')}")
        self.setMinimumSize(560, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.tabs.addTab(self._build_find(), tr("Find"))
        self.tabs.addTab(self._build_list("favorites"), tr("Favorites"))
        self.tabs.addTab(self._build_list("history"), tr("History"))
        self.tabs.currentChanged.connect(lambda _: self.refresh())
        QShortcut(QKeySequence.Find, self, lambda: self.show_tab("find"))  # Ctrl+F
        self.refresh()

    # ----- Building the tabs -----

    def _tree(self, kind):
        tree = QTreeWidget()
        tree.setColumnCount(3)
        tree.setHeaderLabels([self._tr("Reference"), self._tr("Verse"), self._tr("Translation")])
        tree.setRootIsDecorated(False)
        tree.setUniformRowHeights(True)
        tree.setSelectionMode(QAbstractItemView.SingleSelection)
        tree.setTextElideMode(Qt.ElideRight)
        header = tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setStretchLastSection(False)
        # Activated = double-click or Enter on a row
        tree.itemActivated.connect(lambda item, _: self._show(item))
        tree.setItemDelegateForColumn(1, MarkedTextDelegate(tree))
        tree.setContextMenuPolicy(Qt.CustomContextMenu)
        tree.customContextMenuRequested.connect(lambda pos: self._row_menu(tree, kind, pos))
        QShortcut(QKeySequence.Copy, tree, lambda: self._copy(tree.currentItem()), context=Qt.WidgetShortcut)
        if kind == "favorites":
            QShortcut(QKeySequence.Delete, tree, lambda: self._remove_favorite(tree.currentItem()),
                      context=Qt.WidgetShortcut)
        return tree

    def _actions(self, tree, kind):
        """(label, slot) for what can be done with the selected row on this tab."""
        item = tree.currentItem
        actions = [("Show on Widget", lambda: self._show(item()))]
        if kind != "favorites":
            actions.append(("Add to Favorites", lambda: self._favorite(item())))
        actions += [
            ("Copy Verse", lambda: self._copy(item())),
            ("Save as Image", lambda: self._save_image(item())),
        ]
        if kind == "favorites":
            actions.append(("Remove", lambda: self._remove_favorite(item())))
        return actions

    def _row_menu(self, tree, kind, pos):
        item = tree.itemAt(pos)
        if item is None:
            return
        tree.setCurrentItem(item)
        menu = QMenu(tree)
        menu.setAttribute(Qt.WA_DeleteOnClose)
        for label, slot in self._actions(tree, kind):
            menu.addAction(self._tr(label).replace("&", "&&")).triggered.connect(slot)
        self._menu = menu  # kept so tests can reach it; replaced on the next right-click
        menu.popup(tree.viewport().mapToGlobal(pos))

    def _fill(self, tree, rows, query=None):
        """Refill a list, keeping the selected verse selected (so a button never acts on a
        different row after a refresh). `query` marks the searched words in each verse."""
        current = tree.currentItem()
        keep = (current.data(0, ROLE)[0], current.data(0, ROLE)[2]) if current is not None else None
        tree.clear()
        selected = None
        for ref, text, abbr in rows:
            flat = " ".join(text.split())
            item = QTreeWidgetItem([ref, flat, get_short_name(abbr)])
            item.setToolTip(1, text)
            item.setData(0, ROLE, (ref, text, abbr))
            if query:
                item.setData(1, MARKED_ROLE, _marked_html(query, flat))
            tree.addTopLevelItem(item)
            if keep == (ref, abbr) and selected is None:
                selected = item
        if selected is None and rows:
            selected = tree.topLevelItem(0)
        if selected is not None:
            tree.setCurrentItem(selected)

    def _build_find(self):
        page = QWidget()
        v = QVBoxLayout(page)
        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText(self._tr("Type a reference (John 3:16) or words"))
        self.query.setClearButtonEnabled(True)
        self.query.returnPressed.connect(self.search)
        row.addWidget(self.query, 1)
        self.translation = QComboBox()
        for abbr, name, _ in get_available_translations():
            self.translation.addItem(name, abbr)
        current = self._widget._translation or self._widget._shown_translation
        index = self.translation.findData(current)
        if index < 0:  # a translation taken out since: its replacement
            index = self.translation.findData(REPLACED.get(current, current) or "en_kjv")
        if index < 0:
            index = self.translation.findData("en_kjv")
        if index >= 0:
            self.translation.setCurrentIndex(index)
        row.addWidget(self.translation)
        search = QPushButton(self._tr("Search"))
        search.clicked.connect(self.search)
        row.addWidget(search)
        v.addLayout(row)

        self.find_status = QLabel()
        v.addWidget(self.find_status)
        self.find_tree = self._tree("find")
        v.addWidget(self.find_tree, 1)
        v.addLayout(self._buttons(self._actions(self.find_tree, "find")))
        return page

    def _build_list(self, kind):
        page = QWidget()
        v = QVBoxLayout(page)
        tree = self._tree(kind)
        v.addWidget(tree, 1)
        if kind == "favorites":
            self.favorites_tree = tree
            v.addLayout(self._buttons(self._actions(tree, kind)))
        else:
            self.history_tree = tree
            # Clear History sits apart on the left, away from the everyday buttons
            v.addLayout(self._buttons(self._actions(tree, kind), left=[("Clear History", self._clear_history)]))
        return page

    def _buttons(self, specs, left=()):
        row = QHBoxLayout()
        for label, slot in left:
            row.addWidget(self._button(label, slot))
        row.addStretch(1)
        for label, slot in specs:
            row.addWidget(self._button(label, slot))
        return row

    def _button(self, label, slot):
        b = QPushButton(self._tr(label))
        b.setAutoDefault(False)  # Enter in a list shows the verse; it never presses a button
        b.clicked.connect(slot)
        return b

    # ----- Actions -----

    def show_tab(self, name):
        self.tabs.setCurrentIndex(self.TABS.index(name))
        if name == "find":
            self.query.setFocus()
            self.query.selectAll()

    def search(self):
        text = self.query.text().strip()
        if not text:
            return
        abbr = self.translation.currentData()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            kind, results, passage = verses.find(text, abbr, fits=self._widget._fits, limit=200)
        except Exception:
            # Measuring passages puts trial text on the widget: put its own passage back
            log.exception("Find failed for %r", text)
            self._widget._redisplay()
            kind, results, passage = "words", [], None
        finally:
            QApplication.restoreOverrideCursor()
        self.find_tree.clear()  # a new search starts with nothing selected
        self._fill(self.find_tree, [(ref, body, abbr) for ref, body, _ in results],
                   query=text if kind == "words" else None)
        if not results:
            self.find_status.setText(self._tr("No verses found"))
        elif kind == "words" and len(results) >= 200:
            self.find_status.setText(self._tr("Showing the first {n} verses").format(n=len(results)))
        else:
            self.find_status.setText(self._tr("1 verse found") if len(results) == 1
                                     else self._tr("{n} verses found").format(n=len(results)))
        if kind == "reference":
            self._show_in_chapter(results, passage, abbr)

    def _show_in_chapter(self, results, passage, abbr):
        """A reference lists its whole chapter: mark the verses asked for, scroll to them,
        and show exactly that passage on the widget."""
        ref, text, start, end = passage
        self.find_status.setText(f"{ref.rsplit(':', 1)[0]}  ·  {self.find_status.text()}")
        bold = QFont(self.find_tree.font())
        bold.setBold(True)
        first = None
        for i, (_, _, verse) in enumerate(results):
            if start <= verse <= end:
                item = self.find_tree.topLevelItem(i)
                for column in range(3):
                    item.setFont(column, bold)
                first = first or item
        if first is not None:
            self.find_tree.setCurrentItem(first)
            self.find_tree.scrollToItem(first, QAbstractItemView.PositionAtCenter)
        self._widget.show_passage(ref, text, abbr)

    def _show(self, item):
        if item is not None:
            self._widget.show_passage(*item.data(0, ROLE))

    def _favorite(self, item):
        if item is not None:
            ref, text, abbr = item.data(0, ROLE)
            self._widget._favorites.add(ref, text, abbr)
            self.refresh()

    def _remove_favorite(self, item):
        if item is not None:
            ref, _, abbr = item.data(0, ROLE)
            self._widget._favorites.remove(ref, abbr)
            self.refresh()

    def _save_image(self, item):
        if item is not None:
            self._widget._save_image(*item.data(0, ROLE))

    def _copy(self, item):
        if item is not None:
            self._widget._copy_verse(item.data(0, ROLE))

    def _confirm_clear(self):
        """Ask before History is emptied; Cancel is the default answer."""
        box = QMessageBox(QMessageBox.Question, self.windowTitle(),
                          self._tr("Remove every verse from History? This can't be undone."),
                          parent=self)
        clear = box.addButton(self._tr("Clear History"), QMessageBox.DestructiveRole)
        cancel = box.addButton(self._tr("Cancel"), QMessageBox.RejectRole)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        box.exec()
        return box.clickedButton() is clear

    def _clear_history(self):
        if not self._widget._history.entries or not self._confirm_clear():
            return
        self._widget._history.clear()
        self._widget._history_pos = 0
        self.refresh()

    def refresh(self):
        entries = lambda store: [(e["ref"], e["text"], e["translation"]) for e in store.entries]
        self._fill(self.favorites_tree, entries(self._widget._favorites))
        self._fill(self.history_tree, entries(self._widget._history))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
