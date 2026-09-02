"""
brief.py
========
الملخص الصباحي: حالة السوق وقائمة متابعتك وتنبيهاتك في نص واحد.

يعمل بطريقتين:
  ١) داخل التطبيق — تفتحه فتشوف الملخص
  ٢) عبر GitHub Actions — يرسل لك إيميلاً كل صباح تلقائياً

    python brief.py            # يطبع الملخص في الطرفية
    python brief.py --email    # يرسله بالإيميل (يحتاج متغيرات SMTP)

المتغيرات المطلوبة للإيميل:
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_TO
"""

from __future__ import annotations

import argparse
import os
import smtplib
import sys
from datetime import datetime
from email.mime.text import MIMEText

import alerts as alerts_mod
import dividends as div_mod
import market_pulse as mp
import storage

NOTABLE = 2.0


def build_brief() -> dict:
    """يجمع كل ما يهمك في جلسة واحدة."""
    watchlist = storage.get("watchlist") or []
    data = mp.get_watchlist_movers(watchlist)
    market = data.get("السوق_العام", {})

    rows = data.get("الأسهم", [])
    movers = [r for r in rows
              if r.get("التغير_%") is not None and abs(r["التغير_%"]) >= NOTABLE]
    volume_flags = [r for r in rows if r.get("حجم_غير_طبيعي")]

    alert_state = alerts_mod.check_alerts()

    # توزيعات قريبة خلال شهر
    upcoming_div = []
    try:
        cal = div_mod.get_calendar(watchlist)
        upcoming_div = [r for r in cal.get("قريباً_خلال_45_يوم", [])
                        if (r.get("أيام_متبقية") or 99) <= 30]
    except Exception:  # noqa: BLE001
        pass

    return {
        "التاريخ": datetime.today().strftime("%Y-%m-%d"),
        "السوق": market,
        "الأسهم": rows,
        "تحركات_ملحوظة": movers,
        "أحجام_غير_طبيعية": volume_flags,
        "تنبيهات_تحققت": alert_state.get("تحققت", []),
        "توزيعات_قريبة": upcoming_div,
    }


def _pct(v) -> str:
    if v is None:
        return "—"
    return f"{'+' if v > 0 else ''}{v:.2f}%"


def to_text(brief: dict) -> str:
    """يحوّل الملخص إلى نص عربي مقروء."""
    lines = [f"📊 نبض تداول — ملخص {brief['التاريخ']}", ""]

    market = brief.get("السوق", {})
    if "error" not in market and market:
        lines.append(
            f"المؤشر العام تاسي: {market.get('النقاط', '—')} "
            f"({_pct(market.get('نسبة_التغير_%'))}) · جلسة {market.get('تاريخ_الجلسة', '—')}"
        )
    else:
        lines.append("تعذّر جلب المؤشر العام.")
    lines.append("")

    triggered = brief.get("تنبيهات_تحققت", [])
    if triggered:
        lines.append("🔔 تنبيهات تحققت:")
        for t in triggered:
            lines.append(f"  • {t['الاسم']} — الشرط {t['الشرط']} · "
                         f"السعر {t['السعر_الحالي']}")
        lines.append("")

    flags = brief.get("أحجام_غير_طبيعية", [])
    if flags:
        lines.append("⚡ أحجام تداول غير طبيعية (غالباً فيها خبر):")
        for f in flags:
            lines.append(f"  • {f['الاسم']} — {_pct(f.get('التغير_%'))} · "
                         f"الحجم {f.get('نسبة_الكمية_للمتوسط')}× المعتاد")
        lines.append("")

    movers = brief.get("تحركات_ملحوظة", [])
    if movers:
        lines.append("📈 تحركات ملحوظة:")
        for m in movers:
            lines.append(f"  • {m['الاسم']}: {m.get('السعر')} ر.س "
                         f"({_pct(m.get('التغير_%'))})")
        lines.append("")

    div = brief.get("توزيعات_قريبة", [])
    if div:
        lines.append("💰 توزيعات متوقعة خلال شهر (تقديرية):")
        for d in div:
            lines.append(f"  • {d['الاسم']} — بعد {d.get('أيام_متبقية')} يوم "
                         f"· عائد {d.get('عائد_التوزيعات_%')}%")
        lines.append("")

    lines.append("— قائمة المتابعة كاملة —")
    for r in brief.get("الأسهم", []):
        flag = " ⚡" if r.get("حجم_غير_طبيعي") else ""
        lines.append(f"  {r['الاسم']}: {r.get('السعر')} ر.س "
                     f"({_pct(r.get('التغير_%'))}){flag}")

    if not movers and not flags and not triggered:
        lines.append("")
        lines.append("ما فيه شي يستحق الانتباه في هذي الجلسة.")

    lines += ["", "—" * 20,
              "أسعار من Yahoo Finance وقد تتأخر عن السوق.",
              "معلومات فقط، وليست توصية استثمارية."]
    return "\n".join(lines)


def send_email(body: str) -> bool:
    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASS", "")
    to = os.getenv("MAIL_TO", "")

    missing = [n for n, v in
               [("SMTP_HOST", host), ("SMTP_USER", user),
                ("SMTP_PASS", password), ("MAIL_TO", to)] if not v]
    if missing:
        print(f"❌ متغيرات ناقصة: {', '.join(missing)}")
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"نبض تداول — {datetime.today().strftime('%Y-%m-%d')}"
    msg["From"] = user
    msg["To"] = to

    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        print("✅ أُرسل الملخص بالإيميل")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"❌ فشل الإرسال: {exc}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="الملخص الصباحي")
    parser.add_argument("--email", action="store_true", help="أرسله بالإيميل")
    args = parser.parse_args()

    text = to_text(build_brief())
    print(text)
    if args.email and not send_email(text):
        sys.exit(1)


if __name__ == "__main__":
    main()
