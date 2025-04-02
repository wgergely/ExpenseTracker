from PySide6 import QtWidgets, QtCore

from . import ui


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

        self.month_picker_widget = None
        self.span_picker_widget = None

        self.expense_view_buttons_bar = None
        self.expense_view = None

        self._create_ui()
        self._connect_signals()

    def _create_ui(self):
        QtWidgets.QVBoxLayout(self)

        o = ui.Size.Margin(1.0)
        self.layout().setContentsMargins(o, o, o, o)
        self.layout().setSpacing(o)

        self.month_picker_widget

    def _connect_signals(self):
        pass

    def sizeHint(self):
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.5),
            ui.Size.DefaultHeight(1.5)
        )
