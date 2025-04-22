import enum
import logging
import math
import os
import re

from PySide6 import QtWidgets, QtGui


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


class FontDatabase(QtGui.QFontDatabase):
    """Custom QFontDatabase used to load and provide the fonts needed by Bookmarks."""

    def __init__(self):
        if not QtWidgets.QApplication.instance():
            raise RuntimeError('FontDatabase must be created after a QApplication is initiated.')
        super().__init__()

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
        idx = self.addApplicationFont(str(lib.settings.font_path))
        if idx < 0:
            raise RuntimeError(f'Could not load font file: {lib.settings.font_path}')
        family = self.applicationFontFamilies(idx)
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

        font = super().font(role.value, style, size)
        if font.family() != role.value:
            raise RuntimeError(f'Could not find font: {role.value} {style} {size}')

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
        Theme.Light.value: (225, 225, 225),
        Theme.Dark.value: (30, 30, 30),
    }
    DarkBackground = {
        Theme.Light.value: (210, 210, 210),
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

    qss = init_stylesheet()
    QtWidgets.QApplication.instance().setStyleSheet(qss)

    for widget in QtWidgets.QApplication.instance().allWidgets():
        try:
            widget.setStyleSheet(qss)
            widget.update()
        except:
            pass


icon_cache = {}


def get_icon(category: str, color: QtGui.QColor = None) -> QtGui.QIcon:
    """Get the icon for the given category.

    Args:
        category (str): The category name.

    Returns:
        QtGui.QIcon: The icon for the category.

    """
    k = f'{category}:{color}'
    if k in icon_cache:
        return icon_cache[k]

    from ..settings import lib
    icon_path = lib.settings.icon_dir / f'{category}.png'
    if not icon_path.is_file():
        logging.warning(f'Icon not found for category: {category}. Using default icon.')
        v = QtGui.QIcon()
        icon_cache[k] = v
        return v

    pixmap = QtGui.QPixmap(str(icon_path))

    color = color if color else Color.SecondaryText()
    painter = QtGui.QPainter(pixmap)
    painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), color)
    painter.end()

    icon = QtGui.QIcon(pixmap)
    icon_cache[k] = icon

    return icon
