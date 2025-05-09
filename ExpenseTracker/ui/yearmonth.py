"""
YearMonthSelector Module.

Provides custom PySide6 widgets for selecting a year-month combination and
a range toolbar for selecting a start and end month. The selected value is
managed as a "YYYY-MM" formatted string.

Classes:
    YearMonthPopup: Popup widget for choosing a year and month.
    YearMonthSelector: Widget for a single year-month selection.
    RangeSelectorBar: Toolbar widget for selecting a start and end range.

"""
import logging
from datetime import datetime

from PySide6 import QtCore, QtWidgets, QtGui
from dateutil.relativedelta import relativedelta

from . import ui
from ..settings import lib


def date_str_to_int(date_str):
    return int(date_str[:4]) * 12 + int(date_str[5:7])


class YearMonthPopup(QtWidgets.QFrame):
    """
    Popup widget for selecting a year-month combination.

    Displays navigation for the year and a grid of month buttons.

    Signals:
        yearMonthSelected(str): Emitted when a month is selected in "YYYY-MM" format.
    """
    yearMonthSelected = QtCore.Signal(str)

    def __init__(self, parent=None, initial_year=None, min_date=None, max_date=None):
        super().__init__(parent=parent)

        self.setWindowFlags(QtCore.Qt.Popup)

        self.next_button = None
        self.prev_button = None
        self.month_buttons = []

        self.current_year = initial_year if initial_year is not None else datetime.now().year
        self.min_date = min_date
        self.max_date = max_date

        # Convert dates to comparable integers (year*12 + month)
        self.min_val = int(min_date[:4]) * 12 + int(min_date[5:7]) if min_date else None
        self.max_val = int(max_date[:4]) * 12 + int(max_date[5:7]) if max_date else None

        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)

        self._create_ui()
        self._connect_signals()

    def _create_ui(self):
        self.month_buttons = []
        QtWidgets.QVBoxLayout(self)
        header_layout = QtWidgets.QHBoxLayout()

        self.prev_button = QtWidgets.QToolButton(self)
        self.prev_button.setToolTip('Previous year')
        self.prev_button.setWhatsThis('Previous year')
        self.prev_button.setShortcut('Alt+Left')
        self.prev_button.setShortcutAutoRepeat(False)
        self.prev_button.setIcon(ui.get_icon('btn_left'))
        self.prev_button.setText('Previous Month')
        self.prev_button.clicked.connect(self.decrement_year)
        header_layout.addWidget(self.prev_button)

        self.year_label = QtWidgets.QLabel(str(self.current_year), self)
        self.year_label.setAlignment(QtCore.Qt.AlignCenter)
        header_layout.addWidget(self.year_label)

        self.next_button = QtWidgets.QToolButton(self)
        self.next_button.setToolTip('Next year')
        self.next_button.setWhatsThis('Next year')
        self.next_button.setShortcut('Alt+Right')
        self.next_button.setShortcutAutoRepeat(False)
        self.next_button.setIcon(ui.get_icon('btn_right'))
        self.next_button.setText('Next Month')
        self.next_button.clicked.connect(self.increment_year)
        header_layout.addWidget(self.next_button)

        self.layout().addLayout(header_layout)

        grid_layout = QtWidgets.QGridLayout()
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

        for i, name in enumerate(month_names):
            btn = QtWidgets.QPushButton(name, self)
            btn.clicked.connect(lambda checked, m=i + 1: self.month_clicked(m))
            self.month_buttons.append(btn)
            grid_layout.addWidget(btn, i // 4, i % 4)
        self.layout().addLayout(grid_layout)

        self.update_month_buttons()

    def _connect_signals(self):
        pass

    def update_month_buttons(self):
        """Enable or disable month buttons and highlight those in the active range."""
        # Determine current active range if available
        parent = self.parent()
        grandparent = parent.parent() if parent else None
        try:
            start_str, end_str = grandparent.get_range()
            start_int = date_str_to_int(start_str)
            end_int = date_str_to_int(end_str)
        except Exception:
            start_int = end_int = None

        for i, btn in enumerate(self.month_buttons):
            month = i + 1
            button_val = self.current_year * 12 + month
            disable = False
            if self.min_val is not None and button_val < self.min_val:
                disable = True
            if self.max_val is not None and button_val > self.max_val:
                disable = True
            btn.setEnabled(not disable)
            # Highlight month button if within active range
            in_range = False
            if start_int is not None and end_int is not None and start_int <= button_val <= end_int:
                in_range = True
            btn.setProperty('inRange', in_range)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()

        # Highlight year label if current year is within active range
        in_range_year = False
        if start_int is not None and end_int is not None:
            try:
                start_year = int(start_str.split('-')[0])
                end_year = int(end_str.split('-')[0])
                if start_year <= self.current_year <= end_year:
                    in_range_year = True
            except Exception:
                pass
        self.year_label.setProperty('inRange', in_range_year)
        self.year_label.style().unpolish(self.year_label)
        self.year_label.style().polish(self.year_label)
        self.year_label.update()

    @QtCore.Slot()
    def decrement_year(self):
        new_year = self.current_year - 1
        if self.min_date is not None:
            min_year = int(self.min_date[:4])
            if new_year < min_year:
                return
        self.current_year = new_year
        self.year_label.setText(str(self.current_year))
        self.update_month_buttons()

    @QtCore.Slot()
    def increment_year(self):
        new_year = self.current_year + 1
        if self.max_date is not None:
            max_year = int(self.max_date[:4])
            if new_year > max_year:
                return
        self.current_year = new_year
        self.year_label.setText(str(self.current_year))
        self.update_month_buttons()

    @QtCore.Slot(int)
    def month_clicked(self, month):
        """
        Handle month button click.

        Args:
            month (int): The selected month (1-12).
        """
        date_str = f'{self.current_year:04d}-{month:02d}'
        self.yearMonthSelected.emit(date_str)
        self.close()


class YearMonthSelector(QtWidgets.QToolButton):
    """
    Widget for selecting a year-month combination.

    Displays a button that opens a dropdown popup for selecting a year and month.
    The selection is maintained as a "YYYY-MM" formatted string.

    Signals:
        yearMonthChanged(str): Emitted when the selection changes.
    """
    yearMonthChanged = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self._popup = None
        self._value = datetime.now().strftime('%Y-%m')

        self.min_date = None
        self.max_date = None

        self.setContextMenuPolicy(QtCore.Qt.NoContextMenu)

        self._init_data()
        self._init_actions()
        self._connect_signals()

    def _init_data(self):
        self.setText(self._value)

    def _connect_signals(self):
        self.clicked.connect(self.show_popup)
        from ..ui.actions import signals

        @QtCore.Slot(str, object)
        def metadata_changed(key: str, value: object) -> None:
            if key == 'yearmonth' and isinstance(value, str):
                self.set_value(value)

        signals.metadataChanged.connect(metadata_changed)

    def _init_actions(self):
        pass

    @QtCore.Slot()
    def show_popup(self):
        self._popup = YearMonthPopup(
            self,
            initial_year=int(self._value[:4]),
            min_date=self.min_date,
            max_date=self.max_date
        )
        self._popup.yearMonthSelected.connect(self.set_value)
        pos = self.mapToGlobal(QtCore.QPoint(0, self.height()))
        self._popup.move(pos)
        self._popup.show()
        self._popup.raise_()
        self._popup.setFocus(QtCore.Qt.PopupFocusReason)

    @QtCore.Slot(str)
    def set_value(self, value):
        """Update the current value and emit a change signal."""
        self._value = value
        self.setText(value)
        self.yearMonthChanged.emit(value)

    def get_value(self):
        """Return the current 'YYYY-MM' string."""
        return self._value


class RangeSelectorBar(QtWidgets.QToolBar):
    """
    Toolbar widget for selecting a start and end year-month range.

    Contains two YearMonthSelector instances and a hyphen label between them.
    Global year selections are capped between (current year - 10) and the current month.
    When the start date exceeds the current end date, the end selector is automatically
    adjusted to match the start date. Emits the range span (in months) via rangeChanged.

    Signals:
        rangeChanged(str, int): Emitted when the range span changes.
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.global_min_date = None
        self.global_max_date = None

        self.start_selector = None
        self.end_selector = None

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Maximum,
            QtWidgets.QSizePolicy.Maximum
        )

        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        self._create_ui()
        self._init_data()
        self._connect_signals()
        self._init_actions()

    def _connect_signals(self):
        self.start_selector.yearMonthChanged.connect(self.on_start_changed)
        self.start_selector.yearMonthChanged.connect(self.save_range)

        self.end_selector.yearMonthChanged.connect(self.on_end_changed)
        self.end_selector.yearMonthChanged.connect(self.save_range)

        from ..ui.actions import signals
        @QtCore.Slot(str, object)
        def metadata_changed(key: str, value: object) -> None:
            if key in ('yearmonth', 'span'):
                self.load_saved_state()

        signals.metadataChanged.connect(metadata_changed)
        signals.initializationRequested.connect(self.load_saved_state)

    def _create_ui(self):
        prev_action = QtGui.QAction(ui.get_icon('btn_left'), '', self)
        prev_action.setToolTip('Previous month')
        prev_action.setShortcuts(['Alt+Left', 'Ctrl+Left'])
        prev_action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
        prev_action.triggered.connect(self.previous_month)
        self.addAction(prev_action)

        self.addSeparator()

        self.start_selector = YearMonthSelector(self)
        self.start_selector.setObjectName('start_selector')
        self.addWidget(self.start_selector)

        self.end_selector = YearMonthSelector(self)
        self.end_selector.setObjectName('end_selector')
        self.addWidget(self.end_selector)

        self.addSeparator()

        next_action = QtGui.QAction(ui.get_icon('btn_right'), '', self)
        next_action.setToolTip('Next month')
        next_action.setShortcuts(['Alt+Right', 'Ctrl+Right'])
        next_action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
        next_action.triggered.connect(self.next_month)
        self.addAction(next_action)

    def _init_data(self):
        now = datetime.now()
        global_min_date = f'{now.year - 10}-01'
        global_max_date = f'{now.year}-{now.month:02d}'

        self.global_min_date = global_min_date
        self.global_max_date = global_max_date

        self.start_selector.min_date = global_min_date
        self.start_selector.max_date = global_max_date

        # End selector's limits: minimum follows start; maximum is global.
        self.end_selector.min_date = self.start_selector.get_value()
        self.end_selector.max_date = global_max_date

    def load_saved_state(self):
        """
        Load saved state for the date range.

        Temporarily blocks signals to avoid undesired overrides during initialization.
        """
        now = datetime.now()
        yearmonth = f'{now.year}-{now.month:02d}'
        yearmonth = lib.settings['yearmonth'] or yearmonth

        span = lib.settings['span'] or 1
        if not isinstance(span, int):
            try:
                span = int(span)
            except ValueError:
                logging.warning(f'Invalid span value: {span}, defaulting to 1')
                span = 1

        if span < 1:
            logging.warning(f'Span value {span} is less than 1, defaulting to 1')
            span = 1

        start_datetime = datetime.strptime(yearmonth, '%Y-%m')
        end_datetime = start_datetime + relativedelta(months=span - 1)
        end_date = end_datetime.strftime('%Y-%m')

        # Temporarily block UI signals to prevent save_range during initialization
        self.start_selector.blockSignals(True)
        self.end_selector.blockSignals(True)
        self.start_selector.set_value(yearmonth)
        self.end_selector.set_value(end_date)
        self.start_selector.blockSignals(False)
        self.end_selector.blockSignals(False)
        # Update end selector limits based on the restored start date
        self.on_start_changed(yearmonth)

    @QtCore.Slot(str)
    def on_start_changed(self, start_value):
        self.end_selector.min_date = start_value
        if date_str_to_int(self.end_selector.get_value()) < date_str_to_int(start_value):
            self.end_selector.set_value(start_value)

    @QtCore.Slot(str)
    def on_end_changed(self, end_value):
        if date_str_to_int(self.start_selector.get_value()) > date_str_to_int(end_value):
            self.start_selector.set_value(end_value)

    @QtCore.Slot()
    def save_range(self):
        logging.debug('Saving range...')

        yearmonth = self.start_selector.get_value()
        start_int = date_str_to_int(yearmonth)

        _yearmonth = self.end_selector.get_value()
        end_int = date_str_to_int(_yearmonth)
        span = (end_int - start_int) + 1

        # Set without emitting signals to avoid unwanted updates
        lib.settings.block_signals(True)
        lib.settings['yearmonth'] = yearmonth
        lib.settings.block_signals(False)

        lib.settings['span'] = span

    def _init_actions(self):
        pass

    def get_range(self) -> tuple[str, str]:
        """Return a tuple of (start_value, end_value)."""
        return self.start_selector.get_value(), self.end_selector.get_value()

    def get_range_span(self) -> int:
        """Return the span of the range in months."""
        start_int = date_str_to_int(self.start_selector.get_value())
        end_int = date_str_to_int(self.end_selector.get_value())
        return (end_int - start_int) + 1

    @QtCore.Slot(int)
    def shift(self, months: int) -> None:
        """Shift the selected start/end range by the given number of months."""
        # Get current range and span
        start_str, _ = self.get_range()
        try:
            start_dt = datetime.strptime(start_str, '%Y-%m')
        except Exception:
            return
        span = self.get_range_span()
        # Compute new start
        new_start = start_dt + relativedelta(months=months)
        # Clamp to global min date
        if self.global_min_date:
            try:
                min_dt = datetime.strptime(self.global_min_date, '%Y-%m')
                if new_start < min_dt:
                    new_start = min_dt
            except Exception:
                pass
        # Compute new end based on span
        new_end = new_start + relativedelta(months=span - 1)
        # Clamp to global max date
        if self.global_max_date:
            try:
                max_dt = datetime.strptime(self.global_max_date, '%Y-%m')
                if new_end > max_dt:
                    new_end = max_dt
                    new_start = new_end - relativedelta(months=span - 1)
            except Exception:
                pass
        # Apply new values
        self.start_selector.set_value(new_start.strftime('%Y-%m'))
        self.end_selector.set_value(new_end.strftime('%Y-%m'))

    @QtCore.Slot()
    def previous_month(self) -> None:
        """Shift the selected range one month earlier."""
        self.shift(-1)

    @QtCore.Slot()
    def next_month(self) -> None:
        """Shift the selected range one month later."""
        self.shift(1)
