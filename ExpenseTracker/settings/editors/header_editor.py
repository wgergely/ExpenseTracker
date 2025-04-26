"""Section editor for ledger.json "header" definitions.

"""
import logging

from PySide6 import QtCore, QtGui, QtWidgets

from .. import lib
from ...core import service
from ...ui import ui
from ...ui.actions import signals


class HeaderItemModel(QtCore.QAbstractTableModel):
    MIME_INTERNAL = 'application/vnd.text.list'
    MIME_EXTERNAL = 'application/x-headeritem'

    HEADERS = ['Name', 'Type']

    def __init__(self, parent=None):
        super().__init__(parent)
        self._headers = []
        self._ignore_reload = False

        self._connect_signals()
        QtCore.QTimer.singleShot(150, self.init_data)

    @QtCore.Slot()
    def init_data(self):
        if self._ignore_reload:
            return

        self.beginResetModel()
        self._headers.clear()
        try:
            self._headers = [{'name': k, 'type': v} for k, v in lib.settings.get_section('header').items()]
        finally:
            self.endResetModel()

    def _connect_signals(self):
        @QtCore.Slot(str)
        def on_config_changed(section):
            if section != 'header':
                return
            self.init_data()

        signals.configSectionChanged.connect(on_config_changed)

        self.dataChanged.connect(
            lambda: lib.settings.set_section('header', self.get_current_section_data())
        )

        @QtCore.Slot()
        def on_layout_changed():
            # We only want to write to disk but not reset the model
            try:
                self._ignore_reload = True
                lib.settings.set_section('header', self.get_current_section_data())
            finally:
                self._ignore_reload = False

        self.rowsRemoved.connect(on_layout_changed)
        self.rowsInserted.connect(on_layout_changed)
        self.rowsMoved.connect(on_layout_changed)

    def rowCount(self, parent=QtCore.QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._headers)

    def columnCount(self, parent=QtCore.QModelIndex()):
        if parent.isValid():
            return 0
        return 2

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None

        item = self._headers[index.row()]

        if role == QtCore.Qt.StatusTipRole:
            return f'{item["name"]} ({item["type"]})'

        if index.column() == 0:
            if role == QtCore.Qt.DisplayRole:
                return item['name']
            elif role == QtCore.Qt.EditRole:
                return item['name']
            elif role == QtCore.Qt.ToolTipRole:
                return item['name']
            elif role == QtCore.Qt.FontRole:
                font, _ = ui.Font.BoldFont(ui.Size.MediumText(1.0))
                return font
        elif index.column() == 1:
            if role == QtCore.Qt.DisplayRole:
                return item['type']
            elif role == QtCore.Qt.EditRole:
                return item['type']
            elif role == QtCore.Qt.ToolTipRole:
                return item['type']
            elif role == QtCore.Qt.FontRole:
                font, _ = ui.Font.ThinFont(ui.Size.MediumText(1.0))
                return font
            elif role == QtCore.Qt.TextAlignmentRole:
                return QtCore.Qt.AlignCenter
            elif role == QtCore.Qt.ForegroundRole:
                return ui.Color.Green()
        return None

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if not index.isValid() or role != QtCore.Qt.EditRole:
            return False

        item = self._headers[index.row()]

        if index.column() == 0:
            if value == item['name']:
                return True
            item['name'] = value
        if index.column() == 1:
            if value == item['type']:
                return True
            item['type'] = value

        self.dataChanged.emit(index, index, [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole])
        return True

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.ItemIsEnabled

        base_flags = super().flags(index)

        if index.isValid():
            # Editable, draggable, droppable for internal reorder
            return (base_flags
                    | QtCore.Qt.ItemIsEnabled
                    | QtCore.Qt.ItemIsSelectable
                    | QtCore.Qt.ItemIsEditable
                    | QtCore.Qt.ItemIsDragEnabled
                    | QtCore.Qt.ItemIsDropEnabled)
        else:
            # Even if no valid index, we can drop items
            return (base_flags
                    | QtCore.Qt.ItemIsEnabled
                    | QtCore.Qt.ItemIsDropEnabled
                    )

    def supportedDropActions(self):
        # For internal reordering, we typically use MoveAction
        return QtCore.Qt.MoveAction

    def mimeTypes(self):
        # application/vnd.text.list for internal reorder
        # application/x-headeritem for external drops into other widgets
        base = super().mimeTypes()
        return list(set(base + [self.MIME_INTERNAL, self.MIME_EXTERNAL]))

    def mimeData(self, indexes):
        """For the first valid index, store the row in 'application/vnd.text.list'
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
        """Handle internal reordering.
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

            self.rowsAboutToBeMoved.emit(parent, row_list[0], row_list[-1], parent, drop_row)
            for r in sorted(row_list, reverse=True):
                self._headers.pop(r)
            for i, itm in enumerate(to_move):
                self._headers.insert(drop_row + i, itm)
            self.rowsMoved.emit(parent, row_list[0], row_list[-1], parent, drop_row)
            return True

        return False

    def insertRow(self, row, parent=QtCore.QModelIndex()):
        """Insert a new row at the specified row.

        """
        default_type = 'string'
        default_name = 'NewColumn'

        # Ensure the new name is unique
        existing_names = {item['name'] for item in self._headers}
        while default_name in existing_names:
            default_name = f'NewColumn_{len(existing_names) + 1}'

        item = {'name': default_name, 'type': default_type}

        self.beginInsertRows(parent, row, row)
        self._headers.insert(row, item)
        self.endInsertRows()

    def moveRow(self, source_parent: QtCore.QModelIndex, row: int, destination_parent: QtCore.QModelIndex,
                dest_row: int):
        """Move the row from source to destination.

        """
        parent = QtCore.QModelIndex()

        if dest_row < 0 or dest_row > self.rowCount():
            return False

        self.beginMoveRows(parent, row, row, parent, dest_row)
        self._ignore_reload = True
        # Adjust the destination index for internal list modification.
        if dest_row > row:
            new_index = dest_row - 1
        else:
            new_index = dest_row
        self._headers.insert(new_index, self._headers.pop(row))
        self._ignore_reload = False
        self.endMoveRows()

        return True

    def removeRow(self, row, parent=QtCore.QModelIndex()):
        """Remove the row at the specified index.

        """
        if row < 0 or row >= len(self._headers):
            return False

        self.beginRemoveRows(parent, row, row)
        self._headers.pop(row)
        self.endRemoveRows()
        return True

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        """Provide header data for the model.

        """
        if role == QtCore.Qt.DisplayRole:
            if orientation == QtCore.Qt.Horizontal:
                return self.HEADERS[section]
            elif orientation == QtCore.Qt.Vertical:
                return str(section + 1)
        return None

    def get_current_section_data(self):
        """Return the current section data as a dictionary.

        """
        return {item['name']: item['type'] for item in self._headers}


class HeaderItemDelegate(QtWidgets.QStyledItemDelegate):

    def createEditor(self, parent, option, index):
        if not index.isValid():
            return None

        if index.column() == 0:
            editor = QtWidgets.QLineEdit(parent=parent)
            return editor
        elif index.column() == 1:
            editor = QtWidgets.QComboBox(parent=parent)
            view = QtWidgets.QListView()
            editor.setView(view)
            editor.addItems(lib.HEADER_TYPES)
            return editor

    def updateEditorGeometry(self, editor, option, index):
        """Explicitly set the editor geometry to match the cell area.

        """
        editor.setGeometry(option.rect)
        editor.setStyleSheet(f'height: {option.rect.height()}px')

    def setEditorData(self, editor, index):
        if not index.isValid():
            return

        if index.column() == 0:
            name = index.data(QtCore.Qt.EditRole)
            editor.setText(name)
        elif index.column() == 1:
            type_val = index.data(QtCore.Qt.EditRole)
            idx = editor.findText(type_val)
            if idx >= 0:
                editor.setCurrentIndex(idx)
            editor.showPopup()

    def setModelData(self, editor, model, index):
        if not index.isValid():
            return  #
        if not editor:
            return

        if index.column() == 0:
            v = editor.text()
        elif index.column() == 1:
            v = editor.currentText()
        else:
            return

        if v == index.data(QtCore.Qt.EditRole):
            return

        model.setData(index, v, QtCore.Qt.EditRole)


class HeaderEditor(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.toolbar = None
        self.view = None

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum,
            QtWidgets.QSizePolicy.MinimumExpanding
        )
        self.setMinimumHeight(ui.Size.RowHeight(10))
        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        self._create_ui()
        self._init_model()
        self._init_actions()
        self._connect_signals()

    def _create_ui(self):
        QtWidgets.QVBoxLayout(self)
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.toolbar = QtWidgets.QToolBar(parent=self)
        row_h = ui.Size.RowHeight(1.0)
        self.toolbar.setFixedHeight(row_h)

        self.layout().addWidget(self.toolbar, 1)

        from .views import TableView
        self.view = TableView(parent=self)

        delegate = HeaderItemDelegate(self.view)
        self.view.setItemDelegate(delegate)
        self.view.setContextMenuPolicy(QtCore.Qt.NoContextMenu)

        self.view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        self.view.setEditTriggers(
            QtWidgets.QAbstractItemView.DoubleClicked |
            QtWidgets.QAbstractItemView.EditKeyPressed
        )

        self.view.setDragEnabled(True)
        self.view.setAcceptDrops(True)
        self.view.setDropIndicatorShown(True)
        self.view.setDragDropMode(QtWidgets.QAbstractItemView.DragDrop)

        self.view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        self.layout().addWidget(self.view)

    def _init_model(self):
        model = HeaderItemModel()
        self.view.setModel(model)

        header = self.view.horizontalHeader()
        header.setSectionsMovable(False)
        header.setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)

        header = self.view.verticalHeader()
        header.setSectionsMovable(False)
        header.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        header.setDefaultSectionSize(ui.Size.RowHeight(1.0))
        header.setHidden(True)

    def _init_actions(self):
        @QtCore.Slot()
        def add_action():
            model = self.view.model()
            row = model.rowCount()
            model.insertRow(row)
            index = model.index(row, 0)
            self.view.setCurrentIndex(index)

        action = QtGui.QAction('Add', self)

        action.setShortcut('Ctrl+N')
        action.setStatusTip('Add a new header')
        action.setIcon(ui.get_icon('btn_add'))
        action.triggered.connect(add_action)
        self.toolbar.addAction(action)
        self.addAction(action)

        @QtCore.Slot()
        def remove_action():
            sm = self.view.selectionModel()
            if not sm.hasSelection():
                return
            index = next(iter(sm.selectedIndexes()), QtCore.QModelIndex())
            if index.isValid():
                self.view.model().removeRow(index.row())

        action = QtGui.QAction('Remove', self)

        action.setShortcut('Delete')
        action.setStatusTip('Remove selected header')
        action.setIcon(ui.get_icon('btn_delete'))
        action.triggered.connect(remove_action)
        self.toolbar.addAction(action)
        self.addAction(action)

        action = QtGui.QAction(self)

        action.setSeparator(True)
        action.setEnabled(False)
        action.setVisible(True)
        self.toolbar.addAction(action)
        self.addAction(action)

        @QtCore.Slot()
        def sync_action():
            try:
                headers = service.fetch_headers()
            except Exception as e:
                logging.error(f'Failed to load header definitions: {e}')
                QtWidgets.QMessageBox.critical(
                    self,
                    'Error',
                    f'Failed to load header definitions: {e}'
                )
                raise RuntimeError(f'Failed to load header definitions: {e}') from e

            if not headers:
                logging.warning('No header definitions found.')
                QtWidgets.QMessageBox.warning(
                    self,
                    'Warning',
                    'No header definitions found.'
                )
                return

            # Convert List to header -> type mapping Dict with a default string type
            data = {k: 'string' for k in headers}

            lib.settings.set_section('header', data)

            msg = f'Found {len(headers)} header columns. Dont\' forget to verify and set the column data types.'
            QtWidgets.QMessageBox.information(
                self,
                'Sync Headers Complete',
                msg,
                QtWidgets.QMessageBox.Ok
            )

        action = QtGui.QAction('Sync', self)

        action.setShortcut('Ctrl+L')
        action.setIcon(ui.get_icon('btn_sync'))
        action.setStatusTip('Load header definitions from the remote Google spreadsheet')
        action.triggered.connect(sync_action)
        self.toolbar.addAction(action)
        self.addAction(action)

        @QtCore.Slot()
        def verify_headers_action():
            try:
                service.verify_headers()
                msg = 'Header definitions are valid.'
                logging.debug(msg)
                QtWidgets.QMessageBox.information(
                    self,
                    'Verify Headers',
                    msg,
                    QtWidgets.QMessageBox.Ok
                )
            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self,
                    'Error',
                    f'Failed to verify header definitions: {e}'
                )

        action = QtGui.QAction('Verify', self)

        action.setShortcut('Ctrl+I')
        action.setStatusTip('Verify header definitions')
        action.setIcon(ui.get_icon('btn_ok'))
        action.triggered.connect(verify_headers_action)
        self.toolbar.addAction(action)
        self.addAction(action)

        action = QtGui.QAction(self)

        action.setSeparator(True)
        action.setEnabled(False)
        action.setVisible(True)
        self.toolbar.addAction(action)
        self.addAction(action)

        @QtCore.Slot()
        def reset_action():
            res = QtWidgets.QMessageBox.question(
                self,
                'Restore',
                'Are you sure you want to restore the header definitions from the template?',
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if res != QtWidgets.QMessageBox.Yes:
                return
            try:
                lib.settings.revert_section('header')
            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self,
                    'Error',
                    f'Failed to restore header definitions: {e}'
                )
                return

        action = QtGui.QAction('Revert', self)

        action.setShortcut('Ctrl+Shift+R')
        action.setStatusTip('Restore header definitions from template')
        action.triggered.connect(reset_action)
        self.toolbar.addAction(action)
        self.addAction(action)

        @QtCore.Slot()
        def reload_action():
            lib.settings.reload_section('header')

        action = QtGui.QAction('Refresh', self)

        action.setShortcut('Ctrl+R')
        action.setStatusTip('Reload header definitions from disk')
        action.triggered.connect(reload_action)
        self.toolbar.addAction(action)
        self.addAction(action)

        action = QtGui.QAction(self)

        action.setSeparator(True)
        action.setEnabled(False)
        action.setVisible(True)
        self.toolbar.addAction(action)
        self.addAction(action)

        @QtCore.Slot()
        def move_up():
            sm = self.view.selectionModel()
            if not sm.hasSelection():
                return
            index = next(iter(sm.selectedIndexes()), QtCore.QModelIndex())
            if not index.isValid():
                return
            row = index.row()
            model = self.view.model()
            dest_row = row - 1
            model.moveRow(QtCore.QModelIndex(), row, QtCore.QModelIndex(), dest_row)

        action = QtGui.QAction('Move Up', self)

        action.setShortcut('Ctrl+Up')
        action.setStatusTip('Move selected header up')
        action.setIcon(ui.get_icon('btn_arrow_up'))
        action.triggered.connect(move_up)
        self.toolbar.addAction(action)
        self.addAction(action)

        @QtCore.Slot()
        def move_down():
            sm = self.view.selectionModel()
            if not sm.hasSelection():
                return
            index = next(iter(sm.selectedIndexes()), QtCore.QModelIndex())
            if not index.isValid():
                return
            row = index.row()
            model = self.view.model()
            if row >= model.rowCount() - 1:
                return
            # When moving down, we want to move the row from 'row' to 'row+1'.
            # Because Qt expects dest_row as the row BEFORE which to insert,
            # and if moving downward, it will subtract one,
            # we pass row + 2 so that internally the new index becomes row + 1.
            dest_row = row + 2
            if model.moveRow(QtCore.QModelIndex(), row, QtCore.QModelIndex(), dest_row):
                new_index = model.index(row + 1, index.column())
                self.view.setCurrentIndex(new_index)

        action = QtGui.QAction('Move Down', self)

        action.setShortcut('Ctrl+Down')
        action.setStatusTip('Move selected header down')
        action.setIcon(ui.get_icon('btn_arrow_down'))
        action.triggered.connect(move_down)
        self.toolbar.addAction(action)
        self.addAction(action)

    def _connect_signals(self):
        pass
