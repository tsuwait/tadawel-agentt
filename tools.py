"""
tools.py
========
تعريف الأدوات التي يقدر Claude يناديها، وربطها بدوال طبقة البيانات.
كل أداة لها: اسم + وصف واضح + مخطط JSON للمدخلات.
"""

from __future__ import annotations

import json
from typing import Any

import market_pulse as mp
import tadawul_data as td

TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_daily_move",
        "description": (
            "استخدمها أولاً وإلزامياً عند أي سؤال عن سبب حركة سهم اليوم "
            "('ليش نزل/طلع؟'). ترجع الأرقام الفعلية: نسبة التغير، فجوة "
            "الافتتاح، المدى اليومي، حجم التداول مقارنة بمتوسط 3 أشهر "
            "(لكشف الأحجام غير الطبيعية)، الموقع من نطاق 52 أسبوع، "
            "وحركة المؤشر العام في نفس اليوم لمعرفة هل الحركة عامة أم "
            "خاصة بالشركة."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "رقم الشركة أو اسمها"}
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_market_overview",
        "description": "حالة المؤشر العام تاسي في آخر جلسة: النقاط ونسبة التغير.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_watchlist_movers",
        "description": (
            "يرتب قائمة أسهم حسب تحرك آخر جلسة ويبرز الأسهم ذات الأحجام "
            "غير الطبيعية. مفيد لسؤال 'وش صار في محفظتي اليوم؟'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "أرقام أو أسماء الشركات",
                }
            },
            "required": ["symbols"],
        },
    },
    {
        "name": "search_stock",
        "description": (
            "ابحث عن سهم سعودي بالاسم العربي أو الإنجليزي أو رقم الشركة الرباعي. "
            "استخدمها أولاً إذا كان المستخدم ذكر اسم شركة ولست متأكداً من رمزها."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "اسم الشركة أو جزء منه أو رقمها، مثل: أرامكو، الراجحي، 2222",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_stock_snapshot",
        "description": (
            "الأداة الأساسية. ترجع آخر سعر إغلاق للسهم مع مقارنته بسعره "
            "قبل يوم وأسبوع وشهر و3 أشهر و6 أشهر وسنة ومن بداية العام، "
            "مع الفرق ونسبة التغير لكل فترة، بالإضافة لأعلى وأدنى سعر خلال سنة. "
            "استخدمها لأي سؤال عن سعر سهم أو أدائه."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "رقم الشركة (مثل 2222) أو اسمها (مثل أرامكو)",
                }
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_price_range",
        "description": (
            "أداء السهم بين تاريخين محددين: سعر البداية والنهاية، نسبة التغير، "
            "أعلى وأدنى سعر مع تواريخها، والمتوسط. استخدمها لو سأل المستخدم عن "
            "فترة مخصصة مثل 'من يناير لمارس' أو 'في 2023'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "رقم الشركة أو اسمها"},
                "start": {"type": "string", "description": "تاريخ البداية بصيغة YYYY-MM-DD"},
                "end": {"type": "string", "description": "تاريخ النهاية بصيغة YYYY-MM-DD (اختياري)"},
            },
            "required": ["symbol", "start"],
        },
    },
    {
        "name": "get_company_profile",
        "description": (
            "معلومات الشركة: القطاع، القيمة السوقية، مكرر الربحية، ربحية السهم، "
            "عائد التوزيعات، وأعلى/أدنى 52 أسبوع."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "رقم الشركة أو اسمها"}
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "compare_stocks",
        "description": "مقارنة أداء عدة أسهم سعودية على نفس الفترة الزمنية.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "قائمة أرقام أو أسماء الشركات (حد أقصى 6)",
                },
                "period": {
                    "type": "string",
                    "enum": ["أسبوع", "شهر", "3_أشهر", "6_أشهر", "سنة", "بداية_العام"],
                    "description": "الفترة المراد المقارنة عليها",
                },
            },
            "required": ["symbols"],
        },
    },
    {
        "name": "get_closing_series",
        "description": (
            "سلسلة أسعار الإغلاق اليومية لعدد من السنوات. استخدمها فقط إذا "
            "احتجت تحلل الاتجاه أو تحسب شيء يعتمد على كامل السلسلة."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "رقم الشركة أو اسمها"},
                "years": {"type": "integer", "description": "عدد السنوات (1 إلى 5)"},
            },
            "required": ["symbol"],
        },
    },
]


def execute_tool(name: str, args: dict) -> str:
    """ينفذ الأداة ويرجع النتيجة كنص JSON عربي."""
    try:
        if name == "get_daily_move":
            result = mp.get_daily_move(args["symbol"])
        elif name == "get_market_overview":
            result = mp.get_market_overview()
        elif name == "get_watchlist_movers":
            result = mp.get_watchlist_movers(args["symbols"])
        elif name == "search_stock":
            result = {"النتائج": td.search_stocks(args["query"])}
        elif name == "get_stock_snapshot":
            result = td.get_snapshot(args["symbol"])
        elif name == "get_price_range":
            result = td.get_range(args["symbol"], args["start"], args.get("end"))
        elif name == "get_company_profile":
            result = td.get_profile(args["symbol"])
        elif name == "compare_stocks":
            result = td.compare_stocks(args["symbols"], args.get("period", "سنة"))
        elif name == "get_closing_series":
            years = min(max(int(args.get("years", 1)), 1), 5)
            data = td.get_closing_series(args["symbol"], years)
            # تقليل الحجم: نأخذ عينة أسبوعية بدل كل يوم
            if "التواريخ" in data and len(data["التواريخ"]) > 260:
                step = len(data["التواريخ"]) // 200 + 1
                data["التواريخ"] = data["التواريخ"][::step]
                data["الإغلاق"] = data["الإغلاق"][::step]
                data["ملاحظة"] = "عيّنة مختصرة من السلسلة"
            result = data
        else:
            result = {"error": f"أداة غير معروفة: {name}"}
    except Exception as exc:  # noqa: BLE001
        result = {"error": f"فشل تنفيذ الأداة {name}: {exc}"}

    return json.dumps(result, ensure_ascii=False, default=str)
