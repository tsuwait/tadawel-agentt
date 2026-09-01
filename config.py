"""
الإعدادات العامة للمشروع.
كل القيم تُقرأ من متغيرات البيئة (.env) مع قيم افتراضية منطقية.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _secret(name: str, default: str = "") -> str:
    """
    يقرأ القيمة من متغيرات البيئة (.env) محلياً،
    ومن Streamlit Secrets عند النشر على السحابة.
    """
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st  # متوفر فقط داخل تطبيق الويب

        return str(st.secrets[name])
    except Exception:
        return default


# --- Claude API ---
ANTHROPIC_API_KEY = _secret("ANTHROPIC_API_KEY")

# كلمة مرور اختيارية لحماية التطبيق بعد النشر (اتركها فاضية لتعطيلها)
APP_PASSWORD = _secret("APP_PASSWORD")
# claude-sonnet-5 = التوازن الأفضل بين السرعة والذكاء للوكلاء
# للمهام الأعقد استخدم claude-opus-5
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")
MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "4000"))
MAX_TOOL_ROUNDS = int(os.getenv("MAX_TOOL_ROUNDS", "8"))

# --- بيانات السوق ---
YAHOO_SUFFIX = ".SR"          # لاحقة السوق السعودي في ياهو فاينانس
DEFAULT_HISTORY_YEARS = 3      # كم سنة نسحب من التاريخ افتراضياً
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))  # 5 دقائق
REQUEST_TIMEOUT = 15

CURRENCY = "ريال سعودي"
TIMEZONE = "Asia/Riyadh"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
