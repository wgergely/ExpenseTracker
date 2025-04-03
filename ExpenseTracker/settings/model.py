"""
Models for the ExpenseTracker settings.

.. seealso:: :mod:`settings.view`, :mod:`settings.editor`, :mod:`settings.settings`
"""
import shutil
import pathlib
import json
import os
import tempfile

from PySide6 import QtCore

TEMPLATE_DIR = pathlib.Path(__file__).parent.parent / 'config'
if not TEMPLATE_DIR.exists():
    raise FileNotFoundError(f"Template directory {TEMPLATE_DIR} does not exist.")

CLIENT_SECRET_TEMPLATE = TEMPLATE_DIR / 'client_secret.json.template'
LEDGER_TEMPLATE = TEMPLATE_DIR / 'ledger.json.template'

CONFIG_DIR = pathlib.Path(tempfile.gettempdir()) / 'ExpenseTracker' / 'config'
CLIENT_SECRET_PATH = CONFIG_DIR / 'client_secret.json'
LEDGER_PATH = CONFIG_DIR / 'ledger.json'

if not CONFIG_DIR.exists():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
if not CLIENT_SECRET_PATH.exists():
    shutil.copy(CLIENT_SECRET_TEMPLATE, CLIENT_SECRET_PATH)
if not LEDGER_PATH.exists():
    shutil.copy(LEDGER_TEMPLATE, LEDGER_PATH)


class LedgerSettingsData:
    """
    Holds ledger.json configuration data.

    Attributes:
        ledger_id (str): The spreadsheet ID.
        sheet_name (str): The sheet name.
        header (list[dict]): List of header entries, each with 'name' and 'type'.
        data_header_mapping (dict): Maps required keys to actual column names.
        categories (dict): Categories dictionary keyed by category key.
    """

    def __init__(self):
        self.ledger_id = ""
        self.sheet_name = ""
        self.header = []
        self.data_header_mapping = {
            "date": "",
            "amount": "",
            "description": "",
            "category": "",
            "account": ""
        }
        self.categories = {}
        self.load()

    def load(self):
        """Loads ledger settings from the module-level LEDGER_PATH."""
        if LEDGER_PATH.exists():
            with open(LEDGER_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.ledger_id = data.get("id", "")
            self.sheet_name = data.get("sheet", "")
            self.header = []
            for k, v in data.get("header", {}).items():
                self.header.append({"name": k, "type": v})
            self.data_header_mapping = data.get("data_header_mapping", self.data_header_mapping)
            self.categories = data.get("categories", {})

    def save(self):
        """Saves ledger settings to the module-level LEDGER_PATH."""
        data = {
            "id": self.ledger_id,
            "sheet": self.sheet_name,
            "header": {h["name"]: h["type"] for h in self.header},
            "data_header_mapping": self.data_header_mapping,
            "categories": self.categories
        }
        with open(LEDGER_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


class HeaderModel(QtCore.QAbstractTableModel):
    """
    Table model for the 'header' section of ledger.json.
    Each row has a 'name' and 'type'.
    """

    def __init__(self, header_data, parent=None):
        super().__init__(parent)
        self._header_data = header_data

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._header_data)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 2

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            row = index.row()
            col = index.column()
            if col == 0:
                return self._header_data[row]["name"]
            elif col == 1:
                return self._header_data[row]["type"]
        return None

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if not index.isValid():
            return False
        if role == QtCore.Qt.EditRole:
            row = index.row()
            col = index.column()
            if col == 0:
                self._header_data[row]["name"] = value
            elif col == 1:
                self._header_data[row]["type"] = value
            self.dataChanged.emit(index, index, [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole])
            return True
        return False

    def flags(self, index):
        base_flags = super().flags(index)
        if index.isValid():
            return base_flags | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsDragEnabled | QtCore.Qt.ItemIsDropEnabled
        return base_flags | QtCore.Qt.ItemIsDropEnabled

    def supportedDropActions(self):
        return QtCore.Qt.MoveAction

    def insertRows(self, row, count, parent=QtCore.QModelIndex()):
        self.beginInsertRows(parent, row, row + count - 1)
        for _ in range(count):
            self._header_data.insert(row, {"name": "", "type": "string"})
        self.endInsertRows()
        return True

    def removeRows(self, row, count, parent=QtCore.QModelIndex()):
        self.beginRemoveRows(parent, row, row + count - 1)
        for _ in range(count):
            self._header_data.pop(row)
        self.endRemoveRows()
        return True

    def mimeTypes(self):
        return ["application/vnd.text.list"]

    def mimeData(self, indexes):
        mime_data = QtCore.QMimeData()
        rows = [i.row() for i in indexes if i.isValid()]
        mime_data.setData("application/vnd.text.list", bytearray(str(rows), "utf-8"))
        return mime_data

    def dropMimeData(self, data, action, row, column, parent):
        if action == QtCore.Qt.IgnoreAction:
            return True
        if not data.hasFormat("application/vnd.text.list"):
            return False

        if parent.isValid():
            drop_row = parent.row()
        else:
            drop_row = self.rowCount()

        encoded_data = data.data("application/vnd.text.list").data()
        row_list = eval(encoded_data.decode("utf-8"))  # simplistic approach

        to_move = [self._header_data[r] for r in row_list]

        self.beginResetModel()
        for r in sorted(row_list, reverse=True):
            self._header_data.pop(r)
        for i, itm in enumerate(to_move):
            self._header_data.insert(drop_row + i, itm)
        self.endResetModel()
        return True


class CategoryModel(QtCore.QAbstractTableModel):
    """
    Table model for the 'categories' section of ledger.json.
    Each row: [key, display_name, color, description, excluded].
    """

    HEADERS = ["Key", "Display Name", "Color", "Description", "Excluded"]

    def __init__(self, categories_dict, parent=None):
        super().__init__(parent)
        self._categories = []
        for k, v in categories_dict.items():
            self._categories.append([
                k,
                v.get("display_name", ""),
                v.get("color", "#FFFFFF"),
                v.get("description", ""),
                v.get("excluded", False)
            ])

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._categories)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self.HEADERS[section]
        return super().headerData(section, orientation, role)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            return self._categories[index.row()][index.column()]
        return None

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if not index.isValid():
            return False
        if role == QtCore.Qt.EditRole:
            self._categories[index.row()][index.column()] = value
            self.dataChanged.emit(index, index, [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole])
            return True
        return False

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.ItemIsEnabled
        return QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled

    def insertRow(self, row, key="", display_name="", color="#FFFFFF", description="", excluded=False):
        self.beginInsertRows(QtCore.QModelIndex(), row, row)
        self._categories.insert(row, [key, display_name, color, description, excluded])
        self.endInsertRows()

    def removeRow(self, row, parent=QtCore.QModelIndex()):
        self.beginRemoveRows(parent, row, row)
        self._categories.pop(row)
        self.endRemoveRows()

    def to_dict(self):
        """Rebuilds the category data into a dict keyed by category key."""
        out = {}
        for cat in self._categories:
            out[cat[0]] = {
                "display_name": cat[1],
                "color": cat[2],
                "description": cat[3],
                "excluded": cat[4]
            }
        return out


class DataHeaderMappingModel(QtCore.QAbstractListModel):
    """
    List model for 'data_header_mapping' items: date, amount, description,
    category, and account.
    """

    def __init__(self, mapping_dict, parent=None):
        super().__init__(parent)
        self._keys = ["date", "amount", "description", "category", "account"]
        self._mapping = mapping_dict

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._keys)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        key = self._keys[index.row()]
        if role == QtCore.Qt.DisplayRole:
            return f"{key}: {self._mapping.get(key, '')}"
        elif role == QtCore.Qt.EditRole:
            return self._mapping.get(key, "")
        return None

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if not index.isValid():
            return False
        key = self._keys[index.row()]
        if role == QtCore.Qt.EditRole:
            self._mapping[key] = value
            self.dataChanged.emit(index, index, [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole])
            return True
        return False

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.ItemIsEnabled
        return QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled

    def get_mapping(self):
        """Returns the updated mapping as a dict."""
        return self._mapping
