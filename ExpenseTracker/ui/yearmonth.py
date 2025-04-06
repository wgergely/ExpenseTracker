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

from datetime import datetime

from PySide6 import QtCore, QtWidgets

from . import ui
from .actions import signals


class YearMonthPopup(QtWidgets.QFrame):
    """
    Popup widget for selecting a year-month combination.

    Displays navigation for the year and a grid of month buttons.

    Signals:
        yearMonthSelected(str): Emitted when a month is selected in "YYYY-MM" format.
    """
    yearMonthSelected = QtCore.Signal(str)

    def __init__(self, parent=None, initial_year=None, min_date=None, max_date=None):
        """
        Initialize the YearMonthPopup.

        Args:
            parent (QWidget, optional): Parent widget.
            initial_year (int, optional): Starting year; defaults to current year.
            min_date (str, optional): Minimum allowed date ("YYYY-MM").
            max_date (str, optional): Maximum allowed date ("YYYY-MM").
        """
        super().__init__(parent=parent)
        self.setWindowFlags(QtCore.Qt.Popup)
        self.current_year = initial_year if initial_year is not None else datetime.now().year
        self.min_date = min_date
        self.max_date = max_date
        # Convert dates to comparable integers (year*12 + month)
        self.min_val = int(min_date[:4]) * 12 + int(min_date[5:7]) if min_date else None
        self.max_val = int(max_date[:4]) * 12 + int(max_date[5:7]) if max_date else None
        ui.set_stylesheet(self)
        self._create_ui()

    def _create_ui(self):
        self.month_buttons = []
        layout = QtWidgets.QVBoxLayout(self)
        header_layout = QtWidgets.QHBoxLayout()

        self.prev_button = QtWidgets.QToolButton(self)
        self.prev_button.setText("<")
        self.prev_button.clicked.connect(self.decrement_year)
        header_layout.addWidget(self.prev_button)

        self.year_label = QtWidgets.QLabel(str(self.current_year), self)
        self.year_label.setAlignment(QtCore.Qt.AlignCenter)
        header_layout.addWidget(self.year_label)

        self.next_button = QtWidgets.QToolButton(self)
        self.next_button.setText(">")
        self.next_button.clicked.connect(self.increment_year)
        header_layout.addWidget(self.next_button)

        layout.addLayout(header_layout)

        grid_layout = QtWidgets.QGridLayout()
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        for i, name in enumerate(month_names):
            btn = QtWidgets.QPushButton(name, self)
            btn.clicked.connect(lambda checked, m=i + 1: self.month_clicked(m))
            self.month_buttons.append(btn)
            grid_layout.addWidget(btn, i // 4, i % 4)
        layout.addLayout(grid_layout)
        self.update_month_buttons()

    def update_month_buttons(self):
        """Enable or disable month buttons based on current_year limits."""
        for i, btn in enumerate(self.month_buttons):
            month = i + 1
            button_val = self.current_year * 12 + month
            disable = False
            if self.min_val is not None and button_val < self.min_val:
                disable = True
            if self.max_val is not None and button_val > self.max_val:
                disable = True
            btn.setEnabled(not disable)

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
        date_str = f"{self.current_year:04d}-{month:02d}"
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

        self.current_value = datetime.now().strftime("%Y-%m")
        self.min_date = None
        self.max_date = None

        self.setText(self.current_value)
        self.clicked.connect(self._show_popup)

    def _show_popup(self):
        self.popup = YearMonthPopup(
            self,
            initial_year=int(self.current_value[:4]),
            min_date=self.min_date,
            max_date=self.max_date
        )
        self.popup.yearMonthSelected.connect(self.set_value)
        pos = self.mapToGlobal(QtCore.QPoint(0, self.height()))
        self.popup.move(pos)
        self.popup.show()
        self.popup.raise_()
        self.popup.setFocus(QtCore.Qt.PopupFocusReason)

    @QtCore.Slot(str)
    def set_value(self, value):
        """Update the current value and emit change signal."""
        self.current_value = value
        self.setText(value)
        self.yearMonthChanged.emit(value)

    def get_value(self):
        """Return the current 'YYYY-MM' string."""
        return self.current_value


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

        ui.set_stylesheet(self)

        self._init_actions()
        self._init_min_max_dates()
        self._connect_signals()

    def _connect_signals(self):
        self.start_selector.yearMonthChanged.connect(self._start_changed)
        self.end_selector.yearMonthChanged.connect(self._end_changed)

    def _init_actions(self):
        button = QtWidgets.QToolButton(self)
        icon = ui.get_icon('btn_date')
        button.setIcon(icon)
        button.setDisabled(True)
        self.addWidget(button)

        self.start_selector = YearMonthSelector(self)
        self.start_selector.setObjectName('start_selector')
        self.addWidget(self.start_selector)

        self.addSeparator()

        self.end_selector = YearMonthSelector(self)
        self.end_selector.setObjectName('end_selector')
        self.addWidget(self.end_selector)

    def _init_min_max_dates(self):
        now = datetime.now()
        global_min_date = f"{now.year - 10}-01"
        global_max_date = f"{now.year}-{now.month:02d}"

        self.global_min_date = global_min_date
        self.global_max_date = global_max_date

        self.start_selector.min_date = global_min_date
        self.start_selector.max_date = global_max_date

        # End selector's limits: minimum follows start; maximum is global.
        self.end_selector.min_date = self.start_selector.get_value()
        self.end_selector.max_date = global_max_date

    def _date_str_to_int(self, date_str):
        return int(date_str[:4]) * 12 + int(date_str[5:7])

    def _start_changed(self, start_value):
        self.end_selector.min_date = start_value
        if self._date_str_to_int(self.end_selector.get_value()) < self._date_str_to_int(start_value):
            self.end_selector.set_value(start_value)
        self.emit_range_changed()

    def _end_changed(self, end_value):
        if self._date_str_to_int(self.start_selector.get_value()) > self._date_str_to_int(end_value):
            self.start_selector.set_value(end_value)
        self.emit_range_changed()

    @QtCore.Slot()
    def emit_range_changed(self):
        start = self.start_selector.get_value()
        start_int = self._date_str_to_int(start)

        end = self.end_selector.get_value()
        end_int = self._date_str_to_int(end)
        span = (end_int - start_int) + 1

        signals.dataRangeChanged.emit(self.start_selector.get_value(), span)

    def get_range(self) -> tuple[str, str]:
        """Return a tuple of (start_value, end_value)."""
        return (self.start_selector.get_value(), self.end_selector.get_value())

    def get_range_span(self) -> int:
        """Return the span of the range in months."""
        start_int = self._date_str_to_int(self.start_selector.get_value())
        end_int = self._date_str_to_int(self.end_selector.get_value())
        return (end_int - start_int) + 1
