"""
Header editor module for ledger headers. Provides:
- Model (HeaderItemModel) with drag reorder
- Also supports external drag: sets 'application/x-headeritem' so other widgets can drop the header name
- Delegate (HeaderItemDelegate) for custom inline editing
- Main widget (HeaderEditor) with toolbar and context menu
- Automatically loads headers from ledger.json or falls back to ledger.json.template
- Each row's height set to ui.Size.RowHeight(1.0)
- Editing can start via double-click or pressing Enter (activated signal)
"""

import json
import pathlib
import tempfile

from PySide6 import QtCore, QtGui, QtWidgets

from ..ui import ui

TEMPLATE_DIR = pathlib.Path(__file__).parent.parent / 'config'
if not TEMPLATE_DIR.exists():
    raise FileNotFoundError(f'Template directory {TEMPLATE_DIR} does not exist.')

LEDGER_TEMPLATE = TEMPLATE_DIR / 'ledger.json.template'
CONFIG_DIR = pathlib.Path(tempfile.gettempdir()) / 'ExpenseTracker' / 'config'
LEDGER_PATH = CONFIG_DIR / 'ledger.json'

HEADER_TYPES = ['string', 'int', 'float', 'date']

def load_ledger_headers() -> dict:
    """
    Loads the 'header' dict from LEDGER_PATH if available,
    otherwise falls back to LEDGER_TEMPLATE.
    Returns a dict of the form { 'Name': 'Type', ... } or an empty dict on failure.
    """
    def load_header_dict_from_path(path: pathlib.Path) -> dict:
        if not path.exists():
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('header', {})
        except Exception:
            return {}

    header_dict = load_header_dict_from_path(LEDGER_PATH)
    if header_dict:
        return header_dict

    fallback_dict = load_header_dict_from_path(LEDGER_TEMPLATE)
    return fallback_dict or {}


class HeaderItemModel(QtCore.QAbstractListModel):
    """
    A model that stores header items as a list of dicts:
      [ { 'name': <str>, 'type': <str> }, ... ]
    Supports internal drag-and-drop reordering,
    and also sets 'application/x-headeritem' to allow external drops.
    """

    MIME_INTERNAL = 'application/vnd.text.list'
    MIME_EXTERNAL = 'application/x-headeritem'

    def __init__(self, headers=None, parent=None):
        super().__init__(parent)
        self._headers = headers or []

    def rowCount(self, parent=QtCore.QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._headers)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._headers):
            return None
        item = self._headers[index.row()]
        if role == QtCore.Qt.DisplayRole:
            return f'{item["name"]} ({item["type"]})'
        elif role == QtCore.Qt.EditRole:
            return item
        return None

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        """
        Expects value to be a dict: { "name": <str>, "type": <str> }
        """
        if not index.isValid() or role != QtCore.Qt.EditRole:
            return False
        self._headers[index.row()] = value
        self.dataChanged.emit(index, index, [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole])
        return True

    def flags(self, index):
        base_flags = super().flags(index)
        if index.isValid():
            # Editable, draggable, droppable for internal reorder
            return (base_flags
                    | QtCore.Qt.ItemIsEditable
                    | QtCore.Qt.ItemIsDragEnabled
                    | QtCore.Qt.ItemIsDropEnabled)
        else:
            # Even if no valid index, we can drop items
            return base_flags | QtCore.Qt.ItemIsDropEnabled

    def supportedDropActions(self):
        # For internal reordering, we typically use MoveAction
        return QtCore.Qt.MoveAction

    def mimeTypes(self):
        # We produce:
        # 1) application/vnd.text.list => for internal reorder
        # 2) application/x-headeritem => for external drops into other widgets
        base = super().mimeTypes()
        return list(set(base + [self.MIME_INTERNAL, self.MIME_EXTERNAL]))

    def mimeData(self, indexes):
        """
        For the first valid index, store the row in 'application/vnd.text.list'
        (for internal reorder) and the item['name'] in 'application/x-headeritem'
        (for external usage).
        """
        mime_data = QtCore.QMimeData()

        valid_rows = [i.row() for i in indexes if i.isValid()]
        if not valid_rows:
            return mime_data

        row = valid_rows[0]  # just handle one item
        if 0 <= row < len(self._headers):
            # For internal reordering
            mime_data.setData(self.MIME_INTERNAL, bytearray(str(valid_rows), 'utf-8'))

            # For external usage
            header_item = self._headers[row]
            header_name = header_item['name']
            mime_data.setData(self.MIME_EXTERNAL, header_name.encode('utf-8'))

        return mime_data

    def dropMimeData(self, data, action, row, column, parent):
        """
        Handle internal reordering if we have 'application/vnd.text.list'.
        The external 'application/x-headeritem' doesn't matter here
        because we are a source, not a target.
        """
        if action == QtCore.Qt.IgnoreAction:
            return True

        if data.hasFormat(self.MIME_INTERNAL):
            # Reorder logic
            if parent.isValid():
                drop_row = parent.row()
            else:
                drop_row = self.rowCount()

            encoded_data = data.data(self.MIME_INTERNAL).data()
            row_list = eval(encoded_data.decode('utf-8'))
            to_move = [self._headers[r] for r in row_list]

            self.beginResetModel()
            for r in sorted(row_list, reverse=True):
                self._headers.pop(r)
            for i, itm in enumerate(to_move):
                self._headers.insert(drop_row + i, itm)
            self.endResetModel()
            return True

        return False

    def insertRow(self, row, name='', type_='string'):
        self.beginInsertRows(QtCore.QModelIndex(), row, row)
        self._headers.insert(row, {'name': name, 'type': type_})
        self.endInsertRows()

    def removeRow(self, row, parent=QtCore.QModelIndex()):
        if 0 <= row < len(self._headers):
            self.beginRemoveRows(parent, row, row)
            self._headers.pop(row)
            self.endRemoveRows()

    def to_header_dict(self):
        """
        Convert the internal list into a dict: { "Name": "Type", ... }
        """
        return {item['name']: item['type'] for item in self._headers}

    def load_from_header_dict(self, header_dict):
        self.beginResetModel()
        self._headers.clear()
        for k, v in header_dict.items():
            self._headers.append({'name': k, 'type': v})
        self.endResetModel()


class HeaderItemDelegate(QtWidgets.QStyledItemDelegate):
    """
    A delegate that provides:
    - row height control via sizeHint()
    - custom inline editor for header items
    """

    def paint(self, painter, option, index):
        # Example custom painting
        hover = option.state & QtWidgets.QStyle.State_MouseOver
        selected = option.state & QtWidgets.QStyle.State_Selected

        if hover or selected:
            painter.setBrush(ui.Color.Background())
        else:
            painter.setBrush(ui.Color.VeryDarkBackground())
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(option.rect)

        # Draw text
        text = index.data(QtCore.Qt.DisplayRole)
        rect = option.rect.marginsRemoved(QtCore.QMargins(ui.Size.Margin(1.0), 0, ui.Size.Margin(1.0), 0))
        if text:
            painter.setPen(ui.Color.Text())
            painter.drawText(rect, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, text)

    def createEditor(self, parent, option, index):
        editor_widget = HeaderEditWidget(parent)
        # Ensure the editor matches the row height
        row_h = ui.Size.RowHeight(1.0)
        editor_widget.setFixedHeight(row_h)
        return editor_widget

    def setEditorData(self, editor, index):
        data = index.model().data(index, QtCore.Qt.EditRole)
        if data is not None:
            editor.set_name(data['name'])
            editor.set_type(data['type'])
            QtCore.QTimer.singleShot(0, editor.focus_and_select)

    def setModelData(self, editor, model, index):
        name_val = editor.get_name()
        type_val = editor.get_type()
        model.setData(index, {'name': name_val, 'type': type_val}, QtCore.Qt.EditRole)

    def sizeHint(self, option, index):
        """
        Return a fixed size for each row, using ui.Size.RowHeight(1.0).
        """
        row_h = ui.Size.RowHeight(1.0)
        return QtCore.QSize(option.rect.width(), row_h)


class HeaderEditWidget(QtWidgets.QWidget):
    """
    Inline editor widget used by HeaderItemDelegate.
    Includes QLineEdit for 'name' and QComboBox for 'type'.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._name_edit = QtWidgets.QLineEdit(self)
        self._type_combo = QtWidgets.QComboBox(self)
        self._type_combo.addItems(HEADER_TYPES)

        row_h = ui.Size.RowHeight(1.0)
        self._name_edit.setFixedHeight(row_h)
        self._type_combo.setFixedHeight(row_h)

        layout.addWidget(self._name_edit)
        layout.addWidget(self._type_combo)
        self.setLayout(layout)

    def set_name(self, text):
        self._name_edit.setText(text)

    def set_type(self, text):
        idx = self._type_combo.findText(text)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)

    def get_name(self):
        return self._name_edit.text()

    def get_type(self):
        return self._type_combo.currentText()

    def focus_and_select(self):
        """
        Give focus to the line edit and select all text.
        """
        self._name_edit.setFocus()
        self._name_edit.selectAll()


class HeaderEditor(QtWidgets.QWidget):
    """
    Main widget for editing the "header" section.
    - QListView with drag reorder & custom delegate
    - Toolbar with add, remove, edit, restore
    - Context menu with same actions
    - Loads from LEDGER_PATH or falls back to LEDGER_TEMPLATE
    - Row height set to ui.Size.RowHeight(1.0) for both list items and editor
    - Exports 'application/x-headeritem' when dragging an item externally
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        # Attempt to load from LEDGER_PATH or fallback
        initial_header_dict = self._load_ledger_header()

        # Convert dict -> list of { 'name': k, 'type': v }
        self.model = HeaderItemModel()
        self.model.load_from_header_dict(initial_header_dict)

        self.delegate = HeaderItemDelegate()

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum,
            QtWidgets.QSizePolicy.MinimumExpanding
        )
        self.setMinimumSize(
            ui.Size.Margin(1.0),
            ui.Size.RowHeight(7.5)
        )

        self._init_ui()
        self._connect_signals()

    def _load_ledger_header(self) -> dict:
        """
        Loads the 'header' dict from LEDGER_PATH if available,
        otherwise falls back to LEDGER_TEMPLATE,
        returning an empty dict if neither is available.
        """
        def load_header_dict_from_path(path: pathlib.Path) -> dict:
            if not path.exists():
                return {}
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get('header', {})
            except Exception:
                return {}

        header_dict = load_header_dict_from_path(LEDGER_PATH)
        if header_dict:
            return header_dict

        fallback_dict = load_header_dict_from_path(LEDGER_TEMPLATE)
        return fallback_dict or {}

    def _init_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        row_h = ui.Size.RowHeight(1.0)

        self.toolbar = QtWidgets.QToolBar()
        f = ui.Size.Indicator(2.0)
        self.toolbar.setIconSize(QtCore.QSize(row_h - f, row_h - f))
        self.toolbar.setFixedHeight(row_h)

        self.act_add = QtGui.QAction('Add', self)
        self.act_remove = QtGui.QAction('Remove', self)
        self.act_edit = QtGui.QAction('Edit', self)
        self.act_restore = QtGui.QAction('Restore', self)

        self.toolbar.addAction(self.act_add)
        self.toolbar.addAction(self.act_remove)
        self.toolbar.addAction(self.act_edit)
        self.toolbar.addAction(self.act_restore)
        main_layout.addWidget(self.toolbar)

        self.view = QtWidgets.QListView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(self.delegate)
        self.view.setUniformItemSizes(True)

        self.view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        # By default, double-click or 'EditKeyPressed' triggers editing
        self.view.setEditTriggers(
            QtWidgets.QAbstractItemView.DoubleClicked |
            QtWidgets.QAbstractItemView.EditKeyPressed
        )
        # Pressing Enter on an item also triggers editing
        self.view.activated.connect(self.on_edit)

        # ** Key: allow external dragging:
        self.view.setDragEnabled(True)
        self.view.setAcceptDrops(True)
        self.view.setDropIndicatorShown(True)
        self.view.setDragDropMode(QtWidgets.QAbstractItemView.DragDrop)

        self.view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.view.setResizeMode(QtWidgets.QListView.Adjust)


        main_layout.addWidget(self.view)
        self.setLayout(main_layout)

    def _connect_signals(self):
        self.act_add.triggered.connect(self.on_add)
        self.act_remove.triggered.connect(self.on_remove)
        self.act_edit.triggered.connect(self.on_edit)
        self.act_restore.triggered.connect(self.on_restore)

        # Context menu
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.show_context_menu)

    def show_context_menu(self, pos):
        menu = QtWidgets.QMenu(self)
        menu.addAction(self.act_add)
        menu.addAction(self.act_remove)
        menu.addAction(self.act_edit)
        menu.addAction(self.act_restore)
        menu.exec_(self.view.mapToGlobal(pos))

    def on_add(self):
        row = self.model.rowCount()
        self.model.insertRow(row, name='', type_='string')
        idx = self.model.index(row)
        self.view.setCurrentIndex(idx)
        self.view.edit(idx)

    def on_remove(self):
        idx = self.view.currentIndex()
        if idx.isValid():
            self.model.removeRow(idx.row())

    def on_edit(self):
        idx = self.view.currentIndex()
        if idx.isValid():
            self.view.edit(idx)

    def on_restore(self):
        if not LEDGER_TEMPLATE.exists():
            QtWidgets.QMessageBox.warning(self, 'Error', 'Ledger template not found.')
            return
        try:
            with open(LEDGER_TEMPLATE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            header_dict = data.get('header', {})
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, 'Error', f'Failed to load template:\n{e}')
            return
        self.model.load_from_header_dict(header_dict)
        QtWidgets.QMessageBox.information(self, 'Restored', 'Header restored from template.')

    def get_header_as_dict(self):
        """
        Return the final header as a dict.
        """
        return self.model.to_header_dict()

    def sizeHint(self):
        # Example size hint
        return QtCore.QSize(
            ui.Size.Margin(10.0),
            ui.Size.RowHeight(8.0)
        )
