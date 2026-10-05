"""Все инлайн-меню бота и безопасное редактирование сообщений."""
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

users_menu_limit = 40


def button(label: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=label, callback_data=callback_data)


async def safe_edit(message: Message, text: str, keyboard: InlineKeyboardMarkup | None = None) -> None:
    if message is None:
        return
    try:
        await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        pass


def main_menu(is_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [button("💰 Курсы", "menu:rates"), button("💬 Чат", "menu:chat")],
        [button("👤 Мой ID", "menu:id")],
    ]
    if is_admin:
        rows.append([button("👑 Админ-панель", "menu:admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[button("◀️ В меню", "nav:main")]])


def back_to_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[button("◀️ Назад", "menu:admin")]])


def rates_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[button("🔄 Обновить", "menu:rates")], [button("◀️ В меню", "nav:main")]]
    )


def users_menu(pairs: list) -> InlineKeyboardMarkup:
    rows = [[button(label, f"chat:open:{chat_id}")] for label, chat_id in pairs[:users_menu_limit]]
    rows.append([button("◀️ В меню", "nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def chat_menu(target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [button("✉️ Написать", f"chat:write:{target_id}")],
            [button("◀️ К списку", "menu:chat")],
        ]
    )


def reply_keyboard(sender_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[button("↩️ Ответить", f"chat:reply:{sender_id}")]])


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [button("🖥 Сервер (/utcp)", "adm:utcp")],
            [button("👮 Админы", "adm:list"), button("➕ Добавить", "adm:add")],
            [button("🤖 ИИ", "adm:ai")],
            [button("♻️ Перевыпустить /addoneadm", "adm:rearm")],
            [button("◀️ В меню", "nav:main")],
        ]
    )


def ai_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [button("🔑 API-ключ", "ai:set:key"), button("🧠 Модель", "ai:set:model")],
            [button("🌐 Base URL", "ai:set:url"), button("📜 Промт", "ai:set:prompt")],
            [button("💬 Управлять сервером", "ai:chat")],
            [button("◀️ Назад", "menu:admin")],
        ]
    )


def ai_session_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [button("🆕 Новая задача", "ai:fresh")],
            [button("◀️ В меню ИИ", "adm:ai")],
        ]
    )


def admins_menu(ids: list) -> InlineKeyboardMarkup:
    rows = [[button(f"🗑 {admin_id}", f"adm:del:{admin_id}")] for admin_id in ids]
    rows.append([button("◀️ Назад", "menu:admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
