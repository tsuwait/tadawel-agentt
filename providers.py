"""
providers.py
============
طبقة مزوّدي البيانات — تفصل المشروع عن أي مصدر واحد.

الفكرة: المشروع يطلب "تاريخ سعر السهم" ولا يهمه من أين جاء.
كل مزوّد يحاول بدوره، وأول من ينجح يفوز. لو سقط ياهو غداً،
تضيف مفتاح مزوّد آخر في .env ويشتغل المشروع بدون تعديل سطر واحد.

المزوّدون:
    1. Yahoo Finance   — مجاني، بلا مفتاح، يعمل فوراً (الافتراضي)
    2. Twelve Data     — يحتاج TWELVEDATA_API_KEY، خطة مجانية تغطي تداول
    3. EODHD           — يحتاج EODHD_API_KEY، تاريخ عميق
    4. FMP             — يحتاج FMP_API_KEY

كل مزوّد يعيد DataFrame بنفس الشكل:
    فهرس زمني (بدون منطقة زمنية) + أعمدة Open/High/Low/Close/Volume
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests

from config import REQUEST_TIMEOUT, USER_AGENT

COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """يوحّد شكل الجدول القادم من أي مزوّد."""
    if df is None or df.empty:
        return pd.DataFrame(columns=COLUMNS)

    if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    df.index = pd.to_datetime(df.index).normalize()

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA

    df = df[COLUMNS]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df.dropna(subset=["Close"])


class Provider(ABC):
    name = "base"

    @property
    def available(self) -> bool:
        return True

    @abstractmethod
    def history(self, symbol: str, years: int) -> pd.DataFrame:
        """symbol بصيغة ياهو، مثل 2222.SR"""


class YahooProvider(Provider):
    """المزوّد الافتراضي — لا يحتاج مفتاحاً."""

    name = "Yahoo Finance"

    def history(self, symbol: str, years: int) -> pd.DataFrame:
        import yfinance as yf

        df = yf.Ticker(symbol).history(
            period=f"{years}y", interval="1d", auto_adjust=False
        )
        return _normalize(df)


class TwelveDataProvider(Provider):
    name = "Twelve Data"
    BASE = "https://api.twelvedata.com/time_series"

    def __init__(self) -> None:
        self.key = os.getenv("TWELVEDATA_API_KEY", "")

    @property
    def available(self) -> bool:
        return bool(self.key)

    def history(self, symbol: str, years: int) -> pd.DataFrame:
        code = symbol.replace(".SR", "")
        resp = requests.get(
            self.BASE,
            params={
                "symbol": code, "exchange": "Tadawul", "interval": "1day",
                "outputsize": min(years * 260 + 20, 5000),
                "apikey": self.key, "format": "JSON",
            },
            headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT,
        )
        payload = resp.json()
        values = payload.get("values")
        if not values:
            return pd.DataFrame(columns=COLUMNS)

        df = pd.DataFrame(values)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime")
        df = df.rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        })
        for col in COLUMNS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return _normalize(df)


class EODHDProvider(Provider):
    name = "EODHD"
    BASE = "https://eodhd.com/api/eod"

    def __init__(self) -> None:
        self.key = os.getenv("EODHD_API_KEY", "")

    @property
    def available(self) -> bool:
        return bool(self.key)

    def history(self, symbol: str, years: int) -> pd.DataFrame:
        code = symbol.replace(".SR", "")
        start = (datetime.today() - timedelta(days=365 * years + 10)).strftime("%Y-%m-%d")
        resp = requests.get(
            f"{self.BASE}/{code}.SR",
            params={"api_token": self.key, "fmt": "json", "from": start},
            headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT,
        )
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            return pd.DataFrame(columns=COLUMNS)

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        })
        return _normalize(df)


class FMPProvider(Provider):
    name = "Financial Modeling Prep"
    BASE = "https://financialmodelingprep.com/api/v3/historical-price-full"

    def __init__(self) -> None:
        self.key = os.getenv("FMP_API_KEY", "")

    @property
    def available(self) -> bool:
        return bool(self.key)

    def history(self, symbol: str, years: int) -> pd.DataFrame:
        start = (datetime.today() - timedelta(days=365 * years + 10)).strftime("%Y-%m-%d")
        resp = requests.get(
            f"{self.BASE}/{symbol}",
            params={"apikey": self.key, "from": start},
            headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT,
        )
        rows = resp.json().get("historical", [])
        if not rows:
            return pd.DataFrame(columns=COLUMNS)

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        })
        return _normalize(df)


# ترتيب المحاولة — عدّله كما تشاء
_REGISTRY: list[Provider] = [
    YahooProvider(),
    TwelveDataProvider(),
    EODHDProvider(),
    FMPProvider(),
]

_LAST_SOURCE: dict[str, str] = {}


def active_providers() -> list[str]:
    return [p.name for p in _REGISTRY if p.available]


def last_source(symbol: str) -> Optional[str]:
    """من أي مزوّد جاءت آخر بيانات لهذا الرمز."""
    return _LAST_SOURCE.get(symbol)


def fetch_history(symbol: str, years: int = 3) -> pd.DataFrame:
    """يجرّب المزوّدين بالترتيب حتى ينجح أحدهم."""
    errors = []
    for provider in _REGISTRY:
        if not provider.available:
            continue
        try:
            df = provider.history(symbol, years)
            if not df.empty:
                _LAST_SOURCE[symbol] = provider.name
                return df
            errors.append(f"{provider.name}: لا توجد بيانات")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{provider.name}: {exc}")

    raise ValueError(
        f"ما قدرت أجيب بيانات {symbol} من أي مزوّد.\n" + "\n".join(errors)
    )
