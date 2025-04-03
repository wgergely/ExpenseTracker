from PySide6 import QtWidgets, QtCore
from . import ui, toolbar
from ..data import view, model

main_window = None

def show_main_window():
    """Show the main window for the Expense Tracker."""
    global main_window
    if main_window is None:
        main_window = MainWindow()
    main_window.show()
    return main_window

class MainWindow(QtWidgets.QMainWindow):
    """
    MainWindow is the primary window for the Expense Tracker.

    It provides a central widget containing the action bar and expense view.
    Additional dockable components (e.g. TransactionsDialog) are added on demand
    using the default QMainWindow docking functionality.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ExpenseTrackerMainWindow")
        self.setWindowTitle("Expense Tracker")
        ui.set_stylesheet(self)

        # Internal attributes for compatibility.
        self._expense_view = None
        self._transactions_view = None

        self._create_ui()
        self._connect_signals()
        self._init_data()

    def _create_ui(self):
        """Set up the central UI structure."""
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ui.Size.Margin(0.5))

        # Action bar at the top.
        self.action_bar = toolbar.ActionToolBar(parent=central)
        self.action_bar.setObjectName("ExpenseTrackerActionToolBar")
        layout.addWidget(self.action_bar, 1)

        # Expense view below the action bar.
        expense = view.ExpenseView(parent=central)
        expense.setObjectName("ExpenseTrackerExpenseView")
        layout.addWidget(expense, 1)
        self._expense_view = expense

    def _connect_signals(self):
        """Connect global signals."""
        pass

    def _init_data(self):
        """Initialize data for the expense view."""
        year_month, _ = self.action_bar.range_selector.get_range()
        span = self.action_bar.range_selector.get_range_span()
        m = model.ExpenseModel(year_month, span=span)
        m.set_year_month(year_month)
        m.set_span(span)
        self._expense_view.setModel(m)

    @property
    def expense_view(self):
        """Property for compatibility: returns the expense view widget."""
        return self._expense_view

    @property
    def transactions_view(self):
        """Property for compatibility: returns the transactions dialog dock widget."""
        return self._transactions_view

    @transactions_view.setter
    def transactions_view(self, widget):
        self._transactions_view = widget
