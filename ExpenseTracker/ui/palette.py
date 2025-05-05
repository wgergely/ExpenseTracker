# via https://www.learnui.design/tools/data-color-picker.html#palette
import functools
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from . import ui
from ..settings.lib import category_manager
from .actions import signals

DEFAULT_ICON = 'cat_unclassified'

PALETTES = {
    'palette1': [
        '#005983',
        '#4d60a1',
        '#935fac',
        '#d1599e',
        '#fe5e7b',
        '#ff7a4c',
        '#ffa600'
    ],
    'palette2': [
        '#c2a957',
        '#d99143',
        '#ee7347',
        '#fd4b5f',
        '#fd0f86',
        '#e300b8',
        '#a136ee'
    ],
    'palette3': [
        '#7b8845',
        '#a7a563',
        '#d3c385',
        '#ffe3aa',
        '#f9ae79',
        '#ef7363',
        '#d92b67'
    ]
}
ICON_PICKER_COLUMNS = 3


@functools.lru_cache(maxsize=128)
def get_all_icons():
    from ..settings import lib

    v = []
    if lib.settings.icon_dir.exists():
        for p in sorted(lib.settings.icon_dir.glob('cat_*.png')):
            v.append(p.stem)
    return v


class PaletteModel(QtCore.QAbstractTableModel):
    """Model for the color palette."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.palettes = PALETTES
        self.palette_names = list(self.palettes.keys())
        self.max_colors = max(len(palette) for palette in self.palettes.values())

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return self.max_colors

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.palettes)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        """Get data for the given model index and role."""
        if not index.isValid():
            return None

        row = index.row()
        column = index.column()

        palette_name = self.palette_names[column]
        palette = self.palettes[palette_name]

        if row >= len(palette):
            return None

        color = palette[row]

        if role == QtCore.Qt.DisplayRole:
            return f'{palette_name}\n{color}'
        elif role == QtCore.Qt.BackgroundRole:
            return QtGui.QColor(color)
        elif role == QtCore.Qt.ForegroundRole:
            # Determine text color based on background brightness
            qcolor = QtGui.QColor(color)
            brightness = (qcolor.red() * 299 + qcolor.green() * 587 + qcolor.blue() * 114) / 1000
            return QtGui.QColor(QtCore.Qt.black if brightness > 128 else QtCore.Qt.white)
        elif role == QtCore.Qt.TextAlignmentRole:
            return QtCore.Qt.AlignCenter
        elif role == QtCore.Qt.SizeHintRole:
            return QtCore.QSize(ui.Size.RowHeight(2.0), ui.Size.RowHeight(2.0))

        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = QtCore.Qt.DisplayRole) -> Any:
        if role == QtCore.Qt.DisplayRole:
            if orientation == QtCore.Qt.Horizontal:
                return self.palette_names[section]
        return None


class PaletteItemDelegate(QtWidgets.QStyledItemDelegate):
    """Custom item delegate for palette items."""

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex) -> None:
        """Paint the color square with a border."""
        if not index.isValid():
            return

        color = index.data(QtCore.Qt.BackgroundRole)
        if not color:
            return

        # Draw color square with padding
        rect = option.rect

        hover = option.state & QtWidgets.QStyle.State_MouseOver
        selected = option.state & QtWidgets.QStyle.State_Selected
        active = option.state & QtWidgets.QStyle.State_Active

        if hover or selected:
            _o = ui.Size.Indicator(0.5)
            rect = rect.adjusted(_o, _o, -_o, -_o)
        else:
            _o = ui.Size.Indicator(1.0)
            rect = option.rect.adjusted(_o, _o, -_o, -_o)

        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        painter.save()
        if selected:
            pen = QtGui.QPen(index.data(QtCore.Qt.ForegroundRole))
            pen.setWidthF(ui.Size.Separator(2.0))
            painter.setPen(pen)
        else:
            painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(color)
        o = ui.Size.Indicator(1.0)
        painter.drawRoundedRect(rect, o, o)

        if hover or selected:
            painter.setPen(index.data(QtCore.Qt.ForegroundRole))
            text = index.data(QtCore.Qt.DisplayRole)
            if text:
                painter.drawText(rect, QtCore.Qt.AlignCenter, text)
        painter.restore()
        return


class PaletteView(QtWidgets.QTableView):
    """Table view for the color palette."""

    colorSelected = QtCore.Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName('ExpenseTrackerPaletteView')
        self.setProperty('rounded', True)

        self.setModel(PaletteModel(self))
        self.setItemDelegate(PaletteItemDelegate())

        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        self.setShowGrid(False)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setSortingEnabled(False)
        self.setAlternatingRowColors(False)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setFocusPolicy(QtCore.Qt.NoFocus)

        cell_size = ui.Size.RowHeight(2.0)
        self.horizontalHeader().setDefaultSectionSize(cell_size)
        self.verticalHeader().setDefaultSectionSize(cell_size)

        self.horizontalHeader().setVisible(False)
        self.verticalHeader().setVisible(False)

        padding = ui.Size.Indicator(2.0)
        nc = self.model().columnCount()
        nr = self.model().rowCount()
        self.setFixedSize(
            (nc * cell_size) + (self.frameWidth() * 2) + (padding * 2),
            (nr * cell_size) + (self.frameWidth() * 2) + (padding * 2)
        )

        self.clicked.connect(self.item_clicked)

    @QtCore.Slot(QtCore.QModelIndex)
    def item_clicked(self, index: QtCore.QModelIndex) -> None:
        """Handle item click to emit the selected color."""
        if index.isValid():
            row = index.row()
            column = index.column()
            palette_name = list(PALETTES.keys())[column]
            palette = PALETTES[palette_name]

            if row < len(palette):
                color = palette[row]
                self.colorSelected.emit(color)


class IconModel(QtCore.QAbstractTableModel):
    """Model for the icon picker grid with fixed columns and max rows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.icons = get_all_icons()
        self.columns = len(PALETTES)
        self.max_rows = max(len(palette) for palette in PALETTES.values())
        self.total_rows = (len(self.icons) + self.columns - 1) // self.columns

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return self.total_rows

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return self.columns

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        idx = index.row() * self.columns + index.column()
        if idx < 0 or idx >= len(self.icons):
            return None
        name = self.icons[idx]
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.UserRole):
            return name
        if role == QtCore.Qt.BackgroundRole:
            return ui.Color.Background()
        if role == QtCore.Qt.ForegroundRole:
            return ui.Color.Text()
        if role == QtCore.Qt.TextAlignmentRole:
            return QtCore.Qt.AlignCenter
        if role == QtCore.Qt.SizeHintRole:
            size = ui.Size.RowHeight(2.0)
            return QtCore.QSize(size, size)
        return None


class IconItemDelegate(QtWidgets.QStyledItemDelegate):
    """Custom delegate for painting icon items with background."""

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex) -> None:
        if not index.isValid():
            return
        color = index.data(QtCore.Qt.BackgroundRole)
        if not color:
            return
        rect = option.rect
        hover = option.state & QtWidgets.QStyle.State_MouseOver
        selected = option.state & QtWidgets.QStyle.State_Selected
        off = ui.Size.Indicator(0.5) if (hover or selected) else ui.Size.Indicator(1.0)
        rect_bg = rect.adjusted(off, off, -off, -off)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.save()
        if selected:
            pen = QtGui.QPen(index.data(QtCore.Qt.ForegroundRole))
            pen.setWidthF(ui.Size.Separator(2.0))
            painter.setPen(pen)
        else:
            painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(color)
        radius = ui.Size.Indicator(1.0)
        painter.drawRoundedRect(rect_bg, radius, radius)
        painter.restore()
        name = index.data(QtCore.Qt.UserRole)
        if not name:
            return
        ico_size = ui.Size.Margin(2.0)
        rect_icon = QtCore.QRect(0, 0, ico_size, ico_size)
        rect_icon.moveCenter(option.rect.center())
        ico = ui.get_icon(name, ui.Color.Text())
        ico.paint(painter, rect_icon, QtCore.Qt.AlignCenter)


class IconPickerView(QtWidgets.QTableView):
    """Table view for the icon picker grid."""
    iconSelected = QtCore.Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName('ExpenseTrackerIconPickerView')
        self.setProperty('rounded', True)

        self.setModel(IconModel(parent=self))
        self.setItemDelegate(IconItemDelegate(parent=self))

        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        self.setShowGrid(False)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setSortingEnabled(False)
        self.setAlternatingRowColors(False)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setFocusPolicy(QtCore.Qt.NoFocus)

        cell = ui.Size.RowHeight(2.0)
        self.horizontalHeader().setDefaultSectionSize(cell)
        self.verticalHeader().setDefaultSectionSize(cell)

        self.horizontalHeader().setVisible(False)
        self.verticalHeader().setVisible(False)

        padding = ui.Size.Indicator(2.0)
        frame = self.frameWidth()
        nc = self.model().columnCount()
        nr = self.model().max_rows
        scrollbar_width = ui.Size.Margin(1.0)
        width = (nc * cell) + (frame * 2) + (padding * 2) + scrollbar_width
        height = (nr * cell) + (frame * 2) + (padding * 2)

        self.setFixedSize(width, height)

        self.clicked.connect(self.item_clicked)

    @QtCore.Slot(QtCore.QModelIndex)
    def item_clicked(self, index: QtCore.QModelIndex) -> None:
        if index.isValid():
            name = index.data(QtCore.Qt.UserRole)
            self.iconSelected.emit(name)


# Widget to preview a category's color and icon
class CategoryPreview(QtWidgets.QWidget):
    """Widget to preview background color and icon."""

    def __init__(self, icon: str, color: str, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._color = color

        padding = ui.Size.Indicator(2.0)
        cell_size = ui.Size.RowHeight(2.0)
        frame_width = ui.Size.Separator(2.0)
        nc = 3
        nr = max(len(palette) for palette in PALETTES.values())
        self.setFixedSize(
            (nc * cell_size) + (frame_width * 2) + (padding * 2),
            (nr * cell_size) + (frame_width * 2) + (padding * 2)
        )


    def set_color(self, color: str):
        self._color = color
        self.update()

    def set_icon(self, icon: str):
        self._icon = icon
        self.update()

    def paintEvent(self, event) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        icon = ui.get_icon(self._icon, QtGui.QColor(self._color), engine=ui.CategoryIconEngine)

        rect = self.rect()
        o = ui.Size.Indicator(2.0)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(ui.Color.DarkBackground())
        painter.drawRoundedRect(
            rect, o, o,
        )

        side = min(self.width(), self.height())

        icon_rect = QtCore.QRect(0, 0, int(side), int(side))
        icon_rect.moveCenter(self.rect().center())

        icon.paint(painter, icon_rect, QtCore.Qt.AlignCenter)


# Dialog combining color palette and icon picker for category editing
class CategoryIconColorEditorDialog(QtWidgets.QDialog):
    """Dialog to edit icon and color for a specific category."""
    iconChanged = QtCore.Signal(str)
    colorChanged = QtCore.Signal(str)

    def __init__(self, category_name: str, parent=None):
        super().__init__(parent)
        self.category = category_name
        self.setWindowTitle(f'Edit Category: {category_name}')

        self.preview = None
        self.palette_view = None
        self.icon_picker = None

        self._create_ui()
        self._connect_signals()
        self._init_actions()

    def _create_ui(self):
        QtWidgets.QVBoxLayout(self)

        # Title layout
        title_layout = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel(self.category.title(), self)
        label.setProperty('rounded', True)
        label.setProperty('h1', True)
        title_layout.addWidget(label, 1)
        self.layout().addLayout(title_layout)

        # editor layout
        editor_layout = QtWidgets.QHBoxLayout()
        self.layout().addLayout(editor_layout)

        from ..settings import lib
        categories = lib.settings.get_section('categories')
        cat = categories.get(self.category, {})
        init_icon = cat.get('icon', DEFAULT_ICON)
        init_color = cat.get('color', ui.Color.Text().name(QtGui.QColor.HexRgb))
        self.preview = CategoryPreview(init_icon, init_color, self)
        editor_layout.addWidget(self.preview)

        self.palette_view = PaletteView(self)
        editor_layout.addWidget(self.palette_view)

        self.icon_picker = IconPickerView(self)
        editor_layout.addWidget(self.icon_picker)

        # Button layout
        btn_layout = QtWidgets.QHBoxLayout()
        self.layout().addLayout(btn_layout)

        done_btn = QtWidgets.QPushButton('Done', self)
        done_btn.clicked.connect(self.accept)
        btn_layout.addWidget(done_btn, 1)

    def _connect_signals(self):
        self.palette_view.colorSelected.connect(self.color_selected)
        self.colorChanged.connect(self.preview.set_color)
        self.icon_picker.iconSelected.connect(self.icon_selected)
        self.iconChanged.connect(self.preview.set_icon)

    @QtCore.Slot(str)
    def color_selected(self, new_color: str):
        # Delegate to CategoryManager
        try:
            category_manager.update_palette(self.category, color=new_color)
            self.colorChanged.emit(new_color)
        except Exception as e:
            logging.error(f'Failed to update category color: {e}')

    @QtCore.Slot(str)
    def icon_selected(self, new_icon: str):
        # Delegate to CategoryManager
        try:
            category_manager.update_palette(self.category, icon=new_icon)
            self.iconChanged.emit(new_icon)
        except Exception as e:
            logging.error(f'Failed to update category icon: {e}')

    def _init_actions(self):
        pass

    def open(self) -> None:
        """Override to prevent showing for invalid categories."""
        from ..settings import lib
        cats = lib.settings.get_section('categories')
        if self.category not in cats:
            return
        super().open()
