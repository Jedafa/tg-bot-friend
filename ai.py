"""ИИ-агент управления сервером: настройки шифруются, команды выполняются и показываются в чате.

Цикл как у шелл-агентов: ИИ отвечает либо RUN: <команда> (показываем, выполняем,
возвращаем вывод), либо DONE: <итог>. Рабочая папка — data-каталог, окружение
описывается в системном промте. Только для админов.
"""
import asyncio
import logging
import os
import platform

import aiohttp
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

import chat
import friend
import keyboards
import storage

log = logging.getLogger(__name__)
router = Router(name="ai")
active_users: set = set()
awaiting_setting: dict = {}
setting_fields = {"key": "api_key", "model": "model", "url": "url", "prompt": "prompt"}
setting_titles = {
    "key": "API-ключ одним сообщением",
    "model": "модель одним сообщением (например, gpt-4o-mini)",
    "url": "Base URL одним сообщением (например, https://api.openai.com/v1)",
    "prompt": "дополнительный промт одним сообщением (что угодно, многострочно)",
}
max_steps = 10
shell_timeout = 60
default_base_url = "https://api.openai.com/v1"


def is_active(user_id: int) -> bool:
    return user_id in active_users


def leave(user_id: int) -> None:
    active_users.discard(user_id)
    awaiting_setting.pop(user_id, None)


def guard(callback: CallbackQuery) -> bool:
    return storage.is_admin(callback.from_user.id)


def ai_status() -> str:
    values = storage.ai_settings()
    key = values["api_key"]
    masked = f"{key[:6]}…{key[-4:]}" if len(key) > 12 else ("задан" if key else "не задан")
    prompt_state = "свой" if values["prompt"] else "по умолчанию"
    return (
        "🤖 ИИ-управление сервером\n\n"
        f"Модель: {values['model'] or 'не задана'}\n"
        f"Base URL: {values['url'] or default_base_url}\n"
        f"API-ключ: {masked}\n"
        f"Промт: {prompt_state}\n\n"
        "ИИ исполняет shell-команды на машине бота: рабочая папка — data-каталог, "
        "каждая команда показывается в чате перед запуском."
    )


def build_system_prompt() -> str:
    values = storage.ai_settings()
    bot_dir = os.path.dirname(os.path.abspath(__file__))
    parts = [
        "Ты — ИИ-администратор сервера, встроенный в Telegram-бота tg-bot-friend. Ты управляешь машиной, где запущен бот.",
        f"Окружение: {platform.system()} {platform.release()} ({platform.machine()}).",
        f"Рабочая папка: {storage.data_dir} — она перезаписываемая и переживает перезапуски.",
        f"Папка бота: {bot_dir}.",
        "Прав root нет, корень файловой системы может быть только для чтения (изолированный контейнер хостинга) — системные команды вроде apt не сработают, опирайся на рабочую папку и питон.",
        "",
        "Формат ответа строго один из двух вариантов:",
        "RUN: <одна bash-команда> — выполнить команду; перед этой строкой можно написать краткое пояснение обычным текстом;",
        "DONE: <итоговый ответ пользователю> — задача решена или данных достаточно.",
        "Правила: одна команда за ответ; результат проверяй сам по выводу; при ошибке меняй подход, а не повторяй; не задавай вопросов пользователю, если ответ добывается командой.",
    ]
    if values["prompt"]:
        parts += ["", "Дополнительные инструкции владельца:", values["prompt"]]
    return "\n".join(parts)


def parse_reply(reply: str) -> tuple:
    commentary_lines = []
    for line in reply.splitlines():
        stripped = line.strip()
        if stripped.startswith("RUN:"):
            return "\n".join(commentary_lines).strip(), "RUN", stripped[4:].strip()
        if stripped.startswith("DONE:"):
            return "\n".join(commentary_lines).strip(), "DONE", reply.split("DONE:", 1)[1].strip()
        commentary_lines.append(line)
    return reply.strip(), "", ""


async def chat_completion(base_url: str, api_key: str, model: str, messages: list) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {"model": model, "messages": messages, "temperature": 0.2}
    headers = {"Authorization": f"Bearer {api_key}", "User-Agent": "tg-bot-friend"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=120)) as response:
            if response.status != 200:
                detail = (await response.text())[:300]
                raise RuntimeError(f"API вернул {response.status}: {detail}")
            data = await response.json()
    return (data["choices"][0]["message"]["content"] or "").strip()


async def run_agent(bot, chat_id: int, task: str) -> None:
    values = storage.ai_settings()
    if not values["api_key"] or not values["model"]:
        await bot.send_message(chat_id, "Сначала настрой ИИ: 🔑 API-ключ и 🧠 Модель в панели.")
        return
    base_url = values["url"] or default_base_url
    messages = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": task},
    ]
    log.info("ИИ-агент стартовал для %s: %s", chat_id, task[:100])
    for step in range(max_steps):
        try:
            reply = await chat_completion(base_url, values["api_key"], values["model"], messages)
        except Exception as error:
            log.warning("ИИ недоступен: %s", error)
            await bot.send_message(chat_id, f"⚠️ ИИ недоступен: {error}")
            return
        commentary, action, payload = parse_reply(reply)
        if commentary:
            await bot.send_message(chat_id, commentary[:4000])
        if action == "DONE":
            await bot.send_message(chat_id, "✅ " + (payload or "Готово.")[:4000])
            return
        if action != "RUN":
            await bot.send_message(chat_id, "🤔 Ответ не по формату:\n" + reply[:3500])
            return
        await bot.send_message(chat_id, f"⚙️ Шаг {step + 1}, выполняю:\n{payload}")
        ok, output = await asyncio.to_thread(friend.run_shell, payload, shell_timeout)
        log.info("ИИ-команда (%s): %s -> %s", chat_id, payload[:80], "ok" if ok else "fail")
        tail = output[-3500:] if len(output) > 3500 else output
        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user", "content": f"Код выхода: {0 if ok else 1}\nВывод:\n{tail or '(пусто)'}"})
    await bot.send_message(chat_id, f"⛔️ Остановился после {max_steps} команд. Пиши продолжение, если надо.")


@router.callback_query(F.data == "adm:ai")
async def open_ai_menu(callback: CallbackQuery) -> None:
    if not guard(callback):
        await callback.answer("🔒 Только для админов", show_alert=True)
        return
    await callback.answer()
    await keyboards.safe_edit(callback.message, ai_status(), keyboards.ai_menu())


@router.callback_query(F.data.startswith("ai:set:"))
async def ask_setting(callback: CallbackQuery) -> None:
    if not guard(callback):
        await callback.answer("🔒 Только для админов", show_alert=True)
        return
    field = callback.data.split(":")[2]
    if field not in setting_fields:
        await callback.answer("Неизвестная настройка")
        return
    awaiting_setting[callback.from_user.id] = field
    await callback.answer()
    await callback.message.answer(f"Пришли {setting_titles[field]}.\n/start — отмена.")


@router.callback_query(F.data == "ai:chat")
async def start_ai_chat(callback: CallbackQuery) -> None:
    if not guard(callback):
        await callback.answer("🔒 Только для админов", show_alert=True)
        return
    chat.leave(callback.from_user.id)
    active_users.add(callback.from_user.id)
    await callback.answer("Режим ИИ включён")
    await callback.message.answer(
        "💬 Режим ИИ включён. Пиши задачу — покажу команды и выполню их.\n/stop — выйти из режима."
    )


async def handle_input(message: Message, bot) -> bool:
    user_id = message.from_user.id
    if user_id in awaiting_setting:
        field = awaiting_setting.pop(user_id)
        value = message.text.strip()
        if field == "url" and not value.startswith(("http://", "https://")):
            awaiting_setting[user_id] = field
            await message.answer("URL должен начинаться с http:// или https://. Пришли ещё раз.")
            return True
        storage.set_ai_setting(setting_fields[field], value)
        log.info("настройка ИИ %s обновлена админом %s", field, user_id)
        await message.answer("✅ Сохранено (в зашифрованном виде).", reply_markup=keyboards.ai_menu())
        return True
    if user_id in active_users:
        if message.text == "/stop":
            leave(user_id)
            await message.answer("🤖 Режим ИИ выключен.", reply_markup=keyboards.main_menu(storage.is_admin(user_id)))
            return True
        await run_agent(bot, user_id, message.text)
        return True
    return False
