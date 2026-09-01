"""
market_pulse.py
===============
طبقة "نبض السوق": تحسب الأرقام التي تفسّر حركة السهم اليوم.

الفلسفة المهمة هنا:
    كل رقم في هذا الملف محسوب من بيانات فعلية — لا شيء يأتي من الموديل.
    مهمة الموديل لاحقاً هي الشرح والربط بالأخبار، وليس الحساب.

الدوال:
    get_daily_move(symbol)        -> حركة السهم اليوم + إشارات غير طبيعية
    get_watchlist_movers(symbols) -> ترتيب قائمة متابعة حسب تحرك اليوم
    get_market_overview()         -> حالة المؤشر العام تاسي
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

import tadawul_data as td

TASI = "^TASI.SR"

# عتبات تصنيف الحركة (نسبة مئوية)
FLAT_THRESHOLD = 0.5
NOTABLE_THRESHOLD = 2.0
BIG_THRESHOLD = 4.0

# نسبة حجم التداول التي تُعد غير طبيعية مقارنة بمتوسط 3 أشهر
VOLUME_SPIKE = 1.8
VOLUME_HUGE = 3.0


def _classify(pct: Optional[float]) -> str:
    if pct is None:
        return "غير معروف"
    a = abs(pct)
    if a < FLAT_THRESHOLD:
        return "شبه ثابت"
    if a < NOTABLE_THRESHOLD:
        return "حركة طبيعية"
    if a < BIG_THRESHOLD:
        return "حركة ملحوظة"
    return "حركة قوية"


def _volume_note(ratio: Optional[float]) -> str:
    if ratio is None:
        return "لا يوجد بيانات كمية"
    if ratio >= VOLUME_HUGE:
        return "حجم تداول ضخم جداً — أعلى بكثير من المعتاد"
    if ratio >= VOLUME_SPIKE:
        return "حجم تداول مرتفع عن المعتاد"
    if ratio < 0.5:
        return "حجم تداول ضعيف"
    return "حجم تداول طبيعي"


def _safe_pct(new: float, old: float) -> Optional[float]:
    if not old:
        return None
    return round((new - old) / old * 100, 2)


def get_daily_move(symbol_or_name: str, with_market_context: bool = True) -> dict:
    """
    كل الأرقام التي تصف حركة السهم في آخر جلسة تداول:
    التغير، الفجوة عند الافتتاح، المدى اليومي، حجم التداول مقابل معدله،
    الموقع من نطاق 52 أسبوع، وحركة السوق العام في نفس اليوم للمقارنة.
    """
    resolved = td.resolve_symbol(symbol_or_name)
    if not resolved:
        return {"error": f"ما قدرت أحدد سهم باسم أو رقم '{symbol_or_name}'."}

    try:
        df = td.get_history(resolved["symbol"], years=1)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}

    if len(df) < 2:
        return {"error": "البيانات التاريخية غير كافية لحساب حركة اليوم."}

    today, prev = df.iloc[-1], df.iloc[-2]
    close = round(float(today["Close"]), 2)
    prev_close = round(float(prev["Close"]), 2)
    change = round(close - prev_close, 2)
    pct = _safe_pct(close, prev_close)

    # حجم التداول مقابل متوسط 3 أشهر (تقريباً 63 جلسة)
    vol = float(today["Volume"]) if pd.notna(today["Volume"]) else None
    avg_vol_series = df["Volume"].tail(64).head(63)
    avg_vol = float(avg_vol_series.mean()) if avg_vol_series.notna().any() else None
    vol_ratio = round(vol / avg_vol, 2) if (vol and avg_vol) else None

    # الموقع ضمن نطاق السنة
    high_52 = round(float(df["High"].max()), 2)
    low_52 = round(float(df["Low"].min()), 2)
    span = high_52 - low_52
    position = round((close - low_52) / span * 100, 1) if span else None

    # الفجوة عند الافتتاح والمدى اليومي
    open_price = round(float(today["Open"]), 2)
    gap_pct = _safe_pct(open_price, prev_close)
    day_range_pct = _safe_pct(float(today["High"]), float(today["Low"]))

    result = {
        "الرمز": resolved["symbol"],
        "رقم_الشركة": resolved["code"],
        "الاسم": resolved["name_ar"],
        "تاريخ_الجلسة": df.index[-1].strftime("%Y-%m-%d"),
        "الإغلاق": close,
        "إغلاق_الجلسة_السابقة": prev_close,
        "التغير": change,
        "نسبة_التغير_%": pct,
        "الاتجاه": "صاعد" if (pct or 0) > 0 else ("هابط" if (pct or 0) < 0 else "ثابت"),
        "تصنيف_الحركة": _classify(pct),
        "الافتتاح": open_price,
        "فجوة_الافتتاح_%": gap_pct,
        "أعلى_اليوم": round(float(today["High"]), 2),
        "أدنى_اليوم": round(float(today["Low"]), 2),
        "المدى_اليومي_%": day_range_pct,
        "كمية_التداول": int(vol) if vol else None,
        "متوسط_الكمية_3أشهر": int(avg_vol) if avg_vol else None,
        "نسبة_الكمية_للمتوسط": vol_ratio,
        "ملاحظة_الكمية": _volume_note(vol_ratio),
        "حجم_غير_طبيعي": bool(vol_ratio and vol_ratio >= VOLUME_SPIKE),
        "أعلى_52_أسبوع": high_52,
        "أدنى_52_أسبوع": low_52,
        "الموقع_من_نطاق_السنة_%": position,
        "العملة": "ريال سعودي",
    }

    # سياق السوق: هل السوق كله يتحرك أم السهم وحده؟
    if with_market_context and resolved["symbol"] != TASI:
        market = get_market_overview()
        if "error" not in market:
            m_pct = market.get("نسبة_التغير_%")
            result["السوق_العام"] = {
                "تاسي_نسبة_التغير_%": m_pct,
                "تاريخ": market.get("تاريخ_الجلسة"),
            }
            if pct is not None and m_pct is not None:
                result["الفرق_عن_السوق_%"] = round(pct - m_pct, 2)
                if abs(m_pct) >= 1 and (pct * m_pct) > 0:
                    result["قراءة_السياق"] = (
                        "السوق كله يتحرك بنفس الاتجاه — الحركة قد تكون عامة "
                        "وليست خاصة بالشركة."
                    )
                elif (pct * m_pct) < 0 and abs(pct) >= NOTABLE_THRESHOLD:
                    result["قراءة_السياق"] = (
                        "السهم يتحرك عكس السوق — غالباً هناك سبب خاص بالشركة."
                    )
                elif abs(result["الفرق_عن_السوق_%"]) >= NOTABLE_THRESHOLD:
                    result["قراءة_السياق"] = (
                        "السهم يتحرك أقوى بكثير من السوق — غالباً هناك سبب "
                        "خاص بالشركة."
                    )
                else:
                    result["قراءة_السياق"] = "الحركة قريبة من حركة السوق العام."

    return result


def get_market_overview() -> dict:
    """حالة المؤشر العام (تاسي) في آخر جلسة."""
    try:
        df = td.get_history(TASI, years=1)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"تعذّر جلب المؤشر العام: {exc}"}

    if len(df) < 2:
        return {"error": "بيانات المؤشر غير كافية."}

    close = round(float(df["Close"].iloc[-1]), 2)
    prev_close = round(float(df["Close"].iloc[-2]), 2)
    return {
        "المؤشر": "تاسي — المؤشر العام",
        "تاريخ_الجلسة": df.index[-1].strftime("%Y-%m-%d"),
        "النقاط": close,
        "التغير": round(close - prev_close, 2),
        "نسبة_التغير_%": _safe_pct(close, prev_close),
        "أعلى_52_أسبوع": round(float(df["High"].max()), 2),
        "أدنى_52_أسبوع": round(float(df["Low"].min()), 2),
    }


def get_watchlist_movers(symbols: list[str]) -> dict:
    """ترتيب قائمة المتابعة حسب تحرك آخر جلسة، مع إبراز الأحجام غير الطبيعية."""
    rows, errors = [], []
    for s in symbols[:30]:
        move = get_daily_move(s, with_market_context=False)
        if "error" in move:
            errors.append({"المدخل": s, "الخطأ": move["error"]})
            continue
        rows.append({
            "الاسم": move["الاسم"],
            "الرمز": move["رقم_الشركة"],
            "السعر": move["الإغلاق"],
            "التغير_%": move["نسبة_التغير_%"],
            "تصنيف_الحركة": move["تصنيف_الحركة"],
            "حجم_غير_طبيعي": move["حجم_غير_طبيعي"],
            "نسبة_الكمية_للمتوسط": move["نسبة_الكمية_للمتوسط"],
            "تاريخ_الجلسة": move["تاريخ_الجلسة"],
        })

    rows.sort(key=lambda r: (r["التغير_%"] is None, -(r["التغير_%"] or 0)))
    flagged = [r for r in rows if r["حجم_غير_طبيعي"]
               or abs(r["التغير_%"] or 0) >= NOTABLE_THRESHOLD]

    return {
        "السوق_العام": get_market_overview(),
        "الأسهم": rows,
        "تستحق_الانتباه": flagged,
        "أخطاء": errors,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_daily_move("2222"), ensure_ascii=False, indent=2))
