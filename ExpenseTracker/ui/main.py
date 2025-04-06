from PySide6 import QtWidgets, QtCore

from . import ui
from .yearmonth import RangeSelectorBar
from ..data import view, model

main_window = None


def show_main_window():
    global main_window
    if main_window is None:
        main_window = MainWindow()
    main_window.show()
    return main_window


class MainWindow(QtWidgets.QMainWindow):
    """The primary window for the Expense Tracker.

    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName('ExpenseTrackerMainWindow')
        self.setWindowTitle('Expense Tracker')

        # Internal attributes for compatibility.
        self.toolbar = None
        self.range_selector = None
        self.expense_view = None
        self.transactions_view = None

        ui.set_stylesheet(self)

        self._create_ui()
        self._init_actions()
        self._connect_signals()

        QtCore.QTimer.singleShot(150, self.init_data)

    def _create_ui(self):
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ui.Size.Margin(0.5))

        # Action bar at the top.
        self.toolbar = QtWidgets.QToolBar(self)
        self.toolbar.setObjectName('ExpenseTrackerActionToolBar')
        layout.addWidget(self.toolbar, 1)

        self.range_selector = RangeSelectorBar(parent=self)
        self.range_selector.setObjectName('ExpenseTrackerRangeSelector')
        self.toolbar.addWidget(self.range_selector)

        # Expense view below the action bar.
        expense = view.ExpenseView(parent=central)
        expense.setObjectName('ExpenseTrackerExpenseView')
        layout.addWidget(expense, 1)
        self.expense_view = expense

    def _connect_signals(self):
        pass

    @QtCore.Slot()
    def init_data(self):
        year_month, _ = self.range_selector.get_range()

        span = self.range_selector.get_range_span()
        m = model.ExpenseModel(year_month, span=span)
        m.set_year_month(year_month)
        m.set_span(span)

        self.expense_view.setModel(m)

    def _init_actions(self):
        pass