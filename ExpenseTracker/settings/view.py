"""
View widgets for displaying settings.

.. seealso:: :mod:`settings.model`, :mod:`settings.editor`, :mod:`settings.settings`
"""

from PySide6 import QtWidgets


class HeadersView(QtWidgets.QWidget):
    """
    Displays and manages a table of ledger headers.
    """

    def __init__(self, model, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        self.table = QtWidgets.QTableView(self)
        self.table.setModel(model)
        self.table.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        layout.addWidget(self.table)
        self.setLayout(layout)


class CategoriesView(QtWidgets.QWidget):
    """
    Displays and manages categories in a table.
    """

    def __init__(self, model, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        self.table = QtWidgets.QTableView(self)
        self.table.setModel(model)
        layout.addWidget(self.table)
        self.setLayout(layout)


class DataMappingView(QtWidgets.QWidget):
    """
    Displays and manages data header mappings in a list view.
    """

    def __init__(self, model, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        self.list_view = QtWidgets.QListView(self)
        self.list_view.setModel(model)
        layout.addWidget(self.list_view)
        self.setLayout(layout)


class LedgerInfoView(QtWidgets.QWidget):
    """
    Displays ledger ID and sheet name fields.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        form_layout = QtWidgets.QFormLayout(self)
        self.ledger_id_edit = QtWidgets.QLineEdit(self)
        self.sheet_name_edit = QtWidgets.QLineEdit(self)
        form_layout.addRow("Ledger ID:", self.ledger_id_edit)
        form_layout.addRow("Sheet Name:", self.sheet_name_edit)
        self.setLayout(form_layout)
