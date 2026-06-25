import os
import traceback
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

CHAT_PROMPT = """Ты — финансовый ИИ-ассистент приложения "Мой бюджет".
Помогаешь пользователям с личными финансами: советы по накоплению,
планированию бюджета, инвестициям, управлению долгами.
Отвечай кратко, по делу, на русском языке.
Используй цифры и конкретные советы. Будь дружелюбным."""

ADVICE_PROMPT = """Ты — персональный финансовый ИИ-аналитик.
Тебе дают реальную статистику пользователя: доходы, расходы по категориям,
цели накопления и долги. Проанализируй данные и дай конкретные персональные советы.
Отвечай на русском, кратко и по делу. Указывай на проблемы и давай практические
рекомендации с цифрами. Будь дружелюбным и поддерживающим, но честным."""


async def send_message(chat_id: int, text: str):
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": text
        })
        print("TELEGRAM SEND:", r.status_code, r.text[:300], flush=True)


async def ask_claude(user_message: str, system_prompt: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": [
                    {"role": "user", "content": user_message}
                ]
            }
        )
        print("CLAUDE STATUS:", response.status_code, flush=True)
        data = response.json()
        if "content" not in data:
            print("CLAUDE ERROR RESPONSE:", data, flush=True)
            raise Exception("No content in response: " + str(data))
        return data["content"][0]["text"]


@app.post("/webhook")
async def webhook(request: Request):
    body = await request.json()
    message = body.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    print("INCOMING:", chat_id, repr(text), flush=True)

    if not chat_id or not text:
        return {"ok": True}

    if text == "/start":
        welcome = (
            "Привет! Я финансовый ИИ-ассистент.\n\n"
            "Помогу тебе с:\n"
            "- Планированием бюджета\n"
            "- Советами по накоплению\n"
            "- Вопросами по инвестициям\n"
            "- Управлением долгами\n\n"
            "Просто напиши свой вопрос!"
        )
        await send_message(chat_id, welcome)
        return {"ok": True}

    async with httpx.AsyncClient() as client:
        await client.post(f"{TELEGRAM_API}/sendChatAction", json={
            "chat_id": chat_id,
            "action": "typing"
        })

    try:
        reply = await ask_claude(text, CHAT_PROMPT)
        await send_message(chat_id, reply)
    except Exception as e:
        print("ERROR IN WEBHOOK:", str(e), flush=True)
        traceback.print_exc()
        await send_message(chat_id, "Ошибка: " + str(e)[:200])

    return {"ok": True}


class AdviceRequest(BaseModel):
    stats: str
    question: str = ""


@app.post("/advice")
async def advice(req: AdviceRequest):
    user_message = "Вот моя финансовая статистика:\n" + req.stats
    if req.question:
        user_message += "\n\nМой вопрос: " + req.question
    else:
        user_message += "\n\nДай мне персональные советы по улучшению финансов."

    try:
        reply = await ask_claude(user_message, ADVICE_PROMPT)
        return {"ok": True, "advice": reply}
    except Exception as e:
        print("ERROR IN ADVICE:", str(e), flush=True)
        traceback.print_exc()
        return {"ok": False, "advice": "Ошибка: " + str(e)[:200]}


@app.get("/")
async def root():
    return {"status": "Bot is running!"}


@app.get("/debug")
async def debug():
    t = TELEGRAM_TOKEN or ""
    # Безопасно показываем только структуру токена
    masked = (t[:8] + "..." + t[-4:]) if len(t) > 12 else "TOO SHORT OR EMPTY"
    has_space = (t != t.strip()) or (" " in t)
    return {
        "token_length": len(t),
        "token_preview": masked,
        "has_space_or_whitespace": has_space,
        "anthropic_key_set": bool(ANTHROPIC_API_KEY),
        "anthropic_key_length": len(ANTHROPIC_API_KEY or "")
    }
