"""tg-bot-friend: курсы BTC/LTC/USDT, чат между пользователями и админ-панель с /utcp.

Зависимости: pip install aiogram
Запуск: BOT_TOKEN=токен_бота ADMIN_ID=твой_telegram_id python main.py
ADMIN_ID необязателен: админка выдаётся только через одноразовую /addoneadm.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

import admin
import chat
import config
import keyboards
import rates
import storage

fallback = Router(name="fallback")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

dp = Dispatcher()
dp.include_routers(admin.router, chat.router, fallback)


@dp.message(CommandStart())
async def start(message: Message) -> None:
    user = message.from_user
    storage.register_user(user.id, user.username or "", user.full_name)
    chat.leave(user.id)
    admin.drop_pending(user.id)
    await message.answer(
        "👋 Привет! Это tg-bot-friend — курсы крипты, чат между пользователями и серверное хозяйство.\n\nВыбери раздел:",
        reply_markup=keyboards.main_menu(storage.is_admin(user.id)),
    )


@dp.callback_query(F.data == "menu:rates")
async def show_rates(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    await callback.answer("Смотрю курсы...")
    try:
        prices = await rates.fetch_prices()
    except Exception:
        await keyboards.safe_edit(callback.message, "⚠️ Не получил курсы, попробуй ещё раз.", keyboards.rates_menu())
        return
    await keyboards.safe_edit(callback.message, rates.format_prices(prices), keyboards.rates_menu())


@dp.callback_query(F.data == "menu:chat")
async def show_users(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    await callback.answer()
    pairs = [(storage.row_label(row), row[0]) for row in storage.all_users() if row[0] != callback.from_user.id]
    if not pairs:
        await keyboards.safe_edit(
            callback.message,
            "Пока некому писать — позови друзей: пусть напишут боту /start.",
            keyboards.back_to_main(),
        )
        return
    await keyboards.safe_edit(callback.message, "💬 Выбери собеседника:", keyboards.users_menu(pairs))


@dp.callback_query(F.data == "menu:id")
async def show_id(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    await callback.answer()
    await keyboards.safe_edit(
        callback.message,
        f"👤 Твой ID: {callback.from_user.id}\n\nПередай его владельцу — он добавит тебя в админы через панель.",
        keyboards.back_to_main(),
    )


@dp.callback_query(F.data == "nav:main")
async def back_to_main(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    await callback.answer()
    await keyboards.safe_edit(
        callback.message,
        "Главное меню:",
        keyboards.main_menu(storage.is_admin(callback.from_user.id)),
    )


@fallback.message(F.text)
async def dispatch_text(message: Message, bot: Bot) -> None:
    if await admin.handle_input(message):
        return
    if chat.is_busy(message.from_user.id):
        if message.text == "/stop":
            chat.leave(message.from_user.id)
            await message.answer(
                "✅ Чат закрыт.",
                reply_markup=keyboards.main_menu(storage.is_admin(message.from_user.id)),
            )
            return
        await chat.relay(bot, message)
        return
    await message.answer("🤔 Не понял сообщение. Открой меню: /start", reply_markup=keyboards.back_to_main())


async def main() -> None:
    if not config.bot_token:
        raise SystemExit("Задай переменную окружения BOT_TOKEN")
    bot = Bot(token=config.bot_token)
    storage.bootstrap_owner(config.owner_id)
    me = await bot.get_me()
    logging.info("бот запущен: @%s", me.username)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
