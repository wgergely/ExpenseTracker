"""
Category editor module for ledger "categories". Provides:
- CategoriesModel (QAbstractTableModel) for columns:
  0) name
  1) display_name
  2) description
  3) icon
  4) color
  5) excluded

- CategoryItemDelegate for custom painting and custom editors:
- CategoryEditor widget with a QToolbar for Add, Remove, Edit, Restore

"""

import json
import pathlib
import tempfile
from PySide6 import QtCore, QtGui, QtWidgets

from ..ui import ui

TEMPLATE_DIR = pathlib.Path(__file__).parent.parent / 'config'
ICON_DIR = TEMPLATE_DIR / 'icons'
LEDGER_TEMPLATE = TEMPLATE_DIR / 'ledger.json.template'

CONFIG_DIR = pathlib.Path(tempfile.gettempdir()) / 'ExpenseTracker' / 'config'
LEDGER_PATH = CONFIG_DIR / 'ledger.json'

# Columns
COL_ICON = 0
COL_NAME = 1
COL_DISPLAY_NAME = 2
COL_DESCRIPTION = 3
COL_COLOR = 4
COL_EXCLUDED = 5

DEFAULT_ICON = "Miscellaneous.png"


def load_categories_dict_from_path(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('categories', {})
    except Exception:
        return {}


class CategoriesModel(QtCore.QAbstractTableModel):
    HEADERS = {
        COL_NAME: "Name",
        COL_DISPLAY_NAME: "Display Name",
        COL_DESCRIPTION: "Description",
        COL_ICON: "Icon",
        COL_COLOR: "Color",
        COL_EXCLUDED: "Excluded"
    }

    def __init__(self, categories_list=None, parent=None):
        super().__init__(parent)
        self._categories = categories_list if categories_list else []

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._categories) if not parent.isValid() else 0

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 6 if not parent.isValid() else 0

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        cat = self._categories[row]
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            if col == COL_NAME:
                return cat["name"]
            elif col == COL_DISPLAY_NAME:
                # fallback if empty
                if role == QtCore.Qt.DisplayRole and not cat["display_name"]:
                    return cat["name"]
                return cat["display_name"]
            elif col == COL_DESCRIPTION:
                return cat["description"]
            elif col == COL_ICON:
                return cat["icon"] if cat["icon"] else DEFAULT_ICON
            elif col == COL_COLOR:
                return cat["color"] or "#FFFFFF"
            elif col == COL_EXCLUDED:
                return cat["excluded"]
        return None

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if not index.isValid() or role != QtCore.Qt.EditRole:
            return False

        row = index.row()
        col = index.column()
        cat = self._categories[row]

        if col == COL_NAME:
            new_name = str(value).strip()
            if not new_name:
                return False  # reject empty name
            cat["name"] = new_name
        elif col == COL_DISPLAY_NAME:
            cat["display_name"] = str(value).strip()
        elif col == COL_DESCRIPTION:
            cat["description"] = str(value).strip()
        elif col == COL_ICON:
            icon_val = value if value else DEFAULT_ICON
            cat["icon"] = icon_val
        elif col == COL_COLOR:
            cat["color"] = str(value).strip()
        elif col == COL_EXCLUDED:
            cat["excluded"] = bool(value)
        else:
            return False

        self.dataChanged.emit(index, index, [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole])
        return True

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.ItemIsEnabled
        return (QtCore.Qt.ItemIsEnabled
                | QtCore.Qt.ItemIsEditable
                | QtCore.Qt.ItemIsSelectable)

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        """
        We'll show real headers for columns 0,1,2 and blank for 3,4,5
        as requested.
        """
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            if section in self.HEADERS:
                return self.HEADERS[section]
        return super().headerData(section, orientation, role)

    def insertRow(self, row, name="", display_name="", desc="", icon="", color="", excluded=False):
        self.beginInsertRows(QtCore.QModelIndex(), row, row)
        if not icon:
            icon = DEFAULT_ICON
        if not color:
            color = "#FFFFFF"
        self._categories.insert(row, {
            "name": name if name else "NewCategory",
            "display_name": display_name,
            "description": desc,
            "icon": icon,
            "color": color,
            "excluded": excluded
        })
        self.endInsertRows()

    def removeRow(self, row, parent=QtCore.QModelIndex()):
        if 0 <= row < len(self._categories):
            self.beginRemoveRows(parent, row, row)
            self._categories.pop(row)
            self.endRemoveRows()

    def to_categories_dict(self) -> dict:
        out = {}
        for c in self._categories:
            nm = c["name"] if c["name"] else "Unnamed"
            out[nm] = {
                "display_name": c["display_name"],
                "description": c["description"],
                "icon": c["icon"] if c["icon"] else DEFAULT_ICON,
                "color": c["color"] if c["color"] else "#FFFFFF",
                "excluded": c["excluded"]
            }
        return out

    def load_from_categories_dict(self, d: dict):
        self.beginResetModel()
        self._categories.clear()
        for k, v in d.items():
            self._categories.append({
                "name": k,
                "display_name": v.get("display_name", ""),
                "description": v.get("description", ""),
                "icon": v.get("icon", DEFAULT_ICON),
                "color": v.get("color", "#FFFFFF"),
                "excluded": bool(v.get("excluded", False))
            })
        self.endResetModel()


class CategoryItemDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, icon_dir, parent=None):
        super().__init__(parent)
        self.icon_dir = icon_dir
        self._all_icons = []
        if icon_dir.exists():
            for p in sorted(icon_dir.glob("*.png")):
                self._all_icons.append(p.name)

    def paint(self, painter, option, index):
        painter.save()
        # background
        hover = option.state & QtWidgets.QStyle.State_MouseOver
        selected = option.state & QtWidgets.QStyle.State_Selected
        if hover or selected:
            painter.setBrush(ui.Color.Background())
        else:
            painter.setBrush(ui.Color.VeryDarkBackground())
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(option.rect)

        col = index.column()
        val = index.data(QtCore.Qt.DisplayRole) or ""

        o = ui.Size.Margin(0.5)
        rect = QtCore.QRect(option.rect).adjusted(o, 0, -o, 0)

        if col == COL_NAME:
            painter.setPen(ui.Color.Text())
            font = QtGui.QFont(option.font)
            font.setWeight(QtGui.QFont.ExtraBold)
            painter.setFont(font)
            painter.drawText(rect, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, str(val or ""))
        elif col == COL_DISPLAY_NAME:
            painter.setPen(ui.Color.Text())
            font = QtGui.QFont(option.font)
            font.setWeight(QtGui.QFont.Medium)
            font.setItalic(True)
            painter.setFont(font)
            painter.drawText(rect, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, str(val or ""))
        elif col == COL_DESCRIPTION:
            painter.setPen(ui.Color.Text())
            font = QtGui.QFont(option.font)
            font.setWeight(QtGui.QFont.Light)
            painter.setFont(font)
            painter.drawText(rect, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, str(val or ""))
        elif col == COL_ICON:
            icon_name = val if val else DEFAULT_ICON

            rect = QtCore.QRect(0, 0, ui.Size.Margin(1.0), ui.Size.Margin(1.0))
            rect.moveCenter(option.rect.center())

            o = ui.Size.Indicator(2.0)
            rect.adjusted(o, o, -o, -o)

            icon = QtGui.QIcon(str(self.icon_dir / icon_name))
            icon.paint(painter, rect, QtCore.Qt.AlignCenter)
        elif col == COL_COLOR:
            rect = QtCore.QRect(0,0,ui.Size.Margin(1.0), ui.Size.Margin(1.0))
            rect.moveCenter(option.rect.center())

            o = ui.Size.Indicator(2.0)
            rect.adjusted(o, o, -o, -o)

            if not val:
                val = ui.Color.Text().name(QtGui.QColor.HexRgb)

            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setBrush(QtGui.QBrush(QtGui.QColor(val)))

            painter.drawRoundedRect(rect, o, o)

        elif col == COL_EXCLUDED:
            # '❌' if True, else blank
            is_excl = bool(val)
            text_val = "❌" if is_excl else "✅"
            painter.setPen(ui.Color.Text())
            font = QtGui.QFont(option.font)
            font.setWeight(QtGui.QFont.ExtraBold)

            painter.drawText(option.rect, QtCore.Qt.AlignCenter, text_val)
        painter.restore()

    def _drawIcon(self, painter, icon_name, option):
        icon_path = self.icon_dir / icon_name
        icon_obj = QtGui.QIcon(str(icon_path)) if icon_path.exists() else QtGui.QIcon()
        icon_size = ui.Size.Margin(1.5)
        x = option.rect.x() + (option.rect.width() - icon_size)//2
        y = option.rect.y() + (option.rect.height() - icon_size)//2
        target_rect = QtCore.QRect(x, y, icon_size, icon_size)
        icon_obj.paint(painter, target_rect)

    #
    # Creating an Editor
    #
    def createEditor(self, parent, option, index):
        col = index.column()
        if col in (COL_NAME, COL_DISPLAY_NAME, COL_DESCRIPTION):
            e = QtWidgets.QLineEdit(parent)
            return e
        else:
            # For col3,4,5, we return a dummy widget. We'll do popups in setEditorData.
            # This ensures the "edit" event is triggered, though.
            e = QtWidgets.QWidget(parent)
            return e

    def setEditorData(self, editor, index):
        """
        Double-click triggers editing -> createEditor -> setEditorData.
        For columns col3(icon), col4(color), col5(excluded), we open dialogs or do toggles.
        """
        col = index.column()
        model = index.model()
        val = index.data(QtCore.Qt.EditRole)

        if col in (COL_NAME, COL_DISPLAY_NAME, COL_DESCRIPTION):
            editor.setText(val or "")
        elif col == COL_ICON:
            # Show icon selection dialog (blocking)
            current_icon = val if val else DEFAULT_ICON
            chosen = self._pick_icon_dialog(current_icon, editor.parentWidget())
            if chosen is not None:
                model.setData(index, chosen, QtCore.Qt.EditRole)
            # done editing
            self.commitData.emit(editor)
            self.closeEditor.emit(editor, QtWidgets.QAbstractItemDelegate.NoHint)
        elif col == COL_COLOR:
            # Show color dialog
            color_str = val or "#FFFFFF"
            old_color = QtGui.QColor(color_str)
            new_col = QtWidgets.QColorDialog.getColor(old_color, editor.parentWidget(), "Pick Color", QtWidgets.QColorDialog.ShowAlphaChannel)
            if new_col.isValid():
                model.setData(index, new_col.name(QtGui.QColor.HexRgb), QtCore.Qt.EditRole)
            self.commitData.emit(editor)
            self.closeEditor.emit(editor, QtWidgets.QAbstractItemDelegate.NoHint)
        elif col == COL_EXCLUDED:
            # toggle
            new_val = not bool(val)
            model.setData(index, new_val, QtCore.Qt.EditRole)
            self.commitData.emit(editor)
            self.closeEditor.emit(editor, QtWidgets.QAbstractItemDelegate.NoHint)

    def setModelData(self, editor, model, index):
        """
        For columns 0..2 with line edits.
        """
        col = index.column()
        if col in (COL_NAME, COL_DISPLAY_NAME, COL_DESCRIPTION):
            text_val = editor.text()
            model.setData(index, text_val, QtCore.Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        """
        Set geometry for text-based columns. For popup columns (icon, color, excluded),
        there's no embedded widget to position, so we do nothing.
        """
        col = index.column()
        if col in (COL_NAME, COL_DISPLAY_NAME, COL_DESCRIPTION):
            editor.setGeometry(option.rect)
            editor.setStyleSheet(f"height: {option.rect.height()}px;")

    def _pick_icon_dialog(self, current_icon, parent):
        """
        Blocking dialog in IconMode. Return the chosen icon or None if canceled.
        """
        d = QtWidgets.QDialog(parent)
        d.setWindowTitle("Pick Icon")
        lay = QtWidgets.QVBoxLayout(d)

        view = QtWidgets.QListView(d)
        model = QtGui.QStandardItemModel(view)
        view.setModel(model)
        view.setViewMode(QtWidgets.QListView.IconMode)
        view.setResizeMode(QtWidgets.QListView.Adjust)
        view.setMovement(QtWidgets.QListView.Static)
        view.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        current_idx = None
        for i, icon_name in enumerate(self._all_icons):
            item = QtGui.QStandardItem()
            icon_path = self.icon_dir / icon_name
            icon_obj = QtGui.QIcon(str(icon_path))
            item.setIcon(icon_obj)
            # item.setText(icon_name)
            item.setData(icon_name, QtCore.Qt.UserRole)
            model.appendRow(item)
            if icon_name == current_icon:
                current_idx = i

        if current_idx is not None:
            idxm = model.index(current_idx, 0)
            view.setCurrentIndex(idxm)

        lay.addWidget(view)

        btn_lay = QtWidgets.QHBoxLayout()
        ok_btn = QtWidgets.QPushButton("OK", d)
        cancel_btn = QtWidgets.QPushButton("Cancel", d)
        btn_lay.addStretch(1)
        btn_lay.addWidget(ok_btn)
        btn_lay.addWidget(cancel_btn)
        lay.addLayout(btn_lay)

        chosen_icon = None

        def on_ok():
            idx = view.currentIndex()
            if idx.isValid():
                ic = idx.data(QtCore.Qt.UserRole)
                nonlocal chosen_icon
                chosen_icon = ic
            d.accept()

        def on_cancel():
            d.reject()

        ok_btn.clicked.connect(on_ok)
        cancel_btn.clicked.connect(on_cancel)

        d.setLayout(lay)
        res = d.exec()
        if res == QtWidgets.QDialog.Accepted and chosen_icon:
            return chosen_icon
        return None


class CategoryEditor(QtWidgets.QWidget):
    """
    Main widget that:
    - loads categories from ledger.json or fallback ledger.json.template
    - shows them in a QTableView with CategoryItemDelegate
    - offers Add/Remove/Edit/Restore through a toolbar
    """
    def __init__(self, parent=None):
        super().__init__(parent)

        cat_dict = self._load_categories()
        cat_list = self._dict_to_list(cat_dict)
        self.model = CategoriesModel(cat_list)

        self.delegate = CategoryItemDelegate(ICON_DIR, self)

        self.setMinimumSize(ui.Size.Margin(2.0),
                            ui.Size.RowHeight(12.0))
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)

        self._init_ui()

    def _load_categories(self) -> dict:
        cd = load_categories_dict_from_path(LEDGER_PATH)
        if cd:
            return cd
        fallback = load_categories_dict_from_path(LEDGER_TEMPLATE)
        return fallback or {}

    def _dict_to_list(self, cat_dict: dict) -> list:
        out = []
        for k, v in cat_dict.items():
            out.append({
                "name": k,
                "display_name": v.get("display_name", ""),
                "description": v.get("description", ""),
                "icon": v.get("icon", ""),
                "color": v.get("color", "#FFFFFF"),
                "excluded": bool(v.get("excluded", False))
            })
        return out

    def _list_to_dict(self) -> dict:
        return self.model.to_categories_dict()

    def _init_ui(self):
        lay = QtWidgets.QVBoxLayout(self)
        self.layout().setContentsMargins(0, 0, 0, 0)

        # Toolbar
        self.toolbar = QtWidgets.QToolBar(self)
        self.toolbar.setMovable(False)
        self.toolbar.setFixedHeight(ui.Size.RowHeight(1.0))
        self.act_add = QtGui.QAction("Add", self)
        self.act_remove = QtGui.QAction("Remove", self)
        self.act_edit = QtGui.QAction("Edit", self)
        self.act_restore = QtGui.QAction("Restore")

        self.toolbar.addAction(self.act_add)
        self.toolbar.addAction(self.act_remove)
        self.toolbar.addAction(self.act_edit)
        self.toolbar.addAction(self.act_restore)
        lay.addWidget(self.toolbar)

        # Table
        self.table = QtWidgets.QTableView(self)
        self.table.setModel(self.model)
        self.table.setItemDelegate(self.delegate)


        # Double-click editing
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked |
                                   QtWidgets.QAbstractItemView.EditKeyPressed)

        # Hide vertical header
        self.table.verticalHeader().setVisible(False)

        # Row height
        rh = ui.Size.RowHeight(1.0)
        self.table.verticalHeader().setDefaultSectionSize(rh)

        # Column widths
        self.table.horizontalHeader().setSectionResizeMode(COL_NAME, QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(COL_DISPLAY_NAME, QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(COL_DESCRIPTION, QtWidgets.QHeaderView.Stretch)

        self.table.horizontalHeader().setSectionResizeMode(COL_ICON, QtWidgets.QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(COL_COLOR, QtWidgets.QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(COL_EXCLUDED, QtWidgets.QHeaderView.Fixed)


        self.table.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.table.horizontalHeader().setDefaultSectionSize(ui.Size.RowHeight(1.0))

        # Possibly hide the header for col3,col4,col5 if you want no text
        # (the model's headerData returns empty strings for them)

        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setFocusPolicy(QtCore.Qt.NoFocus)

        lay.addWidget(self.table)
        self.setLayout(lay)

        self._connect_signals()

    def _connect_signals(self):
        self.act_add.triggered.connect(self.on_add)
        self.act_remove.triggered.connect(self.on_remove)
        self.act_edit.triggered.connect(self.on_edit)
        self.act_restore.triggered.connect(self.on_restore)

    def on_add(self):
        r = self.model.rowCount()
        self.model.insertRow(r, name="NewCategory", icon=DEFAULT_ICON)
        idx = self.model.index(r, 0)
        self.table.setCurrentIndex(idx)
        self.table.edit(idx)

    def on_remove(self):
        idx = self.table.currentIndex()
        if idx.isValid():
            self.model.removeRow(idx.row())

    def on_edit(self):
        idx = self.table.currentIndex()
        if idx.isValid():
            self.table.edit(idx)

    def on_restore(self):
        if not LEDGER_TEMPLATE.exists():
            QtWidgets.QMessageBox.warning(self, "Error", "ledger.json.template not found.")
            return
        cat_dict = load_categories_dict_from_path(LEDGER_TEMPLATE)
        self.model.load_from_categories_dict(cat_dict)
        QtWidgets.QMessageBox.information(self, "Restored", "Categories restored from template.")

    def get_categories_dict(self) -> dict:
        """Return the final categories dict for saving to ledger.json."""
        return self._list_to_dict()
