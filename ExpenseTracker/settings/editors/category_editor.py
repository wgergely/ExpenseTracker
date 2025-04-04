"""
Category editor module for ledger "categories". Provides:
- CategoriesModel (QAbstractTableModel) for columns
- CategoryItemDelegate for custom painting and custom editors:
- CategoryEditor widget with a QToolbar for Add, Remove, Edit, Restore

"""
import logging

from PySide6 import QtCore, QtGui, QtWidgets

from .. import lib
from ...ui import ui

COL_ICON = 0
COL_COLOR = 1
COL_NAME = 2
COL_DISPLAY_NAME = 3
COL_DESCRIPTION = 4
COL_EXCLUDED = 5

DEFAULT_ICON = "Miscellaneous.png"


class CategoriesModel(QtCore.QAbstractTableModel):
    HEADERS = {
        COL_NAME: "Name",
        COL_DISPLAY_NAME: "Display Name",
        COL_DESCRIPTION: "Description",
        COL_ICON: "",
        COL_COLOR: "",
        COL_EXCLUDED: ""
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._categories = []

        QtCore.QTimer.singleShot(150, self.init_data)

    def init_data(self):
        d = lib.settings.get_section('categories')

        self.beginResetModel()
        self._categories.clear()
        for k, v in d.items():
            self._categories.append({
                "name": k,
                "display_name": v.get("display_name", ""),
                "description": v.get("description", ""),
                "icon": v.get("icon", DEFAULT_ICON),
                "color": v.get("color", ui.Color.Text().name(QtGui.QColor.HexRgb)),
                "excluded": bool(v.get("excluded", False))
            })
        self.endResetModel()

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
                return cat["color"] or ui.Color.Text().name(QtGui.QColor.HexRgb)
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
                logging.warning("Category name cannot be empty.")
                return False  # reject empty name
            if new_name in [cat["name"] for cat in self._categories if cat != self._categories[row]]:
                logging.warning(f"Category name '{new_name}' already exists.")
                return False

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
            color = ui.Color.Text().name(QtGui.QColor.HexRgb)

        name = name if name else "NewCategory"

        # Ensure name is unique
        names = [c["name"] for c in self._categories]
        if name in names:
            i = 1
            while f"{name}_{i}" in names:
                i += 1
            name = f"{name}_{i}"

        self._categories.insert(row, {
            "name": name,
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
                "color": c["color"] if c["color"] else ui.Color.Text().name(QtGui.QColor.HexRgb),
                "excluded": c["excluded"]
            }
        return out

    @QtCore.Slot()
    def add_new(self):
        """
        Add a new category with default values.
        """
        r = self.rowCount()
        self.insertRow(r, name="NewCategory", icon=DEFAULT_ICON)
        idx = self.index(r, COL_NAME)
        self.dataChanged.emit(idx, idx, [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole])
        return idx

class CategoryItemDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._all_icons = []

        if lib.settings.paths.icon_dir.exists():
            for p in sorted(lib.settings.paths.icon_dir.glob("*.png")):
                self._all_icons.append(p.name)

    def paint(self, painter, option, index):
        painter.save()

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

            index = index.sibling(index.row(), COL_COLOR)
            val = index.data(QtCore.Qt.EditRole) or ui.Color.Text().name(QtGui.QColor.HexRgb)

            painter.setBrush(QtGui.QBrush(QtGui.QColor(val)))
            painter.setOpacity(0.2)
            painter.drawRect(option.rect)

            painter.setOpacity(1.0)
            icon = QtGui.QIcon(str(lib.settings.paths.icon_dir / icon_name))
            icon.paint(painter, rect, QtCore.Qt.AlignCenter)
        elif col == COL_COLOR:
            rect = QtCore.QRect(0, 0, ui.Size.Margin(1.0), ui.Size.Margin(1.0))
            rect.moveCenter(option.rect.center())

            o = ui.Size.Indicator(1.0)
            rect = rect.adjusted(o, o, -o, -o)

            if not val:
                val = ui.Color.Text().name(QtGui.QColor.HexRgb)

            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setBrush(QtGui.QBrush(QtGui.QColor(val)))

            painter.setOpacity(0.2)
            painter.drawRect(option.rect)

            painter.setOpacity(1.0)
            o = ui.Size.Indicator(1.0)
            painter.drawRoundedRect(rect, o, o)

        elif col == COL_EXCLUDED:
            is_excl = bool(val)
            text_val = "❌" if is_excl else "✅"
            painter.setPen(ui.Color.Text())
            font = QtGui.QFont(option.font)
            font.setWeight(QtGui.QFont.ExtraBold)

            painter.drawText(option.rect, QtCore.Qt.AlignCenter, text_val)
        painter.restore()

    def createEditor(self, parent, option, index):
        col = index.column()
        if col in (COL_NAME, COL_DISPLAY_NAME, COL_DESCRIPTION):
            e = QtWidgets.QLineEdit(parent)
            return e
        else:
            # dummy widget for popups
            # This ensures the "edit" event is triggered, though.
            e = QtWidgets.QWidget(parent)
            e.setAttribute(QtCore.Qt.WA_NoSystemBackground)
            e.setAttribute(QtCore.Qt.WA_OpaquePaintEvent)
            e.setAttribute(QtCore.Qt.WA_NoChildEventsForParent)
            e.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            e.setFocusPolicy(QtCore.Qt.NoFocus)
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

            editor.deleteLater()

        elif col == COL_COLOR:
            color_str = val or ui.Color.Text().name(QtGui.QColor.HexRgb)
            old_color = QtGui.QColor(color_str)
            new_col = QtWidgets.QColorDialog.getColor(old_color, editor.parentWidget(), "Pick Color",
                                                      QtWidgets.QColorDialog.ShowAlphaChannel)
            if new_col.isValid():
                model.setData(index, new_col.name(QtGui.QColor.HexRgb), QtCore.Qt.EditRole)
            self.commitData.emit(editor)
            self.closeEditor.emit(editor, QtWidgets.QAbstractItemDelegate.NoHint)

            editor.deleteLater()

        elif col == COL_EXCLUDED:
            # toggle
            new_val = not bool(val)
            model.setData(index, new_val, QtCore.Qt.EditRole)
            self.commitData.emit(editor)
            self.closeEditor.emit(editor, QtWidgets.QAbstractItemDelegate.NoHint)

            editor.deleteLater()

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
        else:
            editor.setGeometry(QtCore.QRect(0, 0, 0, 0))

    def _pick_icon_dialog(self, current_icon, parent):
        """
        Blocking dialog in IconMode. Return the chosen icon or None if canceled.
        """
        d = QtWidgets.QDialog(parent)
        d.setWindowTitle("Pick Icon")
        d.setMinimumSize(
            ui.Size.DefaultWidth(0.5),
            ui.Size.DefaultWidth(0.5),
        )
        lay = QtWidgets.QVBoxLayout(d)
        lay.setContentsMargins(0, 0, 0, 0)

        o = ui.Size.Margin(0.5)
        lay.setSpacing(o)

        view = QtWidgets.QListView(d)
        model = QtGui.QStandardItemModel(view)
        view.setModel(model)
        view.setViewMode(QtWidgets.QListView.IconMode)
        view.setResizeMode(QtWidgets.QListView.Adjust)
        view.setMovement(QtWidgets.QListView.Static)
        view.setFlow(QtWidgets.QListView.LeftToRight)
        view.setItemAlignment(QtCore.Qt.AlignCenter)
        view.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        view.setSpacing(ui.Size.Margin(1.0))

        current_idx = None
        for i, icon_name in enumerate(self._all_icons):
            item = QtGui.QStandardItem()
            icon_path = lib.settings.paths.icon_dir / icon_name
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
        btn_lay.addWidget(ok_btn, 1)
        btn_lay.addWidget(cancel_btn, 0)
        lay.addLayout(btn_lay)

        chosen_icon = None

        @QtCore.Slot()
        def on_ok():
            idx = view.currentIndex()
            if idx.isValid():
                ic = idx.data(QtCore.Qt.UserRole)
                nonlocal chosen_icon
                chosen_icon = ic
            d.accept()

        view.doubleClicked.connect(on_ok)
        view.activated.connect(on_ok)

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
        super().__init__(parent=parent)
        self.toolbar = None
        self.view = None

        self.setMinimumSize(
            ui.Size.Margin(2.0),
            ui.Size.RowHeight(12.0)
        )
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Expanding
        )

        self._create_ui()
        self._init_model()
        self._init_actions()
        self._connect_signals()

    def _create_ui(self):
        QtWidgets.QVBoxLayout(self)
        self.layout().setContentsMargins(0, 0, 0, 0)
        # Toolbar
        self.toolbar = QtWidgets.QToolBar(self)
        self.toolbar.setMovable(False)
        self.toolbar.setFixedHeight(ui.Size.RowHeight(1.0))
        self.layout().addWidget(self.toolbar, 1)

        # Table
        self.view = QtWidgets.QTableView(self)
        self.view.setItemDelegate(CategoryItemDelegate())
        self.view.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        # Double-click editing
        self.view.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked |
                                  QtWidgets.QAbstractItemView.EditKeyPressed)

        # Hide vertical header
        self.view.verticalHeader().setVisible(False)

        self.view.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.view.horizontalHeader().setDefaultSectionSize(ui.Size.RowHeight(1.0))

        self.view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.view.setFocusPolicy(QtCore.Qt.NoFocus)

        self.layout().addWidget(self.view)

    def _connect_signals(self):
        pass
        # self.act_add.triggered.connect(self.on_add)
        # self.act_remove.triggered.connect(self.on_remove)
        # self.act_edit.triggered.connect(self.on_edit)
        # self.act_restore.triggered.connect(self.on_restore)

    def _init_model(self):
        model = CategoriesModel(parent=self)
        self.view.setModel(model)

        # Row height
        rh = ui.Size.RowHeight(1.0)
        self.view.verticalHeader().setDefaultSectionSize(rh)

        # Column widths
        self.view.horizontalHeader().setSectionResizeMode(COL_NAME, QtWidgets.QHeaderView.ResizeToContents)
        self.view.horizontalHeader().setSectionResizeMode(COL_DISPLAY_NAME, QtWidgets.QHeaderView.ResizeToContents)
        self.view.horizontalHeader().setSectionResizeMode(COL_DESCRIPTION, QtWidgets.QHeaderView.Stretch)

        self.view.horizontalHeader().setSectionResizeMode(COL_ICON, QtWidgets.QHeaderView.Fixed)
        self.view.horizontalHeader().setSectionResizeMode(COL_COLOR, QtWidgets.QHeaderView.Fixed)
        self.view.horizontalHeader().setSectionResizeMode(COL_EXCLUDED, QtWidgets.QHeaderView.Fixed)

    def _init_actions(self):

        action = QtGui.QAction('Add', self)
        action.setShortcut('Ctrl+N')
        action.setStatusTip('Add a new category')
        action.triggered.connect(self.view.model().add_new)
        self.toolbar.addAction(action)
        self.view.addAction(action)

        @QtCore.Slot()
        def on_remove():
            if not self.view.selectionModel().hasSelection():
                logging.warning("No category selected.")
                return

            index = next(iter(self.view.selectionModel().selectedIndexes()), QtCore.QModelIndex())

            if not index.isValid():
                logging.warning("No category selected.")
                return

            self.view.model().removeRow(index.row())

        action = QtGui.QAction('Remove', self)
        action.setShortcut('Delete')
        action.setStatusTip('Remove selected category')
        action.triggered.connect(on_remove)
        self.toolbar.addAction(action)
        self.view.addAction(action)


        # self.act_remove = QtGui.QAction("Remove", self)
        # self.act_edit = QtGui.QAction("Edit", self)
        # self.act_restore = QtGui.QAction("Restore")
        #
        # self.toolbar.addAction(self.act_add)



    def on_edit(self):
        idx = self.view.currentIndex()
        if idx.isValid():
            self.view.edit(idx)

    def on_restore(self):
        # Confirm first
        res = QtWidgets.QMessageBox.question(
            self,
            "Restore",
            "Are you sure you want to restore the categories from the template?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if res != QtWidgets.QMessageBox.Yes:
            return

        if not lib.settings.paths.ledger_template.exists():
            QtWidgets.QMessageBox.warning(self, "Error", "ledger.json.template not found.")
            return

        cat_dict = lib.settings.get_section('categories')
        self.model.load_from_categories_dict(cat_dict)

        QtWidgets.QMessageBox.information(self, "Restored", "Categories restored from template.")
