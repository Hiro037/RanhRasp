import json
from datetime import datetime, timedelta, date
from vkbottle.bot import BotLabeler, Message
from vkbottle import PhotoMessageUploader, KeyboardButtonColor, Keyboard, Text

from database.connection import async_session
from database.models import Teacher
from services import user_service, schedule_service
from services.user_service import determine_user_role
from vk_bot import keyboards as kb
from config import settings
from utils.timezone import get_now
from utils.image_generator import generate_schedule_image
from vk_bot.loader import vk_bot

vk_menu_labeler = BotLabeler()
photo_uploader = PhotoMessageUploader(vk_bot.api)


@vk_menu_labeler.message(text=["/menu", "Меню", "назад"])
@vk_menu_labeler.message(func=lambda msg: msg.payload is not None and json.loads(msg.payload).get("menu") == "back")
async def vk_show_main_menu(message: Message):
    is_admin = message.from_id in settings.VK_ADMINS
    await message.answer(
        "👋 Главное меню расписания филиала РАНХиГС (ВК):\n"
        "Выберите нужный пункт ниже:",
        keyboard=kb.get_vk_inline_main_menu(is_admin)
    )


@vk_menu_labeler.message(func=lambda msg: msg.payload is not None and json.loads(msg.payload).get("menu") == "schedule")
async def vk_initial_schedule(message: Message):
    today = get_now().date()
    await vk_send_schedule_core(message, today)


@vk_menu_labeler.message(func=lambda msg: msg.payload is not None and "vk_nav" in json.loads(msg.payload))
async def vk_schedule_navigation(message: Message):
    payload_val = json.loads(message.payload)["vk_nav"]
    action, current_date_str = payload_val.split(":")
    current_date = datetime.strptime(current_date_str, "%Y-%m-%d").date()

    if action == "prev":
        target_date = current_date - timedelta(days=1)
    elif action == "next":
        target_date = current_date + timedelta(days=1)
    else:
        target_date = current_date

    await vk_send_schedule_core(message, target_date)


async def vk_send_schedule_core(message: Message, target_date: date, from_week_mode: bool = False):
    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "vk", message.from_id)
        if not user:
            await message.answer("⚠️ Сначала зарегистрируйтесь: /start")
            return

        role = await determine_user_role(user)

        lessons = []
        entity_name = None
        has_next = False

        if role == "student":
            if not user.groups:
                await message.answer("⚠️ Вы не привязаны к группе. Исправьте в настройках.")
                return
            group = user.groups[0]
            group_id = group.id
            group_name = group.name
            lessons = await schedule_service.get_lessons_for_student(session, group_id, target_date)
            entity_name = group_name
            has_next = await schedule_service.has_lessons_future(session, target_date, group_id=group_id)

        elif role == "teacher":
            if not user.teacher_profile_id:
                await message.answer("⚠️ Ваш профиль преподавателя не активирован. Обратитесь к администратору.")
                return
            lessons = await schedule_service.get_lessons_for_teacher(session, user.teacher_profile_id, target_date)
            teacher = await session.get(Teacher, user.teacher_profile_id)
            entity_name = teacher.name if teacher else "Преподаватель"
            has_next = await schedule_service.has_lessons_future(session, target_date, teacher_id=user.teacher_profile_id)

        else:  # admin
            if user.groups:
                group = user.groups[0]
                group_id = group.id
                group_name = group.name
                lessons = await schedule_service.get_lessons_for_student(session, group_id, target_date)
                entity_name = group_name
                has_next = await schedule_service.has_lessons_future(session, target_date, group_id=group_id)
            else:
                await message.answer("⚠️ У вас нет группы или преподавательского профиля.")
                return

        vk_keyboard = kb.get_vk_schedule_keyboard(target_date, has_next, role=role)
        date_str = target_date.strftime("%d.%m.%Y")

        if user.schedule_message_type == "pic":
            image_bytes = await generate_schedule_image(lessons, target_date, entity_name)
            attachment = await photo_uploader.upload(
                file_source=image_bytes,
                peer_id=message.peer_id
            )
            await message.answer(
                message=f"🖼️ Расписание на {date_str} для {entity_name}",
                attachment=attachment,
                keyboard=vk_keyboard
            )
        else:
            text = f"📅 Расписание на {date_str} | {entity_name}\n\n"
            if not lessons:
                text += "💤 В этот день занятий нет. Отдыхайте!"
            else:
                for idx, lesson in enumerate(lessons, 1):
                    time_start = lesson.start_datetime.strftime("%H:%M")
                    teacher = lesson.teacher.name if lesson.teacher else "Не указан"
                    subject_name = lesson.subject.name if lesson.subject else "Без названия"
                    classroom_name = lesson.classroom.name if lesson.classroom else "—"
                    text += f"{idx}. {time_start} — {subject_name}\n"
                    text += f"🏫 Ауд: {classroom_name} | 👤 {teacher} ({lesson.type})\n"
                    if lesson.comment:
                        text += f"📝 Заметка: {lesson.comment}\n"
                    text += "\n"
            await message.answer(message=text, keyboard=vk_keyboard)

@vk_menu_labeler.message(func=lambda msg: msg.payload is not None and json.loads(msg.payload).get("menu") == "schedule")
async def vk_choose_schedule_period(message: Message):
    await message.answer("📅 Выберите период:", keyboard=kb.get_vk_schedule_period_keyboard())


@vk_menu_labeler.message(func=lambda msg: msg.payload is not None and json.loads(msg.payload).get("menu") == "schedule_today")
async def vk_schedule_today(message: Message):
    today = get_now().date()
    await vk_send_schedule_core(message, today)


@vk_menu_labeler.message(func=lambda msg: msg.payload is not None and json.loads(msg.payload).get("menu") == "schedule_tomorrow")
async def vk_schedule_tomorrow(message: Message):
    tomorrow = get_now().date() + timedelta(days=1)
    await vk_send_schedule_core(message, tomorrow)


@vk_menu_labeler.message(func=lambda msg: msg.payload is not None and json.loads(msg.payload).get("menu") == "schedule_this_week")
async def vk_schedule_this_week(message: Message):
    today = get_now().date()
    start_of_week = today - timedelta(days=today.weekday())
    await vk_show_week_keyboard(message, start_of_week, "this")


@vk_menu_labeler.message(func=lambda msg: msg.payload is not None and json.loads(msg.payload).get("menu") == "schedule_next_week")
async def vk_schedule_next_week(message: Message):
    today = get_now().date()
    start_of_next_week = today - timedelta(days=today.weekday()) + timedelta(days=7)
    await vk_show_week_keyboard(message, start_of_next_week, "next")


async def vk_show_week_keyboard(message: Message, start_date: date, week_type: str):
    days = []
    for i in range(7):
        d = start_date + timedelta(days=i)
        weekday_ru = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"][i]
        days.append((d, f"{weekday_ru} {d.strftime('%d.%m')}"))

    kb = Keyboard(one_time=False, inline=True)
    for d, label in days:
        kb.add(Text(label, payload={"week_day": d.strftime("%Y-%m-%d"), "week_type": week_type}), color=KeyboardButtonColor.PRIMARY)
        kb.row()
    # Навигация
    if week_type == "this":
        kb.add(Text("Следующая неделя ➡️", payload={"menu": "schedule_next_week"}), color=KeyboardButtonColor.SECONDARY)
    else:
        kb.add(Text("⬅️ Эта неделя", payload={"menu": "schedule_this_week"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text("🔙 Главное меню", payload={"menu": "back"}), color=KeyboardButtonColor.SECONDARY)

    await message.answer("📅 Выберите день:", keyboard=kb.get_json())


@vk_menu_labeler.message(func=lambda msg: msg.payload is not None and "week_day" in json.loads(msg.payload))
async def vk_week_day_selected(message: Message):
    payload = json.loads(message.payload)
    date_str = payload["week_day"]
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    await vk_send_schedule_core(message, target_date, from_week_mode=True)