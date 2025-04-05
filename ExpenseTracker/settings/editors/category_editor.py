"""Category editor module for ledger.json's "categories" section.

"""
import functools
import logging

from PySide6 import QtCore, QtGui, QtWidgets

from .. import lib
from ...ui import ui
from ...ui.actions import signals

COL_ICON = 0
COL_COLOR = 1
COL_NAME = 2
COL_DISPLAY_NAME = 3
COL_DESCRIPTION = 4
COL_EXCLUDED = 5

DEFAULT_ICON = 'Miscellaneous.png'


@functools.lru_cache(maxsize=128)
def get_all_icons():
    v = []
    if lib.settings.paths.icon_dir.exists():
        for p in sorted(lib.settings.paths.icon_dir.glob('*.png')):
            v.append(p.name)
    return v


class IconPickerDialog(QtWidgets.QDialog):
    """Dialog to pick an icon."""

    def __init__(self, current_icon, parent=None):
        super().__init__(parent=parent)

        self.setWindowTitle('Pick Icon')
        self.setMinimumSize(
            ui.Size.DefaultWidth(0.5),
            ui.Size.DefaultWidth(0.5),
        )
        self._chosen_icon = None
        self._current_icon = current_icon

        self.view = None
        self.ok_btn = None
        self.cancel_btn = None

        self._create_ui()
        self._init_model()
        self._connect_signals()

    def _create_ui(self):
        QtWidgets.QVBoxLayout(self)

        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(ui.Size.Margin(0.5))

        self.view = QtWidgets.QListView(self)
        self.view.setViewMode(QtWidgets.QListView.IconMode)
        self.view.setResizeMode(QtWidgets.QListView.Adjust)
        self.view.setMovement(QtWidgets.QListView.Static)
        self.view.setFlow(QtWidgets.QListView.LeftToRight)
        self.view.setItemAlignment(QtCore.Qt.AlignCenter)

        self.view.setEditTriggers(
            QtWidgets.QAbstractItemView.DoubleClicked |
            QtWidgets.QAbstractItemView.EditKeyPressed
        )

        self.view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.view.setSpacing(ui.Size.Margin(1.0))

        self.layout().addWidget(self.view)

        btn_lay = QtWidgets.QHBoxLayout()

        self.ok_btn = QtWidgets.QPushButton('OK', self)
        btn_lay.addWidget(self.ok_btn, 1)

        self.cancel_btn = QtWidgets.QPushButton('Cancel', self)
        btn_lay.addWidget(self.cancel_btn, 0)

        self.layout().addLayout(btn_lay)

    def _init_model(self):
        model = QtGui.QStandardItemModel(self.view)
        self.view.setModel(model)

        current_idx = None
        for i, icon_name in enumerate(get_all_icons()):
            item = QtGui.QStandardItem()
            icon_path = lib.settings.paths.icon_dir / icon_name
            item.setIcon(QtGui.QIcon(str(icon_path)))
            item.setData(icon_name, QtCore.Qt.UserRole)
            model.appendRow(item)
            if icon_name == self._current_icon:
                current_idx = i

        if current_idx is not None:
            idx = model.index(current_idx, 0)
            self.view.setCurrentIndex(idx)

    def _connect_signals(self):
        self.ok_btn.clicked.connect(self.accept_selection)
        self.cancel_btn.clicked.connect(self.reject)

        self.view.doubleClicked.connect(self.accept_selection)
        self.view.activated.connect(self.accept_selection)

    @QtCore.Slot()
    def accept_selection(self):
        idx = self.view.currentIndex()
        if idx.isValid():
            self._chosen_icon = idx.data(QtCore.Qt.UserRole)
        self.accept()

    def chosen_icon(self):
        """Return selected icon name or None."""
        return self._chosen_icon

    @classmethod
    def get_icon(cls, current_icon, parent=None):
        """Open icon picker dialog and return selected icon name."""
        w = cls(current_icon, parent=parent)
        if w.exec() != QtWidgets.QDialog.Accepted:
            return None
        return w.chosen_icon()


class CategoriesModel(QtCore.QAbstractTableModel):
    """Model responsible representing, editing and saving category items.

    """
    HEADERS = {
        COL_NAME: 'Name',
        COL_DISPLAY_NAME: 'Display Name',
        COL_DESCRIPTION: 'Description',
        COL_ICON: '',
        COL_COLOR: '',
        COL_EXCLUDED: ''
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._categories = []
        self._ignore_reload = False

        self._connect_signals()
        QtCore.QTimer.singleShot(150, self.init_data)

    @QtCore.Slot()
    def init_data(self):
        if self._ignore_reload:
            return

        d = lib.settings.get_section('categories')

        self.beginResetModel()
        try:
            self._categories.clear()
            for k, v in d.items():
                self._categories.append({
                    'name': k,
                    'display_name': v.get('display_name', ''),
                    'description': v.get('description', ''),
                    'icon': v.get('icon', DEFAULT_ICON),
                    'color': v.get('color', ui.Color.Text().name(QtGui.QColor.HexRgb)),
                    'excluded': bool(v.get('excluded', False))
                })
        finally:
            self.endResetModel()

    def _connect_signals(self):
        @QtCore.Slot(str)
        def on_config_changed(section_name):
            if section_name != 'categories':
                return
            self.init_data()

        signals.configSectionChanged.connect(on_config_changed)

        self.dataChanged.connect(
            lambda: lib.settings.set_section('categories', self.get_current_section_data())
        )

        @QtCore.Slot()
        def on_layout_changed():
            # We only want to write to disk but not reset the model
            try:
                self._ignore_reload = True
                lib.settings.set_section('categories', self.get_current_section_data())
            finally:
                self._ignore_reload = False

        self.rowsRemoved.connect(on_layout_changed)
        self.rowsInserted.connect(on_layout_changed)
        self.rowsMoved.connect(on_layout_changed)

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
                return cat['name']
            elif col == COL_DISPLAY_NAME:
                if role == QtCore.Qt.DisplayRole and not cat['display_name']:
                    return cat['name']
                return cat['display_name']
            elif col == COL_DESCRIPTION:
                return cat['description']
            elif col == COL_ICON:
                return cat['icon'] if cat['icon'] else DEFAULT_ICON
            elif col == COL_COLOR:
                return cat['color'] or ui.Color.Text().name(QtGui.QColor.HexRgb)
            elif col == COL_EXCLUDED:
                return cat['excluded']

        if role == QtCore.Qt.FontRole:
            if col == COL_NAME:
                font, _ = ui.Font.BoldFont(ui.Size.MediumText(1.0))
                font.setItalic(True)
            elif col == COL_DISPLAY_NAME:
                font, _ = ui.Font.BoldFont(ui.Size.MediumText(1.0))
            else:
                font, _ = ui.Font.MediumFont(ui.Size.MediumText(1.0))
            return font
        if role == QtCore.Qt.TextAlignmentRole:
            if col in (COL_NAME, COL_DISPLAY_NAME):
                return QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
            elif col == COL_DESCRIPTION:
                return QtCore.Qt.AlignRight | QtCore.Qt.AlignTop
            return QtCore.Qt.AlignCenter
        if role == QtCore.Qt.ForegroundRole:
            if col == COL_NAME:
                return ui.Color.SecondaryText()
            if col == COL_DISPLAY_NAME:
                return ui.Color.Text()
            if col == COL_DESCRIPTION:
                return ui.Color.SecondaryText()
            return ui.Color.Text()

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
                logging.warning('Category name cannot be empty.')
                return False  # reject empty name
            if new_name in [cat['name'] for cat in self._categories if cat != self._categories[row]]:
                logging.warning(f'Category name "{new_name}" already exists.')
                return False

            cat['name'] = new_name
        elif col == COL_DISPLAY_NAME:
            cat['display_name'] = str(value).strip()
        elif col == COL_DESCRIPTION:
            cat['description'] = str(value).strip()
        elif col == COL_ICON:
            icon_val = value if value else DEFAULT_ICON
            cat['icon'] = icon_val
        elif col == COL_COLOR:
            cat['color'] = str(value).strip()
        elif col == COL_EXCLUDED:
            cat['excluded'] = bool(value)
        else:
            return False

        try:
            self._ignore_reload = True
            self.dataChanged.emit(index, index, [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole])
        finally:
            self._ignore_reload = False

        return True

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.ItemIsEnabled
        return (QtCore.Qt.ItemIsEnabled
                | QtCore.Qt.ItemIsEditable
                | QtCore.Qt.ItemIsSelectable)

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
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

        name = name if name else 'NewCategory'

        # Ensure name is unique
        names = [c['name'] for c in self._categories]
        if name in names:
            i = 1
            while f'{name}_{i}' in names:
                i += 1
            name = f'{name}_{i}'

        self._categories.insert(row, {
            'name': name,
            'display_name': display_name,
            'description': desc,
            'icon': icon,
            'color': color,
            'excluded': excluded
        })
        self.endInsertRows()

    def removeRow(self, row, parent=QtCore.QModelIndex()):
        if 0 <= row < len(self._categories):
            self.beginRemoveRows(parent, row, row)
            self._categories.pop(row)
            self.endRemoveRows()

    @QtCore.Slot()
    def add_new(self):
        """Add a new category with default values.
        """
        r = self.rowCount()
        self.insertRow(r, name='NewCategory', icon=DEFAULT_ICON)
        idx = self.index(r, COL_NAME)
        self.dataChanged.emit(idx, idx, [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole])
        return idx

    @QtCore.Slot()
    def get_current_section_data(self):
        """ Return a dictionary of all categories.
        """
        data = {}
        for cat in self._categories:
            name = cat['name']
            data[name] = {
                'display_name': cat['display_name'],
                'description': cat['description'],
                'icon': cat['icon'] if cat['icon'] else DEFAULT_ICON,
                'color': cat['color'] if cat['color'] else ui.Color.Text().name(QtGui.QColor.HexRgb),
                'excluded': cat['excluded']
            }
        return data


class CategoryItemDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

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
        val = index.data(QtCore.Qt.DisplayRole) or ''

        if col == COL_NAME:
            super().paint(painter, option, index)
            return
        elif col == COL_DISPLAY_NAME:
            super().paint(painter, option, index)
        elif col == COL_DESCRIPTION:
            super().paint(painter, option, index)
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
            super().paint(painter, option, index)

            is_excl = bool(val)
            text_val = '❌' if is_excl else '✅'
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
            # placeholder widget for popups
            e = QtWidgets.QWidget(parent)
            e.setAttribute(QtCore.Qt.WA_NoSystemBackground)
            e.setAttribute(QtCore.Qt.WA_OpaquePaintEvent)
            e.setAttribute(QtCore.Qt.WA_NoChildEventsForParent)
            e.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            e.setFocusPolicy(QtCore.Qt.NoFocus)
            return e

    def setEditorData(self, editor, index):
        col = index.column()
        model = index.model()
        val = index.data(QtCore.Qt.EditRole)

        if col in (COL_NAME, COL_DISPLAY_NAME, COL_DESCRIPTION):
            editor.setText(val or "")

        elif col == COL_ICON:
            current_icon = val if val else DEFAULT_ICON

            v = IconPickerDialog.get_icon(current_icon, editor.parentWidget())
            if v is not None:
                model.setData(index, v, QtCore.Qt.EditRole)

            self.commitData.emit(editor)
            self.closeEditor.emit(editor, QtWidgets.QAbstractItemDelegate.NoHint)

            editor.deleteLater()

        elif col == COL_COLOR:
            color_str = val or ui.Color.Text().name(QtGui.QColor.HexRgb)
            old_color = QtGui.QColor(color_str)

            new_col = QtWidgets.QColorDialog.getColor(
                old_color,
                editor.parentWidget(),
                'Pick Color',
            )

            if new_col.isValid():
                model.setData(index, new_col.name(QtGui.QColor.HexRgb), QtCore.Qt.EditRole)

            self.commitData.emit(editor)
            self.closeEditor.emit(editor, QtWidgets.QAbstractItemDelegate.NoHint)

            editor.deleteLater()

        elif col == COL_EXCLUDED:
            # toggle
            new_val = not bool(val)
            model.setData(index, new_val, QtCore.Qt.EditRole)
            model.setData(index, new_val, QtCore.Qt.DisplayRole)
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
        col = index.column()
        if col in (COL_NAME, COL_DISPLAY_NAME, COL_DESCRIPTION):
            editor.setGeometry(option.rect)
            editor.setStyleSheet(f"height: {option.rect.height()}px;")
        else:
            editor.setGeometry(QtCore.QRect(0, 0, 0, 0))


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

        ui.set_stylesheet(self)

        self._create_ui()
        self._init_model()
        self._init_actions()
        self._connect_signals()

    def _create_ui(self):
        QtWidgets.QVBoxLayout(self)
        self.layout().setContentsMargins(0, 0, 0, 0)
        # Toolbar
        self.toolbar = QtWidgets.QToolBar(self)
        self.toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
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

        self.view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        self.layout().addWidget(self.view)

    def _connect_signals(self):
        pass

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

        self.view.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.view.horizontalHeader().setDefaultSectionSize(ui.Size.RowHeight(1.0))

        self.view.verticalHeader().setVisible(False)

    def _init_actions(self):
        @QtCore.Slot()
        def edit_action():
            self.view.model().add_new()

        action = QtGui.QAction('Add', self)
        action.setShortcut('Ctrl+N')
        action.setStatusTip('Add a new category')
        action.setIcon(ui.get_icon('btn_add'))
        action.triggered.connect(edit_action)
        self.toolbar.addAction(action)
        self.view.addAction(action)

        @QtCore.Slot()
        def remove_action():
            if not self.view.selectionModel().hasSelection():
                logging.warning('No category selected.')
                return

            index = next(iter(self.view.selectionModel().selectedIndexes()), QtCore.QModelIndex())

            if not index.isValid():
                logging.warning('No category selected.')
                return

            self.view.model().removeRow(index.row())

        action = QtGui.QAction('Remove', self)
        action.setShortcut('Delete')
        action.setStatusTip('Remove selected category')
        action.setIcon(ui.get_icon('btn_delete'))
        action.triggered.connect(remove_action)
        self.toolbar.addAction(action)
        self.view.addAction(action)

        # Separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        action.setVisible(True)

        self.toolbar.addAction(action)
        self.view.addAction(action)

        @QtCore.Slot()
        def revert_to_defaults():
            # Confirm first

            res = QtWidgets.QMessageBox.question(
                self,
                'Restore',
                'Are you sure you want to restore the categories from the template?',
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )

            if res != QtWidgets.QMessageBox.Yes:
                return

            if not lib.settings.paths.ledger_template.exists():
                QtWidgets.QMessageBox.warning(
                    self,
                    'Error',
                    'ledger.json.template not found.'
                )
                raise FileNotFoundError('ledger.json.template not found.')

            try:
                lib.settings.revert_section('categories')
            except Exception as e:
                logging.error(f'Failed to restore categories: {e}')
                QtWidgets.QMessageBox.critical(
                    self,
                    'Error',
                    f'Failed to restore categories: {e}'
                )
                return

        action = QtGui.QAction('Revert', self)
        action.setShortcut('Ctrl+Shift+R')
        action.setStatusTip('Restore categories from template')

        action.triggered.connect(revert_to_defaults)
        self.toolbar.addAction(action)
        self.view.addAction(action)

        @QtCore.Slot()
        def reload_from_disk():
            lib.settings.reload_section('categories')

        action = QtGui.QAction('Refresh', self)
        action.setShortcut('Ctrl+R')
        action.setStatusTip('Reload categories from disk')
        action.triggered.connect(reload_from_disk)
        self.toolbar.addAction(action)
        self.view.addAction(action)

        # Separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        action.setVisible(True)
        self.toolbar.addAction(action)
        self.view.addAction(action)

        def exclude_action():
            if not self.view.selectionModel().hasSelection():
                logging.warning('No category selected.')
                return

            index = next(iter(self.view.selectionModel().selectedIndexes()), QtCore.QModelIndex())

            if not index.isValid():
                logging.warning('No category selected.')
                return

            index = index.sibling(index.row(), COL_EXCLUDED)

            model = self.view.model()
            model.setData(index, not model.data(index, QtCore.Qt.EditRole), QtCore.Qt.EditRole)

        action = QtGui.QAction('Exclude', self)
        action.setShortcut('Ctrl+E')
        action.setStatusTip('Exclude selected category')
        action.setIcon(ui.get_icon('btn_remove'))
        action.triggered.connect(exclude_action)

        self.toolbar.addAction(action)
        self.view.addAction(action)
