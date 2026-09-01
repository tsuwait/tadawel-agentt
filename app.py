"""
app.py
======
واجهة الويب لوكيل الأسهم السعودية.

الصفحات:
    الرئيسية    — نبض السوق وقائمة المتابعة في نظرة واحدة
    ليش تحرك؟   — الميزة الأساسية: تفسير حركة السهم اليوم
    بحث         — لقطة سعرية كاملة لأي سهم
    المحلل      — محادثة حرة

التشغيل:  streamlit run app.py
"""

from __future__ import annotations

import json
import os
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import market_pulse as mp
import providers
import tadawul_data as td
from config import ANTHROPIC_API_KEY, APP_PASSWORD

WATCHLIST_FILE = "watchlist.json"
DEFAULT_WATCHLIST = ["2222", "1120", "2010", "7010", "2280"]

st.set_page_config(page_title="نبض تداول", page_icon="📊",
                   layout="wide", initial_sidebar_state="collapsed")

# ══════════════════════════════════════════════════════════════
# التنسيق
# ══════════════════════════════════════════════════════════════
st.markdown("""
<style>
  :root {
    --ink: #0E1519; --muted: #5C6B75; --line: #D9E0E5;
    --surface: #FFFFFF; --bg: #EEF1F3;
    --pine: #0B5C4E; --up: #0E7C5A; --down: #B23A2E; --amber: #8A6A1F;
  }
  html, body, [class*="css"], .stApp {
    direction: rtl; text-align: right;
    font-family: "SF Arabic", "Geeza Pro", "Tajawal", "Segoe UI", system-ui, sans-serif;
  }
  .stApp { background: var(--bg); }
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding-top: 1.6rem; max-width: 900px; }
  h1, h2, h3, p, label, div { text-align: right; }

  .hero { margin-bottom: 6px; }
  .hero .eyebrow {
    font-size: 11px; letter-spacing: .16em; color: var(--pine); font-weight: 700;
  }
  .hero h1 { font-size: 26px; font-weight: 800; margin: 4px 0 2px; letter-spacing: -.4px; }
  .hero .when { font-size: 12.5px; color: var(--muted); }

  .card {
    background: var(--surface); border: 1px solid var(--line);
    border-radius: 13px; padding: 16px 18px; margin-bottom: 12px;
  }
  .card-label {
    font-size: 11px; letter-spacing: .13em; color: var(--muted);
    font-weight: 700; margin-bottom: 8px;
  }
  .tasi-val {
    font-size: 32px; font-weight: 800; letter-spacing: -1px;
    font-variant-numeric: tabular-nums; direction: ltr; display: inline-block;
  }
  .tasi-chg { font-size: 15px; font-weight: 700; direction: ltr; display: inline-block; margin-right: 10px; }
  .asof { font-size: 11.5px; color: var(--muted); margin-top: 5px; font-variant-numeric: tabular-nums; }

  .srow {
    display: grid; grid-template-columns: 1fr 84px 78px;
    align-items: center; gap: 8px;
    padding: 12px 2px; border-bottom: 1px solid var(--line);
  }
  .srow:last-child { border-bottom: none; }
  .srow .nm { font-size: 14.5px; font-weight: 700; }
  .srow .cd { font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; }
  .srow .px { font-size: 15px; font-weight: 700; font-variant-numeric: tabular-nums; direction: ltr; text-align: left; }
  .srow .ch { font-size: 14px; font-weight: 800; font-variant-numeric: tabular-nums; direction: ltr; text-align: left; }
  .up { color: var(--up); } .down { color: var(--down); } .flat { color: var(--muted); }

  .flag {
    display: inline-block; font-size: 10.5px; font-weight: 700;
    color: var(--amber); background: #FBF6E9; border: 1px solid #EADFC0;
    border-radius: 5px; padding: 1px 6px; margin-right: 6px; vertical-align: 1px;
  }
  .attn {
    background: #FBF6E9; border: 1px solid #EADFC0; border-radius: 11px;
    padding: 13px 15px; margin-bottom: 12px; font-size: 13.5px; line-height: 1.75;
    color: #6B5316;
  }
  .attn b { color: var(--ink); }
  .empty { color: var(--muted); font-size: 13.5px; padding: 14px 2px; line-height: 1.7; }
  .foot { font-size: 11.5px; color: var(--muted); line-height: 1.7; padding-top: 8px; }
  .stTabs [data-baseweb="tab-list"] { gap: 4px; }
  .stTabs [data-baseweb="tab"] { font-size: 14px; font-weight: 600; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# بوابة كلمة المرور (اختيارية)
# ══════════════════════════════════════════════════════════════
def _gate() -> bool:
    if not APP_PASSWORD or st.session_state.get("authed"):
        return True
    st.markdown("### 🔒 الدخول")
    entered = st.text_input("كلمة المرور", type="password")
    if entered:
        if entered == APP_PASSWORD:
            st.session_state.authed = True
            st.rerun()
        st.error("كلمة المرور غير صحيحة")
    return False


if not _gate():
    st.stop()


# ══════════════════════════════════════════════════════════════
# قائمة المتابعة
# ══════════════════════════════════════════════════════════════
def load_watchlist() -> list[str]:
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, encoding="utf-8") as f:
                items = json.load(f)
            if isinstance(items, list) and items:
                return items
        except Exception:
            pass
    return DEFAULT_WATCHLIST.copy()


def save_watchlist(items: list[str]) -> None:
    try:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)
    except Exception:
        pass


if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_watchlist()


def greeting() -> str:
    h = datetime.now().hour
    if h < 12:
        return "صباح الخير"
    if h < 17:
        return "مساء الخير"
    return "مساء الخير"


def chg_class(pct) -> str:
    if pct is None:
        return "flat"
    return "up" if pct > 0 else ("down" if pct < 0 else "flat")


def chg_text(pct) -> str:
    if pct is None:
        return "—"
    return f"{'+' if pct > 0 else ''}{pct:.2f}%"


# ══════════════════════════════════════════════════════════════
# الترويسة
# ══════════════════════════════════════════════════════════════
st.markdown(
    f"""<div class="hero">
      <div class="eyebrow">نبض تداول</div>
      <h1>{greeting()}</h1>
      <div class="when">{datetime.now().strftime('%Y-%m-%d')} · السوق السعودي</div>
    </div>""",
    unsafe_allow_html=True,
)

tab_home, tab_why, tab_search, tab_chat = st.tabs(
    ["الرئيسية", "ليش تحرك؟", "بحث", "المحلل"]
)

# ══════════════════════════════════════════════════════════════
# ١ — الرئيسية
# ══════════════════════════════════════════════════════════════
with tab_home:
    with st.spinner("جاري قراءة السوق..."):
        data = mp.get_watchlist_movers(st.session_state.watchlist)

    market = data.get("السوق_العام", {})
    if "error" in market:
        st.warning("تعذّر جلب المؤشر العام حالياً.")
    else:
        pct = market.get("نسبة_التغير_%")
        st.markdown(
            f"""<div class="card">
              <div class="card-label">المؤشر العام · تاسي</div>
              <span class="tasi-val">{market['النقاط']:,.2f}</span>
              <span class="tasi-chg {chg_class(pct)}">{chg_text(pct)}</span>
              <div class="asof">آخر جلسة · {market['تاريخ_الجلسة']}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    flagged = data.get("تستحق_الانتباه", [])
    if flagged:
        names = "، ".join(f"<b>{r['الاسم']}</b> ({chg_text(r['التغير_%'])})"
                          for r in flagged[:4])
        st.markdown(
            f'<div class="attn">⚡ تستحق الانتباه اليوم: {names}'
            f'<br>افتح تبويب «ليش تحرك؟» لمعرفة السبب.</div>',
            unsafe_allow_html=True,
        )

    rows = data.get("الأسهم", [])
    if not rows:
        st.markdown('<div class="empty">قائمة المتابعة فاضية. أضف أسهماً من الأسفل.</div>',
                    unsafe_allow_html=True)
    else:
        html = '<div class="card"><div class="card-label">قائمة المتابعة</div>'
        for r in rows:
            flag = '<span class="flag">حجم غير طبيعي</span>' if r["حجم_غير_طبيعي"] else ""
            html += (
                f'<div class="srow">'
                f'<div><div class="nm">{r["الاسم"]}{flag}</div>'
                f'<div class="cd">{r["الرمز"]}</div></div>'
                f'<div class="px">{r["السعر"]:,.2f}</div>'
                f'<div class="ch {chg_class(r["التغير_%"])}">{chg_text(r["التغير_%"])}</div>'
                f'</div>'
            )
        html += '</div>'
        st.markdown(html, unsafe_allow_html=True)

    for e in data.get("أخطاء", []):
        st.caption(f"⚠️ {e['المدخل']}: {e['الخطأ']}")

    with st.expander("حالة النظام"):
        st.write(f"**قائمة الشركات:** {td.universe_status()}")
        st.write(f"**مزوّدو البيانات النشطون:** {'، '.join(providers.active_providers())}")
        st.caption(
            "لتغطية كل أسهم تاسي تلقائياً شغّل: `python build_universe.py` "
            "— يكتشف كل سهم مدرج ويحفظه، وأعد تشغيله كل بضعة أشهر."
        )

    with st.expander("تعديل قائمة المتابعة"):
        c1, c2 = st.columns([3, 1])
        new_item = c1.text_input("أضف سهماً", placeholder="مثال: معادن أو 1211",
                                 label_visibility="collapsed")
        if c2.button("إضافة", use_container_width=True) and new_item.strip():
            r = td.resolve_symbol(new_item.strip())
            if not r:
                st.error("ما لقيت هذا السهم.")
            elif r["code"] in st.session_state.watchlist:
                st.info("موجود مسبقاً.")
            else:
                st.session_state.watchlist.append(r["code"])
                save_watchlist(st.session_state.watchlist)
                st.rerun()

        if st.session_state.watchlist:
            to_remove = st.multiselect(
                "حذف أسهم",
                options=st.session_state.watchlist,
                format_func=lambda c: f"{td.SYMBOLS.get(c, (c, ''))[0]} ({c})",
            )
            if st.button("احذف المحدد") and to_remove:
                st.session_state.watchlist = [
                    c for c in st.session_state.watchlist if c not in to_remove
                ]
                save_watchlist(st.session_state.watchlist)
                st.rerun()

# ══════════════════════════════════════════════════════════════
# ٢ — ليش تحرك؟
# ══════════════════════════════════════════════════════════════
with tab_why:
    st.markdown("اختر سهماً، ونشوف كم تحرك اليوم — ثم نبحث عن السبب.")

    options = st.session_state.watchlist
    c1, c2 = st.columns([2, 2])
    picked = c1.selectbox(
        "من قائمة المتابعة", options=["—"] + options,
        format_func=lambda c: "—" if c == "—" else f"{td.SYMBOLS.get(c, (c, ''))[0]} ({c})",
    )
    typed = c2.text_input("أو اكتب سهماً آخر", placeholder="مثال: معادن")
    target = typed.strip() or (picked if picked != "—" else "")

    if target:
        with st.spinner("جاري حساب الحركة..."):
            move = mp.get_daily_move(target)

        if "error" in move:
            st.error(move["error"])
        else:
            pct = move["نسبة_التغير_%"]
            st.markdown(
                f"""<div class="card">
                  <div class="card-label">{move['الاسم']} · {move['رقم_الشركة']}</div>
                  <span class="tasi-val">{move['الإغلاق']:,.2f}</span>
                  <span class="tasi-chg {chg_class(pct)}">{chg_text(pct)}</span>
                  <div class="asof">جلسة {move['تاريخ_الجلسة']} · {move['تصنيف_الحركة']}</div>
                </div>""",
                unsafe_allow_html=True,
            )

            m1, m2, m3 = st.columns(3)
            m1.metric("حجم التداول مقابل معدله",
                      f"{move['نسبة_الكمية_للمتوسط'] or '—'}×",
                      help=move["ملاحظة_الكمية"])
            m2.metric("المدى اليومي", f"{move['المدى_اليومي_%'] or '—'}%")
            m3.metric("الموقع من نطاق السنة",
                      f"{move['الموقع_من_نطاق_السنة_%'] or '—'}%",
                      help=f"أدنى {move['أدنى_52_أسبوع']} · أعلى {move['أعلى_52_أسبوع']}")

            if move.get("قراءة_السياق"):
                st.info(move["قراءة_السياق"])

            if move["حجم_غير_طبيعي"]:
                st.markdown(f'<div class="attn">⚡ {move["ملاحظة_الكمية"]} — '
                            f'غالباً فيه خبر أو إعلان.</div>', unsafe_allow_html=True)

            st.divider()
            if not ANTHROPIC_API_KEY:
                st.warning("لتفعيل البحث عن السبب، ضع ANTHROPIC_API_KEY في ملف .env")
            elif st.button("🔍 ابحث عن السبب", type="primary", use_container_width=True):
                if "agent" not in st.session_state:
                    from agent import TadawulAgent
                    st.session_state.agent = TadawulAgent()
                    st.session_state.history = []
                with st.spinner("جاري البحث في الأخبار وإعلانات تداول..."):
                    try:
                        answer = st.session_state.agent.chat(
                            f"ليش تحرك سهم {move['الاسم']} "
                            f"({move['رقم_الشركة']}) في جلسة {move['تاريخ_الجلسة']}؟ "
                            f"اتبع منهجية 'ليش تحرك السهم' كاملة."
                        )
                    except Exception as exc:
                        answer = f"صار خطأ: {exc}"
                st.markdown(answer)

# ══════════════════════════════════════════════════════════════
# ٣ — بحث
# ══════════════════════════════════════════════════════════════
with tab_search:
    query = st.text_input("اسم الشركة أو رقمها",
                          placeholder="مثال: أرامكو أو 2222 أو الراجحي")
    years = st.selectbox("مدة الرسم", [1, 2, 3, 5], index=1,
                         format_func=lambda y: f"{y} سنة")

    if query:
        with st.spinner("جاري جلب البيانات..."):
            snap = td.get_snapshot(query)

        if "error" in snap:
            st.error(snap["error"])
            for m in td.search_stocks(query):
                st.write(f"• {m['name_ar']} — `{m['code']}`")
        else:
            last = snap["آخر_إغلاق"]
            st.markdown(
                f"""<div class="card">
                  <div class="card-label">{snap['الاسم']} · {snap['رقم_الشركة']}</div>
                  <span class="tasi-val">{last['السعر']:,.2f}</span>
                  <span class="tasi-chg flat">ريال</span>
                  <div class="asof">آخر إغلاق · {last['التاريخ']} · {snap.get('المصدر','')}</div>
                </div>""",
                unsafe_allow_html=True,
            )

            labels = {"يوم_سابق": "الجلسة السابقة", "أسبوع": "قبل أسبوع",
                      "شهر": "قبل شهر", "3_أشهر": "قبل 3 أشهر",
                      "6_أشهر": "قبل 6 أشهر", "سنة": "قبل سنة",
                      "بداية_العام": "من بداية العام"}
            rows = [{
                "الفترة": lbl,
                "تاريخ الإغلاق": it["تاريخ_الإغلاق"],
                "السعر وقتها": it["السعر"],
                "الفرق": it["الفرق"],
                "التغير %": it["نسبة_التغير_%"],
            } for k, lbl in labels.items()
                if (it := snap["المقارنات"].get(k, {})).get("available")]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            try:
                df = td.get_history(snap["الرمز"], years=max(years, 1))
                df = df.loc[df.index >= df.index[-1] - pd.DateOffset(years=years)]
                fig = go.Figure(go.Scatter(x=df.index, y=df["Close"], mode="lines",
                                           line=dict(width=2, color="#0B5C4E")))
                fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10),
                                  yaxis_title="ريال", hovermode="x unified",
                                  plot_bgcolor="white", paper_bgcolor="white")
                st.plotly_chart(fig, use_container_width=True)
            except Exception as exc:
                st.warning(f"تعذّر رسم البيان: {exc}")

            with st.expander("معلومات الشركة"):
                st.json(td.get_profile(snap["الرمز"]))

# ══════════════════════════════════════════════════════════════
# ٤ — المحلل
# ══════════════════════════════════════════════════════════════
with tab_chat:
    if not ANTHROPIC_API_KEY:
        st.warning("ضع ANTHROPIC_API_KEY في ملف .env لتفعيل المحادثة.")
    else:
        if "agent" not in st.session_state:
            from agent import TadawulAgent
            st.session_state.agent = TadawulAgent()
            st.session_state.history = []

        if st.button("محادثة جديدة"):
            st.session_state.agent.reset()
            st.session_state.history = []
            st.rerun()

        for msg in st.session_state.history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        prompt = st.chat_input("مثال: ليش نزل الراجحي اليوم؟")
        if prompt:
            st.session_state.history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("جاري التحليل..."):
                    try:
                        answer = st.session_state.agent.chat(prompt)
                    except Exception as exc:
                        answer = f"صار خطأ: {exc}"
                st.markdown(answer)
            st.session_state.history.append({"role": "assistant", "content": answer})

st.markdown(
    f'<div class="foot">المصادر: {"، ".join(providers.active_providers())} · '
    f'{td.universe_status()} · الأخبار من بحث الويب · '
    'معلومات فقط، ليست توصية استثمارية.</div>',
    unsafe_allow_html=True,
)
