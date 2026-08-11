
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        result = pd.isna(value)
        if isinstance(result, bool):
            return result
    except (TypeError, ValueError):
        pass
    return False


def clean_str(value: Any, *, max_len: int | None = None) -> str | None:
    if is_missing(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len] if max_len else text


def clean_int(value: Any, *, positive_only: bool = False) -> int | None:
    if is_missing(value):
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return None
    if positive_only and number <= 0:
        return None
    return number


def clean_decimal(value: Any) -> Decimal | None:
    if is_missing(value):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def clean_bool(value: Any) -> bool | None:
    if is_missing(value):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def clean_date(value: Any) -> date | None:
    dt = to_utc_naive(value)
    return dt.date() if dt else None


def td_to_us(value: Any) -> int | None:
    """Convert pandas/python timedelta-like values to integer microseconds."""
    if is_missing(value):
        return None
    if isinstance(value, pd.Timedelta):
        return int(value.total_seconds() * 1_000_000)
    if isinstance(value, timedelta):
        return int(value.total_seconds() * 1_000_000)
    try:
        td = pd.to_timedelta(value)
        if pd.isna(td):
            return None
        return int(td.total_seconds() * 1_000_000)
    except (TypeError, ValueError, OverflowError):
        return None


def to_utc_naive(value: Any) -> datetime | None:
    """
    Convert timestamps to UTC and strip tzinfo for storage in MySQL DATETIME.
    Naive input is assumed to already be UTC.
    """
    if is_missing(value):
        return None
    try:
        ts = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if pd.isna(ts):
        return None
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.to_pydatetime()


def utc_naive_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def slugify(value: Any, fallback: str) -> str:
    text = clean_str(value) or fallback
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text or fallback


def first_present(row: Any, *keys: str) -> Any:
    for key in keys:
        try:
            value = row.get(key)
        except AttributeError:
            try:
                value = row[key]
            except (KeyError, TypeError):
                continue
        if not is_missing(value):
            return value
    return None


def list_last(value: Any) -> Any:
    if is_missing(value):
        return None
    if isinstance(value, (list, tuple)):
        return value[-1] if value else None
    return value


def session_time_to_datetime(session: Any, value: Any) -> datetime | None:
    """
    Convert a FastF1 session-relative timedelta to an absolute UTC timestamp.

    FastF1 exposes t0_date only when telemetry is loaded. This project normally
    disables telemetry, so we use the documented `session.date` and
    `session_start_time` as a fallback anchor.
    """
    if is_missing(value):
        return None

    try:
        delta = pd.to_timedelta(value)
    except (TypeError, ValueError):
        return None

    # Most accurate anchor, if telemetry happened to be loaded.
    try:
        t0_date = getattr(session, "t0_date", None)
        if t0_date is not None and not is_missing(t0_date):
            return to_utc_naive(pd.Timestamp(t0_date) + delta)
    except (AttributeError, ValueError, TypeError):
        pass

    # Fallback: session.date is the session start; session_start_time is the
    # stream-relative value at that start.
    session_date = getattr(session, "date", None)
    session_start = getattr(session, "session_start_time", None)
    if session_date is None or is_missing(session_date):
        return None
    try:
        start_delta = pd.to_timedelta(session_start) if not is_missing(session_start) else pd.Timedelta(0)
        return to_utc_naive(pd.Timestamp(session_date) + (delta - start_delta))
    except (TypeError, ValueError, OverflowError):
        return None
