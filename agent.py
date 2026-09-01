"""
agent.py
========
محرك الوكيل الذكي: يربط Claude بأدوات بيانات السوق السعودي.

الاستخدام كمكتبة:
    from agent import TadawulAgent
    agent = TadawulAgent()
    print(agent.chat("كم سعر أرامكو الحين وكم كان قبل سنة؟"))

الاستخدام كبرنامج طرفية:
    python agent.py
"""

from __future__ import annotations

import json
from datetime import datetime

from anthropic import Anthropic

from config import ANTHROPIC_API_KEY, MAX_TOKENS, MAX_TOOL_ROUNDS, MODEL
from tools import TOOLS, execute_tool

# أداة بحث الويب تُنفَّذ على خوادم Anthropic، ولا نحتاج ننفذها محلياً.
# نستخدمها لجلب أخبار الشركات وإعلانات تداول.
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 5,
}

ALL_TOOLS = TOOLS + [WEB_SEARCH_TOOL]

SYSTEM_PROMPT = """أنت "محلل تداول" — مساعد ذكي متخصص في سوق الأسهم السعودي (تداول).

مهمتك: تجاوب على أسئلة المستخدم عن أسعار الأسهم السعودية وأدائها التاريخي.

قواعد إلزامية:
1. لا تذكر أي سعر أو رقم من ذاكرتك أبداً. كل رقم لازم يجي من الأدوات.
   إذا ما نجحت الأداة، قل ذلك بصراحة ولا تخمّن.
2. إذا ذكر المستخدم اسم شركة ولست متأكداً من رمزها، استخدم search_stock أولاً.
3. لأي سؤال عن السعر الحالي أو المقارنة مع فترات سابقة، استخدم get_stock_snapshot.
4. اذكر دائماً تاريخ آخر إغلاق مع السعر، لأن البيانات ممكن تكون متأخرة عن السوق.
5. اعرض الأرقام بشكل منظم وواضح — استخدم جدول أو نقاط، مع الرمز (+/-) ونسبة التغير.
6. تكلم بالعربي بأسلوب واضح ومباشر. اذكر العملة (ريال).
7. أنت لست مستشاراً مالياً مرخصاً. لا تعطي توصية شراء أو بيع أو أهداف سعرية.
   قدّم البيانات والتحليل الوصفي فقط، ودع القرار للمستخدم. إذا طلب توصية،
   وضّح أنك تقدم معلومات لا نصيحة استثمارية، واعرض عليه العوامل التي يفكر فيها.
8. إذا كان السؤال يخص عدة أسهم، استخدم compare_stocks بدل نداءات متكررة.

═══════════════════════════════════════
منهجية "ليش تحرك السهم؟" — اتبعها بالترتيب
═══════════════════════════════════════
هذا أهم ما تقدمه. لا تختصر أي خطوة:

الخطوة ١ — الأرقام أولاً:
نادِ get_daily_move. لا تبحث في الأخبار قبل ما تعرف حجم الحركة، لأن
حركة 0.4% ما تحتاج تفسيراً أصلاً، وقول "نزل بسبب كذا" عن حركة عادية
تضليل. إذا كان التصنيف "شبه ثابت"، قل ذلك وانتهِ.

الخطوة ٢ — اقرأ السياق قبل ما تفتّش:
- إذا السوق العام متحرك بنفس الاتجاه بقوة → الحركة على الأغلب عامة،
  قل ذلك ولا تفتعل سبباً خاصاً بالشركة.
- إذا حجم التداول غير طبيعي → فيه شيء حصل، ابحث بجدية.
- إذا السهم عكس السوق → غالباً سبب خاص بالشركة.

الخطوة ٣ — ابحث في الويب:
ابحث بالعربي عن أخبار الشركة وإعلاناتها في آخر ثلاثة أيام. جرّب:
"<اسم الشركة> إعلان تداول"، "<اسم الشركة> نتائج"، "<اسم الشركة> خبر اليوم".
ركّز على المصادر الموثوقة: موقع تداول السعودية، أرقام، مباشر، الاقتصادية.
انتبه لهذه المحفزات: النتائج المالية، التوزيعات، تغيّر الإدارة، عقود
جديدة، زيادة رأس المال، تقارير محللين، وأسعار النفط للشركات البتروكيماوية.

الخطوة ٤ — اربط بصدق وصنّف ثقتك:
اذكر في نهاية جوابك درجة الثقة صراحة:
  🟢 مؤكد   — يوجد إعلان رسمي أو خبر مباشر يفسّر الحركة
  🟡 مرجّح  — يوجد خبر ذو صلة لكن الربط غير مؤكد
  🔴 غير معروف — ما لقيت سبباً واضحاً

⚠️ القاعدة الأهم في هذه المنهجية:
إذا ما لقيت سبباً، قل "ما لقيت خبراً يفسّر الحركة" بوضوح.
لا تخترع سرداً مقنعاً من العدم. اختلاق تفسير مقنع لكنه خاطئ أسوأ
بكثير من الاعتراف بعدم المعرفة، لأن القارئ ممكن يبني عليه قراراً.
الأسواق أحياناً تتحرك بلا سبب معلن، وهذه إجابة صحيحة ومقبولة.

تاريخ اليوم: {today}
"""


class TadawulAgent:
    """وكيل محادثة يحتفظ بسياق الجلسة."""

    def __init__(self, api_key: str | None = None, model: str = MODEL):
        key = api_key or ANTHROPIC_API_KEY
        if not key:
            raise RuntimeError(
                "ما فيه مفتاح API. حط ANTHROPIC_API_KEY في ملف .env"
            )
        self.client = Anthropic(api_key=key)
        self.model = model
        self.messages: list[dict] = []
        self.tool_log: list[dict] = []

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self.messages = []
        self.tool_log = []

    # ------------------------------------------------------------------
    def chat(self, user_message: str, verbose: bool = False) -> str:
        """يرسل رسالة المستخدم ويدير حلقة الأدوات حتى يوصل لجواب نهائي."""
        self.messages.append({"role": "user", "content": user_message})
        self.tool_log = []
        system = SYSTEM_PROMPT.format(today=datetime.today().strftime("%Y-%m-%d"))

        for _ in range(MAX_TOOL_ROUNDS):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                tools=ALL_TOOLS,
                messages=self.messages,
            )

            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                return self._extract_text(response.content)

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                if verbose:
                    print(f"  ⚙️  {block.name}({json.dumps(block.input, ensure_ascii=False)})")
                output = execute_tool(block.name, block.input)
                self.tool_log.append({
                    "tool": block.name, "input": block.input, "output": output,
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                })

            self.messages.append({"role": "user", "content": tool_results})

        return "توقفت بعد عدد كبير من محاولات جلب البيانات. جرّب تسأل بشكل أبسط أو حدد سهماً واحداً."

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_text(content) -> str:
        parts = [b.text for b in content if getattr(b, "type", "") == "text"]
        return "\n".join(parts).strip() or "(ما فيه رد نصي)"


# ----------------------------------------------------------------------
def main() -> None:
    print("=" * 60)
    print("  محلل تداول — وكيل الأسهم السعودية")
    print("  اكتب سؤالك، أو 'خروج' للإنهاء، أو 'جديد' لبدء محادثة جديدة.")
    print("=" * 60)

    agent = TadawulAgent()
    while True:
        try:
            user_input = input("\nأنت: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nمع السلامة 👋")
            break

        if not user_input:
            continue
        if user_input in {"خروج", "exit", "quit", "q"}:
            print("مع السلامة 👋")
            break
        if user_input in {"جديد", "new", "reset"}:
            agent.reset()
            print("تم بدء محادثة جديدة.")
            continue

        print("\n🤖 جاري التحليل...")
        try:
            answer = agent.chat(user_input, verbose=True)
        except Exception as exc:  # noqa: BLE001
            print(f"❌ صار خطأ: {exc}")
            continue
        print(f"\nالمحلل: {answer}")


if __name__ == "__main__":
    main()
