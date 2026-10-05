"""Чат между пользователями: выбор собеседника, доставка сообщений и ответы."""
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message

import keyboards
import storage

router = Router(name="chat")
active_chats: dict = {}


def is_busy(user_id: int) -> bool:
    return user_id in active_chats


def leave(user_id: int) -> None:
    active_chats.pop(user_id, None)


@router.callback_query(F.data.startswith("chat:open:"))
async def open_chat(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    target_id = int(callback.data.rsplit(":", 1)[1])
    if target_id == callback.from_user.id:
        await callback.answer("Это ты 🙂")
        return
    await callback.answer()
    await keyboards.safe_edit(callback.message, f"💬 Собеседник: {storage.user_label(target_id)}", keyboards.chat_menu(target_id))


@router.callback_query(F.data.startswith("chat:write:"))
async def write_message(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    target_id = int(callback.data.rsplit(":", 1)[1])
    active_chats[callback.from_user.id] = target_id
    await callback.answer("Режим чата включён")
    await keyboards.safe_edit(
        callback.message,
        f"✍️ Пиши сообщение — доставлю {storage.user_label(target_id)}.\n/stop — выйти из чата.",
    )


@router.callback_query(F.data.startswith("chat:reply:"))
async def reply_message(callback: CallbackQuery) -> None:
    sender_id = int(callback.data.rsplit(":", 1)[1])
    active_chats[callback.from_user.id] = sender_id
    await callback.answer("Режим чата включён")
    await callback.message.answer(
        f"↩️ Пиши ответ — доставлю {storage.user_label(sender_id)}.\n/stop — выйти из чата."
    )


@router.callback_query(F.data == "chat:close")
async def close_chat(callback: CallbackQuery) -> None:
    leave(callback.from_user.id)
    await callback.answer("Чат закрыт")
    await keyboards.safe_edit(
        callback.message,
        "Чат закрыт.",
        keyboards.main_menu(storage.is_admin(callback.from_user.id)),
    )


async def relay(bot: Bot, message: Message) -> None:
    sender = message.from_user
    label = f"@{sender.username}" if sender.username else sender.full_name
    try:
        await bot.send_message(
            active_chats[sender.id],
            f"✉️ Сообщение от {label} (ID {sender.id}):\n\n{message.text}",
            reply_markup=keyboards.reply_keyboard(sender.id),
        )
    except TelegramAPIError:
        await message.answer("⚠️ Не доставил: собеседник мог заблокировать бота или ещё не писал ему /start.")
