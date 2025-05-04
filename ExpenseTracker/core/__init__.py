"""
Core package for ExpenseTracker providing essential functionality.

This package includes:

- :mod:`ExpenseTracker.core.auth` – Google OAuth2 authentication and credential management.
- :mod:`ExpenseTracker.core.database` – Local SQLite cache and data access for ledger data.
- :mod:`ExpenseTracker.core.service` – Google Sheets API integration with asynchronous fetch, verify, and utility operations.
- :mod:`ExpenseTracker.core.sync` – Queued local edit management and optimistic synchronization with the remote sheet.
"""
