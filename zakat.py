"""
zakat.py
========
حاسبة تقديرية لزكاة الأسهم.

⚠️ هذه أداة حسابية، وليست فتوى.
المسألة فيها اجتهادات فقهية متعددة، وهذا الملف يعرض الطريقتين
الأكثر تداولاً بين الهيئات الشرعية دون ترجيح إحداهما. القرار
في نيّتك وفي رأي من تثق به من أهل العلم.

الطريقتان:
  ١) نية المتاجرة (المضاربة قصيرة المدى)
     تُزكّى القيمة السوقية كاملة عند حولان الحول.

  ٢) نية الاستثمار طويل المدى (الاقتناء للعائد)
     الرأي الشائع: تُزكّى الموجودات الزكوية في الشركة لا كامل
     قيمة السهم، وتُستخرج نسبتها من القوائم المالية. ولأنها تختلف
     من شركة لأخرى ولا تتوفر آلياً، نتيح لك إدخال النسبة يدوياً،
     ومع عدم معرفتها تُستخدم نسبة تقديرية متحفّظة.

النِصاب: قيمة 85 جراماً من الذهب عيار 24 (تختلف بتغير سعر الذهب).
المقدار: 2.5% للسنة الهجرية · 2.577% للسنة الميلادية.
"""

from __future__ import annotations

from typing import Optional

import tadawul_data as td

RATE_HIJRI = 0.025
RATE_GREGORIAN = 0.02577
NISAB_GOLD_GRAMS = 85

# نسبة تقديرية متحفّظة للموجودات الزكوية عند عدم معرفة النسبة الفعلية
DEFAULT_ZAKATABLE_RATIO = 0.30


def _price(code: str) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """يرجع (السعر، الاسم، الخطأ)."""
    snap = td.get_snapshot(code)
    if "error" in snap:
        return None, None, snap["error"]
    return snap["آخر_إغلاق"]["السعر"], snap["الاسم"], None


def calculate(
    holdings: list[dict],
    intent: str = "متاجرة",
    year_type: str = "هجري",
    gold_gram_price: Optional[float] = None,
    zakatable_ratio: Optional[float] = None,
) -> dict:
    """
    holdings: [{"code": "2222", "shares": 100}, ...]
    intent: "متاجرة" أو "استثمار"
    year_type: "هجري" أو "ميلادي"
    gold_gram_price: سعر جرام الذهب عيار 24 بالريال (لحساب النصاب)
    zakatable_ratio: نسبة الموجودات الزكوية (0 إلى 1) لنية الاستثمار
    """
    if not holdings:
        return {"error": "ما فيه أسهم مدخلة."}

    rate = RATE_HIJRI if year_type == "هجري" else RATE_GREGORIAN
    rows, errors = [], []
    total_market = 0.0

    for h in holdings:
        code = str(h.get("code", "")).strip()
        try:
            shares = float(h.get("shares", 0))
        except Exception:  # noqa: BLE001
            shares = 0
        if not code or shares <= 0:
            continue

        price, name, err = _price(code)
        if err or price is None:
            errors.append({"الرمز": code, "الخطأ": err or "ما لقيت سعراً"})
            continue

        value = round(price * shares, 2)
        total_market += value
        rows.append({
            "الاسم": name, "الرمز": code,
            "عدد_الأسهم": shares, "السعر": price, "القيمة_السوقية": value,
        })

    if not rows:
        return {"error": "ما قدرت أجيب أسعار أي سهم.", "تفاصيل": errors}

    total_market = round(total_market, 2)

    if intent == "متاجرة":
        base = total_market
        basis_note = ("نية المتاجرة: تُزكّى القيمة السوقية كاملة، "
                      "لأن السهم هنا في حكم عروض التجارة.")
        ratio_used = 1.0
    else:
        ratio_used = zakatable_ratio if zakatable_ratio is not None else DEFAULT_ZAKATABLE_RATIO
        ratio_used = max(0.0, min(1.0, float(ratio_used)))
        base = round(total_market * ratio_used, 2)
        basis_note = (
            f"نية الاستثمار: حُسبت الزكاة على {ratio_used * 100:.0f}% من القيمة "
            "السوقية كتقدير للموجودات الزكوية في الشركات. النسبة الدقيقة "
            "تختلف لكل شركة وتُستخرج من قوائمها المالية أو من إعلانها "
            "عن زكاة السهم إن وُجد."
        )

    zakat_due = round(base * rate, 2)

    nisab_value, above_nisab = None, None
    if gold_gram_price:
        nisab_value = round(float(gold_gram_price) * NISAB_GOLD_GRAMS, 2)
        above_nisab = total_market >= nisab_value

    return {
        "الأسهم": rows,
        "إجمالي_القيمة_السوقية": total_market,
        "نية_التملك": intent,
        "أساس_الحساب": basis_note,
        "الوعاء_الزكوي": base,
        "نسبة_الموجودات_الزكوية": ratio_used,
        "نوع_السنة": year_type,
        "المقدار_%": round(rate * 100, 3),
        "الزكاة_المستحقة": zakat_due,
        "النصاب": {
            "جرامات_الذهب": NISAB_GOLD_GRAMS,
            "سعر_الجرام_المدخل": gold_gram_price,
            "قيمة_النصاب": nisab_value,
            "المحفظة_تبلغ_النصاب": above_nisab,
            "ملاحظة": ("أدخل سعر جرام الذهب عيار 24 لمعرفة هل بلغت المحفظة "
                       "النصاب." if not gold_gram_price else
                       "النصاب يتغير بتغير سعر الذهب، فتحقق منه وقت الإخراج."),
        },
        "أخطاء": errors,
        "⚠️_تنبيه": (
            "هذا حساب تقديري وليس فتوى. زكاة الأسهم فيها اجتهادات فقهية "
            "متعددة، خصوصاً في نية الاستثمار طويل المدى. راجع جهة شرعية "
            "معتبرة أو الهيئة الشرعية في بنكك قبل الإخراج. كما أن الزكاة "
            "تجب عند حولان الحول على المال، لا عند تشغيل هذه الحاسبة."
        ),
        "ملاحظة_الحول": (
            "احسب من تاريخ بلوغ مالك النصاب أول مرة، واستخدم السنة الهجرية "
            "(2.5%) أو الميلادية (2.577%) بحسب ما تعتمده."
        ),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(
        calculate([{"code": "2222", "shares": 100}], "متاجرة", "هجري", 300),
        ensure_ascii=False, indent=2))
