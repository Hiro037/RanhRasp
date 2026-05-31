import json
import math
from vkbottle.bot import BotLabeler, Message
from vkbottle import Keyboard, KeyboardButtonColor, Text
from sqlalchemy import select, and_

from database.connection import async_session_maker
from database.models import User
from services import admin_service
from config import settings

vk_admin_labeler = BotLabeler()


def is_vk_admin(vk_id: int) -> bool:
    return vk_id in settings.ADMIN_IDS


@vk_admin_labeler.message(text=["Админ", "Админка", "/admin"])
async def vk_show_admin_panel(message: Message):
    if not is_vk_admin(message.from_id): return

    kb = (
        Keyboard(inline=True)
        .add(Text("📊 Статистика", payload={"admin": "stats"}), color=KeyboardButtonColor.PRIMARY)
        .row()
        .add(Text("⏳ Заявки учителей", payload={"admin": "pending"}), color=KeyboardButtonColor.POSITIVE)
        .row()
        .add(Text("🔙 Главное меню", payload={"menu": "back"}), color=KeyboardButtonColor.SECONDARY)
    )
    await message.answer("🔑 Панель администратора базы данных (ВК):", keyboard=kb.get_json())


@vk_admin_labeler.message(func=lambda msg: msg.payload is not None and json.loads(msg.payload).get("admin") == "stats")
async def vk_show_statistics(message: Message):
    if not is_vk_admin(message.from_id): return

    async with async_session_maker() as session:
        stats = await admin_service.get_bot_statistics(session)

    text = (
        "📈 Статистика системы:\n\n"
        f"👥 Студенты: {stats['students_count']}\n"
        f"👨‍🏫 Учителя с профилем: {stats['teachers_count']}\n\n"
        f"📱 Активность сегодня: {stats['active_today']}\n"
        f"📅 Активность за неделю: {stats['active_week']}\n"
        f"📊 Активность за месяц: {stats['active_month']}"
    )
    kb = Keyboard(inline=True).add(Text("🔙 Назад", payload={"admin": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    await message.answer(text, keyboard=kb.get_json())


@vk_admin_labeler.message(
    func=lambda msg: msg.payload is not None and json.loads(msg.payload).get("admin") == "pending")
async def vk_show_pending_users(message: Message):
    if not is_vk_admin(message.from_id): return

    async with async_session_maker() as session:
        stmt = select(User).where(and_(User.role == "teacher", User.teacher_profile_id.is_(None))).order_by(User.id)
        result = await session.execute(stmt)
        pending_users = result.scalars().all()

    if not pending_users:
        kb = Keyboard(inline=True).add(Text("🔙 В админку", payload={"admin": "main_menu"}),
                                       color=KeyboardButtonColor.SECONDARY)
        await message.answer("🎉 Все заявки учителей рассмотрены!", keyboard=kb.get_json())
        return

    kb = Keyboard(inline=True)
    for idx, u in enumerate(pending_users):
        if idx > 0: kb.row()
        display_name = u.username or f"ID {u.id}"
        kb.add(Text(f"❓ Заявка: {display_name}", payload={"admin_rev_u": u.id}), color=KeyboardButtonColor.PRIMARY)

    kb.row().add(Text("🔙 Назад", payload={"admin": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    await message.answer("⏳ Выберите пользователя для привязки профиля:", keyboard=kb.get_json())


@vk_admin_labeler.message(func=lambda msg: msg.payload is not None and "admin_rev_u" in json.loads(msg.payload))
async def vk_review_user(message: Message):
    if not is_vk_admin(message.from_id): return
    target_user_id = json.loads(message.payload)["admin_rev_u"]

    kb = (
        Keyboard(inline=True)
        .add(Text("✅ Привязать профиль", payload={"vk_pag_t": 1, "uid": target_user_id}),
             color=KeyboardButtonColor.POSITIVE)
        .add(Text("❌ Отклонить", payload={"vk_rej_u": target_user_id}), color=KeyboardButtonColor.NEGATIVE)
        .row()
        .add(Text("🔙 К списку заявок", payload={"admin": "pending"}), color=KeyboardButtonColor.SECONDARY)
    )
    await message.answer(f"👤 Решение по пользователю ID {target_user_id}:", keyboard=kb.get_json())


@vk_admin_labeler.message(func=lambda msg: msg.payload is not None and "vk_pag_t" in json.loads(msg.payload))
async def vk_teachers_pagination(message: Message):
    if not is_vk_admin(message.from_id): return
    payload = json.loads(message.payload)
    target_user_id = payload["uid"]
    page = payload["vk_pag_t"]
    PER_PAGE = 8

    async with async_session_maker() as session:
        all_teachers = await admin_service.get_teachers_sorted(session)

    total_teachers = len(all_teachers)
    total_pages = math.ceil(total_teachers / PER_PAGE)

    start_idx = (page - 1) * PER_PAGE
    teachers_slice = all_teachers[start_idx:start_idx + PER_PAGE]

    kb = Keyboard(inline=True)
    for idx, t in enumerate(teachers_slice):
        if idx > 0: kb.row()
        kb.add(Text(f"👨‍🏫 {t.name[:35]}", payload={"vk_lnk": 1, "uid": target_user_id, "tid": t.id}),
               color=KeyboardButtonColor.PRIMARY)

    # Кнопки пагинации ВК
    kb.row()
    if page > 1:
        kb.add(Text("⬅️ Назад", payload={"vk_pag_t": page - 1, "uid": target_user_id}),
               color=KeyboardButtonColor.SECONDARY)
    kb.add(Text(f"📄 {page}/{total_pages}", payload={"ignore": 1}), color=KeyboardButtonColor.SECONDARY)
    if page < total_pages:
        kb.add(Text("Вперед ➡️", payload={"vk_pag_t": page + 1, "uid": target_user_id}),
               color=KeyboardButtonColor.SECONDARY)

    kb.row().add(Text("🔙 Отмена", payload={"admin_rev_u": target_user_id}), color=KeyboardButtonColor.SECONDARY)
    await message.answer(f"📖 Выберите ФИО преподавателя для ID {target_user_id}:", keyboard=kb.get_json())


@vk_admin_labeler.message(func=lambda msg: msg.payload is not None and "vk_lnk" in json.loads(msg.payload))
async def vk_process_link(message: Message):
    if not is_vk_admin(message.from_id): return
    payload = json.loads(message.payload)
    target_user_id = payload["uid"]
    teacher_id = payload["tid"]

    from main_loader import tg_bot, vk_bot

    async with async_session_maker() as session:
        await admin_service.link_teacher_to_user(session, target_user_id, teacher_id)
        stmt = select(User).where(User.id == target_user_id)
        res = await session.execute(stmt)
        user = res.scalars().first()

    await message.answer("✅ Профиль привязан!")
    if user:
        msg = "🎉 Ваш аккаунт успешно верифицирован администратором филиала!"
        try:
            if user.platform == "tg":
                await tg_bot.send_message(chat_id=user.platform_user_id, text=msg)
            elif user.platform == "vk":
                await vk_bot.api.messages.send(peer_id=user.platform_user_id, message=msg, random_id=0)
        except Exception as e:
            print(e)

    # Возвращаем админа к списку заявок
    await vk_show_pending_users(message)


@vk_admin_labeler.message(func=lambda msg: msg.payload is not None and "admin_main_menu" in json.loads(msg.payload))
async def vk_back_to_main_wrapper(message: Message):
    await vk_show_admin_panel(message)