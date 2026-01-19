import os
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from openai import OpenAI


key = os.getenv("OPENAI_API_KEY")

if key:
    print("OPENAI_API_KEY prefix:", key[:6])
else:
    print("OPENAI_API_KEY is NOT set")
    
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "Відповідай коротко і по суті."},
            {"role": "user", "content": update.message.text}
        ]
    )
    await update.message.reply_text(response.choices[0].message.content)

app = ApplicationBuilder() \
    .token(os.getenv("TELEGRAM_BOT_TOKEN")) \
    .build()

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
app.run_polling()