"""Expense view and delegates for rendering expense summaries.

This module provides:
    - IconColumnDelegate and WeightColumnDelegate for custom cell rendering
    - ExpenseView for displaying expense data as a Qt table with interactive actions
    - Context menu actions for filtering, sorting, and refreshing expense data
"""
import logging
from copy import deepcopy
from typing import Optional

from PySide6 import QtWidgets, QtGui, QtCore

from ..model.expense import ExpenseModel, ExpenseSortFilterProxyModel, WeightRole, Columns, CategoryRole, \
    TransactionsRole
from ...settings import lib
from ...ui import ui
from ...ui.actions import signals
from ...ui.dockable_widget import DockableWidget


class IconColumnDelegate(QtWidgets.QStyledItemDelegate):
    """Delegate to draw category icons in the icon column."""

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem,
              index: QtCore.QModelIndex) -> None:

        if index.column() != Columns.Icon or index.row() == index.model().rowCount() - 1:
            return

        icon = index.data(QtCore.Qt.DecorationRole)
        if not icon:
            return

        center = option.rect.center()
        rect = QtCore.QRect(
            0, 0,
            ui.Size.Margin(1.5),
            ui.Size.Margin(1.5)
        )
        rect.moveCenter(center)

        painter.setOpacity(self.parent().weight_anim_value)

        icon.paint(painter, rect, QtCore.Qt.AlignCenter)

    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                     index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        # Placeholder editor to launch the category icon/color dialog
        editor = QtWidgets.QWidget(parent)
        editor.setAttribute(QtCore.Qt.WA_NoSystemBackground)
        editor.setAttribute(QtCore.Qt.WA_OpaquePaintEvent)
        editor.setAttribute(QtCore.Qt.WA_NoChildEventsForParent)
        editor.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        editor.setFocusPolicy(QtCore.Qt.NoFocus)
        return editor

    def setEditorData(self, editor: QtWidgets.QWidget, index: QtCore.QModelIndex) -> None:
        # Launch the unified icon/color editor for valid categories
        category = index.data(CategoryRole)
        from ...ui.palette import CategoryIconColorEditorDialog
        dlg = CategoryIconColorEditorDialog(category, editor.parentWidget())
        # live updates: repaint the view on changes
        # connect live-update to the table view's viewport
        view = self.parent()
        dlg.iconChanged.connect(view.viewport().update)
        dlg.colorChanged.connect(view.viewport().update)
        dlg.open()
        # Commit and close the placeholder editor
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QtWidgets.QAbstractItemDelegate.NoHint)
        editor.deleteLater()


class WeightColumnDelegate(QtWidgets.QStyledItemDelegate):
    """Delegate to draw a bar chart in the weight column."""

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem,
              index: QtCore.QModelIndex) -> None:
        super().paint(painter, option, index)

        if index.column() != Columns.Weight or index.row() == index.model().rowCount() - 1:
            return

        selected = option.state & QtWidgets.QStyle.State_Selected
        hover = option.state & QtWidgets.QStyle.State_MouseOver

        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

        rect = QtCore.QRectF(option.rect)
        offset = ui.Size.Indicator(0.8)
        rect = rect.adjusted(offset, offset, -offset, -offset)
        center = rect.center()

        rect.setHeight(ui.Size.Margin(0.6) if (selected or hover) else ui.Size.Margin(0.5))
        rect.moveCenter(center)

        gradient = QtGui.QLinearGradient(rect.topLeft(), rect.topRight())
        gradient.setColorAt(0.3, ui.Color.Green())
        gradient.setColorAt(0.8, ui.Color.Yellow())
        gradient.setColorAt(1.0, ui.Color.Red())

        weight = index.data(WeightRole)
        weight *= self.parent().weight_anim_value

        width = float(rect.width()) * weight
        width = max(width, ui.Size.Separator(1.0)) if weight > 0.0 else width
        rect.setWidth(width)

        painter.setBrush(gradient)
        painter.setPen(QtCore.Qt.NoPen)

        o = ui.Size.Separator(5.0) if (hover or selected) else ui.Size.Separator(3.0)

        painter.setOpacity(self.parent().weight_anim_value)
        painter.drawRoundedRect(rect, o, o)


class ExpenseView(QtWidgets.QTableView):
    """Table view for displaying expense summaries with interactive controls."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent=parent)
        self.setObjectName('ExpenseTrackerExpenseView')
        self.horizontalHeader().hide()
        self.verticalHeader().hide()

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum,
            QtWidgets.QSizePolicy.Minimum
        )

        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.setWordWrap(True)
        self.setTextElideMode(QtCore.Qt.ElideRight)

        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        self.viewport().setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.viewport().setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        config = lib.settings.get_section('categories') or {}
        self._saved_category = next(iter(config.keys()), '')

        self.weight_anim_value = 0.0

        self._weight_anim = QtCore.QVariantAnimation(self)
        self._weight_anim.setDuration(400)
        self._weight_anim.setStartValue(0.0)
        self._weight_anim.setEndValue(1.0)
        self._weight_anim.setEasingCurve(QtCore.QEasingCurve.OutQuad)
        self._weight_anim.setLoopCount(1)
        self._weight_anim.setDirection(QtCore.QAbstractAnimation.Forward)
        self._weight_anim.finished.connect(self._weight_anim.stop)

        self._init_delegates()
        self._init_model()
        self._init_actions()
        self._connect_signals()

    def _init_model(self) -> None:
        model = ExpenseModel(parent=self)
        proxy = ExpenseSortFilterProxyModel(parent=self)
        proxy.setSourceModel(model)

        self.setModel(proxy)
        self._init_section_sizing()

    def _init_delegates(self) -> None:
        self.setItemDelegateForColumn(Columns.Icon.value, IconColumnDelegate(self))
        self.setItemDelegateForColumn(Columns.Weight.value, WeightColumnDelegate(self))

    def _init_actions(self) -> None:
        action = QtGui.QAction('', self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.addAction(action)

        @QtCore.Slot()
        def exclude_category() -> None:
            index = self.selectionModel().currentIndex()
            if not index.isValid():
                logging.debug('No valid index')
                return

            config = lib.settings.get_section('categories')
            if not config:
                raise RuntimeError('Invalid configuration')

            category = index.data(CategoryRole)
            if not category:
                logging.debug('No category selected')
                return

            config[category]['excluded'] = True
            lib.settings.set_section('categories', config)

        action = QtGui.QAction('Exclude Category', self)
        action.setShortcuts(['Ctrl+E', 'delete'])
        action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
        action.setIcon(ui.get_icon('btn_exclude'))
        action.triggered.connect(exclude_category)
        self.addAction(action)

        @QtCore.Slot()
        def show_all_categories() -> None:
            config = lib.settings.get_section('categories')
            if not config:
                raise RuntimeError('Invalid configuration')

            for category in config.keys():
                config[category]['excluded'] = False
            lib.settings.set_section('categories', config)

        action = QtGui.QAction('Show All Categories', self)
        action.setShortcuts(['Ctrl+Shift+E'])
        action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
        action.setIcon(ui.get_icon('btn_show_all'))
        action.triggered.connect(show_all_categories)
        self.addAction(action)

        # separator
        action = QtGui.QAction('', self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.addAction(action)

        action_group = QtGui.QActionGroup(self)
        action_group.setExclusive(False)

        action = QtGui.QAction('Show Icons', self)
        action.setCheckable(True)
        action.setChecked(True)
        action.setShortcut('Alt+I')
        action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
        action.toggled.connect(lambda v: self.setColumnHidden(Columns.Icon.value, not v))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Show Category', self)
        action.setCheckable(True)
        action.setChecked(True)
        action.setShortcut('Alt+C')
        action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
        action.toggled.connect(lambda v: self.setColumnHidden(Columns.Category.value, not v))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Show Graph', self)  # weights
        action.setCheckable(True)
        action.setChecked(True)
        action.setShortcut('Alt+G')
        action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
        action.toggled.connect(lambda v: self.setColumnHidden(Columns.Weight.value, not v))
        action.toggled.connect(
            lambda v:
            self.horizontalHeader().setSectionResizeMode(Columns.Amount.value,
                                                         QtWidgets.QHeaderView.ResizeToContents) if v else
            self.horizontalHeader().setSectionResizeMode(Columns.Amount.value, QtWidgets.QHeaderView.Stretch)
        )
        action_group.addAction(action)
        self.addAction(action)

        # separator before sort actions
        action = QtGui.QAction('', self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.addAction(action)

        # sort column actions (exclusive)
        action_group = QtGui.QActionGroup(self)
        action_group.setExclusive(True)

        # Custom order (config-defined) - default
        action = QtGui.QAction('Sort by Custom Order', self)
        action.setCheckable(True)
        action.setChecked(True)
        action.setStatusTip('Sort by custom order defined in configuration')
        action.toggled.connect(lambda checked: self.model().sort(-1))
        action_group.addAction(action)
        self.addAction(action)

        # Alphabetical by Category
        action = QtGui.QAction('Sort by Category', self)
        action.setCheckable(True)
        action.setChecked(False)
        action.setStatusTip('Sort categories alphabetically')
        action.toggled.connect(lambda checked: self.model().sort(Columns.Category.value))
        action_group.addAction(action)
        self.addAction(action)

        # By Amount
        action = QtGui.QAction('Sort by Amount', self)
        action.setCheckable(True)
        action.setChecked(False)
        action.setStatusTip('Sort categories by total amount')
        action.toggled.connect(lambda checked: self.model().sort(Columns.Amount.value))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('', self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.addAction(action)

        action = QtGui.QAction('Refresh Data...', self)
        action.setShortcut('Ctrl+R')
        action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
        action.setIcon(ui.get_icon('btn_fetch', color=ui.Color.Green))
        action.triggered.connect(signals.dataFetchRequested)
        self.addAction(action)

        action = QtGui.QAction('Reload', self)
        action.setShortcut('Ctrl+Shift+R')
        action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
        action.setIcon(ui.get_icon('btn_reload'))
        action.triggered.connect(self.model().sourceModel().init_data)
        self.addAction(action)

        action = QtGui.QAction('', self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.addAction(action)

        action = QtGui.QAction('Open Settings...', self)
        action.setShortcuts(['Ctrl+,', 'Ctrl+.', 'Ctrl+P'])
        action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
        action.setIcon(ui.get_icon('btn_settings'))
        action.triggered.connect(signals.showSettings)
        self.addAction(action)

    def _connect_signals(self) -> None:
        self.activated.connect(signals.openTransactions)

        self.model().sourceModel().modelAboutToBeReset.connect(self.save_category_selection)
        self.model().sourceModel().modelReset.connect(
            lambda: QtCore.QTimer.singleShot(10, self.restore_category_selection))

        self.model().sourceModel().modelReset.connect(self.resizeColumnsToContents)
        self.model().sourceModel().modelReset.connect(self._weight_anim.start)

        @QtCore.Slot(float)
        def on_anim_value_chaged(value):
            self.weight_anim_value = value
            self.viewport().update()

        self._weight_anim.valueChanged.connect(on_anim_value_chaged)

        # emit transaction and category changes on user selection
        self.selectionModel().selectionChanged.connect(self.emit_category_selection_changed)

        # respond to external category selection requests (e.g. from charts)
        @QtCore.Slot(str)
        def _on_external_category_requested(category: str) -> None:
            if not category or category == self._saved_category:
                return
            indexes = [self.model().index(i, Columns.Category.value) for i in range(self.model().rowCount())]
            if category not in [i.data(CategoryRole) for i in indexes]:
                return

            self._saved_category = category
            QtCore.QTimer.singleShot(0, self.restore_category_selection)

        signals.categoryUpdateRequested.connect(_on_external_category_requested)
        signals.categoryPaletteChanged.connect(self.viewport().update)

        @QtCore.Slot(str, object)
        def _on_metadata_changed(key: str, value: object) -> None:
            """Repaint and resize amount column when locale changes."""
            if key != 'locale':
                return
            # Adjust amount column width to fit new locale formatting
            self.resizeColumnToContents(Columns.Amount.value)
            self.viewport().update()

        signals.metadataChanged.connect(_on_metadata_changed)

    @QtCore.Slot()
    def emit_category_selection_changed(self) -> None:
        """Emit signals for the selected category's transactions and key."""
        sel = self.selectionModel()
        if not sel.hasSelection():
            logging.debug('No selection')
            signals.transactionsChanged.emit([])
            signals.categoryChanged.emit('')
            return

        index = next(iter(sel.selectedIndexes()), QtCore.QModelIndex())
        if not index.isValid():
            logging.debug('No valid index')
            signals.transactionsChanged.emit([])
            signals.categoryChanged.emit('')
            return

        v = index.data(TransactionsRole) or []
        v = deepcopy(v)
        logging.debug('Category selection changed')
        signals.transactionsChanged.emit(v)
        category = index.data(CategoryRole) or ''
        logging.debug(f'Category selected: {category}')
        signals.categoryChanged.emit(category)

    @QtCore.Slot()
    def save_category_selection(self) -> None:
        """Save the selected category before the model is reset."""
        logging.debug('Saving category selection')

        sel = self.selectionModel()
        if not sel.hasSelection():
            return

        index = next(iter(sel.selectedIndexes()), QtCore.QModelIndex())
        if not index.isValid():
            return

        self._saved_category = index.data(CategoryRole)

    @QtCore.Slot()
    def restore_category_selection(self) -> None:
        """Restore the selected category after the model has been reset."""

        proxy = self.model()
        col = Columns.Category.value
        sel = self.selectionModel()

        for row in range(proxy.rowCount()):
            index = proxy.index(row, 0)
            index = index.sibling(row, col)
            if index.data(CategoryRole) == self._saved_category:
                logging.debug(f'Restoring category selection: {self._saved_category}')
                sel.clearSelection()
                sel.select(index,
                           QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
                sel.setCurrentIndex(index, QtCore.QItemSelectionModel.NoUpdate)
                break

        self.emit_category_selection_changed()

    def _init_section_sizing(self) -> None:
        header = self.horizontalHeader()
        header.setSectionResizeMode(Columns.Icon.value, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(Columns.Category.value, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(Columns.Weight.value, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(Columns.Amount.value, QtWidgets.QHeaderView.Interactive)
        header = self.verticalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        header.setDefaultSectionSize(ui.Size.RowHeight(1.4))


class ExpenseDockWidget(DockableWidget):
    """Dockable widget for displaying the expense view. Not closeable."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__('Expenses', parent=parent, closable=False)

        self.setObjectName('ExpenseTrackerExpenseDockWidget')
        view = ExpenseView(self)
        view.setObjectName('ExpenseTrackerExpenseView')
        self.setWidget(view)
