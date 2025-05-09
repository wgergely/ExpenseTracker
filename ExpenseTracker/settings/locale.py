"""Locale utilities for formatting numbers, currency, and dates.

Provides:
    - get_currency_from_locale: map locale to default currency code.
    - format_float: format decimal numbers per locale conventions.
    - format_currency_value: format currency values based on locale.
    - parse_date: parse date strings into datetime objects.
    - CURRENCY_MAP and LOCALE_MAP for default mappings.
"""
import datetime
import logging
from datetime import date
from typing import List

from babel import Locale, numbers, dates

CURRENCY_MAP: dict[str, str] = {
    'US': 'USD',
    'GB': 'GBP',
    'DE': 'EUR',
    'FR': 'EUR',
    'BE': 'EUR',
    'IT': 'EUR',
    'ES': 'EUR',
    'JP': 'JPY',
    'CA': 'CAD',
    'AU': 'AUD',
    'IN': 'INR',
    'BR': 'BRL',
    'RU': 'RUB',
    'CN': 'CNY',
    'KR': 'KRW',
    'DK': 'DKK',
    'SE': 'SEK',
    'NO': 'NOK',
    'FI': 'EUR',
    'HU': 'HUF',
    'MX': 'MXN',
    'ID': 'IDR',
    'SA': 'SAR',
    'ZA': 'ZAR',
    'TR': 'TRY',
    'NL': 'EUR',
}

LOCALE_MAP: List[str] = [
    "en_GB",
    "de_DE",
    "es_ES",
    "hu_HU",
    "ar_SA",
    "da_DK",
    "en_AU",
    "en_CA",
    "en_IN",
    "en_US",
    "en_ZA",
    "es_MX",
    "fi_FI",
    "fr_BE",
    "fr_FR",
    "id_ID",
    "it_IT",
    "ja_JP",
    "ko_KR",
    "nb_NO",
    "nl_NL",
    "pt_BR",
    "ru_RU",
    "sv_SE",
    "tr_TR",
    "zh_CN",
]


def get_currency_from_locale(locale: str) -> str:
    """
    Retrieve the default currency code based on the locale's territory.

    Args:
        locale (str): Locale string, e.g. 'fr_FR'.

    Returns:
        str: Currency code such as 'EUR'. Defaults to 'EUR' if the territory is unknown.
    """
    parts = locale.split('_')
    if len(parts) < 2:
        return 'EUR'
    country_code = parts[1]
    return CURRENCY_MAP.get(country_code, 'EUR')


def format_float(value: float, locale: str) -> str:
    """
    Format a float as a decimal string according to the locale conventions.

    Args:
        value (float): The numeric value to be formatted.
        locale (str): Locale string, e.g. 'en_US'.

    Returns:
        str: The formatted decimal string.
    """
    try:
        locale_obj = Locale.parse(locale)
        formatted_value = numbers.format_decimal(value, locale=locale_obj)
        return formatted_value
    except Exception as e:
        logging.debug(f'Error formatting float: {value} for locale: {locale}: {e}')
        return str(value)


def format_currency_value(value: float, locale: str) -> str:
    """
    Format a float as a currency string based on the locale's default currency.

    The default currency is determined by the territory extracted from the locale.

    Args:
        value (float): The numeric value to be formatted.
        locale (str): Locale string, e.g. 'fr_FR'.

    Returns:
        str: The formatted currency string.
    """
    try:
        currency_code = get_currency_from_locale(locale)
        locale_obj = Locale.parse(locale)
        formatted_currency = numbers.format_currency(value, currency=currency_code, locale=locale_obj)
        return formatted_currency
    except Exception as e:
        logging.debug(f'Error formatting currency: {value} for locale: {locale}, error: {e}')
        return str(value)


def parse_date(date_str: str, locale: str = None, format: str = 'short') -> date:
    """
    Parse a date string into a datetime object based on the locale.

    Args:
        date_str (str): The date string to be parsed.
        locale (str, optional): Locale string, e.g. 'en_US'. Defaults to None.
        format: (str, optional): The format of the date string. Defaults to 'short'.

    Returns:
        datetime.datetime: The parsed datetime object.
    """
    return dates.parse_date(date_str, locale=locale, format=format)
