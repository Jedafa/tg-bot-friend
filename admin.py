"""Админ-панель: сервер (/utcp) и управление админами с шифрованным хранением ID."""
import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import friend
import keyboards
import storage

log = logging.getLogger(__name__)
router = Router(name="admin")
awaiting_admin_id: set = set()


def drop_pending(user_id: int) -> None:
    awaiting_admin_id.discard(user_id)


def panel_text() -> str:
    available = storage.one_time_admin_state()[0]
    status = "доступна" if available else "уже использована"
    return f"👑 Админ-панель\n\nАдминов в боте: {len(storage.admin_ids())}\n🎫 Разовая /addoneadm: {status}"


def guard(callback: CallbackQuery) -> bool:
    return storage.is_admin(callback.from_user.id)


async def send_server_report(message: Message) -> None:
    placeholder = await message.answer("⏳ Собираю статистику сервера...")
    report = "🖥 Статистика недоступна, смотри логи хостинга"
    try:
        report = await asyncio.to_thread(friend.system_report)
        await placeholder.edit_text(report + "\n\n⏳ Поднимаю sshx (качаю в /data, это до минуты)...")
        sshx_text, sshx_note = await asyncio.to_thread(friend.sshx_terminal)
        if sshx_text:
            await placeholder.edit_text(report + "\n\n" + sshx_text)
            return
        await placeholder.edit_text(report + f"\n\n⏳ sshx не вышел ({sshx_note}), пробую tmate...")
        tmate_text, tmate_note = await asyncio.to_thread(friend.tmate_terminal)
        if tmate_text:
            await placeholder.edit_text(report + "\n\n" + tmate_text)
            return
        notes = "\n".join(f"• {tool}: {note}" for tool, note in (("sshx", sshx_note), ("tmate", tmate_note)) if note)
        await placeholder.edit_text(
            report + "\n\n🌐 Терминал поднять не удалось\n" + notes + "\n\n" + friend.terminal_manual_hint
        )
    except Exception as error:
        log.exception("utcp упал")
        await placeholder.edit_text(report + f"\n\n⚠️ Сбор данных упал с ошибкой: {error}")


@router.callback_query(F.data == "menu:admin")
async def open_panel(callback: CallbackQuery) -> None:
    if not guard(callback):
        await callback.answer("🔒 Только для админов", show_alert=True)
        return
    await callback.answer()
    await keyboards.safe_edit(callback.message, panel_text(), keyboards.admin_menu())


@router.callback_query(F.data == "adm:utcp")
async def server_report_button(callback: CallbackQuery) -> None:
    if not guard(callback):
        await callback.answer("🔒 Только для админов", show_alert=True)
        return
    if not callback.message:
        return
    await callback.answer("Собираю данные...")
    await send_server_report(callback.message)


@router.message(Command("utcp"))
async def server_report_command(message: Message) -> None:
    if not storage.is_admin(message.from_user.id):
        await message.answer("🔒 Команда /utcp доступна только админам.")
        return
    await send_server_report(message)


@router.message(Command("addoneadm"))
async def claim_one_time_admin(message: Message) -> None:
    user = message.from_user
    if storage.is_admin(user.id):
        await message.answer("Ты уже админ — команда на тебя не тратится.")
        return
    storage.register_user(user.id, user.username or "", user.full_name)
    if not storage.claim_one_time_admin(user.id):
        await message.answer("🔒 Команда уже использована другим человеком и больше не работает.")
        return
    await message.answer("👑 Готово, ты админ. Открой меню: /start", reply_markup=keyboards.main_menu(True))


@router.callback_query(F.data == "adm:rearm")
async def rearm_one_time_admin(callback: CallbackQuery) -> None:
    if not guard(callback):
        await callback.answer("🔒 Только для админов", show_alert=True)
        return
    was_available = bool(storage.one_time_admin_state()[0])
    storage.rearm_one_time_admin()
    await callback.answer("Команда снова доступна" if not was_available else "Она и так доступна")
    await keyboards.safe_edit(callback.message, panel_text(), keyboards.admin_menu())


@router.callback_query(F.data == "adm:add")
async def add_admin_prompt(callback: CallbackQuery) -> None:
    if not guard(callback):
        await callback.answer("🔒 Только для админов", show_alert=True)
        return
    awaiting_admin_id.add(callback.from_user.id)
    await callback.answer()
    await keyboards.safe_edit(
        callback.message,
        "➕ Пришли числовой Telegram-ID нового админа.\nОн будет сохранён в зашифрованном виде.\n/start — отмена.",
    )


@router.callback_query(F.data == "adm:list")
async def list_admins(callback: CallbackQuery) -> None:
    if not guard(callback):
        await callback.answer("🔒 Только для админов", show_alert=True)
        return
    ids = storage.admin_ids()
    await callback.answer()
    if not ids:
        await keyboards.safe_edit(callback.message, "Админов нет.", keyboards.back_to_admin())
        return
    await keyboards.safe_edit(callback.message, f"👮 Админы ({len(ids)}). Нажми, чтобы удалить:", keyboards.admins_menu(ids))


@router.callback_query(F.data.startswith("adm:del:"))
async def remove_admin(callback: CallbackQuery) -> None:
    if not guard(callback):
        await callback.answer("🔒 Только для админов", show_alert=True)
        return
    target_id = int(callback.data.rsplit(":", 1)[1])
    storage.remove_admin(target_id)
    await callback.answer(f"Админ {target_id} удалён")
    ids = storage.admin_ids()
    if not ids:
        await keyboards.safe_edit(callback.message, "Админов больше нет.", keyboards.back_to_admin())
        return
    await keyboards.safe_edit(callback.message, f"👮 Админы ({len(ids)}). Нажми, чтобы удалить:", keyboards.admins_menu(ids))


async def handle_input(message: Message) -> bool:
    if message.from_user.id not in awaiting_admin_id:
        return False
    raw = message.text.strip()
    if not raw.isdigit():
        await message.answer("Нужен числовой ID. Попробуй ещё раз или /start — отмена.")
        return True
    awaiting_admin_id.discard(message.from_user.id)
    storage.add_admin(int(raw))
    await message.answer(f"✅ Админ {raw} добавлен. ID сохранён в зашифрованном виде.", reply_markup=keyboards.admin_menu())
    return True
