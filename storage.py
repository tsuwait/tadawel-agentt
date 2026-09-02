"""
storage.py
==========
تخزين بسيط لقائمة المتابعة والتنبيهات.

⚠️ ملاحظة مهمة عن Streamlit Cloud:
نظام الملفات مؤقت — أي إعادة تشغيل للتطبيق تمسح الملفات.
لذلك أضفنا تصدير/استيراد بكود نصي: تنسخه وتحتفظ به، وتلصقه
لاسترجاع كل شيء خلال ثوانٍ لو انمسح.

للتخزين الدائم فعلاً تحتاج قاعدة بيانات خارجية (Supabase أو
Google Sheets مثلاً) — انظر ملاحظة في نهاية الملف.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

DATA_FILE = "app_data.json"

DEFAULTS: dict[str, Any] = {
    "watchlist": ["2222", "1120", "2010", "7010", "2280"],
    "alerts": [],          # [{symbol, code, name, op, price, note, created}]
    "holdings": [],        # [{code, name, shares, cost}] لحاسبة الزكاة
}


def _path() -> str:
    if os.path.exists(DATA_FILE):
        return DATA_FILE
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), DATA_FILE)


def load() -> dict:
    """يقرأ كل بيانات التطبيق، ويرجع القيم الافتراضية لو ما فيه ملف."""
    data = json.loads(json.dumps(DEFAULTS))  # نسخة عميقة
    try:
        with open(_path(), encoding="utf-8") as f:
            saved = json.load(f)
        for key in DEFAULTS:
            if key in saved:
                data[key] = saved[key]
    except Exception:  # noqa: BLE001
        pass
    return data


def save(data: dict) -> bool:
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        return True
    except Exception:  # noqa: BLE001
        return False


def get(key: str):
    return load().get(key, DEFAULTS.get(key))


def put(key: str, value) -> bool:
    data = load()
    data[key] = value
    return save(data)


# ───────────────────────── نسخ احتياطي ─────────────────────────
def export_code() -> str:
    """يحوّل كل البيانات إلى كود نصي قصير تنسخه وتحتفظ به."""
    raw = json.dumps(load(), ensure_ascii=False, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def import_code(code: str) -> tuple[bool, str]:
    """يستعيد البيانات من كود النسخة الاحتياطية."""
    try:
        raw = base64.urlsafe_b64decode(code.strip().encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            return False, "الكود غير صالح."
        merged = load()
        for key in DEFAULTS:
            if key in data:
                merged[key] = data[key]
        return (True, "تم الاسترجاع بنجاح.") if save(merged) else (False, "تعذّر الحفظ.")
    except Exception as exc:  # noqa: BLE001
        return False, f"الكود غير صالح: {exc}"


# للتخزين الدائم: استبدل load/save أعلاه بقراءة وكتابة من Supabase
# أو Google Sheets. بقية المشروع لا يتغير، لأنه يتعامل مع هذه الدوال فقط.
