"""
app.py
======
واجهة الويب لوكيل الأسهم السعودية.

الصفحات:
    الرئيسية   نبض السوق + قائمة المتابعة + الملخص الصباحي
    السهم      لقطة سعرية + ليش تحرك + مقارنة بتاسي + مصادر الأخبار
    تنبيهات    تنبيهات سعرية
    توزيعات    تقويم التوزيعات
    زكاة       حاسبة زكاة الأسهم
    المحلل     محادثة حرة

التشغيل:  streamlit run app.py
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import alerts as alerts_mod
import announcements
import brief as brief_mod
import dividends as div_mod
import market_pulse as mp
import providers
import storage
import tadawul_data as td
import zakat as zakat_mod
from config import ANTHROPIC_API_KEY, APP_PASSWORD

st.set_page_config(page_title="نبض تداول", page_icon="📊",
                   layout="wide", initial_sidebar_state="collapsed")

# ══════════════════════════ التنسيق ══════════════════════════
st.markdown("""
<style>
  :root {
    --ink:#0E1519; --muted:#5C6B75; --line:#D9E0E5; --surface:#FFF; --bg:#EEF1F3;
    --pine:#0B5C4E; --up:#0E7C5A; --down:#B23A2E; --amber:#8A6A1F;
  }
  html, body, [class*="css"], .stApp {
    direction: rtl; text-align: right;
    font-family: "SF Arabic","Geeza Pro","Tajawal","Segoe UI",system-ui,sans-serif;
  }
  .stApp { background: var(--bg); }
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding-top: 1.5rem; max-width: 900px; }
  h1,h2,h3,p,label,div { text-align: right; }

  .hero .eyebrow { font-size:11px; letter-spacing:.16em; color:var(--pine); font-weight:700; }
  .hero h1 { font-size:26px; font-weight:800; margin:4px 0 2px; letter-spacing:-.4px; }
  .hero .when { font-size:12.5px; color:var(--muted); }

  .card { background:var(--surface); border:1px solid var(--line);
    border-radius:13px; padding:16px 18px; margin-bottom:12px; }
  .card-label { font-size:11px; letter-spacing:.13em; color:var(--muted);
    font-weight:700; margin-bottom:8px; }
  .big { font-size:32px; font-weight:800; letter-spacing:-1px;
    font-variant-numeric:tabular-nums; direction:ltr; display:inline-block; }
  .chg { font-size:15px; font-weight:700; direction:ltr; display:inline-block; margin-right:10px; }
  .asof { font-size:11.5px; color:var(--muted); margin-top:5px; font-variant-numeric:tabular-nums; }

  .srow { display:grid; grid-template-columns:1fr 84px 78px; align-items:center;
    gap:8px; padding:12px 2px; border-bottom:1px solid var(--line); }
  .srow:last-child { border-bottom:none; }
  .srow .nm { font-size:14.5px; font-weight:700; }
  .srow .cd { font-size:11px; color:var(--muted); font-variant-numeric:tabular-nums; }
  .srow .px { font-size:15px; font-weight:700; font-variant-numeric:tabular-nums;
    direction:ltr; text-align:left; }
  .srow .ch { font-size:14px; font-weight:800; font-variant-numeric:tabular-nums;
    direction:ltr; text-align:left; }
  .up{color:var(--up)} .down{color:var(--down)} .flat{color:var(--muted)}

  .flag { display:inline-block; font-size:10.5px; font-weight:700; color:var(--amber);
    background:#FBF6E9; border:1px solid #EADFC0; border-radius:5px;
    padding:1px 6px; margin-right:6px; vertical-align:1px; }
  .attn { background:#FBF6E9; border:1px solid #EADFC0; border-radius:11px;
    padding:13px 15px; margin-bottom:12px; font-size:13.5px; line-height:1.75; color:#6B5316; }
  .attn b { color:var(--ink); }
  .hit { background:#E4F2EC; border:1px solid #BFE0D3; border-radius:11px;
    padding:13px 15px; margin-bottom:12px; font-size:13.5px; line-height:1.75; color:#0A5B44; }
  .empty { color:var(--muted); font-size:13.5px; padding:14px 2px; line-height:1.7; }
  .foot { font-size:11.5px; color:var(--muted); line-height:1.7; padding-top:8px; }
  .stTabs [data-baseweb="tab"] { font-size:14px; font-weight:600; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════ بوابة الدخول ══════════════════════════
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


# ══════════════════════════ أدوات مساعدة ══════════════════════════
def chg_class(pct) -> str:
    if pct is None:
        return "flat"
    return "up" if pct > 0 else ("down" if pct < 0 else "flat")


def chg_text(pct) -> str:
    if pct is None:
        return "—"
    return f"{'+' if pct > 0 else ''}{pct:.2f}%"


def greeting() -> str:
    h = pd.Timestamp.now().hour
    return "صباح الخير" if h < 12 else "مساء الخير"


if "watchlist" not in st.session_state:
    st.session_state.watchlist = storage.get("watchlist") or []


def save_watchlist() -> None:
    storage.put("watchlist", st.session_state.watchlist)


st.markdown(
    f"""<div class="hero">
      <div class="eyebrow">نبض تداول</div>
      <h1>{greeting()}</h1>
      <div class="when">{pd.Timestamp.now().strftime('%Y-%m-%d')} · السوق السعودي</div>
    </div>""",
    unsafe_allow_html=True,
)

tabs = st.tabs(["الرئيسية", "السهم", "تنبيهات", "توزيعات", "زكاة", "المحلل"])

# ══════════════════════════ ١ · الرئيسية ══════════════════════════
with tabs[0]:
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
              <span class="big">{market['النقاط']:,.2f}</span>
              <span class="chg {chg_class(pct)}">{chg_text(pct)}</span>
              <div class="asof">آخر جلسة · {market['تاريخ_الجلسة']}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    # تنبيهات تحققت
    alert_state = alerts_mod.check_alerts()
    hits = alert_state.get("تحققت", [])
    if hits:
        body = "<br>".join(
            f"<b>{h['الاسم']}</b> — الشرط {h['الشرط']} · السعر {h['السعر_الحالي']}"
            for h in hits
        )
        st.markdown(f'<div class="hit">🔔 تنبيهات تحققت:<br>{body}</div>',
                    unsafe_allow_html=True)

    flagged = data.get("تستحق_الانتباه", [])
    if flagged:
        names = "، ".join(f"<b>{r['الاسم']}</b> ({chg_text(r['التغير_%'])})"
                          for r in flagged[:4])
        st.markdown(
            f'<div class="attn">⚡ تستحق الانتباه اليوم: {names}'
            f'<br>افتح تبويب «السهم» لمعرفة السبب.</div>',
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
                f'<div class="srow"><div><div class="nm">{r["الاسم"]}{flag}</div>'
                f'<div class="cd">{r["الرمز"]}</div></div>'
                f'<div class="px">{r["السعر"]:,.2f}</div>'
                f'<div class="ch {chg_class(r["التغير_%"])}">{chg_text(r["التغير_%"])}</div></div>'
            )
        st.markdown(html + "</div>", unsafe_allow_html=True)

    for e in data.get("أخطاء", []):
        st.caption(f"⚠️ {e['المدخل']}: {e['الخطأ']}")

    with st.expander("📋 الملخص الصباحي — نص جاهز للنسخ"):
        if st.button("جهّز الملخص", width="stretch"):
            with st.spinner("جاري التجهيز..."):
                st.code(brief_mod.to_text(brief_mod.build_brief()), language=None)
        st.caption("لاستلامه بالإيميل كل صباح تلقائياً، فعّل GitHub Actions — "
                   "الشرح في ملف README.")

    with st.expander("تعديل قائمة المتابعة"):
        c1, c2 = st.columns([3, 1])
        new_item = c1.text_input("أضف سهماً", placeholder="مثال: معادن أو 1211",
                                 label_visibility="collapsed")
        if c2.button("إضافة", width="stretch") and new_item.strip():
            r = td.resolve_symbol(new_item.strip())
            if not r:
                st.error("ما لقيت هذا السهم.")
            elif r["code"] in st.session_state.watchlist:
                st.info("موجود مسبقاً.")
            else:
                st.session_state.watchlist.append(r["code"])
                save_watchlist()
                st.rerun()

        if st.session_state.watchlist:
            to_remove = st.multiselect(
                "حذف أسهم", options=st.session_state.watchlist,
                format_func=lambda c: f"{td.SYMBOLS.get(c, (c, ''))[0]} ({c})",
            )
            if st.button("احذف المحدد") and to_remove:
                st.session_state.watchlist = [
                    c for c in st.session_state.watchlist if c not in to_remove]
                save_watchlist()
                st.rerun()

    with st.expander("حالة النظام والنسخ الاحتياطي"):
        st.write(f"**قائمة الشركات:** {td.universe_status()}")
        st.write(f"**مزوّدو البيانات:** {'، '.join(providers.active_providers())}")
        st.divider()
        st.caption("بيانات التطبيق تنمسح عند إعادة تشغيله. انسخ هذا الكود "
                   "واحتفظ به، والصقه للاسترجاع.")
        st.code(storage.export_code(), language=None)
        restore = st.text_input("الصق كود النسخة الاحتياطية")
        if st.button("استرجع") and restore.strip():
            ok, msg = storage.import_code(restore)
            (st.success if ok else st.error)(msg)
            if ok:
                st.session_state.watchlist = storage.get("watchlist")
                st.rerun()

# ══════════════════════════ ٢ · السهم ══════════════════════════
with tabs[1]:
    options = st.session_state.watchlist
    c1, c2 = st.columns([2, 2])
    picked = c1.selectbox(
        "من قائمة المتابعة", options=["—"] + options,
        format_func=lambda c: "—" if c == "—" else f"{td.SYMBOLS.get(c, (c, ''))[0]} ({c})",
    )
    typed = c2.text_input("أو اكتب سهماً آخر", placeholder="مثال: 4009 أو معادن")
    target = typed.strip() or (picked if picked != "—" else "")

    if target:
        with st.spinner("جاري جلب البيانات..."):
            snap = td.get_snapshot(target)
            move = mp.get_daily_move(target)

        if "error" in snap:
            st.error(snap["error"])
            for m in td.search_stocks(target):
                st.write(f"• {m['name_ar']} — `{m['code']}`")
        else:
            last = snap["آخر_إغلاق"]
            pct = move.get("نسبة_التغير_%") if "error" not in move else None
            st.markdown(
                f"""<div class="card">
                  <div class="card-label">{snap['الاسم']} · {snap['رقم_الشركة']}</div>
                  <span class="big">{last['السعر']:,.2f}</span>
                  <span class="chg {chg_class(pct)}">{chg_text(pct)}</span>
                  <div class="asof">ريال · آخر إغلاق {last['التاريخ']} · {snap.get('المصدر','')}</div>
                </div>""",
                unsafe_allow_html=True,
            )

            # مؤشرات الحركة
            if "error" not in move:
                m1, m2, m3 = st.columns(3)
                m1.metric("الحجم مقابل معدله",
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

            # جدول الفترات
            labels = {"يوم_سابق": "الجلسة السابقة", "أسبوع": "قبل أسبوع",
                      "شهر": "قبل شهر", "3_أشهر": "قبل 3 أشهر",
                      "6_أشهر": "قبل 6 أشهر", "سنة": "قبل سنة",
                      "بداية_العام": "من بداية العام"}
            table = [{
                "الفترة": lbl, "تاريخ الإغلاق": it["تاريخ_الإغلاق"],
                "السعر وقتها": it["السعر"], "الفرق": it["الفرق"],
                "التغير %": it["نسبة_التغير_%"],
            } for k, lbl in labels.items()
                if (it := snap["المقارنات"].get(k, {})).get("available")]
            st.dataframe(pd.DataFrame(table), width="stretch", hide_index=True)

            # مقارنة بتاسي — الأداء النسبي
            st.markdown("##### الأداء مقابل السوق")
            period = st.radio("المدة", [1, 2, 3], index=0, horizontal=True,
                              format_func=lambda y: f"{y} سنة", key="cmp_years")
            try:
                df = td.get_history(snap["الرمز"], years=max(period, 1))
                tasi = td.get_history(mp.TASI, years=max(period, 1))
                cutoff = df.index[-1] - pd.DateOffset(years=period)
                df, tasi = df.loc[df.index >= cutoff], tasi.loc[tasi.index >= cutoff]

                if not df.empty and not tasi.empty:
                    norm_s = df["Close"] / float(df["Close"].iloc[0]) * 100
                    norm_t = tasi["Close"] / float(tasi["Close"].iloc[0]) * 100
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=norm_s.index, y=norm_s, name=snap["الاسم"],
                                             line=dict(width=2.5, color="#0B5C4E")))
                    fig.add_trace(go.Scatter(x=norm_t.index, y=norm_t, name="تاسي",
                                             line=dict(width=1.8, color="#9AA8B2", dash="dot")))
                    fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10),
                                      yaxis_title="مُعادل 100 عند البداية",
                                      hovermode="x unified", plot_bgcolor="white",
                                      paper_bgcolor="white",
                                      legend=dict(orientation="h", y=1.12))
                    st.plotly_chart(fig, width="stretch")

                    diff = float(norm_s.iloc[-1]) - float(norm_t.iloc[-1])
                    verdict = "أفضل من السوق" if diff > 0 else "أضعف من السوق"
                    st.caption(f"خلال {period} سنة: السهم {verdict} بفارق "
                               f"{abs(diff):.1f} نقطة مئوية.")
            except Exception as exc:  # noqa: BLE001
                st.warning(f"تعذّر رسم المقارنة: {exc}")

            # مصادر الأخبار
            links = announcements.news_links(target)
            if "error" not in links:
                st.markdown("##### مصادر الأخبار والإعلانات")
                for item in links["الروابط"]:
                    st.markdown(f"- [{item['المصدر']}]({item['الرابط']}) — {item['الوصف']}")
                st.caption(links["ملاحظة"])

            # البحث الذكي عن السبب
            st.divider()
            if not ANTHROPIC_API_KEY:
                st.info("لتلخيص السبب آلياً، أضف ANTHROPIC_API_KEY في Secrets. "
                        "بدونه استخدم روابط المصادر أعلاه.")
            elif st.button("🔍 ابحث عن السبب", type="primary", width="stretch"):
                if "agent" not in st.session_state:
                    from agent import TadawulAgent
                    st.session_state.agent = TadawulAgent()
                    st.session_state.history = []
                with st.spinner("جاري البحث في الأخبار وإعلانات تداول..."):
                    try:
                        answer = st.session_state.agent.chat(
                            f"ليش تحرك سهم {snap['الاسم']} ({snap['رقم_الشركة']})؟ "
                            f"اتبع منهجية 'ليش تحرك السهم' كاملة."
                        )
                    except Exception as exc:  # noqa: BLE001
                        answer = f"صار خطأ: {exc}"
                st.markdown(answer)

# ══════════════════════════ ٣ · تنبيهات ══════════════════════════
with tabs[2]:
    st.markdown("نبّهني لو وصل سهم سعراً معيناً.")
    st.caption("⚠️ الفحص يتم عند فتح التطبيق أو مع الملخص الصباحي — "
               "ليس تنبيهاً لحظياً.")

    c1, c2, c3 = st.columns([2, 1, 1])
    a_sym = c1.text_input("السهم", placeholder="4009 أو السعودي الألماني")
    a_op = c2.selectbox("الشرط", ["فوق", "تحت"])
    a_price = c3.number_input("السعر", min_value=0.0, step=0.5, format="%.2f")
    a_note = st.text_input("ملاحظة (اختياري)", placeholder="مثال: نقطة الدخول")

    if st.button("أضف التنبيه", type="primary") and a_sym.strip() and a_price > 0:
        res = alerts_mod.add_alert(a_sym.strip(), a_op, a_price, a_note)
        if "error" in res:
            st.error(res["error"])
        else:
            st.success("أُضيف التنبيه.")
            st.rerun()

    st.divider()
    state = alerts_mod.check_alerts()
    if state["عدد_التنبيهات"] == 0:
        st.markdown('<div class="empty">ما فيه تنبيهات بعد.</div>',
                    unsafe_allow_html=True)
    else:
        if state["تحققت"]:
            st.markdown("##### 🔔 تحققت")
            st.dataframe(pd.DataFrame(state["تحققت"]).drop(columns=["المفتاح"]),
                         width="stretch", hide_index=True)
        if state["لم_تتحقق"]:
            st.markdown("##### ⏳ بالانتظار")
            st.dataframe(pd.DataFrame(state["لم_تتحقق"]).drop(columns=["المفتاح"]),
                         width="stretch", hide_index=True)

        saved = storage.get("alerts") or []
        idx = st.selectbox(
            "حذف تنبيه", options=list(range(len(saved))),
            format_func=lambda i: f"{saved[i]['name']} — {saved[i]['op']} {saved[i]['price']}",
        )
        if st.button("احذف") and saved:
            alerts_mod.remove_alert(idx)
            st.rerun()

# ══════════════════════════ ٤ · توزيعات ══════════════════════════
with tabs[3]:
    st.markdown("تقويم التوزيعات النقدية لأسهم قائمة متابعتك.")
    if st.button("حدّث التقويم", type="primary"):
        st.session_state.pop("div_cache", None)

    if "div_cache" not in st.session_state:
        with st.spinner("جاري جلب سجل التوزيعات..."):
            st.session_state.div_cache = div_mod.get_calendar(st.session_state.watchlist)
    cal = st.session_state.div_cache

    soon = cal.get("قريباً_خلال_45_يوم", [])
    if soon:
        body = "<br>".join(
            f"<b>{r['الاسم']}</b> — بعد {r['أيام_متبقية']} يوم · "
            f"عائد {r.get('عائد_التوزيعات_%')}%" for r in soon
        )
        st.markdown(f'<div class="attn">💰 توزيعات متوقعة قريباً:<br>{body}</div>',
                    unsafe_allow_html=True)

    rows = cal.get("التقويم", [])
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.markdown('<div class="empty">ما فيه بيانات توزيعات لأسهم قائمتك.</div>',
                    unsafe_allow_html=True)

    if cal.get("غير_موزعة"):
        with st.expander("أسهم بلا توزيعات"):
            for s in cal["غير_موزعة"]:
                st.write(f"• {s['المدخل']} — {s['السبب']}")

    st.warning(cal.get("⚠️", ""))

    with st.expander("تفاصيل سهم معيّن"):
        d_sym = st.text_input("السهم", placeholder="2222", key="div_sym")
        if d_sym.strip():
            info = div_mod.get_dividends(d_sym.strip())
            if "error" in info:
                st.error(info["error"])
            elif not info.get("يوزع_أرباحاً"):
                st.info(info.get("ملاحظة"))
            else:
                k1, k2, k3 = st.columns(3)
                k1.metric("عائد التوزيعات", f"{info.get('عائد_التوزيعات_%') or '—'}%")
                k2.metric("توزيعات 12 شهر", f"{info.get('توزيعات_آخر_12_شهر')} ر.س")
                k3.metric("عدد التوزيعات", info.get("عدد_التوزيعات_آخر_12_شهر"))
                if info.get("السجل"):
                    st.dataframe(pd.DataFrame(info["السجل"]),
                                 width="stretch", hide_index=True)
                est = info.get("التوزيع_القادم_تقديري")
                if est:
                    st.caption(f"النمط: {est['النمط_المتوقع']} · "
                               f"الموعد التقديري: {est['تاريخ_تقديري']} — {est['⚠️']}")

# ══════════════════════════ ٥ · زكاة ══════════════════════════
with tabs[4]:
    st.markdown("### حاسبة زكاة الأسهم")
    st.warning("أداة حسابية تقديرية، وليست فتوى. المسألة فيها اجتهادات فقهية "
               "متعددة — راجع جهة شرعية معتبرة قبل الإخراج.")

    intent = st.radio(
        "نية التملك", ["متاجرة", "استثمار"], horizontal=True,
        help="متاجرة = بيع وشراء قصير المدى · استثمار = اقتناء طويل للعائد",
    )
    if intent == "متاجرة":
        st.caption("تُزكّى القيمة السوقية كاملة، لأن السهم في حكم عروض التجارة.")
        ratio = None
    else:
        st.caption("تُزكّى الموجودات الزكوية في الشركة لا كامل قيمة السهم. "
                   "النسبة تختلف لكل شركة وتُستخرج من قوائمها المالية.")
        ratio = st.slider("نسبة الموجودات الزكوية التقديرية %", 5, 100, 30) / 100

    c1, c2 = st.columns(2)
    year_type = c1.radio("نوع السنة", ["هجري", "ميلادي"], horizontal=True,
                         help="هجري 2.5% · ميلادي 2.577%")
    gold = c2.number_input("سعر جرام الذهب عيار 24 (ريال)", min_value=0.0,
                           step=10.0, help="لحساب النصاب — اتركه صفراً لتخطيه")

    st.markdown("##### محفظتك")
    holdings = storage.get("holdings") or []
    edited = st.data_editor(
        pd.DataFrame(holdings if holdings else [{"code": "", "shares": 0}]),
        num_rows="dynamic", width="stretch",
        column_config={
            "code": st.column_config.TextColumn("رقم السهم", help="مثال: 2222"),
            "shares": st.column_config.NumberColumn("عدد الأسهم", min_value=0),
        },
    )

    cc1, cc2 = st.columns(2)
    if cc1.button("احسب الزكاة", type="primary", width="stretch"):
        records = [r for r in edited.to_dict("records")
                   if str(r.get("code", "")).strip() and float(r.get("shares") or 0) > 0]
        if not records:
            st.error("أدخل سهماً واحداً على الأقل.")
        else:
            storage.put("holdings", records)
            with st.spinner("جاري جلب الأسعار..."):
                result = zakat_mod.calculate(records, intent, year_type,
                                             gold or None, ratio)
            if "error" in result:
                st.error(result["error"])
            else:
                st.dataframe(pd.DataFrame(result["الأسهم"]),
                             width="stretch", hide_index=True)
                z1, z2, z3 = st.columns(3)
                z1.metric("القيمة السوقية", f"{result['إجمالي_القيمة_السوقية']:,.2f}")
                z2.metric("الوعاء الزكوي", f"{result['الوعاء_الزكوي']:,.2f}")
                z3.metric("الزكاة المستحقة", f"{result['الزكاة_المستحقة']:,.2f} ر.س")
                st.info(result["أساس_الحساب"])
                nisab = result["النصاب"]
                if nisab.get("قيمة_النصاب"):
                    verdict = "بلغت النصاب" if nisab["المحفظة_تبلغ_النصاب"] else "لم تبلغ النصاب"
                    st.write(f"**النصاب:** {nisab['قيمة_النصاب']:,.2f} ر.س — محفظتك {verdict}.")
                st.caption(result["ملاحظة_الحول"])
                st.warning(result["⚠️_تنبيه"])
                for e in result.get("أخطاء", []):
                    st.caption(f"⚠️ {e['الرمز']}: {e['الخطأ']}")

    if cc2.button("امسح المحفظة", width="stretch"):
        storage.put("holdings", [])
        st.rerun()

# ══════════════════════════ ٦ · المحلل ══════════════════════════
with tabs[5]:
    if not ANTHROPIC_API_KEY:
        st.warning("أضف ANTHROPIC_API_KEY في Secrets لتفعيل المحادثة.")
        st.caption("بدونه: الأسعار والتوزيعات والزكاة والتنبيهات كلها تشتغل عادي.")
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
                    except Exception as exc:  # noqa: BLE001
                        answer = f"صار خطأ: {exc}"
                st.markdown(answer)
            st.session_state.history.append({"role": "assistant", "content": answer})

st.markdown(
    f'<div class="foot">المصادر: {"، ".join(providers.active_providers())} · '
    f'{td.universe_status()} · الأسعار قد تتأخر عن السوق · '
    'معلومات فقط، ليست توصية استثمارية.</div>',
    unsafe_allow_html=True,
)
