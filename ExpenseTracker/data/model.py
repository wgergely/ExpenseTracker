"""
MonthlyExpenseModel Module

This module provides the MonthlyExpenseModel, a QAbstractTableModel for displaying
monthly expense data per category. The model automatically fetches data using the
ExpenseTracker data API and is designed for a PySide2 UI front-end.
"""

from PySide6 import QtCore

import pandas as pd
from .data import load_transactions, prepare_expenses_dataframe, get_category_breakdown


class MonthlyExpenseModel(QtCore.QAbstractTableModel):
    """
    MonthlyExpenseModel provides a table model for monthly expense data per category.

    Columns:
        0 - Category label.
        1 - Chart data (raw amount for custom delegate rendering).
        2 - Amount formatted as currency.

    Attributes:
        year_month (str): Target month in 'YYYY-MM' format.
        data_df (pd.DataFrame): DataFrame containing columns ['category', 'total_spend'].
    """

    def __init__(self, year_month, parent=None):
        """
        Initializes the MonthlyExpenseModel with the specified year and month.

        Args:
            year_month (str): Target month in 'YYYY-MM' format.
            parent (QObject, optional): Parent QObject.
        """
        super(MonthlyExpenseModel, self).__init__(parent)
        self.year_month = year_month
        self.data_df = pd.DataFrame(columns=['category', 'total_spend'])
        self.refresh_data()

    def refresh_data(self):
        """
        Refreshes the model data by fetching expense data for the current month.
        """
        transactions_df = load_transactions()
        expenses_df = prepare_expenses_dataframe(transactions_df, years_back=5)
        self.data_df = get_category_breakdown(expenses_df, self.year_month)
        self.layoutChanged.emit()

    def set_year_month(self, year_month):
        """
        Sets a new target month and refreshes the model data.

        Args:
            year_month (str): New target month in 'YYYY-MM' format.
        """
        self.year_month = year_month
        self.refresh_data()

    def rowCount(self, parent=QtCore.QModelIndex()):
        """
        Returns the number of rows in the model.

        Args:
            parent (QModelIndex): Parent index.

        Returns:
            int: Number of rows.
        """
        return len(self.data_df)

    def columnCount(self, parent=QtCore.QModelIndex()):
        """
        Returns the number of columns in the model.

        Args:
            parent (QModelIndex): Parent index.

        Returns:
            int: Number of columns (3).
        """
        return 3

    def data(self, index, role=QtCore.Qt.DisplayRole):
        """
        Returns data for the given index and role.

        Args:
            index (QModelIndex): Index of the item.
            role (int): Role for which data is requested.

        Returns:
            Any: Data for display or other roles.
        """
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()
        if row < 0 or row >= len(self.data_df):
            return None

        record = self.data_df.iloc[row]
        if role == QtCore.Qt.DisplayRole:
            if col == 0:
                return record['category']
            elif col == 1:
                # Return the raw total spend value for custom delegate rendering.
                return record['total_spend']
            elif col == 2:
                return f"€{record['total_spend']:.2f}"
        return None

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        """
        Provides header labels for the model.

        Args:
            section (int): Section index.
            orientation (Qt.Orientation): Horizontal or Vertical.
            role (int): Role for header data.

        Returns:
            Any: Header label if applicable.
        """
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            if section == 0:
                return "Category"
            elif section == 1:
                return "Chart"
            elif section == 2:
                return "Amount"
        return None
