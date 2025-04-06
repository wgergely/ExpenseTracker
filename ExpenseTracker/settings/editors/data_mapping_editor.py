"""
Data Mapping Editor for the 'data_header_mapping' portion of ledger.json.

"""

from PySide6 import QtCore, QtWidgets, QtGui

from .. import lib
from ...ui import ui
from ...ui.actions import signals


class DataMappingModel(QtCore.QAbstractTableModel):
    HEADERS = ['Field To Map To', 'Spreadsheet Column to Map From']  # column 0, column 1
    MIME_HEADER = 'application/x-headeritem'

    def __init__(self, parent=None):
        super().__init__(parent)

        self._mapping = {k: '' for k in lib.DATA_MAPPING_KEYS}

        self._connect_signals()

        QtCore.QTimer.singleShot(150, self.init_data)

    def _connect_signals(self):

        @QtCore.Slot(str)
        def on_config_changed(section_name):
            if section_name != 'data_header_mapping':
                return
            self.init_data()

        signals.configSectionChanged.connect(on_config_changed)

        self.dataChanged.connect(
            lambda: lib.settings.set_section('data_header_mapping', self.get_current_section_data())
        )
        self.rowsRemoved.connect(
            lambda: lib.settings.set_section('data_header_mapping', self.get_current_section_data())
        )
        self.rowsInserted.connect(
            lambda: lib.settings.set_section('data_header_mapping', self.get_current_section_data())
        )
        self.rowsMoved.connect(
            lambda: lib.settings.set_section('data_header_mapping', self.get_current_section_data())
        )

    @QtCore.Slot()
    def init_data(self):
        self.beginResetModel()
        self._mapping = {k: '' for k in lib.DATA_MAPPING_KEYS}
        try:
            v = lib.settings.get_section('data_header_mapping').copy()
            self._mapping = {k: v.get(k, '') for k in lib.DATA_MAPPING_KEYS}
        finally:
            self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()):
        if parent.isValid():
            return 0
        return len(lib.DATA_MAPPING_KEYS)

    def columnCount(self, parent=QtCore.QModelIndex()):
        if parent.isValid():
            return 0
        return 2

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()
        key = lib.DATA_MAPPING_KEYS[row]

        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            if col == 0:
                return f'{key.title()}  =>'
            else:
                return self._mapping.get(key, '')
        return None

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if not index.isValid() or role != QtCore.Qt.EditRole:
            return False

        row = index.row()
        col = index.column()
        if col == 1:
            key = lib.DATA_MAPPING_KEYS[row]
            self._mapping[key] = value
            self.dataChanged.emit(index, index, [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole])

            return True
        return False

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.ItemIsEnabled

        col = index.column()
        base_flags = super().flags(index)

        # Column 0 is read-only
        if col == 0:
            return QtCore.Qt.NoItemFlags

        # Column 1 is editable + droppable
        return (base_flags
                | QtCore.Qt.ItemIsSelectable
                | QtCore.Qt.ItemIsEditable
                | QtCore.Qt.ItemIsEnabled
                | QtCore.Qt.ItemIsDropEnabled)

    def supportedDropActions(self):
        # We'll allow MoveAction or CopyAction as needed
        return QtCore.Qt.CopyAction | QtCore.Qt.MoveAction

    def mimeTypes(self):
        """
        We can accept 'application/x-headeritem' from the header editor.
        """
        base_types = super().mimeTypes()
        return base_types + [self.MIME_HEADER]

    def dropMimeData(self, data, action, row, column, parent):
        """
        If we receive a 'application/x-headeritem', interpret the payload as
        the header name to place into col=1.
        """
        if action == QtCore.Qt.IgnoreAction:
            return True

        # If no data for 'application/x-headeritem', let the base do its normal check
        if not data.hasFormat(self.MIME_HEADER):
            return super().dropMimeData(data, action, row, column, parent)

        # decode the dropped header name
        header_name = data.data(self.MIME_HEADER).data().decode('utf-8', errors='replace').strip()
        if not header_name:
            return False

        # Determine drop row/col
        if parent.isValid():
            drop_row = parent.row()
            drop_col = parent.column()
        else:
            drop_row = row
            drop_col = column

        # We only want to set col=1
        if drop_row < 0:
            drop_row = 0
        if drop_col != 1:
            drop_col = 1

        # Set the cell value
        success = self.setData(self.index(drop_row, drop_col), header_name, QtCore.Qt.EditRole)
        return success

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
        return super().headerData(section, orientation, role)

    def get_current_section_data(self):
        return self._mapping.copy()


class DataMappingDelegate(QtWidgets.QStyledItemDelegate):

    def __init__(self, parent=None):
        super().__init__(parent)

    def createEditor(self, parent, option, index):
        if index.column() != 1:
            return None

        editor = QtWidgets.QLineEdit(parent)
        headers = lib.settings.get_section('header').keys()
        completer = QtWidgets.QCompleter(headers, editor)

        completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        completer.setCompletionMode(QtWidgets.QCompleter.UnfilteredPopupCompletion)

        editor.setCompleter(completer)
        return editor

    def setEditorData(self, editor, index):
        if editor is None:
            return

        value = index.model().data(index, QtCore.Qt.EditRole)
        editor.setText(value or '')

        QtCore.QTimer.singleShot(0, lambda: (editor.setFocus(), editor.selectAll()))

        if editor.completer():
            editor.completer().complete()

    def setModelData(self, editor, model, index):
        if editor is None:
            return
        text_val = editor.text()
        model.setData(index, text_val, QtCore.Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        """
        Explicitly set the editor geometry to match the cell area.
        """
        editor.setGeometry(option.rect)
        editor.setStyleSheet(f'height: {option.rect.height()}px')


class DataMappingEditor(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.view = None

        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.Maximum
        )
        self.setMinimumHeight(ui.Size.RowHeight(1.0) * 6.5)

        ui.set_stylesheet(self)

        self.delegate = DataMappingDelegate(self)

        self._create_ui()
        self._init_model()
        self._init_actions()
        self._connect_signals()

    def _create_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.view = QtWidgets.QTableView(self)
        self.view.setItemDelegate(self.delegate)

        self.view.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        self.view.setEditTriggers(
            QtWidgets.QAbstractItemView.DoubleClicked |
            QtWidgets.QAbstractItemView.EditKeyPressed
        )

        self.view.setAcceptDrops(True)
        self.view.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)
        self.view.setDropIndicatorShown(True)

        layout.addWidget(self.view)
        self.setLayout(layout)

    def _init_actions(self):
        QtCore.Slot()

        def save_to_disk():
            lib.settings.set_section('data_header_mapping', self.view.modelw().get_current_section_data())

        action = QtGui.QAction('Save to Disk', self.view)
        action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
        action.setShortcut(QtGui.QKeySequence('Ctrl+S'))
        action.triggered.connect(save_to_disk)
        self.view.addAction(action)

        @QtCore.Slot()
        def revert_to_defaults():
            lib.settings.revert_section('data_header_mapping')

        action = QtGui.QAction('Revert', self.view)
        action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
        action.setShortcut(QtGui.QKeySequence('Ctrl+Shift+R'))
        action.triggered.connect(revert_to_defaults)
        self.view.addAction(action)

        @QtCore.Slot()
        def reload_from_disk():
            lib.settings.reload_section('data_header_mapping')

        action = QtGui.QAction('Refresh', self.view)
        action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
        action.setShortcut(QtGui.QKeySequence('Ctrl+R'))
        action.triggered.connect(reload_from_disk)
        self.view.addAction(action)

    def _init_model(self):
        model = DataMappingModel()
        self.view.setModel(model)

        rh = ui.Size.RowHeight(1.0)
        self.view.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.view.verticalHeader().setDefaultSectionSize(rh)
        self.view.verticalHeader().setVisible(False)


        self.view.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.view.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.view.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.view.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)


    def _connect_signals(self):
        pass
