"""
alerts.py
=========
تنبيهات سعرية بسيطة.

⚠️ حقيقة تقنية مهمة:
Streamlit المجاني لا يشغّل شيئاً في الخلفية — التطبيق ينام حتى يفتحه أحد.
لذلك التنبيهات هنا تُفحص في حالتين فقط:
  ١) عند فتح التطبيق
  ٢) عند تشغيل المهمة اليومية في GitHub Actions (ترسل لك إيميلاً)

يعني: التنبيه ما "يرن" لحظياً. لو تبي تنبيهاً لحظياً فعلياً تحتاج
خدمة تعمل دائماً (خادم صغير أو بوت تيليجرام).
"""

from __future__ import annotations

from datetime import datetime

import storage
import tadawul_data as td

OPS = {
    "فوق": lambda price, target: price >= target,
    "تحت": lambda price, target: price <= target,
}


def add_alert(symbol_or_name: str, op: str, price: float, note: str = "") -> dict:
    """يضيف تنبيهاً جديداً."""
    if op not in OPS:
        return {"error": "الشرط يجب أن يكون 'فوق' أو 'تحت'."}
    try:
        price = float(price)
    except Exception:  # noqa: BLE001
        return {"error": "السعر غير صالح."}
    if price <= 0:
        return {"error": "السعر يجب أن يكون أكبر من صفر."}

    resolved = td.resolve_symbol(symbol_or_name)
    if not resolved:
        return {"error": f"ما قدرت أحدد سهم '{symbol_or_name}'."}

    alerts = storage.get("alerts") or []
    for a in alerts:
        if a["code"] == resolved["code"] and a["op"] == op and abs(a["price"] - price) < 0.001:
            return {"error": "هذا التنبيه موجود مسبقاً."}

    alerts.append({
        "code": resolved["code"],
        "symbol": resolved["symbol"],
        "name": resolved["name_ar"],
        "op": op,
        "price": round(price, 2),
        "note": note.strip(),
        "created": datetime.today().strftime("%Y-%m-%d"),
    })
    storage.put("alerts", alerts)
    return {"ok": True, "التنبيه": alerts[-1]}


def remove_alert(index: int) -> bool:
    alerts = storage.get("alerts") or []
    if 0 <= index < len(alerts):
        alerts.pop(index)
        return storage.put("alerts", alerts)
    return False


def clear_triggered(triggered_codes: list[str]) -> None:
    """يحذف التنبيهات التي تحققت حتى لا تتكرر."""
    alerts = storage.get("alerts") or []
    keep = [a for a in alerts
            if f"{a['code']}|{a['op']}|{a['price']}" not in triggered_codes]
    storage.put("alerts", keep)


def check_alerts() -> dict:
    """يفحص كل التنبيهات مقابل آخر إغلاق."""
    alerts = storage.get("alerts") or []
    if not alerts:
        return {"عدد_التنبيهات": 0, "تحققت": [], "لم_تتحقق": [], "أخطاء": []}

    triggered, pending, errors = [], [], []
    cache: dict[str, dict] = {}

    for a in alerts:
        code = a["code"]
        if code not in cache:
            cache[code] = td.get_snapshot(code)
        snap = cache[code]

        if "error" in snap:
            errors.append({"الرمز": code, "الخطأ": snap["error"]})
            continue

        price = snap["آخر_إغلاق"]["السعر"]
        date = snap["آخر_إغلاق"]["التاريخ"]
        row = {
            "الاسم": a["name"], "الرمز": code,
            "الشرط": f"{a['op']} {a['price']}",
            "السعر_الحالي": price,
            "تاريخ_الإغلاق": date,
            "الفارق": round(price - a["price"], 2),
            "ملاحظة": a.get("note", ""),
            "المفتاح": f"{code}|{a['op']}|{a['price']}",
        }
        (triggered if OPS[a["op"]](price, a["price"]) else pending).append(row)

    return {
        "عدد_التنبيهات": len(alerts),
        "تحققت": triggered,
        "لم_تتحقق": pending,
        "أخطاء": errors,
        "ملاحظة": "الفحص يعتمد على آخر إغلاق متاح، لا على السعر اللحظي.",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(check_alerts(), ensure_ascii=False, indent=2))
