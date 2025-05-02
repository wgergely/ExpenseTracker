"""Category editor: UI for editing expense categories in ledger.json.

Provides:
    - IconPickerDialog: dialog for selecting category icons
    - CategoriesModel: table model for editing category properties (name, display name, icon, color, excluded)
"""
import logging

from PySide6 import QtCore, QtGui, QtWidgets

from .. import lib
from ...ui import ui
from ...ui.actions import signals
from ...ui.palette import CategoryIconColorEditorDialog, DEFAULT_ICON

COL_ICON = 0
COL_NAME = 1
COL_DISPLAY_NAME = 2
COL_DESCRIPTION = 3
COL_EXCLUDED = 4


class CategoriesModel(QtCore.QAbstractTableModel):
    """Model responsible representing, editing and saving category items.

    """
    HEADERS = {
        COL_ICON: '',
        COL_NAME: 'Spreadsheet Name',
        COL_DISPLAY_NAME: 'Display Name',
        COL_DESCRIPTION: 'Description',
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
        self._categories.clear()
        try:
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
        return 5 if not parent.isValid() else 0

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
                return cat.get('icon', DEFAULT_ICON)
            elif col == COL_EXCLUDED:
                return cat['excluded']

        if role == QtCore.Qt.FontRole:
            if col == COL_NAME:
                font, _ = ui.Font.BoldFont(ui.Size.MediumText(1.0))
            elif col == COL_DISPLAY_NAME:
                font, _ = ui.Font.BoldFont(ui.Size.MediumText(1.0))
            else:
                font, _ = ui.Font.MediumFont(ui.Size.MediumText(1.0))
            return font
        if role == QtCore.Qt.TextAlignmentRole:
            if col in (COL_NAME, COL_DISPLAY_NAME):
                return QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
            elif col == COL_DESCRIPTION:
                return QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter
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
        elif col == COL_EXCLUDED:
            cat['excluded'] = bool(value)
        else:
            return False

        # block reload signal
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

        hover = option.state & QtWidgets.QStyle.State_MouseOver
        selected = option.state & QtWidgets.QStyle.State_Selected
        if hover or selected:
            painter.setBrush(ui.Color.Background())
        else:
            painter.setBrush(ui.Color.VeryDarkBackground())
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(option.rect)

        col = index.column()
        # Render text columns normally
        if col in (COL_NAME, COL_DISPLAY_NAME, COL_DESCRIPTION):
            super().paint(painter, option, index)
            return

        # ICON column: draw tinted icon and label
        if col == COL_ICON:
            # retrieve category info from model
            model = index.model()
            try:
                cat = model._categories[index.row()]
                icon_name = cat.get('icon', DEFAULT_ICON)
                color_str = cat.get('color', ui.Color.Text().name(QtGui.QColor.HexRgb))
                display_name = cat.get('display_name') or cat.get('name')
            except Exception:
                icon_name = index.data(QtCore.Qt.DisplayRole) or DEFAULT_ICON
                color_str = ui.Color.Text().name(QtGui.QColor.HexRgb)
                display_name = icon_name

            # tinted icon
            color = QtGui.QColor(color_str)
            icon = ui.get_icon(icon_name, color, engine=ui.CategoryIconEngine)

            rect = option.rect
            edge = min(rect.width(), rect.height())
            rect = QtCore.QRect(
                0, 0,
                edge, edge
            )

            o = ui.Size.Indicator(1.5)
            rect = rect.adjusted(o, o, -o, -o)
            rect.moveCenter(option.rect.center())

            icon.paint(painter, rect, QtCore.Qt.AlignCenter)
            return

        # EXCLUDED column: draw checkmark
        if col == COL_EXCLUDED:
            is_excl = bool(index.data(QtCore.Qt.DisplayRole))
            if is_excl:
                icon = ui.get_icon('btn_remove', ui.Color.Red())
            else:
                icon = ui.get_icon('btn_ok', ui.Color.Green())
            rect = option.rect
            edge = min(rect.width(), rect.height())
            rect = QtCore.QRect(
                0, 0,
                edge, edge
            )
            o = ui.Size.Indicator(1.5)
            rect = rect.adjusted(o, o, -o, -o)
            rect.moveCenter(option.rect.center())
            icon.paint(painter, rect, QtCore.Qt.AlignCenter)

    def createEditor(self, parent, option, index):
        col = index.column()
        if col in (COL_NAME, COL_DISPLAY_NAME, COL_DESCRIPTION):
            e = QtWidgets.QLineEdit(parent=parent)
            return e
        else:
            # placeholder widget for popups
            e = QtWidgets.QWidget(parent=parent)
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

        # For icon column, open unified editor dialog
        elif col == COL_ICON:
            # Obtain the raw category key and open the unified editor
            cat_index = index.sibling(index.row(), COL_NAME)
            category = cat_index.data(QtCore.Qt.EditRole)
            dlg = CategoryIconColorEditorDialog(category, editor.parentWidget())
            # live updates: repaint table view on changes
            view = self.parent()
            dlg.iconChanged.connect(view.viewport().update)
            dlg.colorChanged.connect(view.viewport().update)
            dlg.open()
            # close placeholder editor
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
            editor.setStyleSheet(f'height: {option.rect.height()}px;')
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

        self.setMinimumHeight(ui.Size.RowHeight(1.0) * 15)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.Maximum
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
        self.toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.toolbar.setMovable(False)
        self.toolbar.setFixedHeight(ui.Size.RowHeight(1.0))
        self.layout().addWidget(self.toolbar, 1)

        # Table
        from .views import TableView
        self.view = TableView(self)
        # set delegate with view as parent for live updates
        self.view.setItemDelegate(CategoryItemDelegate(self.view))
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
        self.view.horizontalHeader().setSectionResizeMode(COL_EXCLUDED, QtWidgets.QHeaderView.Fixed)

        self.view.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.view.horizontalHeader().setDefaultSectionSize(ui.Size.RowHeight(1.0))

        self.view.verticalHeader().setVisible(False)

    def _init_actions(self):
        def sync_action():
            from ...core import service
            categories = service.fetch_categories()
            if categories:
                msg = (f'Found {len(categories)} categories in the remote spreadsheet.\n\n'
                       'Do you want to replace and override the current definition? '
                       'This action cannot be undone.')

                res = QtWidgets.QMessageBox.question(
                    self,
                    'Sync Categories',
                    msg,
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
                )
                if res == QtWidgets.QMessageBox.No:
                    return

                data = {}
                default_category_item = {
                    'display_name': '',
                    'color': ui.Color.Blue().name(QtGui.QColor.HexRgb),
                    'description': '',
                    'icon': 'cat_unclassified',
                    'excluded': False
                }
                for cat in categories:
                    data[cat] = default_category_item.copy()
                if not categories:
                    return
                lib.settings.set_section('categories', data)

        action = QtGui.QAction('Sync', self)
        action.setShortcut('Ctrl+S')
        action.setStatusTip('Sync categories from the remote spreadsheet')
        action.triggered.connect(sync_action)
        action.setIcon(ui.get_icon('btn_sync'))
        self.toolbar.addAction(action)
        self.view.addAction(action)

        # separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.toolbar.addAction(action)
        self.view.addAction(action)

        @QtCore.Slot()
        def add_action():
            self.view.model().add_new()

        action = QtGui.QAction('Add', self)

        action.setShortcut('Ctrl+N')
        action.setStatusTip('Add a new category')
        action.setIcon(ui.get_icon('btn_add'))
        action.triggered.connect(add_action)
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

            if not lib.settings.ledger_template.exists():
                logging.warning('ledger.json.template not found.')
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
