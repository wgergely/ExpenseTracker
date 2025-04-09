"""
Module for formatting decimal and currency values using Babel.

"""
import logging
from typing import List

from babel import Locale, numbers
from babel.dates import get_date_format



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
        print(f'Error formatting currency: {e}')
        return str(value)


def get_strptime_fmt(locale: str) -> str:
    """
    Get the date format string for a given locale.

    Args:
        locale (str): Locale string, for example 'en_US'.

    Returns:
        str: The date format string.
    """
    if locale not in LOCALE_MAP:
        return '%d/%m/%Y'  # Default format

    pattern = get_date_format('short', Locale.parse(locale)).pattern
    return (
        pattern
        .replace('yyyy', '%Y')
        .replace('yy', '%y')
        .replace('MM', '%m')
        .replace('dd', '%d')
        .replace('d', '%-d')
    )
