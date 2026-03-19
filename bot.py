import os
from collections import defaultdict, deque
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
from openai import OpenAI, RateLimitError

# init_db()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")

SYSTEM_PROMPT = "Ти аналітик військової обстановки. Аналізуєш телеграм-дописи про події на фронті та формулюєш стислий аналітичний висновок. Використовуй тільки інформацію з наданого тексту, не вигадуй і не додавай нічого від себе, ігноруй емоції, оцінки, припущення та пропаганду, якщо інформації недостатньо — прямо вкажи це. Обовʼязково визначай і зазначай у висновку джерело інформації: українські або російські тг-канали. Замінюй усі форми слова противник на ворог з урахуванням відмінків і ЗСУ на СОУ. Формат відповіді: короткий аналітичний висновок 2–4 речення, тільки суть і значення події, без деталей, списків, цитування чи пояснень, текст має звучати природно як написаний людиною. Перевести на українську та стисло подати з позиції сторони України. Якщо в тексті є підрозділи, включати в готову відповідь."

HELP_TEXT = (
    "Доступні команди:\n\n"
    "/start — почати роботу\n"
    "\nПросто напиши питання текстом 👇"
)

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, user_id = user_key(update)
    k = (chat_id, user_id)

    await update.message.reply_text("Ок. Я очистив твою памʼять у цьому чаті.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

def user_key(update: Update):
    return (update.effective_chat.id, update.effective_user.id)

def build_messages(new_text: str):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
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
        model=OPENAI_MODEL,
        messages=prompt,
    )
    st["summary"] = resp.choices[0].message.content.strip()
    st["count"] = 0
    st["turns"].clear()

async def cmd_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, user_id = user_key(update)
    k = (chat_id, user_id)

    db_state = load_state(chat_id, user_id)
    STATE[k]["summary"] = db_state["summary"]
    STATE[k]["memory_on"] = db_state["memory_on"]

    summary = STATE[k]["summary"].strip()
    if not summary:
        await update.message.reply_text("Зараз я нічого не пам'ятаю (summary порожній).")
        return

    await update.message.reply_text(f"Що я пам'ятаю (summary):\n{summary}")

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Я чат-бот.\n\n" + HELP_TEXT
    )

async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Поточна модель: {OPENAI_MODEL}"
    )


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    text = message.text or message.caption or ""

    # Якщо є медіа, але тексту немає
    has_media = bool(message.photo or message.video or message.document)

    if not text:
        if has_media:
            await message.reply_text(
                "⚠️ У цьому forward-повідомленні немає тексту або підпису. "
                "Я поки що не вмію аналізувати сам вміст скріншотів і відео."
            )
        else:
            await message.reply_text("⚠️ Немає тексту для аналізу.")
        return

    try:
        msgs = build_messages(text)
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=msgs,
        )
        answer = resp.choices[0].message.content or "Модель повернула порожню відповідь."

        if len(answer) > 4000:
            for i in range(0, len(answer), 4000):
                await message.reply_text(answer[i:i+4000])
        else:
            await message.reply_text(answer)

    except RateLimitError:
        await message.reply_text("⚠️ Немає доступної квоти API. Перевір billing/ліміти.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        await message.reply_text(f"Сталася помилка: {type(e).__name__}")

app = ApplicationBuilder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle))
app.add_handler(CommandHandler("help", help_cmd))
app.add_handler(CommandHandler("start", start_cmd))
app.add_handler(CommandHandler("model", cmd_model))

app.run_polling()
