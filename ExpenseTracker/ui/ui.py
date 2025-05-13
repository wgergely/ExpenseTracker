"""UI styling and asset utilities for ExpenseTracker.

This module provides:
    - Font and FontDatabase: custom font loading and sizing
    - Theme: supported UI themes (light, dark)
    - Size: standardized size constants and scaling logic
    - Color: standardized color palette for widgets and themes
    - Icon asset management and retrieval functions
"""
import enum
import logging
import math
import os
import re
from typing import Union, Optional

from PySide6 import QtWidgets, QtGui, QtCore

icons = []


class Font(enum.Enum):
    """Enumeration of font names."""

    BlackFont = 'Inter Black'
    BoldFont = 'Inter SemiBold'
    MediumFont = 'Inter'
    LightFont = 'Inter Medium'
    ThinFont = 'Inter Light'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db = None

    def __call__(self, size):
        """
        Returns a QFont object for the given size and this font enum.

        Args:
            size (float|int): The desired font size.

        Returns:
            QFont: The font object.
        """
        if self.db is None:
            self.db = FontDatabase()
        return self.db.get(size, self)


class FontDatabase:
    """Custom font database used to load and provide the fonts needed by Bookmarks without instantiating QFontDatabase."""

    def __init__(self):
        if not QtWidgets.QApplication.instance():
            msg = 'FontDatabase must be created after a QApplication is initiated.'
            logging.error(msg)
            raise RuntimeError(msg)

        self._family = None
        self.font_cache = {role: {} for role in Font}
        self.metrics_cache = {role: {} for role in Font}

        self._init_custom_fonts()

    @property
    def family(self):
        """Return the font family used by Bookmarks."""
        if self._family is None:
            raise RuntimeError('Font family not initialized!')
        return self._family

    def _init_custom_fonts(self):
        """Load the fonts used by Bookmarks into the font database."""
        from ..settings import lib
        if not lib.settings.font_path.is_file():
            raise FileNotFoundError(f'Font file not found: {lib.settings.font_path}')
        # Add custom font file to application font database
        idx = QtGui.QFontDatabase.addApplicationFont(str(lib.settings.font_path))
        if idx < 0:
            raise RuntimeError(f'Could not load font file: {lib.settings.font_path}')
        # Retrieve the loaded font family
        family = QtGui.QFontDatabase.applicationFontFamilies(idx)
        if not family:
            raise RuntimeError(f'Could not find font family in file: {lib.settings.font_path} ({idx})')

        self._family = family[0]

    def get(self, size, role):
        """Retrieve the font and metrics for the given font size and role.

        Args:
            size (float): The font size.
            role (Font): The font role.

        Returns:
            tuple: (QFont, QFontMetricsF)
        """
        # Validate role
        if not isinstance(role, Font):
            raise ValueError(f'Invalid font role: {role}. Must be a member of Font.')

        # Validate size
        if size <= 0:
            raise RuntimeError(f'Font size must be greater than 0, got {size}')

        # Check cache
        if size in self.font_cache[role] and size in self.metrics_cache[role]:
            return (QtGui.QFont(self.font_cache[role][size]),
                    QtGui.QFontMetricsF(self.metrics_cache[role][size]))

        # Map role to style
        if role == Font.BlackFont:
            style = 'SemiBold'
        elif role == Font.BoldFont:
            style = 'Bold'
        elif role == Font.MediumFont:
            style = 'Medium'
        elif role == Font.LightFont:
            style = 'Regular'
        elif role == Font.ThinFont:
            style = 'Thin'
        else:
            raise ValueError(f'Invalid font role: {role}')

        # Retrieve a font of the specified family, style, and size
        font = QtGui.QFontDatabase.font(role.value, style, size)
        if font.family() != role.value:
            logging.warning(f'Font not found: {role.value} {style} {size}. Found: {font.family()}')

        font.setPixelSize(size)

        # Cache the font and metrics
        self.font_cache[role][size] = font
        self.metrics_cache[role][size] = QtGui.QFontMetricsF(font)

        return font, self.metrics_cache[role][size]


class Theme(enum.StrEnum):
    Light = 'light'
    Dark = 'dark'


class Size(enum.Enum):
    """Enumeration of size values used for UI scaling."""
    SmallText = 11.0
    MediumText = 12.0
    LargeText = 16.0
    Indicator = 4.0
    Separator = 1.0
    Margin = 18.0
    Section = 86.0
    RowHeight = 34.0
    Thumbnail = 512.0
    DefaultWidth = 640.0
    DefaultHeight = 480.0

    def __new__(cls, value):
        obj = object.__new__(cls)
        obj._value_ = float(value)
        return obj

    def __eq__(self, other):
        if isinstance(other, (float, int)):
            return self._value_ == float(other)
        return super().__eq__(other)

    def __call__(self, multiplier=1.0, apply_scale=True):
        """
        Returns the scaled size value.

        Args:
            multiplier (float): A multiplier to apply to the size.
            apply_scale (bool): If True, applies UI scaling factors.

        Returns:
            int: The scaled size.
        """
        if apply_scale:
            return round(self.value * float(multiplier))
        return round(self._value_ * float(multiplier))

    @property
    def value(self):
        """float: The scaled size value."""
        return self.size(self._value_)

    @classmethod
    def size(cls, value, ui_scale_factor=1.0, dpi=72.0):
        """Scale a value by DPI and UI scale factor."""
        return math.ceil(float(value) * (float(dpi) / 72.0)) * float(ui_scale_factor)


class Color(enum.Enum):
    """Enumeration of colours used across the UI."""

    Opaque = {
        Theme.Light.value: (250, 250, 250, 30),
        Theme.Dark.value: (0, 0, 0, 30),
    }
    Transparent = {
        Theme.Light.value: (0, 0, 0, 0),
        Theme.Dark.value: (0, 0, 0, 0),
    }
    VeryDarkBackground = {
        Theme.Light.value: (245, 245, 245),
        Theme.Dark.value: (30, 30, 30),
    }
    DarkBackground = {
        Theme.Light.value: (220, 220, 220),
        Theme.Dark.value: (45, 45, 45),
    }
    Background = {
        Theme.Light.value: (190, 190, 190),
        Theme.Dark.value: (65, 65, 65),
    }
    LightBackground = {
        Theme.Light.value: (170, 170, 170),
        Theme.Dark.value: (85, 85, 85),
    }
    DisabledText = {
        Theme.Light.value: (120, 120, 120),
        Theme.Dark.value: (135, 135, 135),
    }
    SecondaryText = {
        Theme.Light.value: (70, 70, 70),
        Theme.Dark.value: (185, 185, 185),
    }
    Text = {
        Theme.Light.value: (30, 30, 30),
        Theme.Dark.value: (225, 225, 225),
    }
    SelectedText = {
        Theme.Light.value: (0, 0, 0),
        Theme.Dark.value: (255, 255, 255),
    }
    Blue = {
        Theme.Light.value: (0, 50, 100),
        Theme.Dark.value: (88, 138, 180),
    }
    LightBlue = {
        Theme.Light.value: (20, 70, 120),
        Theme.Dark.value: (98, 158, 190),
    }
    Red = {
        Theme.Light.value: (179, 94, 94),
        Theme.Dark.value: (229, 114, 114),
    }
    Green = {
        Theme.Light.value: (60, 180, 125),
        Theme.Dark.value: (90, 200, 155),
    }
    Yellow = {
        Theme.Light.value: (233, 146, 1),
        Theme.Dark.value: (253, 166, 1),
    }

    @classmethod
    def _get_theme(cls):
        from ..settings import lib
        theme = lib.settings['theme']
        if theme not in [f.value for f in Theme]:
            theme = Theme.Dark.value
        return theme

    def __new__(cls, v):
        if not isinstance(v, dict):
            raise ValueError(f'Invalid color value: {v}. Must be a dictionary, got {type(v)}: {v}')
        obj = object.__new__(cls)
        obj._value_ = v
        return obj

    def __call__(self, qss=False):
        """
        Returns a QColor or CSS rgba string.

        Args:
            qss (bool): If True, returns a CSS rgba string suitable for QSS.

        Returns:
            QColor or str: A QColor instance if qss=False, otherwise a CSS rgba string.
        """
        theme = self._get_theme()
        if theme not in self._value_:
            theme = Theme.Dark.value

        # Get color from theme
        color = QtGui.QColor(*self._value_[theme])
        if not qss:
            return color

        return self.rgb(color)

    @staticmethod
    def rgb(color):
        """Returns the CSS rgba string for a QColor."""
        rgb = [str(f) for f in color.getRgb()]
        return f'rgba({",".join(rgb)})'


def init_stylesheet():
    """Loads and stores the custom style sheet used by the app.

    The style sheet template is stored in the ``/stylesheet.qss`` file, and we use
    the values in ``config.json`` to expand it.

    Returns:
        str: The style sheet.

    """
    if not QtWidgets.QApplication.instance():
        raise RuntimeError('init_stylesheet() must be called after a QApplication is initiated.')

    from ..settings import lib
    if not os.path.isfile(lib.settings.stylesheet_path):
        raise FileNotFoundError(f'Style sheet file not found: {lib.settings.stylesheet_path}')

    with open(lib.settings.stylesheet_path, 'r', encoding='utf-8') as f:
        qss = f.read()

    kwargs = {}

    for enum in Font:
        if not enum:
            raise RuntimeError(f'Font {enum.name} not found!')
        font, _ = enum(Size.MediumText())
        kwargs[enum.name] = font.family()

    for enum in Color:
        key = enum.name
        if key in kwargs:
            raise KeyError(f'Key {key} already set!')
        kwargs[enum.name] = Color.rgb(enum())

    for enum in Size:
        for i in [float(f) / 10.0 for f in range(1, 101)]:
            key = f'{enum.name}@{i:.1f}'
            if key in kwargs:
                raise KeyError(f'Key {key} already set!')
            kwargs[key] = round(enum() * i)

    # Tokens are defined as "<token>" in the stylesheet file
    for match in re.finditer(r'<(.*?)>', qss):
        if not match:
            continue

        key = match.group(1)
        if key not in kwargs:
            raise KeyError(f'Key {key} not found in kwargs!')

        qss = qss.replace(f'<{key}>', str(kwargs[key]))

    # Make sure all tokens are replaced
    if re.search(r'<(.*?)>', qss):
        raise RuntimeError('Not all tokens were replaced!')

    return qss


def apply_theme() -> None:
    """Set the style sheet for the entire app.

    This function should be called after the QApplication is created.

    """
    if not QtWidgets.QApplication.instance():
        raise RuntimeError('set_app_stylesheet() must be called after a QApplication is initiated.')

    if os.environ.get('EXPENSETRACKER_DISABLE_STYLESHEET', '').lower() in ['1', 'true', 'yes']:
        logging.warning('Stylesheet disabled by environment variable.')
        return

    qss = init_stylesheet()
    QtWidgets.QApplication.instance().setStyleSheet(qss)

    for widget in QtWidgets.QApplication.instance().topLevelWidgets():
        try:
            widget.setStyleSheet(qss)
        except:
            pass


icon_cache = {}


class ThemedIconEngine(QtGui.QIconEngine):
    """The icon engine used to load and paint icons dynamically based on the current theme.

    """

    def __init__(self, icon: str, color: Union[QtGui.QColor, Color] = Color.Text):
        super().__init__()
        self._icon = icon
        self._color = color

        self._cache = {}
        self._scaled_pixmap_cache = {}

    def theme(self):
        from ..settings import lib
        return lib.settings['theme']

    def get_icon(self) -> QtGui.QIcon:
        """Get the icon for the given category, tinting dynamically based on the theme.

        Returns:
            QtGui.QIcon: The icon for the given category.
        """
        k = f'{self._icon}:{self.theme()}'
        if k in self._cache:
            return self._cache[k]

        icon = QtGui.QIcon()

        pixmap = QtGui.QPixmap(self._icon)
        if pixmap.isNull():
            logging.debug(f'Icon not found: {self._icon}')
            return icon

        if isinstance(self._color, Color):
            color = self._color()
        elif isinstance(self._color, QtGui.QColor):
            color = self._color

        pixmap_normal = self.tint(pixmap, color)
        icon.addPixmap(pixmap_normal, QtGui.QIcon.Normal, QtGui.QIcon.On)
        icon.addPixmap(pixmap_normal, QtGui.QIcon.Normal, QtGui.QIcon.Off)

        pixmap_disabled = self.tint(pixmap, Color.DisabledText())
        icon.addPixmap(pixmap_disabled, QtGui.QIcon.Disabled, QtGui.QIcon.On)
        icon.addPixmap(pixmap_disabled, QtGui.QIcon.Disabled, QtGui.QIcon.Off)

        pixmap_active = self.tint(pixmap, color.lighter(125))
        icon.addPixmap(pixmap_active, QtGui.QIcon.Active, QtGui.QIcon.On)
        icon.addPixmap(pixmap_active, QtGui.QIcon.Active, QtGui.QIcon.Off)

        pixmap_selected = self.tint(pixmap, Color.SelectedText())
        icon.addPixmap(pixmap_selected, QtGui.QIcon.Selected, QtGui.QIcon.On)
        icon.addPixmap(pixmap_selected, QtGui.QIcon.Selected, QtGui.QIcon.Off)

        # Add icon to cache
        self._cache[k] = icon
        return self._cache[k]

    def tint(self, pixmap, color):
        """Tint the given pixmap with the given color."""
        if color.alpha() == 0:
            return pixmap

        painter = QtGui.QPainter(pixmap)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), color)
        painter.end()

        return pixmap

    def paint(self, painter, rect, mode, state):

        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        painter.setBrush(QtCore.Qt.NoBrush)
        painter.setPen(QtCore.Qt.NoPen)

        icon = self.get_icon()
        if icon.isNull():
            return

        icon.paint(
            painter,
            rect,
            alignment=QtCore.Qt.AlignCenter,
            mode=mode,
            state=state,
        )

    def pixmap(self, size, mode, state):
        icon = self.get_icon()
        return icon.pixmap(size, mode, state)

    def scaledPixmap(self, size, mode, state, scale):
        k = f'{self._icon}:{self.theme()}:{size.width()}x{size.height()}:{scale}'
        if k in self._scaled_pixmap_cache:
            return self._scaled_pixmap_cache[k]

        icon = self.get_icon()
        pixmap = icon.pixmap(size, mode, state)

        if pixmap.isNull():
            return pixmap

        pixmap = pixmap.scaled(
            QtCore.QSize(
                size.width() * scale,
                size.height() * scale
            ),
            aspectMode=QtCore.Qt.KeepAspectRatio,
            mode=QtCore.Qt.SmoothTransformation
        )

        self._scaled_pixmap_cache[k] = pixmap
        return self._scaled_pixmap_cache[k]

    def actualSize(self, size, mode, state):
        icon = self.get_icon()
        return icon.actualSize(size, mode, state)

    def clone(self):
        return ThemedIconEngine(
            self._icon,
            self._color
        )


class CategoryIconEngine(ThemedIconEngine):
    """The icon engine used to load and paint icons dynamically based on the current theme.

    """

    def __init__(self, icon: str, color: Union[QtGui.QColor, Color] = Color.Text):
        super().__init__(icon, color)

        global icons
        if not icons:
            from ..settings import lib
            if not lib.settings.icon_dir.is_dir():
                raise FileNotFoundError(f'Icon directory not found: {lib.settings.icon_dir}')

            for _icon in lib.settings.icon_dir.glob('*.png'):
                if not _icon.is_file():
                    continue
                logging.debug(f'Found icon: {_icon.stem}')
                icons.append(_icon.stem)

    def paint(self, painter, rect, mode, state):
        painter.save()

        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

        pen = QtGui.QPen(self._color)
        pen.setWidthF(rect.height() / 10.0)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        painter.setPen(pen)

        if mode == QtGui.QIcon.Active:
            painter.setBrush(self._color)
        else:
            painter.setBrush(Color.Opaque())

        o = rect.height() / 2.0
        painter.drawRoundedRect(rect, o, o)

        painter.restore()

        o = rect.height() / 5.0
        rect = rect.adjusted(o, o, -o, -o)

        super().paint(painter, rect, mode, state)

    def clone(self):
        return CategoryIconEngine(
            self._icon,
            self._color
        )


def get_icon(icon: str, color: Union[QtGui.QColor, Color] = Color.Text,
             engine: QtGui.QIconEngine = ThemedIconEngine) -> QtGui.QIcon:
    """Get the icon for the given category, tinting dynamically based on the theme.

    Args:
        icon (str): The icon category.
        color (QColor): The color to tint the icon with. If None, uses the default color.

    """
    from ..settings import lib

    global icons

    if not isinstance(icon, str) and icon not in icons:
        raise ValueError(f'Invalid icon category: {icon}. Must be one of {icons}')

    if isinstance(color, QtGui.QColor):
        k = f'{icon}:{color.name(QtGui.QColor.HexRgb)}:{engine.__name__}'
    elif isinstance(color, Color):
        k = f'{icon}:{color.name}:{engine.__name__}'

    if k in icon_cache:
        return icon_cache[k]

    icon = QtGui.QIcon(engine(
        lib.settings.icon_dir / f'{icon}.png',
        color
    ))

    icon_cache[k] = icon
    return icon


class RoundedRowDelegate(QtWidgets.QStyledItemDelegate):
    """Delegate that draws rounded-corner backgrounds for selected row cells."""

    def __init__(self, first_column: int = 0, last_column: int = -1,
                 parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent=parent)

        self._first_column = first_column
        self._last_column = last_column

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem,
              index: QtCore.QModelIndex) -> None:
        """Paint the item with rounded corners if selected."""
        selected = option.state & QtWidgets.QStyle.State_Selected
        hover = option.state & QtWidgets.QStyle.State_MouseOver

        column = index.column()

        painter.setPen(QtCore.Qt.NoPen)
        if selected:
            color = Color.Background()
        else:
            color = Color.Transparent()

        painter.setBrush(color)

        last_column = index.model().columnCount() + self._last_column

        o = Size.Indicator(1.5)
        rect1 = QtCore.QRect(option.rect)
        rect2 = QtCore.QRect(option.rect)

        if column == self._first_column:
            rect1 = rect1.adjusted(0, 0, -option.rect.width() / 2 + o, 0)
            painter.drawRoundedRect(rect1, o, o)
            rect2 = rect2.adjusted(option.rect.width() / 2, 0, 0, 0)
            painter.fillRect(rect2, color)
        elif column == last_column:
            rect1 = rect1.adjusted(option.rect.width() / 2, 0, 0, 0)
            painter.drawRoundedRect(rect1, o, o)
            rect2 = rect2.adjusted(0, 0, -option.rect.width() / 2 + o, 0)
            painter.fillRect(rect2, color)
        else:
            painter.fillRect(option.rect, color)

        super().paint(painter, option, index)
