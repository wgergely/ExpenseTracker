"""
ExpenseTracker data package: analytics, models, and views.

This package provides:

- :mod:`ExpenseTracker.data.data` – High-level API for loading, filtering, and summarizing expense data from the local cache (via :func:`ExpenseTracker.data.data.get_data`, :func:`ExpenseTracker.data.data.get_trends`) with settings-driven metadata.
- :mod:`ExpenseTracker.data.model` – Qt table models (:class:`ExpenseTracker.data.model.ExpenseModel`, :class:`ExpenseTracker.data.model.TransactionModel`) for displaying categorized summaries and transaction lists.
- :mod:`ExpenseTracker.data.view` – Qt views and delegates for rendering charts, tables, and interactive widgets to visualize expense analytics.
"""
