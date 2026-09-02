"""
announcements.py
================
روابط مصادر أخبار وإعلانات الشركات السعودية.

لماذا روابط وليس تلخيصاً آلياً؟
موقع تداول لا يوفر واجهة برمجية مجانية للإعلانات، وتخمين
محتواها يخالف قاعدة المشروع الأساسية: لا رقم ولا خبر بلا مصدر.

فالحل الصادق: نوصلك للمصدر الرسمي بضغطة واحدة، وتقرأ بنفسك.
ولو فعّلت مفتاح Claude، الوكيل يبحث ويلخّص مع ذكر المصدر.
"""

from __future__ import annotations

from urllib.parse import quote

import tadawul_data as td

SAUDI_EXCHANGE = "https://www.saudiexchange.sa"
ARGAAM = "https://www.argaam.com"
MUBASHER = "https://www.mubasher.info"


def news_links(symbol_or_name: str) -> dict:
    """روابط بحث جاهزة عن أخبار الشركة وإعلاناتها."""
    resolved = td.resolve_symbol(symbol_or_name)
    if not resolved:
        return {"error": f"ما قدرت أحدد سهم '{symbol_or_name}'."}

    name = resolved["name_ar"]
    code = resolved["code"]
    q_news = quote(f"{name} سهم {code} تداول")
    q_ann = quote(f"{name} إعلان تداول")

    return {
        "الاسم": name,
        "رقم_الشركة": code,
        "الروابط": [
            {
                "المصدر": "أخبار اليوم (Google News)",
                "الوصف": "أحدث ما نُشر عن الشركة بالعربي",
                "الرابط": f"https://news.google.com/search?q={q_news}&hl=ar",
            },
            {
                "المصدر": "إعلانات الشركة",
                "الوصف": "بحث عن إعلانات تداول الرسمية",
                "الرابط": f"https://news.google.com/search?q={q_ann}&hl=ar",
            },
            {
                "المصدر": "موقع تداول السعودية",
                "الوصف": "المرجع الرسمي للإعلانات والقوائم المالية",
                "الرابط": SAUDI_EXCHANGE,
            },
            {
                "المصدر": "أرقام",
                "الوصف": "بيانات وتحليلات الشركات المدرجة",
                "الرابط": f"{ARGAAM}/ar/search?q={quote(name)}",
            },
            {
                "المصدر": "مباشر",
                "الوصف": "أخبار السوق والشركات",
                "الرابط": MUBASHER,
            },
        ],
        "ملاحظة": "الإعلان في موقع تداول هو المرجع الرسمي الوحيد المعتمد.",
    }


def watchlist_links(codes: list[str]) -> list[dict]:
    """روابط أخبار لكل أسهم قائمة المتابعة."""
    out = []
    for c in codes[:30]:
        info = news_links(c)
        if "error" not in info:
            out.append(info)
    return out
