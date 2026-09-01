"""
tadawul_data.py
===============
طبقة البيانات للسوق السعودي (تداول).

لا تتحدث مع أي مزوّد مباشرة — تمر عبر providers.py،
فلو سقط مصدر أو أضفت مصدراً جديداً، هذا الملف لا يتغير.

الدوال العامة:
    resolve_symbol(query)   تحويل اسم/رقم إلى رمز موحّد
    search_stocks(query)    بحث يرجع نتائج محتملة
    get_history(symbol)     البيانات التاريخية الخام
    get_snapshot(symbol)    السعر الحالي مقابل أسبوع/شهر/سنة
    get_range(symbol,a,b)   أداء بين تاريخين
    get_profile(symbol)     معلومات الشركة
    compare_stocks(list)    مقارنة عدة أسهم
"""

from __future__ import annotations

import re
import time
from datetime import date, datetime
from typing import Any, Optional

import pandas as pd
import requests
from dateutil.relativedelta import relativedelta

import providers
from config import (
    CACHE_TTL_SECONDS,
    CURRENCY,
    DEFAULT_HISTORY_YEARS,
    REQUEST_TIMEOUT,
    USER_AGENT,
    YAHOO_SUFFIX,
)
from symbols import (
    ALIASES,
    INDICES,
    SYMBOLS,
    UNIVERSE_META,
    strip_arabic,
    universe_status,
)

__all__ = [
    "SYMBOLS", "INDICES", "UNIVERSE_META", "universe_status",
    "normalize_symbol", "resolve_symbol", "search_stocks",
    "get_history", "get_snapshot", "get_range", "get_closing_series",
    "get_profile", "compare_stocks", "data_source_for",
]

# ───────────────────────── كاش بسيط ─────────────────────────
_CACHE: dict[str, tuple[float, Any]] = {}


def _cache_get(key: str):
    hit = _CACHE.get(key)
    if hit and (time.time() - hit[0]) < CACHE_TTL_SECONDS:
        return hit[1]
    return None


def _cache_set(key: str, value):
    _CACHE[key] = (time.time(), value)
    return value


# ───────────────────────── الرموز ─────────────────────────
def normalize_symbol(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("^"):
        return raw
    raw = raw.upper().replace(YAHOO_SUFFIX, "")
    return f"{raw}{YAHOO_SUFFIX}"


def _entry(code: str) -> dict:
    name_ar, name_en = SYMBOLS.get(code, (f"شركة {code}", ""))
    return {"symbol": normalize_symbol(code), "code": code,
            "name_ar": name_ar, "name_en": name_en}


def resolve_symbol(query: str) -> Optional[dict]:
    """يحوّل اسم شركة أو رقمها إلى رمز موحّد."""
    if not query:
        return None
    q = str(query).strip()

    # رقم رباعي مباشر — يعمل حتى لو الشركة غير مذكورة في أي قائمة
    m = re.fullmatch(r"(\d{4})(\.SR)?", q, flags=re.IGNORECASE)
    if m:
        return _entry(m.group(1))

    if q.startswith("^"):
        name_ar, name_en = INDICES.get(q, (q, ""))
        return {"symbol": q, "code": q, "name_ar": name_ar, "name_en": name_en}

    key = strip_arabic(q)

    # اختصارات
    for alias, code in ALIASES.items():
        if strip_arabic(alias) == key:
            if code.startswith("^"):
                name_ar, name_en = INDICES[code]
                return {"symbol": code, "code": code,
                        "name_ar": name_ar, "name_en": name_en}
            return _entry(code)

    # مطابقة تامة ثم جزئية على الأسماء
    for code, (name_ar, name_en) in SYMBOLS.items():
        if strip_arabic(name_ar) == key or name_en.lower() == key:
            return _entry(code)
    for code, (name_ar, name_en) in SYMBOLS.items():
        if key and (key in strip_arabic(name_ar)
                    or (name_en and key in name_en.lower())):
            return _entry(code)

    # آخر محاولة: بحث ياهو
    hits = _yahoo_search(q)
    if hits:
        code = hits[0]["symbol"].replace(YAHOO_SUFFIX, "")
        entry = _entry(code)
        if entry["name_ar"].startswith("شركة "):
            entry["name_ar"] = hits[0].get("name", entry["name_ar"])
        return entry

    return None


def _yahoo_search(query: str, limit: int = 8) -> list[dict]:
    cache_key = f"search::{query}::{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        resp = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": query, "quotesCount": 20, "newsCount": 0},
            headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        quotes = resp.json().get("quotes", [])
    except Exception:  # noqa: BLE001
        return []

    out = []
    for q in quotes:
        sym = q.get("symbol", "")
        if not sym.endswith(YAHOO_SUFFIX):
            continue
        out.append({"symbol": sym,
                    "name": q.get("longname") or q.get("shortname") or sym})
        if len(out) >= limit:
            break
    return _cache_set(cache_key, out)


def search_stocks(query: str, limit: int = 10) -> list[dict]:
    """بحث شامل في القائمة المحلية ثم ياهو."""
    key = strip_arabic(query)
    results: list[dict] = []
    seen: set[str] = set()

    if not key:
        return []

    exact, partial = [], []
    for code, (name_ar, name_en) in SYMBOLS.items():
        n_ar, n_en = strip_arabic(name_ar), name_en.lower()
        if n_ar == key or n_en == key or code == key:
            exact.append(code)
        elif key in n_ar or (name_en and key in n_en) or code.startswith(key):
            partial.append(code)

    for code in exact + partial:
        if code in seen:
            continue
        seen.add(code)
        item = _entry(code)
        item["source"] = "local"
        results.append(item)
        if len(results) >= limit:
            return results

    for r in _yahoo_search(query, limit):
        code = r["symbol"].replace(YAHOO_SUFFIX, "")
        if code in seen:
            continue
        seen.add(code)
        item = _entry(code)
        if item["name_ar"].startswith("شركة "):
            item["name_ar"] = r["name"]
        item["source"] = "yahoo"
        results.append(item)
        if len(results) >= limit:
            break

    return results


# ───────────────────────── البيانات ─────────────────────────
def get_history(symbol: str, years: int = DEFAULT_HISTORY_YEARS) -> pd.DataFrame:
    """بيانات تاريخية يومية عبر طبقة المزوّدين، مع كاش."""
    symbol = symbol if symbol.startswith("^") else normalize_symbol(symbol)
    cache_key = f"hist::{symbol}::{years}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    df = providers.fetch_history(symbol, years)
    if df.empty:
        raise ValueError(
            f"ما لقيت بيانات للرمز {symbol}. تأكد من الرقم أو أن السهم مدرج حالياً."
        )
    return _cache_set(cache_key, df)


def data_source_for(symbol: str) -> Optional[str]:
    """اسم المزوّد الذي أعطى آخر بيانات لهذا الرمز."""
    return providers.last_source(
        symbol if symbol.startswith("^") else normalize_symbol(symbol)
    )


def _price_on_or_before(df: pd.DataFrame, target) -> Optional[dict]:
    target = pd.Timestamp(target).normalize()
    sub = df.loc[:target]
    if sub.empty:
        return None
    row = sub.iloc[-1]
    return {"date": sub.index[-1].strftime("%Y-%m-%d"),
            "close": round(float(row["Close"]), 2)}


def _pct(new: float, old: float) -> Optional[float]:
    if not old:
        return None
    return round((new - old) / old * 100, 2)


def get_snapshot(symbol_or_name: str) -> dict:
    """السعر الحالي مقابل أسعار الفترات السابقة."""
    resolved = resolve_symbol(symbol_or_name)
    if not resolved:
        return {"error": f"ما قدرت أحدد سهم باسم أو رقم '{symbol_or_name}'."}

    try:
        df = get_history(resolved["symbol"], years=max(DEFAULT_HISTORY_YEARS, 2))
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}

    last_date = df.index[-1]
    last_close = round(float(df["Close"].iloc[-1]), 2)

    targets = {
        "يوم_سابق": last_date - relativedelta(days=1),
        "أسبوع": last_date - relativedelta(weeks=1),
        "شهر": last_date - relativedelta(months=1),
        "3_أشهر": last_date - relativedelta(months=3),
        "6_أشهر": last_date - relativedelta(months=6),
        "سنة": last_date - relativedelta(years=1),
        "بداية_العام": pd.Timestamp(date(last_date.year, 1, 1)),
    }

    periods = {}
    for label, target in targets.items():
        point = _price_on_or_before(df, target)
        if not point:
            periods[label] = {"available": False,
                              "note": "لا توجد بيانات لهذه الفترة"}
            continue
        periods[label] = {
            "available": True,
            "تاريخ_الإغلاق": point["date"],
            "السعر": point["close"],
            "الفرق": round(last_close - point["close"], 2),
            "نسبة_التغير_%": _pct(last_close, point["close"]),
        }

    year_df = df.loc[df.index >= (last_date - relativedelta(years=1))]

    return {
        "الرمز": resolved["symbol"],
        "رقم_الشركة": resolved["code"],
        "الاسم": resolved["name_ar"],
        "الاسم_بالإنجليزي": resolved["name_en"],
        "العملة": CURRENCY,
        "آخر_إغلاق": {"التاريخ": last_date.strftime("%Y-%m-%d"), "السعر": last_close},
        "المقارنات": periods,
        "أعلى_سعر_خلال_سنة": round(float(year_df["High"].max()), 2),
        "أدنى_سعر_خلال_سنة": round(float(year_df["Low"].min()), 2),
        "المصدر": data_source_for(resolved["symbol"]) or "غير معروف",
        "ملاحظة": "الأسعار قد تتأخر عن السوق الفعلي.",
    }


def get_range(symbol_or_name: str, start: str, end: Optional[str] = None) -> dict:
    resolved = resolve_symbol(symbol_or_name)
    if not resolved:
        return {"error": f"ما قدرت أحدد سهم باسم أو رقم '{symbol_or_name}'."}

    end = end or datetime.today().strftime("%Y-%m-%d")
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    years_needed = max(1, int((datetime.today() - start_ts.to_pydatetime()).days / 365) + 1)

    try:
        df = get_history(resolved["symbol"], years=years_needed)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}

    window = df.loc[start_ts:end_ts]
    if window.empty:
        return {"error": "ما فيه بيانات تداول في هذه الفترة."}

    first_close = round(float(window["Close"].iloc[0]), 2)
    last_close = round(float(window["Close"].iloc[-1]), 2)

    return {
        "الرمز": resolved["symbol"], "الاسم": resolved["name_ar"],
        "من": window.index[0].strftime("%Y-%m-%d"),
        "إلى": window.index[-1].strftime("%Y-%m-%d"),
        "سعر_البداية": first_close, "سعر_النهاية": last_close,
        "التغير": round(last_close - first_close, 2),
        "نسبة_التغير_%": _pct(last_close, first_close),
        "أعلى_سعر": round(float(window["High"].max()), 2),
        "تاريخ_الأعلى": window["High"].idxmax().strftime("%Y-%m-%d"),
        "أدنى_سعر": round(float(window["Low"].min()), 2),
        "تاريخ_الأدنى": window["Low"].idxmin().strftime("%Y-%m-%d"),
        "عدد_أيام_التداول": int(len(window)),
        "متوسط_السعر": round(float(window["Close"].mean()), 2),
        "العملة": CURRENCY,
    }


def get_closing_series(symbol_or_name: str, years: int = 1) -> dict:
    resolved = resolve_symbol(symbol_or_name)
    if not resolved:
        return {"error": f"ما قدرت أحدد سهم باسم أو رقم '{symbol_or_name}'."}
    try:
        df = get_history(resolved["symbol"], years=max(1, years))
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    cutoff = df.index[-1] - relativedelta(years=years)
    df = df.loc[df.index >= cutoff]
    return {
        "الرمز": resolved["symbol"], "الاسم": resolved["name_ar"],
        "التواريخ": [d.strftime("%Y-%m-%d") for d in df.index],
        "الإغلاق": [round(float(v), 2) for v in df["Close"]],
    }


def get_profile(symbol_or_name: str) -> dict:
    """معلومات الشركة — متاحة عبر ياهو فقط حالياً."""
    resolved = resolve_symbol(symbol_or_name)
    if not resolved:
        return {"error": f"ما قدرت أحدد سهم باسم أو رقم '{symbol_or_name}'."}

    cache_key = f"profile::{resolved['symbol']}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        import yfinance as yf
        info = yf.Ticker(resolved["symbol"]).info or {}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"تعذّر جلب بيانات الشركة: {exc}"}

    def num(key, digits=2):
        val = info.get(key)
        return round(float(val), digits) if isinstance(val, (int, float)) else None

    profile = {
        "الرمز": resolved["symbol"], "الاسم": resolved["name_ar"],
        "الاسم_بالإنجليزي": info.get("longName") or resolved["name_en"],
        "القطاع": info.get("sector"), "الصناعة": info.get("industry"),
        "القيمة_السوقية": info.get("marketCap"),
        "مكرر_الربحية": num("trailingPE"), "ربحية_السهم": num("trailingEps"),
        "عائد_التوزيعات_%": round(info.get("dividendYield", 0) * 100, 2)
        if isinstance(info.get("dividendYield"), (int, float)) else None,
        "أعلى_52_أسبوع": num("fiftyTwoWeekHigh"), "أدنى_52_أسبوع": num("fiftyTwoWeekLow"),
        "الموقع": info.get("website"), "الموظفون": info.get("fullTimeEmployees"),
        "العملة": CURRENCY,
    }
    return _cache_set(cache_key, profile)


def compare_stocks(symbols: list[str], period: str = "سنة") -> dict:
    rows = []
    for s in symbols[:8]:
        snap = get_snapshot(s)
        if "error" in snap:
            rows.append({"المدخل": s, "خطأ": snap["error"]})
            continue
        comp = snap["المقارنات"].get(period, {})
        rows.append({
            "الاسم": snap["الاسم"], "الرمز": snap["الرمز"],
            "السعر_الحالي": snap["آخر_إغلاق"]["السعر"],
            f"سعر_قبل_{period}": comp.get("السعر"),
            "نسبة_التغير_%": comp.get("نسبة_التغير_%"),
        })
    return {"الفترة": period, "النتائج": rows}


if __name__ == "__main__":
    import json
    print("قائمة الشركات:", universe_status())
    print("المزوّدون النشطون:", ", ".join(providers.active_providers()))
    print(json.dumps(get_snapshot("4009"), ensure_ascii=False, indent=2))
