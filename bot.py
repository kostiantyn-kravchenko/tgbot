import os
from collections import defaultdict, deque
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
from openai import OpenAI, RateLimitError

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = "Відповідай коротко й по суті."
MAX_TURNS = 10
SUMMARIZE_EVERY = 12

STATE = defaultdict(lambda: {
    "summary": "",
    "turns": deque(maxlen=MAX_TURNS),
    "count": 0,
    "memory_on": True,
})

def user_key(update: Update):
    # Безпечно і для приватів, і для груп
    return (update.effective_chat.id, update.effective_user.id)

def build_messages(key, new_text: str):
    st = STATE[key]
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]

    if st["memory_on"] and st["summary"]:
        msgs.append({"role": "system", "content": f"Пам'ять (summary):\n{st['summary']}"})
    if st["memory_on"]:
        msgs.extend(list(st["turns"]))

    msgs.append({"role": "user", "content": new_text})
    return msgs

def memorize(key, role, content):
    st = STATE[key]
    if not st["memory_on"]:
        return
    st["turns"].append({"role": role, "content": content})
    st["count"] += 1

def should_summarize(key):
    st = STATE[key]
    return st["memory_on"] and st["count"] > 0 and (st["count"] % SUMMARIZE_EVERY == 0)

def summarize(key):
    st = STATE[key]
    prompt = [{"role": "system", "content":
        "Стисни діалог у пам'ять. Тільки факти, цілі, обмеження, важливі рішення. "
        "Не вигадуй. 5-15 булітів українською."
    }]

    if st["summary"]:
        prompt.append({"role": "user", "content": f"Попередній summary:\n{st['summary']}"})

    prompt.append({"role": "user", "content": "Останні репліки:"})
    prompt.extend(list(st["turns"]))

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=prompt,
    )
    st["summary"] = resp.choices[0].message.content.strip()
    st["turns"].clear()

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = user_key(update)
    STATE.pop(key, None)
    await update.message.reply_text("Гаразд. Я очистив твою пам'ять у цьому чаті.")

async def cmd_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = user_key(update)
    st = STATE.get(key)
    if not st or (not st["summary"] and not st["turns"]):
        await update.message.reply_text("Зараз я нічого не пам'ятаю.")
        return

    summary = st["summary"] or "(summary ще порожній)"
    await update.message.reply_text(f"Що я пам'ятаю (summary):\n{summary}")

async def cmd_memory_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = user_key(update)
    STATE[key]["memory_on"] = False
    STATE[key]["turns"].clear()
    await update.message.reply_text("Ок. Пам'ять вимкнена для цього чату.")

async def cmd_memory_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = user_key(update)
    STATE[key]["memory_on"] = True
    await update.message.reply_text("Ок. Пам'ять увімкнена для цього чату.")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = user_key(update)
    text = update.message.text or ""

    try:
        msgs = build_messages(key, text)
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=msgs,
        )
        answer = resp.choices[0].message.content

        memorize(key, "user", text)
        memorize(key, "assistant", answer)

        if should_summarize(key):
            summarize(key)

        await update.message.reply_text(answer)

    except RateLimitError:
        await update.message.reply_text("⚠️ Немає доступної квоти API. Перевір billing/ліміти.")

app = ApplicationBuilder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
app.add_handler(CommandHandler("reset", cmd_reset))
app.add_handler(CommandHandler("forget", cmd_reset))
app.add_handler(CommandHandler("privacy", cmd_privacy))
app.add_handler(CommandHandler("memory_off", cmd_memory_off))
app.add_handler(CommandHandler("memory_on", cmd_memory_on))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
app.run_polling()
