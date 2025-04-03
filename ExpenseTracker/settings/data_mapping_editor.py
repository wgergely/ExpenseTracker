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

Row height is enforced with ui.Size.RowHeight(1.0).
The table is non-focusable but still allows cell editing via click/double-click.

We fix the editor alignment by overriding updateEditorGeometry in the delegate.
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
    """

    HEADERS = ['Data Column', 'Spreadsheet Column']  # column 0, column 1

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

        # Column 1 is editable
        return (base_flags
                | QtCore.Qt.ItemIsSelectable
                | QtCore.Qt.ItemIsEditable
                | QtCore.Qt.ItemIsEnabled)

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
            completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
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


class DataMappingEditor(QtWidgets.QWidget):
    """
    Main widget for editing data_header_mapping with:
      - 5 rows (date, amount, description, category, account)
      - 2 columns: "Data Column" (read-only) + "Spreadsheet Column" (editable)
      - A horizontal header, hidden vertical header
      - A custom delegate for col 1 that offers a QLineEdit + QCompleter
      - Non-focusable table, but still clickable/double-clickable for editing
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Attempt to load column names from ledger.json, else fallback ledger.json.template
        self._all_headers = get_all_header_names()

        # Create model & delegate
        self.model = DataMappingModel()
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

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

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

        # Set alignment for the header
        self.table.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignLeft)

        # Table is clickable for editing, but won't appear focused
        self.table.setFocusPolicy(QtCore.Qt.NoFocus)
        # Allow double-click or Enter to edit
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked |
                                   QtWidgets.QAbstractItemView.EditKeyPressed)

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
