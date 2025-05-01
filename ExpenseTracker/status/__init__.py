"""Status package: enums and exceptions for handling application state and errors.

This package defines:
    - Status: a StrEnum of possible application states
    - STATUS_MESSAGE: default user-facing messages per status
    - get_message: helper to retrieve messages for statuses
    - BaseStatusException: base exception for status-driven error handling
    - Specific exceptions (e.g., LedgerConfigNotFoundException) tagged with statuses
"""
