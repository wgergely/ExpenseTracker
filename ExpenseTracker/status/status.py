import enum
import logging
from typing import Dict




class Status(enum.StrEnum):
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

    Status.LedgerConfigNotFound: 'Could not find the ledger config. Please check the settings.',
    Status.LedgerConfigInvalid: 'The ledger config seems to be incomplete, or contains invalid values. Please check the settings!',

    Status.ClientSecretNotFound: 'Could not find the google client secret. Have you set up a valid Google client secret?',
    Status.ClientSecretInvalid: 'Could not verify the client secret. Have you set up a valid Google client secret?',
    Status.CredsNotFound: 'Could not find the credentials. Please sign in to your Google account.',
    Status.CredsInvalid: 'Could not verify the credentials. Please sign in again to your Google account.',
    Status.NotAuthenticated: 'Authentication error. Try signing in again to your Google account.',

    Status.SpreadsheetIdNotConfigured: 'Could not find a valid spreadsheet id. Have you set up a valid spreadsheet id in the settings?',
    Status.SpreadsheetWorksheetNotConfigured: 'Worksheet name could not be found. Have you set  name in the settings?',

    Status.SpreadsheetNotFound: 'Could not find the spreadsheet. Have you set up a valid spreadsheet id in the settings?',
    Status.WorksheetNotFound: 'Could not find the worksheet. Have you set up a valid worksheet name in the settings?',

    Status.HeadersInvalid: 'Is the spreadsheet\'s headers set up correctly? Please check the settings!',
    Status.HeaderMappingInvalid: 'The header mapping seems to be incomplete, or contains invalid values. Please check the settings!',
    Status.CategoriesInvalid: 'The categories seem to be incomplete, or contain invalid values. Please check the settings!',

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
    """Exception raised when the status is unknown.

    """
    status = Status.UnknownStatus

    def __init__(self, message: str = None):
        self.status_message = get_message(self.status)
        exception_message = f'{self.status_message} {message}' if message else self.status_message
        super().__init__(exception_message)

        logging.error(exception_message)

        from ..ui.actions import signals
        signals.statusError.emit(self.status)


class UnknownException(BaseStatusException):
    pass


class LedgerConfigNotFoundException(BaseStatusException):
    status = Status.LedgerConfigNotFound


class LedgerConfigInvalidException(BaseStatusException):
    status = Status.LedgerConfigInvalid


class ClientSecretNotFoundException(BaseStatusException):
    status = Status.ClientSecretNotFound


class ClientSecretInvalidException(BaseStatusException):
    status = Status.ClientSecretInvalid


class CredsNotFoundException(BaseStatusException):
    status = Status.CredsNotFound


class CredsInvalidException(BaseStatusException):
    status = Status.CredsInvalid


class AuthenticationExceptionException(BaseStatusException):
    status = Status.NotAuthenticated


class SpreadsheetIdNotConfiguredException(BaseStatusException):
    status = Status.SpreadsheetIdNotConfigured


class SpreadsheetWorksheetNotConfiguredException(BaseStatusException):
    status = Status.SpreadsheetWorksheetNotConfigured


class SpreadsheetNotFoundException(BaseStatusException):
    status = Status.SpreadsheetNotFound


class WorksheetNotFoundException(BaseStatusException):
    status = Status.WorksheetNotFound


class ServiceUnavailableException(BaseStatusException):
    status = Status.ServiceUnavailable


class HeadersInvalidException(BaseStatusException):
    status = Status.HeadersInvalid


class HeaderMappingInvalidException(BaseStatusException):
    status = Status.HeaderMappingInvalid


class CategoriesInvalidException(BaseStatusException):
    status = Status.CategoriesInvalid


class CacheInvalidException(BaseStatusException):
    status = Status.CacheInvalid
