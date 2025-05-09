"""Metadata editor: UI components for general application settings.

Provides editors for:
    - Locale selection (LocaleEditor)
    - Summary mode and theme (SummaryModeEditor, ThemeEditor)
    - Boolean settings (BooleanEditor)
    - Composite settings panel (MetadataWidget)
"""

import enum
import logging

import babel
from PySide6 import QtCore, QtWidgets

from .. import lib
from ...ui import ui
from ...ui.actions import signals

logger = logging.getLogger(__name__)


class SummaryModes(enum.StrEnum):
    Total = enum.auto()
    Monthly = enum.auto()


class ThemeModes(enum.StrEnum):
    Light = enum.auto()
    Dark = enum.auto()


class BaseComboBoxEditor(QtWidgets.QComboBox):
    """Base combo-box editor for a configuration property.

    The editor is initialized using:
      - property_name: key for lib.settings.
      - default_value: a default value if the stored configuration is invalid.
      - options: list of (display, value) tuples.
    """

    def __init__(self, property_name, default_value, options, parent=None):
        super().__init__(parent=parent)
        self._options = options
        self.property_name = property_name
        self.default_value = default_value
        self.setView(QtWidgets.QListView(self))

        self._connect_signals()

    def get_options(self):
        """Return a list of option tuples (display, value)."""
        return self._options

    def init_data(self):

        self.blockSignals(True)
        self.clear()

        try:
            for display, value in self.get_options():
                self.addItem(display, userData=value)
        finally:
            self.blockSignals(False)

        # Validate and set the current value.
        stored = lib.settings[self.property_name]
        valid = self.validate_value(stored)
        idx = self.findData(valid)

        if idx != -1:
            self.blockSignals(True)
            self.setCurrentIndex(idx)
            self.blockSignals(False)

    def validate_value(self, value):
        """Check if a value exists in options; otherwise return the default."""
        for _, option in self.get_options():
            if isinstance(option, enum.Enum):
                if isinstance(value, str) and value == option.name:
                    return option
                elif value == option:
                    return option
            elif value == option:
                return option
        return self.default_value

    def _connect_signals(self):
        self.currentIndexChanged.connect(self.save)

        @QtCore.Slot(str, object)
        def metadata_changed(key: str, value: object) -> None:
            if key != self.property_name:
                return

            QtCore.QTimer.singleShot(0, self.init_data)

        signals.metadataChanged.connect(metadata_changed)
        signals.initializationRequested.connect(self.init_data)

    @QtCore.Slot(int)
    def save(self, index):
        if index == -1:
            return
        option = self.itemData(index)
        if isinstance(option, enum.Enum):
            value_to_save = option.name
        else:
            value_to_save = option
        logging.debug(f'Setting {self.property_name} to {value_to_save}')
        lib.settings[self.property_name] = value_to_save


class NameEditor(QtWidgets.QLineEdit):
    """Edits the "name" metadata property.

    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setPlaceholderText('Enter name')
        self.setClearButtonEnabled(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Maximum)
        self.setMinimumWidth(ui.Size.DefaultWidth(1.0))
        self._connect_signals()
        QtCore.QTimer.singleShot(150, self.init_data)

    def init_data(self):
        v = lib.settings['name']
        self.blockSignals(True)
        self.setText(v or '')
        self.blockSignals(False)

    def _connect_signals(self):
        self.textChanged.connect(self.save)

        @QtCore.Slot(str, object)
        def metadata_changed(key: str, value: object) -> None:
            if key != 'name':
                return
            self.init_data()

        signals.metadataChanged.connect(metadata_changed)

    @QtCore.Slot(str)
    def save(self, text):
        lib.settings['name'] = text


class DescriptionEditor(QtWidgets.QLineEdit):
    """Edits the "description" metadata property.

    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setPlaceholderText('Enter description')
        self.setClearButtonEnabled(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Maximum)
        self.setMinimumWidth(ui.Size.DefaultWidth(1.0))
        self._connect_signals()
        QtCore.QTimer.singleShot(150, self.init_data)

    def init_data(self):
        v = lib.settings['description']
        self.blockSignals(True)
        self.setText(v or '')
        self.blockSignals(False)

    def _connect_signals(self):
        self.textChanged.connect(self.save)

        @QtCore.Slot(str, object)
        def metadata_changed(key: str, value: object) -> None:
            if key != 'description':
                return
            self.init_data()

        signals.metadataChanged.connect(metadata_changed)

    @QtCore.Slot(str)
    def save(self, text):
        lib.settings['description'] = text


class LocaleEditor(BaseComboBoxEditor):
    """Editor for locale.

    Uses the LOCALE_MAP from the locale module and Babel for display names.
    Stores the locale as a string.
    """

    def __init__(self, parent=None):
        from .. import locale
        # Build options from the LOCALE_MAP.
        options = []
        for loc in locale.LOCALE_MAP:
            display = babel.Locale.parse(loc).get_display_name('en')
            options.append((display, loc))
        default = 'en_GB'
        super().__init__('locale', default, options, parent=parent)


class EnumEditor(BaseComboBoxEditor):
    """Generic editor for enum configuration properties.

    The options are constructed from an enum class.
    """

    def __init__(self, property_name, enum_class, default_value, parent=None):
        options = [(member.name, member) for member in enum_class]
        super().__init__(property_name, default_value, options, parent=parent)


class SummaryModeEditor(EnumEditor):
    """Editor for summary mode.

    Uses SummaryModes enum. The configuration value is stored as the enum name.
    """

    def __init__(self, parent=None):
        super().__init__('summary_mode', SummaryModes, SummaryModes.Monthly, parent=parent)


class ThemeEditor(EnumEditor):
    """Editor for theme selection.

    Uses ThemeModes enum. The configuration value is stored as the enum name.
    """

    def __init__(self, parent=None):
        super().__init__('theme', ThemeModes, ThemeModes.Light, parent=parent)


class BooleanEditor(QtWidgets.QCheckBox):
    """Check-box editor for boolean settings.

    The widget is initialized with the provided property name.
    """

    def __init__(self, prop, parent=None):
        super().__init__(parent=parent)
        self.property_name = prop
        self.setChecked(False)
        self.setTristate(False)
        self._connect_signals()
        QtCore.QTimer.singleShot(150, self.init_data)

    def init_data(self):
        v = lib.settings[self.property_name]
        self.blockSignals(True)
        self.setChecked(v or False)
        self.blockSignals(False)

    def _connect_signals(self):
        self.stateChanged.connect(self.save)

        @QtCore.Slot(str, object)
        def metadata_changed(key: str, value: object) -> None:
            if key != self.property_name:
                return
            self.init_data()

        signals.metadataChanged.connect(metadata_changed)

    @QtCore.Slot()
    def save(self, *args, **kwargs):
        lib.settings[self.property_name] = self.isChecked()


class MetadataWidget(QtWidgets.QWidget):
    """Widget that aggregates editors for locale, summary mode, booleans, and theme."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.text_changed_timer = QtCore.QTimer(self)
        self.text_changed_timer.setSingleShot(True)
        self.text_changed_timer.setInterval(QtWidgets.QApplication.keyboardInputInterval())
        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        self.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Maximum)

        self._create_ui()
        self._init_actions()
        self._connect_signals()

    def _create_ui(self):
        layout = QtWidgets.QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        spacing = ui.Size.Indicator(1.0)
        layout.setSpacing(spacing)
        layout.addRow('Name', NameEditor(self))
        layout.addRow('Description', DescriptionEditor(self))
        separator = QtWidgets.QFrame(self)

        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        separator.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Fixed)
        separator.setFixedHeight(spacing * 1.0)

        layout.addRow(separator)
        layout.addRow('Locale', LocaleEditor(self))
        layout.addRow('Summary Mode', SummaryModeEditor(self))
        layout.addRow('Hide Empty Categories', BooleanEditor('hide_empty_categories', parent=self))
        layout.addRow('Exclude Negative Values', BooleanEditor('exclude_negative', parent=self))
        layout.addRow('Exclude Zero Values', BooleanEditor('exclude_zero', parent=self))
        layout.addRow('Exclude Positive Values', BooleanEditor('exclude_positive', parent=self))
        layout.addRow('Theme', ThemeEditor(self))

    def _init_actions(self):
        pass

    def _connect_signals(self):
        pass
