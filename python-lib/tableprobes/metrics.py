"""Values as DSS stores metrics: int, float, text, or a date given as (ISO text, DATE).

A value read from the database can be missing (NULL, read as None or NaN): the functions
return None then, and without_missing() drops those metrics, so a probe never stores an
empty value (a column of the other engine, statistics never gathered...).
"""
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from dataiku.metric import MetricDataTypes


def is_missing(value: Any) -> bool:
    """True for None, NaN and pandas' missing values."""
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def as_int(value: Any) -> Optional[int]:
    """value as an int (numbers read from the database can come as floats)."""
    if is_missing(value):
        return None
    return int(round(float(value)))


def as_float(value: Any, digits: int = 3) -> Optional[float]:
    """value as a float, rounded."""
    if is_missing(value):
        return None
    return round(float(value), digits)


def as_text(value: Any) -> Optional[str]:
    """value as a text, None when empty."""
    if is_missing(value):
        return None
    text = str(value).strip()
    if text == "":
        return None
    return text


def as_date(value: Any) -> Optional[Tuple[str, Any]]:
    """An ISO 8601 UTC text (2026-10-28T09:15:00.000Z) as a DSS date metric."""
    text = as_text(value)
    if text is None:
        return None
    return (text, MetricDataTypes.DATE)


def without_missing(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """metrics without those whose value is missing."""
    kept = {}
    for name in metrics:
        if metrics[name] is not None:
            kept[name] = metrics[name]
    return kept


def keep_ticked(metrics: Dict[str, Any], ticked: List[str]) -> Dict[str, Any]:
    """The ticked metrics only."""
    kept = {}
    for name in ticked:
        if name in metrics:
            kept[name] = metrics[name]
    return kept
