# إضافات Claude Code لهذا المشروع

| الإضافة | ماذا تفعل | ملاحظات |
|---|---|---|
| **claude-code-setup** | تحلّل المشروع وتقترح أتمتة مناسبة (hooks, skills, MCP) | اطلب: "recommend automations for this project" |
| **claude-mem** | ذاكرة دائمة بين الجلسات | وضع محلي، بلا حساب cmem.ai، التليمتري مطفأ. في الجلسات السحابية تُمسح الذاكرة مع كل حاوية جديدة |
| **Agent Reach** | قراءة يوتيوب، Reddit، X، GitHub… | يحتاج سماح الشبكة لتلك المواقع في إعدادات البيئة |
| **Strix** | اختبار اختراق آلي لتطبيقك (لتطبيقاتك فقط) | يحتاج Docker و`STRIX_LLM` + `LLM_API_KEY` |

## التثبيت

```bash
bash .claude/setup-tools.sh
```

السكربت يثبّت الأدوات على مستوى المستخدم (`~/.claude`)، وآمن لإعادة التشغيل.

**في جلسات Claude Code السحابية** كل جلسة تبدأ بحاوية جديدة، فلتبقى الإضافات دائماً:
افتح قائمة البيئة (من شريط عنوان الجلسة) ← **Edit** ← **Setup script** والصق:

```bash
cd /home/user/FAHED && bash .claude/setup-tools.sh || true
```

## تشغيل Strix

```bash
dockerd > /tmp/dockerd.log 2>&1 &         # في الحاوية السحابية
export STRIX_LLM="anthropic/claude-sonnet-5-5"   # أو أي مزوّد مدعوم
export LLM_API_KEY="..."                  # ضعه في متغيرات البيئة، لا في الكود
strix --target ./
```
