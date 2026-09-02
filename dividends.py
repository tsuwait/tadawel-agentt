"""
dividends.py
============
تقويم التوزيعات النقدية للأسهم السعودية.

⚠️ حدود مهمة يجب أن تكون واضحة للمستخدم:
- التوزيعات **السابقة** تُجلب من بيانات فعلية (تواريخ أحقية حقيقية).
- التوزيع **القادم** لا يوجد له مصدر مجاني موثوق، فنقدّره من نمط
  السنوات الماضية ونضعه صراحةً كـ "تقدير" لا كحقيقة.
- الموعد الرسمي الوحيد المعتمد هو إعلان الشركة في موقع تداول.

الدوال:
    get_dividends(symbol)        سجل التوزيعات + العائد + التقدير القادم
    get_calendar(symbols)        تقويم مرتب لعدة أسهم
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
from dateutil.relativedelta import relativedelta

import tadawul_data as td

LOOKBACK_YEARS = 3


def _safe_float(value) -> Optional[float]:
    try:
        return round(float(value), 4)
    except Exception:  # noqa: BLE001
        return None


def get_dividends(symbol_or_name: str) -> dict:
    """سجل توزيعات السهم مع العائد وتقدير الموعد القادم."""
    resolved = td.resolve_symbol(symbol_or_name)
    if not resolved:
        return {"error": f"ما قدرت أحدد سهم '{symbol_or_name}'."}

    try:
        import yfinance as yf
        series = yf.Ticker(resolved["symbol"]).dividends
    except Exception as exc:  # noqa: BLE001
        return {"error": f"تعذّر جلب التوزيعات: {exc}"}

    if series is None or len(series) == 0:
        return {
            "الرمز": resolved["symbol"], "الاسم": resolved["name_ar"],
            "يوزع_أرباحاً": False,
            "ملاحظة": "ما فيه سجل توزيعات لهذا السهم في المصدر المتاح.",
        }

    if getattr(series.index, "tz", None) is not None:
        series.index = series.index.tz_convert(None)
    series.index = pd.to_datetime(series.index).normalize()
    series = series.sort_index()

    today = pd.Timestamp(datetime.today().date())
    cutoff = today - relativedelta(years=LOOKBACK_YEARS)
    recent = series.loc[series.index >= cutoff]

    history = [
        {"تاريخ_الأحقية": d.strftime("%Y-%m-%d"), "المبلغ_للسهم": _safe_float(v)}
        for d, v in recent.items()
    ]
    history.reverse()

    # عائد التوزيعات من آخر 12 شهراً مقابل السعر الحالي
    last_12m = series.loc[series.index >= (today - relativedelta(months=12))]
    total_12m = _safe_float(last_12m.sum()) if len(last_12m) else 0.0

    price, yield_pct = None, None
    try:
        df = td.get_history(resolved["symbol"], years=1)
        price = round(float(df["Close"].iloc[-1]), 2)
        if price and total_12m:
            yield_pct = round(total_12m / price * 100, 2)
    except Exception:  # noqa: BLE001
        pass

    # تقدير الموعد القادم من نمط السنوات السابقة
    estimate = None
    if len(series) >= 2:
        dates = list(series.index)
        gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
        recent_gaps = gaps[-6:] if len(gaps) >= 6 else gaps
        avg_gap = sum(recent_gaps) / len(recent_gaps)
        # نقرّب لأقرب نمط معروف: ربعي / نصف سنوي / سنوي
        pattern, days = "غير منتظم", avg_gap
        for label, ref in [("ربعي", 91), ("نصف سنوي", 182), ("سنوي", 365)]:
            if abs(avg_gap - ref) <= 25:
                pattern, days = label, ref
                break
        next_date = dates[-1] + pd.Timedelta(days=int(days))
        estimate = {
            "النمط_المتوقع": pattern,
            "تاريخ_تقديري": next_date.strftime("%Y-%m-%d"),
            "أيام_متبقية": int((next_date - today).days),
            "متأخر_عن_التقدير": bool(next_date < today),
            "⚠️": "تقدير من نمط السنوات السابقة — وليس إعلاناً رسمياً.",
        }

    return {
        "الرمز": resolved["symbol"], "رقم_الشركة": resolved["code"],
        "الاسم": resolved["name_ar"],
        "يوزع_أرباحاً": True,
        "السعر_الحالي": price,
        "توزيعات_آخر_12_شهر": total_12m,
        "عائد_التوزيعات_%": yield_pct,
        "عدد_التوزيعات_آخر_12_شهر": int(len(last_12m)),
        "آخر_توزيع": history[0] if history else None,
        "السجل": history[:12],
        "التوزيع_القادم_تقديري": estimate,
        "المصدر_الرسمي": "أعلن الشركة في موقع تداول السعودية هو المرجع المعتمد.",
    }


def get_calendar(symbols: list[str]) -> dict:
    """تقويم توزيعات مرتب حسب قرب الموعد التقديري."""
    rows, skipped = [], []
    for s in symbols[:25]:
        info = get_dividends(s)
        if "error" in info or not info.get("يوزع_أرباحاً"):
            skipped.append({"المدخل": s,
                            "السبب": info.get("error") or "لا يوزع أرباحاً"})
            continue
        est = info.get("التوزيع_القادم_تقديري") or {}
        rows.append({
            "الاسم": info["الاسم"], "الرمز": info["رقم_الشركة"],
            "السعر": info.get("السعر_الحالي"),
            "عائد_التوزيعات_%": info.get("عائد_التوزيعات_%"),
            "توزيعات_12_شهر": info.get("توزيعات_آخر_12_شهر"),
            "النمط": est.get("النمط_المتوقع"),
            "الموعد_التقديري": est.get("تاريخ_تقديري"),
            "أيام_متبقية": est.get("أيام_متبقية"),
            "متأخر": est.get("متأخر_عن_التقدير", False),
        })

    def sort_key(r):
        days = r.get("أيام_متبقية")
        if days is None:
            return (2, 0)
        return (1, days) if days < 0 else (0, days)

    rows.sort(key=sort_key)
    upcoming = [r for r in rows
                if r.get("أيام_متبقية") is not None and 0 <= r["أيام_متبقية"] <= 45]

    return {
        "التقويم": rows,
        "قريباً_خلال_45_يوم": upcoming,
        "غير_موزعة": skipped,
        "⚠️": "المواعيد تقديرية من أنماط سابقة. تحقق من موقع تداول قبل أي قرار.",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_dividends("2222"), ensure_ascii=False, indent=2))
