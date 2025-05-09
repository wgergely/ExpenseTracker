"""Status definitions and exceptions for ExpenseTracker.

This module provides:
    - Status: enumeration of possible application states
    - STATUS_MESSAGE: user-facing messages for each status
    - get_message: retrieve the message for a status
    - BaseStatusException: base exception carrying a Status
    - Specific exceptions (e.g., LedgerConfigNotFoundException) for error handling in services
"""
import enum
import logging
from typing import Dict


class Status(enum.StrEnum):
    """Enumeration of application status codes."""
    UnknownStatus = enum.auto()
    Okay = enum.auto()

    # Config status
    LedgerConfigNotFound = enum.auto()
    LedgerConfigInvalid = enum.auto()

    # Authentication status
    ClientSecretNotFound = enum.auto()
    ClientSecretInvalid = enum.auto()
    CredsNotFound = enum.auto()
    CredsInvalid = enum.auto()
    NotAuthenticated = enum.auto()

    # Spreadsheet access status
    SpreadsheetIdNotConfigured = enum.auto()
    SpreadsheetWorksheetNotConfigured = enum.auto()

    SpreadsheetNotFound = enum.auto()
    WorksheetNotFound = enum.auto()
    # Empty spreadsheet (no sheets or no data)
    SpreadsheetEmpty = enum.auto()

    # Service status
    ServiceUnavailable = enum.auto()

    # Configuration status
    HeadersInvalid = enum.auto()
    HeaderMappingInvalid = enum.auto()
    CategoriesInvalid = enum.auto()

    CacheInvalid = enum.auto()


STATUS_MESSAGE: Dict[Status, str] = {
    Status.UnknownStatus: 'Unknown status. Please check the settings.',
    Status.Okay: 'Everything is okay.',

    Status.LedgerConfigNotFound: 'Could not find the ledger config.',
    Status.LedgerConfigInvalid: 'The ledger config seems to be incomplete, or contains invalid values.',

    Status.ClientSecretNotFound: 'Could not find the google client secret. Have you set up a valid Google client secret?',
    Status.ClientSecretInvalid: 'Could not verify the client secret. Have you set up a valid Google client secret?',
    Status.CredsNotFound: 'Could not find the credentials. Please sign in to your Google account.',
    Status.CredsInvalid: 'Could not verify the credentials. Please sign in again to your Google account.',
    Status.NotAuthenticated: 'Authentication error. Try signing in again to your Google account.',

    Status.SpreadsheetIdNotConfigured: 'Could not find a valid spreadsheet id. Have you set up a valid spreadsheet id in the settings?',
    Status.SpreadsheetWorksheetNotConfigured: 'Worksheet name could not be found. Have you set  name in the settings?',

    Status.SpreadsheetNotFound: 'Could not find the spreadsheet. Have you set up a valid spreadsheet id in the settings?',
    Status.WorksheetNotFound: 'Could not find the worksheet. Have you set up a valid worksheet name in the settings?',
    Status.SpreadsheetEmpty: 'The spreadsheet is empty. No data found.',

    Status.HeadersInvalid: 'Is the spreadsheet\'s headers set up correctly?',
    Status.HeaderMappingInvalid: 'The header mapping seems to be incomplete, or contains invalid values.',
    Status.CategoriesInvalid: 'The categories seem to be incomplete, or contain invalid values.',

    Status.ServiceUnavailable: 'Google Sheets service is unavailable. Please check your connection.',
    Status.CacheInvalid: 'The cache is invalid. Try fetching the data from the source again.',

}


def get_message(status: Status) -> str:
    """
    Get the message for a given status.

    Args:
        status (Status): The status enum.

    Returns:
        str: The message associated with the status.
    """
    return STATUS_MESSAGE.get(status, 'Unknown status')


class BaseStatusException(Exception):
    """Base exception for status-based errors in ExpenseTracker.

    Attributes:
        status (Status): Status code associated with this error.
        status_message (str): User-facing message for the status.

    Args:
        message (str): Optional additional context for the error.
    """
    status = Status.UnknownStatus

    def __init__(self, message: str = None):
        self.status_message = get_message(self.status)
        exception_message = f'{self.status_message} {message}' if message else self.status_message
        super().__init__(exception_message)

        logging.error(exception_message)

        from ..ui.actions import signals
        signals.error.emit(message or self.status_message)


class UnknownException(BaseStatusException):
    """Exception for an unknown error during status processing."""
    pass


class LedgerConfigNotFoundException(BaseStatusException):
    """Exception raised when the ledger configuration file cannot be found."""
    status = Status.LedgerConfigNotFound


class LedgerConfigInvalidException(BaseStatusException):
    """Exception raised when the ledger configuration is invalid or malformed."""
    status = Status.LedgerConfigInvalid


class ClientSecretNotFoundException(BaseStatusException):
    """Exception raised when the Google OAuth client secret file cannot be found."""
    status = Status.ClientSecretNotFound


class ClientSecretInvalidException(BaseStatusException):
    """Exception raised when the Google OAuth client secret is invalid or malformed."""
    status = Status.ClientSecretInvalid


class CredsNotFoundException(BaseStatusException):
    """Exception raised when stored Google credentials cannot be found."""
    status = Status.CredsNotFound


class CredsInvalidException(BaseStatusException):
    """Exception raised when stored Google credentials are invalid or expired."""
    status = Status.CredsInvalid


class AuthenticationExceptionException(BaseStatusException):
    """Exception raised when user is not authenticated with Google services."""
    status = Status.NotAuthenticated


class SpreadsheetIdNotConfiguredException(BaseStatusException):
    """Exception raised when the spreadsheet ID is not configured in settings."""
    status = Status.SpreadsheetIdNotConfigured


class SpreadsheetWorksheetNotConfiguredException(BaseStatusException):
    """Exception raised when the worksheet name is not configured in settings."""
    status = Status.SpreadsheetWorksheetNotConfigured


class SpreadsheetNotFoundException(BaseStatusException):
    """Exception raised when the specified spreadsheet cannot be accessed."""
    status = Status.SpreadsheetNotFound


class WorksheetNotFoundException(BaseStatusException):
    """Exception raised when the specified worksheet cannot be accessed."""
    status = Status.WorksheetNotFound

    # Exception for an empty spreadsheet (no data)


class SpreadsheetEmptyException(BaseStatusException):
    """Exception raised when the specified spreadsheet contains no data."""
    status = Status.SpreadsheetEmpty


class ServiceUnavailableException(BaseStatusException):
    """Exception raised when the Google Sheets service is unavailable."""
    status = Status.ServiceUnavailable


class HeadersInvalidException(BaseStatusException):
    """Exception raised when spreadsheet headers are invalid or misconfigured."""
    status = Status.HeadersInvalid


class HeaderMappingInvalidException(BaseStatusException):
    """Exception raised when header mapping configuration is invalid."""
    status = Status.HeaderMappingInvalid


class CategoriesInvalidException(BaseStatusException):
    """Exception raised when category configuration is invalid or incomplete."""
    status = Status.CategoriesInvalid


class CacheInvalidException(BaseStatusException):
    """Exception raised when the local data cache is invalid or corrupted."""
    status = Status.CacheInvalid
