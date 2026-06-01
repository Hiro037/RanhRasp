from vkbottle.bot import Blueprint, Message

from database.connection import async_session
from services import user_service

bp = Blueprint("SettingsFeedbackHandlers")


@bp.on.message(text="Настройки")
async def settings_main_vk(message: Message):
    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "vk", message.from_id)
        if not user:
            user = await user_service.create_user(session, "vk", message.from_id)

        notify_text = "Включены" if user.is_notification_on else "Выключены"
        format_text = "Картинка" if user.schedule_message_type == "pic" else "Текст"
        group_text = user.groups[0].name if user.groups else "Не выбрана"

        return (
            f"⚙ Настройки вашего профиля:\n"
            f"1. Уведомления: {notify_text} (Напишите 'Переключить уведомления')\n"
            f"2. Формат: {format_text} (Напишите 'Переключить формат')\n"
            f"3. Ваша группа: {group_text} (Напишите 'Поменять группу [Имя группы]')"
        )


@bp.on.message(text="Переключить уведомления")
async def toggle_not_vk(message: Message):
    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "vk", message.from_id)
        if user:
            await user_service.update_user_preferences(
                session, user.id,
                is_notification_on=not user.is_notification_on
            )
            return "✅ Настройки уведомлений успешно изменены!"
        return "❌ Пользователь не найден."


@bp.on.message(text="Переключить формат")
async def toggle_fmt_vk(message: Message):
    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "vk", message.from_id)
        if user:
            new_fmt = "text" if user.schedule_message_type == "pic" else "pic"
            await user_service.update_user_preferences(session, user.id, schedule_type=new_fmt)
            return f"✅ Формат расписания изменен на: {'Картинка' if new_fmt == 'pic' else 'Текст'}"
        return "❌ Пользователь не найден."


@bp.on.message(text="Поменять группу <group_name>")
async def change_grp_vk(message: Message, group_name: str):
    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "vk", message.from_id)
        if not user:
            return "❌ Пользователь не найден. Начните с /start"

        success = await user_service.update_user_group(session, user.id, group_name.strip())
        if success:
            return f"✅ Ваша группа успешно изменена на {group_name}!"
        return "❌ Ошибка. Такой группы не найдено в базе данных."


@bp.on.message(text="Отзыв")
async def feedback_start_vk(message: Message):
    # VK не поддерживает FSM так же легко, поэтому используем простой подход:
    # сохраняем состояние в БД или просто просим отправить сообщение
    # Для простоты: просим написать текст отдельным сообщением
    await message.answer(
        "💬 Напишите ваше предложение, отзыв или сообщение об ошибке.\n"
        "Отправьте его следующим сообщением, и оно будет передано администрации."
    )
    # Устанавливаем флаг ожидания обратной связи (храним в БД или временно)
    # Здесь используем контекст: следующий текст от этого пользователя будет обработан как фидбек.
    # Реализуем через словарь (простейший вариант, но лучше через БД)
    if not hasattr(bp, '_pending_feedback'):
        bp._pending_feedback = {}
    bp._pending_feedback[message.from_id] = True


@bp.on.message(func=lambda msg: hasattr(bp, '_pending_feedback') and bp._pending_feedback.get(msg.from_id))
async def feedback_receive_vk(message: Message):
    async with async_session() as session:
        user = await user_service.get_user_by_platform_id(session, "vk", message.from_id)
        if not user:
            user = await user_service.create_user(session, "vk", message.from_id)

        await user_service.create_feedback(session, user.id, message.text)

    # Убираем флаг ожидания
    if hasattr(bp, '_pending_feedback'):
        bp._pending_feedback.pop(message.from_id, None)

    await message.answer(
        "✅ Ваше обращение успешно сохранено и отправлено администрации! Спасибо за обратную связь."
    )
