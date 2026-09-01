"""
symbols.py
==========
إدارة رموز الشركات في السوق السعودي.

مصدران:
  1. SEED_NAMES — أسماء عربية مكتوبة يدوياً لأشهر الشركات.
     غرضها البحث بالعربي، لأن ياهو ما يعرف الأسماء العربية.
  2. tadawul_universe.json — القائمة الكاملة المكتشفة آلياً.
     يبنيها سكربت build_universe.py ويغطي كل سهم مدرج فعلياً.

لو الملف موجود نستخدمه، ولو غير موجود نشتغل بالبذرة فقط
بالإضافة إلى أي رقم رباعي يكتبه المستخدم مباشرة.
"""

from __future__ import annotations

import json
import os
import re

UNIVERSE_FILE = "tadawul_universe.json"

# ───────────────────────────────────────────────────────────────
# أسماء عربية لأشهر الشركات — تُستخدم للبحث بالعربي
# ───────────────────────────────────────────────────────────────
SEED_NAMES: dict[str, tuple[str, str]] = {
    # البنوك والخدمات المالية
    "1010": ("بنك الرياض", "Riyad Bank"),
    "1020": ("بنك الجزيرة", "Bank Aljazira"),
    "1030": ("سيرا القابضة", "Seera Group"),
    "1050": ("البنك السعودي الفرنسي", "Banque Saudi Fransi"),
    "1060": ("البنك السعودي الأول", "Saudi Awwal Bank"),
    "1080": ("البنك العربي الوطني", "Arab National Bank"),
    "1111": ("مجموعة تداول السعودية", "Saudi Tadawul Group"),
    "1120": ("مصرف الراجحي", "Al Rajhi Bank"),
    "1140": ("بنك البلاد", "Bank Albilad"),
    "1150": ("مصرف الإنماء", "Alinma Bank"),
    "1180": ("البنك الأهلي السعودي", "Saudi National Bank"),
    "1182": ("أملاك العالمية", "Amlak International"),
    "1183": ("سهل للتمويل", "SHL Finance"),
    # المواد الأساسية والصناعة
    "1201": ("تكوين", "Takween"),
    "1202": ("مبكو", "MEPCO"),
    "1210": ("بي سي آي", "BCI"),
    "1211": ("معادن", "Maaden"),
    "1212": ("أسترا الصناعية", "Astra Industrial"),
    "1213": ("نسيج", "Naseej"),
    "1214": ("شاكر", "Al Hassan Shaker"),
    "1301": ("أسلاك", "United Wire Factories"),
    "1302": ("بوان", "Bawan"),
    "1303": ("اليمامة للحديد", "Al Yamamah Steel"),
    "1320": ("الأنابيب السعودية", "Saudi Steel Pipe"),
    "2010": ("سابك", "SABIC"),
    "2020": ("سابك للمغذيات الزراعية", "SABIC Agri-Nutrients"),
    "2030": ("المصافي", "Saudi Arabia Refineries"),
    "2040": ("الخزف السعودي", "Saudi Ceramics"),
    "2050": ("صافولا", "Savola Group"),
    "2060": ("التصنيع", "Tasnee"),
    "2070": ("سبيماكو", "SPIMACO"),
    "2080": ("غازات", "GASCO"),
    "2081": ("الخريف للمياه", "Alkhorayef Water"),
    "2082": ("أكوا باور", "ACWA Power"),
    "2083": ("مرافق", "Marafiq"),
    "2090": ("جبسكو", "National Gypsum"),
    "2170": ("اللجين", "Alujain"),
    "2180": ("فيبكو", "FIPCO"),
    "2190": ("السيسكو", "SISCO"),
    "2200": ("أنابيب عربية", "Arabian Pipes"),
    "2210": ("نماء للكيماويات", "Nama Chemicals"),
    "2222": ("أرامكو السعودية", "Saudi Aramco"),
    "2223": ("لوبريف", "Luberef"),
    "2230": ("الكيميائية السعودية", "Saudi Chemical"),
    "2240": ("الزامل للصناعة", "Zamil Industrial"),
    "2250": ("المجموعة السعودية", "SIIG"),
    "2270": ("سدافكو", "SADAFCO"),
    "2280": ("المراعي", "Almarai"),
    "2290": ("ينساب", "Yansab"),
    "2300": ("صناعة الورق", "Saudi Paper"),
    "2310": ("سبكيم العالمية", "Sipchem"),
    "2320": ("البابطين", "Al Babtain"),
    "2330": ("المتقدمة", "Advanced Petrochemical"),
    "2340": ("العبداللطيف", "Al Abdullatif"),
    "2350": ("كيان السعودية", "Saudi Kayan"),
    "2360": ("الفخارية", "Saudi Vitrified Clay Pipe"),
    "2370": ("مسك", "MESC"),
    "2380": ("بترو رابغ", "Petro Rabigh"),
    # الأسمنت
    "3001": ("أسمنت حائل", "Hail Cement"),
    "3002": ("أسمنت نجران", "Najran Cement"),
    "3003": ("أسمنت المدينة", "City Cement"),
    "3004": ("أسمنت الشمالية", "Northern Region Cement"),
    "3005": ("أسمنت أم القرى", "Umm Al Qura Cement"),
    "3010": ("أسمنت العربية", "Arabian Cement"),
    "3020": ("أسمنت اليمامة", "Yamama Cement"),
    "3030": ("أسمنت السعودية", "Saudi Cement"),
    "3040": ("أسمنت القصيم", "Qassim Cement"),
    "3050": ("أسمنت الجنوبية", "Southern Province Cement"),
    "3060": ("أسمنت ينبع", "Yanbu Cement"),
    "3080": ("أسمنت الشرقية", "Eastern Province Cement"),
    "3090": ("أسمنت تبوك", "Tabuk Cement"),
    "3091": ("أسمنت الجوف", "Al Jouf Cement"),
    # التجزئة والرعاية الصحية والعقار والنقل
    "4001": ("أسواق العثيم", "Al Othaim Markets"),
    "4002": ("المواساة", "Mouwasat Medical"),
    "4003": ("إكسترا", "United Electronics eXtra"),
    "4004": ("دله الصحية", "Dallah Health"),
    "4005": ("رعاية", "National Medical Care"),
    "4006": ("أسواق المزرعة", "Farm Superstores"),
    "4007": ("الحمادي", "Al Hammadi"),
    "4008": ("ساكو", "SACO"),
    "4009": ("السعودي الألماني الصحية", "Saudi German Health"),
    "4010": ("دور للضيافة", "Dur Hospitality"),
    "4011": ("لازوردي", "Lazurde"),
    "4013": ("د. سليمان الحبيب", "Dr Sulaiman Al Habib"),
    "4015": ("جمجوم فارما", "Jamjoom Pharma"),
    "4020": ("العقارية", "Saudi Real Estate"),
    "4030": ("البحري", "Bahri"),
    "4031": ("الخدمات الأرضية", "Saudi Ground Services"),
    "4040": ("سابتكو", "SAPTCO"),
    "4050": ("ساسكو", "SASCO"),
    "4051": ("باعظيم التجارية", "Baazeem Trading"),
    "4061": ("أنعام القابضة", "Anaam Holding"),
    "4090": ("طيبة", "Taiba Investments"),
    "4100": ("مكة للإنشاء", "Makkah Construction"),
    "4110": ("باتك", "BATIC"),
    "4150": ("الرياض للتعمير", "Arriyadh Development"),
    "4160": ("ثمار التنمية", "Tanmiah Food"),
    "4161": ("بن داود القابضة", "BinDawood Holding"),
    "4162": ("المنجم للأغذية", "Almunajem Foods"),
    "4163": ("الدواء", "Al Dawaa Medical"),
    "4164": ("النهدي", "Nahdi Medical"),
    "4165": ("الموسى الصحية", "Almoosa Health"),
    "4180": ("فتيحي القابضة", "Fitaihi Holding"),
    "4190": ("جرير", "Jarir Marketing"),
    "4200": ("الدريس", "Aldrees"),
    "4210": ("الأبحاث والإعلام", "SRMG"),
    "4220": ("إعمار المدينة الاقتصادية", "Emaar Economic City"),
    "4230": ("البحر الأحمر", "Red Sea International"),
    "4240": ("سينومي ريتيل", "Cenomi Retail"),
    "4250": ("جبل عمر", "Jabal Omar"),
    "4260": ("بدجت السعودية", "Budget Saudi"),
    "4261": ("ذيب لتأجير السيارات", "Theeb Rent a Car"),
    "4262": ("لومي", "Lumi Rental"),
    "4263": ("سال", "SAL Saudi Logistics"),
    "4280": ("المملكة القابضة", "Kingdom Holding"),
    "4300": ("دار الأركان", "Dar Al Arkan"),
    "4310": ("مدينة المعرفة", "Knowledge Economic City"),
    "4320": ("الأندلس العقارية", "Alandalus Property"),
    "4321": ("سينومي سنترز", "Cenomi Centers"),
    "4330": ("الرياض ريت", "Riyad REIT"),
    "4331": ("الجزيرة ريت", "Aljazira REIT"),
    "4338": ("الأهلي ريت", "Alahli REIT"),
    "4339": ("الراجحي ريت", "Al Rajhi REIT"),
    # المرافق والأغذية والزراعة
    "5110": ("كهرباء السعودية", "Saudi Electricity"),
    "6001": ("حلواني إخوان", "Halwani Bros"),
    "6002": ("هرفي للأغذية", "Herfy Foods"),
    "6004": ("كاتريون", "Catrion Catering"),
    "6010": ("نادك", "NADEC"),
    "6012": ("ريدان الغذائية", "Raydan Food"),
    "6015": ("أمريكانا", "Americana Restaurants"),
    "6020": ("القصيم الزراعية", "Gaco"),
    "6040": ("تبوك الزراعية", "Tabuk Agriculture"),
    "6050": ("الأسماك", "Saudi Fisheries"),
    "6070": ("الجوف الزراعية", "Al Jouf Agriculture"),
    "6090": ("جازادكو", "Jazan Development"),
    # الاتصالات والتقنية والإعلام
    "7010": ("الاتصالات السعودية", "stc"),
    "7020": ("موبايلي", "Mobily"),
    "7030": ("زين السعودية", "Zain KSA"),
    "7040": ("عذيب للاتصالات", "Atheeb Telecom"),
    "7200": ("إم بي سي", "MBC Group"),
    "7201": ("عرب سات", "Arabsat"),
    "7203": ("علم", "Elm"),
    "7210": ("نايس ون", "Nice One"),
    # التأمين
    "8010": ("التعاونية", "Tawuniya"),
    "8012": ("جزيرة تكافل", "Jazira Takaful"),
    "8020": ("ملاذ للتأمين", "Malath Insurance"),
    "8030": ("ميدغلف", "MedGulf"),
    "8040": ("أليانز إس إف", "Allianz SF"),
    "8050": ("سلامة", "Salama"),
    "8060": ("ولاء للتأمين", "Walaa Insurance"),
    "8070": ("الدرع العربي", "Arabian Shield"),
    "8100": ("سايكو", "SAICO"),
    "8210": ("بوبا العربية", "Bupa Arabia"),
    "8230": ("تكافل الراجحي", "Al Rajhi Takaful"),
}

INDICES: dict[str, tuple[str, str]] = {
    "^TASI.SR": ("المؤشر العام تاسي", "Tadawul All Share Index"),
}

# اختصارات ينطقها الناس
ALIASES: dict[str, str] = {
    "ارامكو": "2222", "aramco": "2222",
    "الراجحي": "1120", "راجحي": "1120", "rajhi": "1120",
    "سابك": "2010", "sabic": "2010",
    "الاهلي": "1180", "snb": "1180",
    "الانماء": "1150", "alinma": "1150",
    "stc": "7010", "اس تي سي": "7010", "الاتصالات": "7010",
    "معادن": "1211", "maaden": "1211",
    "المراعي": "2280", "almarai": "2280",
    "جرير": "4190", "jarir": "4190",
    "الكهرباء": "5110", "كهرباء": "5110",
    "اكوا": "2082", "اكوا باور": "2082", "acwa": "2082",
    "موبايلي": "7020", "mobily": "7020",
    "زين": "7030", "zain": "7030",
    "بوبا": "8210", "bupa": "8210",
    "السعودي الالماني": "4009", "الالماني": "4009",
    "سعودي الماني": "4009", "saudi german": "4009",
    "الحبيب": "4013", "سليمان الحبيب": "4013",
    "النهدي": "4164", "nahdi": "4164",
    "تاسي": "^TASI.SR", "المؤشر": "^TASI.SR", "tasi": "^TASI.SR",
}


def strip_arabic(text: str) -> str:
    """توحيد النص العربي لتسهيل المطابقة: بدون تشكيل، ألف وهاء موحّدة."""
    text = re.sub(r"[\u064B-\u0652\u0640]", "", text or "")
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ة", "ه").replace("ى", "ي")
    return " ".join(text.split()).strip().lower()


# ───────────────────────────────────────────────────────────────
# تحميل القائمة الكاملة المكتشفة آلياً
# ───────────────────────────────────────────────────────────────
def _load_universe() -> tuple[dict[str, tuple[str, str]], dict]:
    table = {code: names for code, names in SEED_NAMES.items()}
    meta = {"source": "seed", "count": len(table), "built_at": None}

    path = UNIVERSE_FILE
    if not os.path.exists(path):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), UNIVERSE_FILE)
    if not os.path.exists(path):
        return table, meta

    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        companies = payload.get("companies", {})
        for code, info in companies.items():
            seed = SEED_NAMES.get(code)
            name_ar = (seed[0] if seed else "") or info.get("name_ar") or f"شركة {code}"
            name_en = (seed[1] if seed else "") or info.get("name_en") or ""
            table[code] = (name_ar, name_en)
        meta = {
            "source": "universe",
            "count": len(table),
            "built_at": payload.get("built_at"),
            "includes_nomu": payload.get("includes_nomu", False),
        }
    except Exception:  # noqa: BLE001
        pass

    return table, meta


SYMBOLS, UNIVERSE_META = _load_universe()


def universe_status() -> str:
    """سطر مختصر يوصف مصدر قائمة الشركات — يُعرض في الواجهة."""
    if UNIVERSE_META["source"] == "universe":
        built = UNIVERSE_META.get("built_at") or "غير معروف"
        nomu = " (يشمل نمو)" if UNIVERSE_META.get("includes_nomu") else ""
        return f"{UNIVERSE_META['count']} شركة · محدّثة {built}{nomu}"
    return (f"{UNIVERSE_META['count']} شركة من القائمة المدمجة · "
            f"شغّل build_universe.py لتغطية كل السوق")
