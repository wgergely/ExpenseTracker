API Overview
============

This reference provides a concise overview of ExpenseTracker’s core Python packages.

* :mod:`ExpenseTracker.core` – Handles authentication, local data caching, Google Sheets integration, and syncing local changes back to the sheet.
* :mod:`ExpenseTracker.data` – Offers high-level functions, table models, and views to load, filter, summarize, and visualize expense and transaction data.
* :mod:`ExpenseTracker.log` – Integrates Python’s logging framework with a live Qt-based log viewer, complete with filtering and clear actions.
* :mod:`ExpenseTracker.settings` – Manages application settings, schema validation, built-in presets, and provides Qt editors for configuring preferences.
* :mod:`ExpenseTracker.ui` – Contains the PySide6 GUI components, including actions, the main window, styling constants, helper widgets, and custom chart views.

.. toctree::
   :maxdepth: 1

   core
   data
   log
   settings
   ui