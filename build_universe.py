"""
build_universe.py
=================
يبني قائمة كاملة بكل الأسهم المدرجة في السوق السعودي — تلقائياً.

بدل كتابة الشركات يدوياً (وهو ما ينتهي دائماً بشركات ناقصة)،
هذا السكربت يمسح كل أرقام الشركات المحتملة، يتحقق أيها له بيانات
تداول فعلية، ثم يجلب اسم كل شركة ويحفظ النتيجة في:

    tadawul_universe.json

التشغيل:
    python build_universe.py              # السوق الرئيسي
    python build_universe.py --nomu       # يشمل السوق الموازي (نمو)
    python build_universe.py --quick      # تحقق فقط، بدون جلب الأسماء

أعِد تشغيله كل بضعة أشهر لالتقاط الإدراجات الجديدة.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Iterable

import pandas as pd
import requests

from config import REQUEST_TIMEOUT, USER_AGENT
from symbols import SEED_NAMES

UNIVERSE_FILE = "tadawul_universe.json"

# نطاقات أرقام الشركات في تداول، حسب القطاعات
MAIN_RANGES = [
    (1010, 1400),   # البنوك والاستثمار والمواد الأساسية
    (2000, 2400),   # الطاقة والبتروكيماويات والصناعة
    (3000, 3100),   # الأسمنت
    (4000, 4600),   # التجزئة والصحة والعقار والنقل
    (5000, 5200),   # المرافق
    (6000, 6100),   # الأغذية والزراعة
    (7000, 7300),   # الاتصالات والتقنية والإعلام
    (8000, 8400),   # التأمين
]
NOMU_RANGES = [(9500, 9700)]   # السوق الموازي

CHUNK = 60          # عدد الرموز في كل طلب تحقق
NAME_DELAY = 0.35   # ثانية بين طلبات جلب الأسماء (تهذيب مع الخادم)


def candidates(ranges: list[tuple[int, int]]) -> list[str]:
    out: list[str] = []
    for lo, hi in ranges:
        out.extend(str(c) for c in range(lo, hi + 1))
    return out


def chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def verify(codes: list[str]) -> list[str]:
    """يتحقق أي الرموز لها بيانات تداول فعلية، دفعة واحدة لكل مجموعة."""
    import yfinance as yf

    valid: list[str] = []
    batches = list(chunks(codes, CHUNK))

    for i, batch in enumerate(batches, 1):
        tickers = [f"{c}.SR" for c in batch]
        print(f"  [{i}/{len(batches)}] فحص {len(batch)} رمزاً…", end=" ", flush=True)
        try:
            data = yf.download(
                tickers, period="1mo", interval="1d",
                group_by="ticker", threads=True,
                progress=False, auto_adjust=False,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"تخطي ({exc})")
            continue

        found = 0
        for code, ticker in zip(batch, tickers):
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    if ticker not in data.columns.get_level_values(0):
                        continue
                    series = data[ticker]["Close"]
                else:
                    series = data["Close"]
                if series.notna().sum() >= 3:
                    valid.append(code)
                    found += 1
            except Exception:  # noqa: BLE001
                continue

        print(f"وجدت {found}")
        time.sleep(0.4)

    return sorted(set(valid))


def fetch_name(code: str) -> tuple[str, str]:
    """اسم الشركة: من قائمة البذرة العربية أولاً، ثم من ياهو."""
    seed = SEED_NAMES.get(code)
    name_ar = seed[0] if seed else ""
    name_en = seed[1] if seed else ""

    if name_ar and name_en:
        return name_ar, name_en

    try:
        resp = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": f"{code}.SR", "quotesCount": 3, "newsCount": 0},
            headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT,
        )
        for quote in resp.json().get("quotes", []):
            if quote.get("symbol") == f"{code}.SR":
                fetched = quote.get("longname") or quote.get("shortname") or ""
                name_en = name_en or fetched
                break
    except Exception:  # noqa: BLE001
        pass

    return (name_ar or name_en or f"شركة {code}"), name_en


def main() -> None:
    parser = argparse.ArgumentParser(description="بناء قائمة أسهم تداول")
    parser.add_argument("--nomu", action="store_true", help="يشمل السوق الموازي نمو")
    parser.add_argument("--quick", action="store_true", help="بدون جلب الأسماء")
    args = parser.parse_args()

    ranges = MAIN_RANGES + (NOMU_RANGES if args.nomu else [])
    codes = candidates(ranges)

    print(f"\n🔍 فحص {len(codes)} رمزاً محتملاً في السوق السعودي")
    print("   قد يستغرق عدة دقائق. اتركه يكمّل.\n")

    valid = verify(codes)
    print(f"\n✅ وجدت {len(valid)} سهماً له بيانات تداول فعلية\n")

    if not valid:
        print("⚠️ ما وجدت أي رمز. تحقق من اتصالك بالإنترنت.")
        sys.exit(1)

    universe: dict[str, dict] = {}
    if args.quick:
        for code in valid:
            seed = SEED_NAMES.get(code, (f"شركة {code}", ""))
            universe[code] = {"symbol": f"{code}.SR",
                              "name_ar": seed[0], "name_en": seed[1]}
    else:
        print("📇 جلب أسماء الشركات…")
        for i, code in enumerate(valid, 1):
            name_ar, name_en = fetch_name(code)
            universe[code] = {"symbol": f"{code}.SR",
                              "name_ar": name_ar, "name_en": name_en}
            if i % 25 == 0 or i == len(valid):
                print(f"  {i}/{len(valid)}")
            if code not in SEED_NAMES:
                time.sleep(NAME_DELAY)

    payload = {
        "built_at": pd.Timestamp.today().strftime("%Y-%m-%d"),
        "count": len(universe),
        "includes_nomu": args.nomu,
        "companies": universe,
    }
    with open(UNIVERSE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(f"\n💾 حُفظت {len(universe)} شركة في {UNIVERSE_FILE}")
    print("   التطبيق سيستخدمها تلقائياً عند التشغيل القادم.\n")

    missing_ar = [c for c, v in universe.items()
                  if not v["name_ar"] or v["name_ar"].startswith("شركة ")]
    if missing_ar:
        print(f"ℹ️  {len(missing_ar)} شركة بدون اسم عربي — البحث بالرقم يعمل معها.")
        print("   لإضافة أسماء عربية، عدّل SEED_NAMES في symbols.py.\n")


if __name__ == "__main__":
    main()
