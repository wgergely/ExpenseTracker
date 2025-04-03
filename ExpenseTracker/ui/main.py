from PySide6 import QtWidgets, QtCore

from . import ui
from . import toolbar
from ..data import view
from ..data import model

main_widget = None


def show_main_widget():
    """Show the main widget."""
    global main_widget
    if main_widget is None:
        main_widget = MainWidget()
    main_widget.show()
    return main_widget


class MainWidget(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setWindowTitle('Expense Tracker')
        self.setObjectName('ExpenseTrackerMainWidget')

        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Preferred
        )

        self.action_bar = None
        self.expense_view = None

        ui.set_stylesheet(self)

        self._initialized = False

        self._create_ui()
        self._connect_signals()

    def _create_ui(self):
        QtWidgets.QVBoxLayout(self)

        o = ui.Size.Margin(1.0)
        self.layout().setContentsMargins(o, o, o, o)
        self.layout().setSpacing(o)

        self.action_bar = toolbar.ActionToolBar(parent=self)
        self.action_bar.setObjectName('ExpenseTrackerActionToolBar')

        self.layout().addWidget(self.action_bar, 1)

        self.expense_view = view.MonthlyExpenseView(parent=self)
        self.expense_view.setObjectName('ExpenseTrackerMonthlyExpenseView')

        self.layout().addWidget(self.expense_view, 1)

    def _connect_signals(self):
        pass

    def showEvent(self, event: QtCore.QEvent) -> None:
        """Handles the show event to initialize the widget."""
        if self._initialized:
            super().showEvent(event)
            return

        self._init_data()

    def _init_data(self):
        year_month, _ = self.action_bar.range_selector.get_range()
        span = self.action_bar.range_selector.get_range_span()

        m = model.ExpenseModel(year_month, span=span)
        m.set_year_month(year_month)
        m.set_span(span)

        self.expense_view.setModel(m)


    def sizeHint(self):
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.5),
            ui.Size.DefaultHeight(1.5)
        )
