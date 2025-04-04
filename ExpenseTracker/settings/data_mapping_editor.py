"""
Data Mapping Editor for the 'data_header_mapping' portion of ledger.json.

We have 5 fixed "data columns":
    1) date
    2) amount
    3) description
    4) category
    5) account

Each appears in rowCount = 5. We have 2 columns:
    Column 0: Data Column  (read-only, e.g. "date")
    Column 1: Spreadsheet Column (editable)

We label column 0 as "Data Column" and column 1 as "Spreadsheet Column".
The horizontal header is visible; the vertical header is hidden.

We load a list of possible spreadsheet columns by first reading ledger.json (LEDGER_PATH).
If that fails or is missing, we fall back to ledger.json.template (LEDGER_TEMPLATE).
If neither is valid, we return an empty list.

We also automatically load the current 'data_header_mapping' from the same ledger.json,
or if that fails, from ledger.json.template. If neither is valid, we start with blank mappings.

Row height is enforced with ui.Size.RowHeight(1.0).
The table is non-focusable but still allows cell editing via click/double-click.

We fix the editor alignment by overriding updateEditorGeometry in the delegate.

We also allow dropping from the Header Editor. If the user drags
a header name (mime type "application/x-headeritem"), the dropped name
becomes the value for the data mapping's spreadsheet column.
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

DATA_MAPPING_KEYS = ['date', 'amount', 'description', 'category', 'account']


def _load_data_mapping_from_path(path: pathlib.Path) -> dict:
    """
    Attempt to read the 'data_header_mapping' from the JSON file at 'path'.
    Return a dict if found, else empty dict.
    """
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('data_header_mapping', {})
    except Exception:
        return {}


def load_data_mapping() -> dict:
    """
    Loads the 'data_header_mapping' from LEDGER_PATH if available,
    otherwise falls back to LEDGER_TEMPLATE.
    If neither is available or fails, returns an empty dict.
    """
    # Attempt from LEDGER_PATH first
    mapping = _load_data_mapping_from_path(LEDGER_PATH)
    if mapping:
        return mapping

    # Fall back to LEDGER_TEMPLATE
    fallback = _load_data_mapping_from_path(LEDGER_TEMPLATE)
    return fallback or {}


def load_header_names_from_path(path: pathlib.Path) -> list[str]:
    """
    Attempt to load 'header' keys from the JSON file at 'path'.
    Return an empty list if not possible.
    """
    if not path.exists():
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        header_dict = data.get('header', {})
        return list(header_dict.keys())
    except Exception:
        return []


def get_all_header_names() -> list[str]:
    """
    Load all possible ledger header names from ledger.json (LEDGER_PATH) first;
    fall back to ledger.json.template (LEDGER_TEMPLATE) if that fails or has none.
    If both fail, returns [].
    """
    from_config = load_header_names_from_path(LEDGER_PATH)
    if from_config:
        return from_config

    from_template = load_header_names_from_path(LEDGER_TEMPLATE)
    return from_template  # possibly empty if that fails


class DataMappingModel(QtCore.QAbstractTableModel):
    """
    Table model with 5 rows (the fixed data columns) and 2 columns:
      Column 0 -> Data Column (read-only)
      Column 1 -> Spreadsheet Column (editable)

    We store the mapping internally like:
      _keys = [ "date", "amount", "description", "category", "account" ]
      _mapping = { "date": <mapped_name>, "amount": <mapped_name>, ... }

    Also implements dropMimeData() to accept "application/x-headeritem"
    from the Header Editor. The dropped header name is used as
    the spreadsheet column value in col=1.
    """

    HEADERS = ['Data Column', 'Spreadsheet Column']  # column 0, column 1
    MIME_HEADER = 'application/x-headeritem'

    def __init__(self, mapping_dict=None, parent=None):
        super().__init__(parent)
        self._keys = DATA_MAPPING_KEYS
        self._mapping = {
            'date': '',
            'amount': '',
            'description': '',
            'category': '',
            'account': ''
        }
        if mapping_dict:
            self._mapping.update(mapping_dict)

    def rowCount(self, parent=QtCore.QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._keys)

    def columnCount(self, parent=QtCore.QModelIndex()):
        if parent.isValid():
            return 0
        return 2

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()
        key = self._keys[row]

        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            if col == 0:
                # Data column name (read-only)
                return key
            else:
                # Spreadsheet Column
                return self._mapping.get(key, '')
        return None

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if not index.isValid() or role != QtCore.Qt.EditRole:
            return False

        row = index.row()
        col = index.column()
        if col == 1:
            key = self._keys[row]
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
            return (base_flags | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable) & ~QtCore.Qt.ItemIsEditable

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
        # Horizontal header with "Data Column" (col 0) / "Spreadsheet Column" (col 1)
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
        return super().headerData(section, orientation, role)

    def get_mapping(self):
        """
        Return the final data_header_mapping as a dict: { 'date': ..., 'amount': ... }
        """
        return dict(self._mapping)

    def set_mapping(self, mapping_dict):
        """
        Load an existing data_header_mapping dict into this model.
        e.g. { 'date': 'Date', 'amount': '€€€', ... }
        """
        self.beginResetModel()
        for k in self._keys:
            self._mapping[k] = mapping_dict.get(k, '')
        self.endResetModel()


class DataMappingDelegate(QtWidgets.QStyledItemDelegate):
    """
    Delegate for column 1 (Spreadsheet Column). Provides a QLineEdit
    with a QCompleter using the ledger's header names.
    Column 0 is read-only. We override updateEditorGeometry to fix alignment.

    The QCompleter is set to be always visible if the user is typing,
    by using UnfilteredPopupCompletion or a similar approach.
    """

    def __init__(self, available_headers, parent=None):
        super().__init__(parent)
        self._available_headers = available_headers

    def paint(self, painter, option, index):
        if index.column() == 1:
            painter.setBrush(ui.Color.VeryDarkBackground())
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRect(option.rect)

            # Draw the text with a custom color
            text = index.data(QtCore.Qt.DisplayRole)
            rect = QtCore.QRect(option.rect)
            rect.adjust(ui.Size.Margin(1.0), 0, -ui.Size.Margin(1.0), 0)

            if text:
                painter.setPen(ui.Color.Text())
                painter.drawText(rect, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, text)

        else:
            # Read-only column, use default paint
            super().paint(painter, option, index)

    def createEditor(self, parent, option, index):
        if index.column() == 1:
            editor = QtWidgets.QLineEdit(parent)
            completer = QtWidgets.QCompleter(self._available_headers, editor)
            # Show all options in a popup as soon as user types
            completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
            completer.setCompletionMode(QtWidgets.QCompleter.UnfilteredPopupCompletion)
            # If you want partial substring matching:
            # completer.setFilterMode(QtCore.Qt.MatchContains)
            editor.setCompleter(completer)
            return editor
        return None

    def setEditorData(self, editor, index):
        if editor is None:
            return
        value = index.model().data(index, QtCore.Qt.EditRole)
        editor.setText(value or '')
        # Focus and select text after 0 ms
        QtCore.QTimer.singleShot(0, lambda: (editor.setFocus(), editor.selectAll()))
        # Force the completer to appear with the current text
        if editor.completer():
            editor.completer().complete()

    def setModelData(self, editor, model, index):
        if editor is None:
            return
        text_val = editor.text()
        model.setData(index, text_val, QtCore.Qt.EditRole)

    def sizeHint(self, option, index):
        """
        Return a fixed row height from ui.Size.RowHeight(1.0).
        """
        row_h = ui.Size.RowHeight(1.0)
        return QtCore.QSize(option.rect.width(), row_h)

    def updateEditorGeometry(self, editor, option, index):
        """
        Explicitly set the editor geometry to match the cell area.
        """
        editor.setGeometry(option.rect)
        editor.setStyleSheet(f'height: {option.rect.height()}px')


class DataMappingEditor(QtWidgets.QWidget):
    """
    Main widget for editing data_header_mapping with:
      - 5 rows (date, amount, description, category, account)
      - 2 columns: "Data Column" (read-only) + "Spreadsheet Column" (editable)
      - A horizontal header, hidden vertical header
      - A custom delegate for col 1 that offers a QLineEdit + QCompleter
      - Non-focusable table, but still clickable/double-clickable for editing
      - Accepts drag-and-drop from the Header Editor:
        If you drop a header name (mime type "application/x-headeritem"),
        it populates the col=1 field with that name
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        # Attempt to load column names from ledger.json, else fallback ledger.json.template
        self._all_headers = get_all_header_names()

        # Load existing data_header_mapping from LEDGER_PATH or fallback to template
        # Then create the model with that mapping
        current_mapping = self._load_data_mapping()
        self.model = DataMappingModel(mapping_dict=current_mapping)

        self.delegate = DataMappingDelegate(self._all_headers, self)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum,
            QtWidgets.QSizePolicy.MinimumExpanding
        )

        self.setMinimumSize(
            ui.Size.Margin(1.0),
            ui.Size.RowHeight(7.5)
        )

        self._init_ui()

    def _load_data_mapping(self) -> dict:
        """
        Load 'data_header_mapping' from LEDGER_PATH if available,
        otherwise fallback to LEDGER_TEMPLATE, else empty.
        """
        def load_mapping_from(path: pathlib.Path) -> dict:
            if not path.exists():
                return {}
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get('data_header_mapping', {})
            except Exception:
                return {}

        # First try LEDGER_PATH
        mapping = load_mapping_from(LEDGER_PATH)
        if mapping:
            return mapping

        # Fallback to template
        fallback = load_mapping_from(LEDGER_TEMPLATE)
        return fallback or {}

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.table = QtWidgets.QTableView(self)
        self.table.setModel(self.model)
        self.table.setItemDelegate(self.delegate)

        # Hide vertical header for clarity
        self.table.verticalHeader().setVisible(False)

        # Fix row height
        self.table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        row_h = ui.Size.RowHeight(1.0)
        self.table.verticalHeader().setDefaultSectionSize(row_h)

        # Let columns expand proportionally
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        # Align column labels left
        self.table.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignLeft)

        # Table is clickable for editing, but won't appear focused
        self.table.setFocusPolicy(QtCore.Qt.NoFocus)
        # Allow double-click or Enter to edit
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked |
                                   QtWidgets.QAbstractItemView.EditKeyPressed)

        # Enable drop acceptance
        self.table.setAcceptDrops(True)
        self.table.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)
        self.table.setDropIndicatorShown(True)

        layout.addWidget(self.table)
        self.setLayout(layout)

    def set_mapping(self, mapping_dict):
        """
        Load a given data_header_mapping dict into our model.
        e.g.: {
          'date': 'Date',
          'amount': '€€€',
          'description': 'Original Description',
          'category': 'Category',
          'account': 'Account Name'
        }
        """
        self.model.set_mapping(mapping_dict)

    def get_mapping(self):
        """
        Return the updated mapping as a dict.
        """
        return self.model.get_mapping()
