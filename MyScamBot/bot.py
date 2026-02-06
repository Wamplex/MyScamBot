import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8477993801:AAGF3dUZSjGI5VicjmLCTr4a4NCUFBLGOqM")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
GUARANTOR_GROUP_ID = os.getenv("GUARANTOR_GROUP_ID")
MAIN_GROUP_ID = os.getenv("MAIN_GROUP_ID")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())


class UserRole:
    USER = "user"
    GUARANTOR = "guarantor"
    ADMIN = "admin"


class UserStatus:
    HUMAN = "human"
    NOT_SCAMMER = "not_scammer"
    POSSIBLE_SCAMMER = "possible_scammer"
    SCAMMER = "scammer"
    GUARANTOR = "guarantor"


class DealStatus:
    SEARCHING = "searching"
    ACTIVE = "active"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class ComplaintStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class UserProfile:
    user_id: int
    username: str
    status: str = UserStatus.HUMAN
    role: str = UserRole.USER
    deals_count: int = 0
    complaints_count: int = 0
    is_afk: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Deal:
    deal_id: int
    client_id: int
    counterparty: str
    client_gives: str
    client_gets: str
    amount: str
    description: str
    guarantor_id: Optional[int] = None
    status: str = DealStatus.SEARCHING
    group_topic_id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Complaint:
    complaint_id: int
    sender_id: int
    scammer_id: str
    description: str
    proof_files: List[str]
    status: str = ComplaintStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)


users: Dict[int, UserProfile] = {}
username_index: Dict[str, int] = {}

deals: Dict[int, Deal] = {}
complaints: Dict[int, Complaint] = {}


def register_user(user: Message) -> UserProfile:
    profile = users.get(user.from_user.id)
    username = (user.from_user.username or "").lower()
    if profile:
        if username and username != profile.username:
            profile.username = username
            username_index[username] = profile.user_id
        return profile

    role = UserRole.ADMIN if user.from_user.id == ADMIN_ID else UserRole.USER
    profile = UserProfile(user_id=user.from_user.id, username=username, role=role)
    users[profile.user_id] = profile
    if username:
        username_index[username] = profile.user_id
    return profile


def format_profile(profile: UserProfile) -> str:
    return (
        "👤 <b>Профиль пользователя</b>\n\n"
        f"🆔 ID: <code>{profile.user_id}</code>\n"
        f"👤 Username: @{profile.username or 'не указан'}\n"
        f"📊 Статус: <b>{profile.status}</b>\n"
        f"🛡 Роль: <b>{profile.role}</b>\n"
        f"📨 Жалоб: <b>{profile.complaints_count}</b>\n"
        f"🤝 Сделок: <b>{profile.deals_count}</b>"
    )


def main_menu(profile: UserProfile) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🔍 Проверить пользователя", callback_data="menu_check")],
        [InlineKeyboardButton(text="🛡 Гаранты", callback_data="menu_guarantors")],
        [InlineKeyboardButton(text="🤝 Найти гаранта", callback_data="menu_find_guarantor")],
        [InlineKeyboardButton(text="🚨 Слить скамера", callback_data="menu_complaint")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile")],
    ]
    if profile.role == UserRole.GUARANTOR:
        status = "ВКЛ" if profile.is_afk else "ВЫКЛ"
        buttons.append([InlineKeyboardButton(text=f"💤 AFK: {status}", callback_data="menu_toggle_afk")])
    if profile.role == UserRole.ADMIN:
        buttons.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="menu_admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def guarantors_list() -> str:
    guarantors = [u for u in users.values() if u.role == UserRole.GUARANTOR]
    if not guarantors:
        return "🛡 <b>Список гарантов:</b>\n\nНет активных гарантов."
    lines = ["🛡 <b>Список гарантов:</b>"]
    for guarantor in guarantors:
        status = "AFK" if guarantor.is_afk else "онлайн"
        lines.append(f"• @{guarantor.username or guarantor.user_id} — {status}")
    return "\n".join(lines)


def parse_user_reference(text: str) -> Tuple[Optional[int], str]:
    value = text.strip()
    if value.startswith("@"):
        username = value[1:].lower()
        user_id = username_index.get(username)
        return user_id, f"@{username}"
    try:
        user_id = int(value)
        return user_id, str(user_id)
    except ValueError:
        return None, value


class FindGuarantorStates(StatesGroup):
    counterparty = State()
    gives = State()
    gets = State()
    amount = State()
    description = State()
    confirm = State()


class ComplaintStates(StatesGroup):
    scammer = State()
    description = State()
    proofs = State()


class AdminStates(StatesGroup):
    guarantor = State()


@dp.message(Command("start"))
async def cmd_start(message: Message):
    profile = register_user(message)
    await message.answer(
        "Добро пожаловать в Scambase Bot! Выберите действие:",
        reply_markup=main_menu(profile),
    )


@dp.callback_query(F.data == "menu_profile")
async def menu_profile(callback: CallbackQuery):
    profile = register_user(callback.message)
    await callback.message.answer(format_profile(profile))
    await callback.answer()


@dp.callback_query(F.data == "menu_guarantors")
async def menu_guarantors(callback: CallbackQuery):
    register_user(callback.message)
    await callback.message.answer(guarantors_list())
    await callback.answer()


@dp.callback_query(F.data == "menu_toggle_afk")
async def menu_toggle_afk(callback: CallbackQuery):
    profile = register_user(callback.message)
    if profile.role != UserRole.GUARANTOR:
        await callback.answer("Недоступно", show_alert=True)
        return
    profile.is_afk = not profile.is_afk
    await callback.message.answer(
        f"Статус AFK обновлён: {'ВКЛ' if profile.is_afk else 'ВЫКЛ'}",
        reply_markup=main_menu(profile),
    )
    await callback.answer()


@dp.message(Command("check"))
async def cmd_check(message: Message):
    register_user(message)
    args = message.text.split(maxsplit=1)
    if len(args) != 2:
        await message.answer("Используй: /check @username | user_id")
        return

    user_id, label = parse_user_reference(args[1])
    profile = users.get(user_id) if user_id else None
    if not profile and label.startswith("@"):
        await message.answer(
            "👤 <b>Профиль пользователя</b>\n\n"
            f"🆔 ID: -\n"
            f"👤 Username: {label}\n"
            f"📊 Статус: <b>{UserStatus.HUMAN}</b>\n"
            f"🛡 Роль: <b>{UserRole.USER}</b>\n"
            f"📨 Жалоб: <b>0</b>\n"
            f"🤝 Сделок: <b>0</b>"
        )
        return

    if not profile:
        profile = UserProfile(user_id=user_id, username="")
    await message.answer(format_profile(profile))


@dp.callback_query(F.data == "menu_check")
async def menu_check(callback: CallbackQuery):
    await callback.message.answer("Используй команду: /check @username | user_id")
    await callback.answer()


@dp.callback_query(F.data == "menu_find_guarantor")
async def menu_find_guarantor(callback: CallbackQuery, state: FSMContext):
    profile = register_user(callback.message)
    if profile.role != UserRole.USER:
        await callback.answer("Доступно только пользователям", show_alert=True)
        return
    await state.set_state(FindGuarantorStates.counterparty)
    await callback.message.answer("С кем сделка?\nВведите @username или ID контрагента:")
    await callback.answer()


@dp.message(FindGuarantorStates.counterparty)
async def find_guarantor_counterparty(message: Message, state: FSMContext):
    await state.update_data(counterparty=message.text.strip())
    await state.set_state(FindGuarantorStates.gives)
    await message.answer("Что он даёт?")


@dp.message(FindGuarantorStates.gives)
async def find_guarantor_gives(message: Message, state: FSMContext):
    await state.update_data(client_gets=message.text.strip())
    await state.set_state(FindGuarantorStates.gets)
    await message.answer("Что вы даёте?")


@dp.message(FindGuarantorStates.gets)
async def find_guarantor_gets(message: Message, state: FSMContext):
    await state.update_data(client_gives=message.text.strip())
    await state.set_state(FindGuarantorStates.amount)
    await message.answer("Примерная сумма сделки:")


@dp.message(FindGuarantorStates.amount)
async def find_guarantor_amount(message: Message, state: FSMContext):
    await state.update_data(amount=message.text.strip())
    await state.set_state(FindGuarantorStates.description)
    await message.answer("Кратко опишите сделку:")


@dp.message(FindGuarantorStates.description)
async def find_guarantor_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    data = await state.get_data()
    summary = (
        "📋 <b>Проверьте данные:</b>\n\n"
        f"👥 Контрагент: {data['counterparty']}\n"
        f"📥 Что он даёт: {data['client_gets']}\n"
        f"📤 Что вы даёте: {data['client_gives']}\n"
        f"💵 Сумма: {data['amount']}\n"
        f"📝 Описание: {data['description']}\n"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data="deal_confirm"),
                InlineKeyboardButton(text="❌ Отменить", callback_data="deal_cancel"),
            ]
        ]
    )
    await state.set_state(FindGuarantorStates.confirm)
    await message.answer(summary, reply_markup=keyboard)


@dp.callback_query(F.data == "deal_cancel")
async def deal_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Заявка отменена.")
    await callback.answer()


@dp.callback_query(F.data == "deal_confirm")
async def deal_confirm(callback: CallbackQuery, state: FSMContext):
    profile = register_user(callback.message)
    data = await state.get_data()
    deal_id = len(deals) + 1
    deal = Deal(
        deal_id=deal_id,
        client_id=profile.user_id,
        counterparty=data["counterparty"],
        client_gives=data["client_gives"],
        client_gets=data["client_gets"],
        amount=data["amount"],
        description=data["description"],
    )
    deals[deal_id] = deal
    profile.deals_count += 1
    await state.clear()

    await callback.message.answer("Заявка создана и отправлена гарантам.")
    await notify_guarantors(deal)
    await callback.answer()


async def notify_guarantors(deal: Deal):
    message_text = (
        "🆕 <b>Новая сделка</b>\n\n"
        f"👤 Клиент: <code>{deal.client_id}</code>\n"
        f"👥 Контрагент: {deal.counterparty}\n"
        f"💵 Сумма: {deal.amount}\n"
        f"📝 Описание: {deal.description}\n\n"
        "👇 Кто проведёт?"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛡 Провести сделку", callback_data=f"deal_take:{deal.deal_id}")]
        ]
    )

    if GUARANTOR_GROUP_ID:
        try:
            await bot.send_message(GUARANTOR_GROUP_ID, message_text, reply_markup=keyboard)
        except TelegramBadRequest:
            logging.warning("Failed to send to guarantor group")

    for guarantor in [u for u in users.values() if u.role == UserRole.GUARANTOR and not u.is_afk]:
        try:
            await bot.send_message(guarantor.user_id, message_text, reply_markup=keyboard)
        except TelegramForbiddenError:
            logging.info("Guarantor %s has закрытые ЛС", guarantor.user_id)


@dp.callback_query(F.data.startswith("deal_take:"))
async def deal_take(callback: CallbackQuery):
    profile = register_user(callback.message)
    if profile.role != UserRole.GUARANTOR:
        await callback.answer("Доступно только гарантам", show_alert=True)
        return

    deal_id = int(callback.data.split(":", 1)[1])
    deal = deals.get(deal_id)
    if not deal or deal.status != DealStatus.SEARCHING:
        await callback.answer("❌ Сделку уже взял другой гарант", show_alert=True)
        return

    deal.guarantor_id = profile.user_id
    deal.status = DealStatus.ACTIVE
    await callback.message.answer("✅ Вы назначены гарантом по сделке.")
    await callback.answer()
    await create_deal_topic(deal)


async def create_deal_topic(deal: Deal):
    if not MAIN_GROUP_ID:
        logging.warning("MAIN_GROUP_ID not configured")
        return

    client = users.get(deal.client_id)
    guarantor = users.get(deal.guarantor_id) if deal.guarantor_id else None
    topic_name = f"Сделка #{deal.deal_id} | @{client.username if client else deal.client_id} + @{guarantor.username if guarantor else deal.guarantor_id}"
    try:
        topic = await bot.create_forum_topic(MAIN_GROUP_ID, name=topic_name)
    except TelegramBadRequest:
        logging.warning("Не удалось создать тему сделки")
        return

    deal.group_topic_id = topic.message_thread_id
    link = f"https://t.me/c/{str(MAIN_GROUP_ID).lstrip('-100')}/{deal.group_topic_id}"

    recipients = {deal.client_id}
    counterparty_id, _ = parse_user_reference(deal.counterparty)
    if counterparty_id:
        recipients.add(counterparty_id)
    if deal.guarantor_id:
        recipients.add(deal.guarantor_id)

    for user_id in recipients:
        try:
            await bot.send_message(user_id, f"🔗 Комната сделки: {link}")
        except TelegramForbiddenError:
            logging.info("Не удалось отправить ссылку пользователю %s", user_id)


@dp.callback_query(F.data == "menu_complaint")
async def menu_complaint(callback: CallbackQuery, state: FSMContext):
    register_user(callback.message)
    await state.set_state(ComplaintStates.scammer)
    await callback.message.answer("Введите @username или ID скамера:")
    await callback.answer()


@dp.message(ComplaintStates.scammer)
async def complaint_scammer(message: Message, state: FSMContext):
    await state.update_data(scammer_id=message.text.strip())
    await state.set_state(ComplaintStates.description)
    await message.answer("Опишите ситуацию:")


@dp.message(ComplaintStates.description)
async def complaint_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip(), proof_files=[])
    await state.set_state(ComplaintStates.proofs)
    await message.answer("Пришлите доказательства (фото/видео/файлы). Напишите 'готово' для отправки.")


@dp.message(ComplaintStates.proofs)
async def complaint_proofs(message: Message, state: FSMContext):
    data = await state.get_data()
    proof_files = data.get("proof_files", [])

    if message.text and message.text.lower() == "готово":
        await finalize_complaint(message, state)
        return

    if message.photo:
        proof_files.append(message.photo[-1].file_id)
    elif message.video:
        proof_files.append(message.video.file_id)
    elif message.document:
        proof_files.append(message.document.file_id)
    else:
        await message.answer("Пожалуйста, пришлите файл или напишите 'готово'.")
        return

    await state.update_data(proof_files=proof_files)
    await message.answer("Файл добавлен. Ещё доказательства или 'готово'.")


async def finalize_complaint(message: Message, state: FSMContext):
    profile = register_user(message)
    data = await state.get_data()
    complaint_id = len(complaints) + 1
    complaint = Complaint(
        complaint_id=complaint_id,
        sender_id=profile.user_id,
        scammer_id=data["scammer_id"],
        description=data["description"],
        proof_files=data.get("proof_files", []),
    )
    complaints[complaint_id] = complaint
    profile.complaints_count += 1
    await state.clear()
    await message.answer("✅ Жалоба отправлена администрации")
    await notify_admin(complaint)


async def notify_admin(complaint: Complaint):
    if ADMIN_ID == 0:
        return
    text = (
        "🚨 <b>Новая жалоба</b>\n\n"
        f"👤 Обвиняемый: {complaint.scammer_id}\n"
        f"📝 Описание: {complaint.description}\n"
        f"📎 Доказательства: {len(complaint.proof_files)} файл(ов)"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❌ СКАМЕР", callback_data=f"complaint:{complaint.complaint_id}:scammer"),
                InlineKeyboardButton(text="⚠️ ВОЗМОЖНО СКАМЕР", callback_data=f"complaint:{complaint.complaint_id}:possible"),
                InlineKeyboardButton(text="✅ ОТКЛОНИТЬ", callback_data=f"complaint:{complaint.complaint_id}:reject"),
            ]
        ]
    )
    try:
        await bot.send_message(ADMIN_ID, text, reply_markup=keyboard)
    except TelegramForbiddenError:
        logging.warning("Admin chat not доступен")


@dp.callback_query(F.data == "menu_admin")
async def menu_admin(callback: CallbackQuery):
    profile = register_user(callback.message)
    if profile.role != UserRole.ADMIN:
        await callback.answer("Недоступно", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📨 Жалобы", callback_data="admin_complaints")],
            [InlineKeyboardButton(text="🎭 Выдать роль гаранта", callback_data="admin_make_guarantor")],
        ]
    )
    await callback.message.answer("Админ-панель:", reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(F.data == "admin_complaints")
async def admin_complaints(callback: CallbackQuery):
    profile = register_user(callback.message)
    if profile.role != UserRole.ADMIN:
        await callback.answer("Недоступно", show_alert=True)
        return
    pending = [c for c in complaints.values() if c.status == ComplaintStatus.PENDING]
    if not pending:
        await callback.message.answer("Нет новых жалоб.")
        await callback.answer()
        return
    lines = ["📨 <b>Ожидающие жалобы:</b>"]
    for complaint in pending:
        lines.append(f"• #{complaint.complaint_id} — {complaint.scammer_id}")
    await callback.message.answer("\n".join(lines))
    await callback.answer()


@dp.callback_query(F.data == "admin_make_guarantor")
async def admin_make_guarantor(callback: CallbackQuery, state: FSMContext):
    profile = register_user(callback.message)
    if profile.role != UserRole.ADMIN:
        await callback.answer("Недоступно", show_alert=True)
        return
    await state.set_state(AdminStates.guarantor)
    await callback.message.answer("Введите ID пользователя для назначения гарантом:")
    await callback.answer()


@dp.message(AdminStates.guarantor)
async def admin_set_guarantor(message: Message, state: FSMContext):
    profile = register_user(message)
    if profile.role != UserRole.ADMIN:
        await message.answer("Недоступно")
        await state.clear()
        return
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("Нужен числовой ID")
        return
    target = users.get(user_id)
    if not target:
        target = UserProfile(user_id=user_id, username="")
        users[user_id] = target
    target.role = UserRole.GUARANTOR
    target.status = UserStatus.GUARANTOR
    await message.answer("Роль гаранта выдана.")
    await state.clear()


@dp.callback_query(F.data.startswith("complaint:"))
async def complaint_action(callback: CallbackQuery):
    profile = register_user(callback.message)
    if profile.role != UserRole.ADMIN:
        await callback.answer("Недоступно", show_alert=True)
        return

    _, complaint_id, action = callback.data.split(":")
    complaint = complaints.get(int(complaint_id))
    if not complaint or complaint.status != ComplaintStatus.PENDING:
        await callback.answer("Жалоба уже обработана", show_alert=True)
        return

    if action == "scammer":
        complaint.status = ComplaintStatus.APPROVED
        set_user_status(complaint.scammer_id, UserStatus.SCAMMER)
    elif action == "possible":
        complaint.status = ComplaintStatus.APPROVED
        set_user_status(complaint.scammer_id, UserStatus.POSSIBLE_SCAMMER)
    else:
        complaint.status = ComplaintStatus.REJECTED

    await callback.message.answer("Жалоба обработана.")
    await callback.answer()


def set_user_status(reference: str, status: str):
    user_id, _ = parse_user_reference(reference)
    if user_id and user_id in users:
        users[user_id].status = status


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено.")


async def main():
    logging.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
