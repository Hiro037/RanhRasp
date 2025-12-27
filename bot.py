"""
Асинхронный Telegram бот для системы расписания RanhRasp

Основные изменения:
- Полный переход на асинхронную работу с БД через UnitOfWork
- Интеграция модели пользователя
- Автоматическое сохранение выбранной группы
- Персонализированный опыт для вернувшихся пользователей
- Улучшенная архитектура с разделением ответственности
"""

import hashlib
import os
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Dict, Optional, Tuple

from aiogram import Bot, F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

from database.models import Group, User
from database.repositories import UnitOfWork
from jinja_renderer import html_to_image, render_html
from test_parse import (convert_doc_to_docx, import_schedule_to_db_async,
                        parse_docx_schedule)

load_dotenv()

ADMIN_ID = os.getenv("ADMIN_ID")


# ========== СОСТОЯНИЯ FSM ==========


class GroupDateChoose(StatesGroup):
    """Состояния для выбора группы и даты"""

    choosing_group = State()
    choosing_date = State()


class Feedback(StatesGroup):
    """Состояние ожидания отзыва от пользователя"""

    waiting_for_text = State()


class MainMenu(StatesGroup):
    """Состояние главного меню"""

    in_menu = State()


class ScheduleFSM(StatesGroup):
    """Состояния для загрузки расписания (админ)"""

    choosing_group = State()
    choosing_month = State()
    waiting_for_file = State()

class TeacherRegistration(StatesGroup):
    """Состояния регистрации преподавателя"""
    waiting_for_name = State()
    waiting_for_confirmation = State()


class TeacherSchedule(StatesGroup):
    """Состояния работы с расписанием преподавателя"""
    choosing_date = State()
    choosing_lesson = State()
    writing_comment = State()



# ========== УТИЛИТЫ ==========


def format_date_readable_manual(date_obj: date) -> str:
    """Преобразует дату в читаемый формат '28 мая'"""
    months_ru = {
        1: "января",
        2: "февраля",
        3: "марта",
        4: "апреля",
        5: "мая",
        6: "июня",
        7: "июля",
        8: "августа",
        9: "сентября",
        10: "октября",
        11: "ноября",
        12: "декабря",
    }
    return f"{date_obj.day} {months_ru[date_obj.month]}"


def format_time(dt_object: datetime) -> str:
    """Преобразует datetime в строку времени ЧЧ:ММ"""
    return dt_object.strftime("%H:%M")


def greeting_by_time() -> str:
    """Возвращает приветствие в зависимости от времени суток"""
    # Часовой пояс МСК+2 (UTC+5)
    msk_plus_2 = timezone(timedelta(hours=5))
    now = datetime.now(msk_plus_2)
    hour = now.hour

    if 5 <= hour < 12:
        return "Доброе утро"
    elif 12 <= hour < 18:
        return "Добрый день"
    elif 18 <= hour < 23:
        return "Добрый вечер"
    else:
        return "Доброй ночи"


async def create_schedule_text(selected_date: date, group_name: str) -> str:
    """
    Создает текстовое описание расписания на дату

    Args:
        selected_date: Дата расписания
        group_name: Название группы

    Returns:
        Текст расписания
    """
    async with UnitOfWork() as uow:
        # Получаем группу
        group = await uow.groups.get_by_name(group_name)
        if not group:
            return f"Группа {group_name} не найдена"

        # Получаем занятия на дату
        lessons = await uow.lessons.get_by_group_and_date(group.group_id, selected_date)

        answer = f"Расписание на {format_date_readable_manual(selected_date)}:\n\n"

        if lessons:
            for lesson in lessons:
                answer += (
                    f"📚 {lesson.subject.name}\n"
                    f"🕐 {format_time(lesson.start_datetime)}\n"
                    f"👨‍🏫 {lesson.teacher.name}\n"
                    f"🚪 Аудитория {lesson.classroom}\n"
                )
                if lesson.lesson_type:
                    answer += f"📝 {lesson.lesson_type}\n"
                answer += "\n"
        else:
            answer += "✨ У вас нет занятий в этот день"

    return answer


# ========== КЭШ ИЗОБРАЖЕНИЙ ==========


class ScheduleImageCache:
    """Класс для управления кэшем изображений расписания"""

    def __init__(self, max_size: int = 100, ttl_hours: int = 24):
        self._cache: Dict[str, Tuple[BytesIO, str, datetime]] = {}
        self.max_size = max_size
        self.ttl_hours = ttl_hours

    def _generate_cache_key(self, selected_date: date, group: str) -> str:
        """Генерирует ключ для кэша на основе даты и группы"""
        date_str = selected_date.isoformat()
        return hashlib.md5(f"{date_str}_{group}".encode()).hexdigest()

    def get(self, selected_date: date, group: str) -> Optional[Tuple[BytesIO, str]]:
        """Получить расписание из кэша если оно есть и не устарело"""
        cache_key = self._generate_cache_key(selected_date, group)

        if cache_key in self._cache:
            image_data, caption, timestamp = self._cache[cache_key]

            # Проверяем не устарело ли изображение
            if datetime.now() - timestamp < timedelta(hours=self.ttl_hours):
                return image_data, caption

        return None

    def set(self, selected_date: date, group: str, image_data: BytesIO, caption: str):
        """Сохранить расписание в кэш"""
        cache_key = self._generate_cache_key(selected_date, group)

        # Очищаем кэш если он превысил максимальный размер
        if len(self._cache) >= self.max_size:
            # Удаляем 25% самых старых записей
            oldest_keys = sorted(self._cache.keys(), key=lambda k: self._cache[k][2])[
                : self.max_size // 4
            ]

            for key in oldest_keys:
                del self._cache[key]

        # Сохраняем новую запись
        self._cache[cache_key] = (image_data, caption, datetime.now())

    def clear(self) -> int:
        """Очистить весь кэш и вернуть количество удаленных элементов"""
        old_size = len(self._cache)
        self._cache.clear()
        return old_size

    def clear_group(self, group_name: str):
        """Очистить кэш для конкретной группы"""
        keys_to_remove = [
            key
            for key in self._cache.keys()
            if key.endswith(hashlib.md5(group_name.encode()).hexdigest()[-8:])
        ]
        for key in keys_to_remove:
            del self._cache[key]


# ========== МЕНЕДЖЕРЫ ==========


class ImageManager:
    """Класс для управления изображениями"""

    def __init__(self):
        self.middle_image_file_id = None

    async def get_or_upload_middle_image(self, bot: Bot, chat_id: int) -> Optional[str]:
        """Получить file_id картинки middle.png, при необходимости загрузить ее"""
        if self.middle_image_file_id:
            return self.middle_image_file_id

        image_path = Path("image/middle.png")
        if not image_path.exists():
            # Ищем альтернативные изображения
            fallback_image = Path("image/fallback.png")
            if fallback_image.exists():
                image_path = fallback_image
            else:
                return None

        try:
            with open(image_path, "rb") as f:
                photo = BufferedInputFile(f.read(), filename=image_path.name)

            message = await bot.send_photo(chat_id, photo)
            self.middle_image_file_id = message.photo[-1].file_id
            await bot.delete_message(chat_id, message.message_id)
            return self.middle_image_file_id
        except Exception as e:
            print(f"⚠️ Ошибка загрузки картинки: {e}")
            return None

    async def get_schedule_image(
        self, selected_date: date, group: str, cache: ScheduleImageCache
    ) -> Tuple[BytesIO, str]:
        """Получить изображение расписания (из кэша или сгенерировать новое)"""
        # Пытаемся получить из кэша
        cached = cache.get(selected_date, group)
        if cached:
            return cached

        # Генерируем новое изображение
        html = await render_html(selected_date, group)
        img = await html_to_image(html)
        caption = f"📅 Расписание на {format_date_readable_manual(selected_date)}"

        # Сохраняем в кэш
        cache.set(selected_date, group, img, caption)

        return img, caption


class BotMessageManager:
    """Класс для управления отправкой сообщений бота"""

    def __init__(self, image_manager: ImageManager):
        self.image_manager = image_manager

    async def send_bot_message(
        self,
        target: types.Message | types.CallbackQuery,
        text: str,
        reply_markup: InlineKeyboardMarkup = None,
        bot: Bot = None,
        state: FSMContext = None,
        with_image: bool = True,
    ) -> types.Message:
        """
        Универсальная функция для отправки сообщений бота с управлением историей
        """
        chat_id = (
            target.message.chat.id
            if isinstance(target, types.CallbackQuery)
            else target.chat.id
        )
        message_to_edit = (
            target.message if isinstance(target, types.CallbackQuery) else None
        )

        # Удаляем предыдущее сообщение бота если есть
        await self.delete_last_bot_message(state, bot, chat_id)

        try:
            if with_image:
                file_id = await self.image_manager.get_or_upload_middle_image(
                    bot, chat_id
                )
                if file_id:
                    if message_to_edit:
                        # Пытаемся отредактировать существующее сообщение
                        try:
                            sent = await message_to_edit.edit_media(
                                media=types.InputMediaPhoto(
                                    media=file_id, caption=text
                                ),
                                reply_markup=reply_markup,
                            )
                            await state.update_data(last_message_id=sent.message_id)
                            return sent
                        except Exception:
                            pass

                    # Отправляем новое сообщение с фото
                    sent = await bot.send_photo(
                        chat_id, file_id, caption=text, reply_markup=reply_markup
                    )
                else:
                    # Если картинка недоступна, отправляем текстовое сообщение
                    if message_to_edit:
                        try:
                            sent = await message_to_edit.edit_text(
                                text, reply_markup=reply_markup
                            )
                            await state.update_data(last_message_id=sent.message_id)
                            return sent
                        except Exception:
                            pass

                    sent = await bot.send_message(
                        chat_id, text, reply_markup=reply_markup
                    )
            else:
                # Отправка без картинки
                if message_to_edit:
                    try:
                        sent = await message_to_edit.edit_text(
                            text, reply_markup=reply_markup
                        )
                        await state.update_data(last_message_id=sent.message_id)
                        return sent
                    except Exception:
                        pass

                sent = await bot.send_message(chat_id, text, reply_markup=reply_markup)

            # Сохраняем ID нового сообщения
            if state:
                await state.update_data(last_message_id=sent.message_id)

            return sent

        except Exception as e:
            print(f"⚠️ Ошибка отправки сообщения: {e}")
            # Фолбэк: просто отправляем текстовое сообщение
            sent = await bot.send_message(chat_id, text, reply_markup=reply_markup)
            if state:
                await state.update_data(last_message_id=sent.message_id)
            return sent

    @staticmethod
    async def delete_last_bot_message(state: FSMContext, bot: Bot, chat_id: int):
        """Удалить последнее сообщение бота если оно сохранено в состоянии"""
        if not state or not bot:
            return

        data = await state.get_data()
        last_message_id = data.get("last_message_id")
        if last_message_id:
            try:
                await bot.delete_message(chat_id, last_message_id)
            except Exception:
                # Сообщение уже удалено или недоступно - игнорируем
                pass


class KeyboardManager:
    """Класс для управления клавиатурами"""

    VALID_FACULTIES = {"Экономика", "Менеджмент", "ГМУ", "Юриспруденция"}
    VALID_GROUPS = {
        "Э-42",
        "Э-43",
        "Э-44",
        "М-42",
        "М-43",
        "М-44",
        "ГМУ-41",
        "ГМУ-42",
        "ГМУ-43",
        "ГМУ-44",
        "Ю-41",
        "Ю-42",
        "Ю-43",
        "Ю-44",
    }

    @staticmethod
    def faculties_choose_keyboard() -> InlineKeyboardMarkup:
        """Клавиатура выбора факультета"""
        builder = InlineKeyboardBuilder()
        for faculty in KeyboardManager.VALID_FACULTIES:
            builder.add(types.InlineKeyboardButton(text=faculty, callback_data=faculty))

        builder.add(
            types.InlineKeyboardButton(
                text="❌ Выход в главное меню", callback_data="cancel"
            )
        )
        builder.adjust(2)
        return builder.as_markup()

    @staticmethod
    def groups_choose_keyboard(faculty: str) -> InlineKeyboardMarkup:
        """Клавиатура выбора группы в зависимости от факультета"""
        builder = InlineKeyboardBuilder()

        if faculty == "Экономика":
            groups = ["Э-42", "Э-43", "Э-44"]
        elif faculty == "Менеджмент":
            groups = ["М-42", "М-43", "М-44"]
        elif faculty == "ГМУ":
            groups = ["ГМУ-41", "ГМУ-42", "ГМУ-43", "ГМУ-44"]
        elif faculty == "Юриспруденция":
            groups = ["Ю-41", "Ю-42", "Ю-43", "Ю-44"]
        else:
            groups = []

        for group in groups:
            builder.add(types.InlineKeyboardButton(text=group, callback_data=group))

        builder.add(
            types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_faculty")
        )
        builder.add(
            types.InlineKeyboardButton(
                text="❌ Выход в главное меню", callback_data="cancel"
            )
        )
        builder.adjust(2)
        return builder.as_markup()

    @staticmethod
    def date_choose_keyboard() -> InlineKeyboardMarkup:
        """Клавиатура выбора даты (8 дней вперед)"""
        builder = InlineKeyboardBuilder()
        today = date.today()

        # Создаем кнопки на 8 дней вперед
        for i in range(8):
            target_date = today + timedelta(days=i)
            button_text = format_date_readable_manual(target_date)
            if i == 0:
                button_text = f"🔴 Сегодня ({button_text})"
            elif i == 1:
                button_text = f"🟡 Завтра ({button_text})"

            builder.add(
                types.InlineKeyboardButton(
                    text=button_text, callback_data=f"date_{target_date.isoformat()}"
                )
            )

        builder.add(
            types.InlineKeyboardButton(
                text="❌ Выход в главное меню", callback_data="cancel"
            )
        )
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def navigation_keyboard(selected_date: date) -> InlineKeyboardMarkup:
        """Клавиатура навигации по датам"""
        builder = InlineKeyboardBuilder()
        today = date.today()
        max_date = today + timedelta(days=13)  # 2 недели вперед

        left_enabled = selected_date > today
        right_enabled = selected_date < max_date
        adjust = 0

        # Левая стрелка (назад)
        if left_enabled:
            builder.add(
                types.InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"nav_{(selected_date - timedelta(days=1)).isoformat()}",
                )
            )
            adjust += 1

        # Правая стрелка (вперед)
        if right_enabled:
            builder.add(
                types.InlineKeyboardButton(
                    text="Вперед ➡️",
                    callback_data=f"nav_{(selected_date + timedelta(days=1)).isoformat()}",
                )
            )
            adjust += 1

        # Кнопка "Выбрать другую дату"
        builder.add(
            types.InlineKeyboardButton(
                text="📅 Выбрать дату", callback_data="choose_another_date"
            )
        )

        builder.add(
            types.InlineKeyboardButton(
                text="❌ Выход в главное меню", callback_data="cancel"
            )
        )

        builder.adjust(adjust, 1, 1)
        return builder.as_markup()

    @staticmethod
    def main_menu_keyboard() -> InlineKeyboardMarkup:
        """Клавиатура главного меню"""
        builder = InlineKeyboardBuilder()

        builder.add(
            types.InlineKeyboardButton(
                text="📅 Посмотреть расписание", callback_data="view_schedule"
            )
        )
        builder.add(
            types.InlineKeyboardButton(
                text="🔄 Сменить группу", callback_data="change_group"
            )
        )
        builder.add(
            types.InlineKeyboardButton(text="ℹ️ Помощь", callback_data="show_help")
        )

        builder.adjust(1)
        return builder.as_markup()
    
class NotificationManager:
    """Менеджер уведомлений студентам"""

    @staticmethod
    async def notify_students_about_comment(
        bot: Bot,
        lesson: Lesson,
        comment: "LessonComment"
    ) -> tuple[int, int]:
        """
        Отправить уведомления студентам о новом комментарии

        Args:
            bot: Экземпляр бота
            lesson: Занятие, к которому добавлен комментарий
            comment: Объект комментария

        Returns:
            tuple[int, int]: (успешно отправлено, неудачно)
        """
        import asyncio
        
        async with UnitOfWork() as uow:
            # Получаем всех студентов группы
            students = await uow.users.get_students_by_group(lesson.group_id)

            # Формируем сообщение
            lesson_date = lesson.start_datetime.strftime("%d.%m.%Y")
            lesson_time = lesson.start_datetime.strftime("%H:%M")

            message_text = (
                f"📢 <b>Новый комментарий к занятию</b>\n\n"
                f"📚 {lesson.subject.name}\n"
                f"📅 {lesson_date} в {lesson_time}\n"
                f"👨‍🏫 {lesson.teacher.name}\n"
                f"🚪 Аудитория {lesson.classroom}\n\n"
                f"💬 <b>Комментарий:</b>\n"
                f"<i>{comment.comment_text}</i>"
            )

            # Отправляем уведомления
            success_count = 0
            failed_count = 0

            for student in students:
                try:
                    await bot.send_message(
                        chat_id=student.user_id,
                        text=message_text
                    )
                    success_count += 1
                    await asyncio.sleep(0.05)  # Защита от rate limit
                except Exception as e:
                    print(f"⚠️ Не удалось отправить уведомление {student.user_id}: {e}")
                    failed_count += 1

            return success_count, failed_count



# ========== ОСНОВНОЙ КЛАСС БОТА ==========


class ScheduleBot:
    """Основной класс бота для управления расписанием"""

    def __init__(self):
        self.router = Router()
        self.cache = ScheduleImageCache()
        self.image_manager = ImageManager()
        self.message_manager = BotMessageManager(self.image_manager)
        self.keyboard_manager = KeyboardManager()

        self._register_handlers()

    def _register_handlers(self):
        """Регистрация всех обработчиков"""
        # Основные команды
        self.router.message(Command("start"))(self.start)
        self.router.message(Command("help"))(self.help_handler)
        self.router.message(Command("mygroup"))(self.my_group_handler)
        self.router.message(Command("stats"))(self.stats_handler)
        self.router.message(Command("clearcache"))(self.clear_cache_handler)
        self.router.message(Command("feedback"))(self.feedback_start)
        self.router.message(Command("prepareschedule"))(self.prepare_schedule_start)

        # Обработчики главного меню
        self.router.callback_query(StateFilter(None), F.data == "view_schedule")(
            self.view_schedule_handler
        )
        self.router.callback_query(StateFilter(None), F.data == "change_group")(
            self.change_group_handler
        )
        self.router.callback_query(StateFilter(None), F.data == "show_help")(
            self.help_from_menu_handler
        )
        self.router.callback_query(StateFilter(None), F.data == "main_menu")(
            self.main_menu
        )

            # Обработчики для преподавателей
        self.router.message(Command("register_teacher"))(self.teacher_register_start)
        self.router.message(TeacherRegistration.waiting_for_name)(self.teacher_register_confirm)
        self.router.callback_query(
            TeacherRegistration.waiting_for_confirmation, 
            F.data == "confirm_teacher"
        )(self.teacher_register_complete)

        self.router.message(Command("teacher_schedule"))(self.teacher_view_schedule)
        self.router.callback_query(
            TeacherSchedule.choosing_date, 
            F.data.startswith("teacher_date_")
        )(self.teacher_select_lesson)

        self.router.callback_query(
            TeacherSchedule.choosing_lesson, 
            F.data.startswith("lesson_")
        )(self.teacher_add_comment_start)
        self.router.message(TeacherSchedule.writing_comment)(self.teacher_add_comment_finish)

        # Обработчики состояний для выбора расписания
        self.router.callback_query(
            StateFilter(None), F.data.in_(self.keyboard_manager.VALID_FACULTIES)
        )(self.group_choose)
        self.router.callback_query(StateFilter(None), F.data == "back_to_faculty")(
            self.back_to_faculty
        )
        self.router.callback_query(
            GroupDateChoose.choosing_group,
            F.data.in_(self.keyboard_manager.VALID_GROUPS),
        )(self.date_choose)
        self.router.callback_query(
            GroupDateChoose.choosing_date, F.data.startswith("date_")
        )(self.answer)
        self.router.callback_query(
            GroupDateChoose.choosing_date, F.data.startswith("nav_")
        )(self.answer)
        self.router.callback_query(
            GroupDateChoose.choosing_date, F.data == "choose_another_date"
        )(self.choose_another_date)
        self.router.callback_query(StateFilter("*"), F.data == "cancel")(
            self.cancel_handler
        )

        # Обработчики для загрузки расписания (админ)
        self.router.callback_query(ScheduleFSM.choosing_group, F.data.startswith("g_"))(
            self.choose_group
        )
        self.router.callback_query(ScheduleFSM.choosing_month, F.data.startswith("m_"))(
            self.choose_month
        )
        self.router.message(ScheduleFSM.waiting_for_file, F.document)(
            self.schedule_file_uploaded
        )

        # Обработчик отзывов
        self.router.message(Feedback.waiting_for_text)(self.feedback_receive)

    # ========== КОМАНДЫ ==========

    async def start(
        self, message: types.Message, state: FSMContext, bot: Bot, db_user: User = None
    ):
        """Команда /start - приветствие и главное меню или выбор группы"""
        greeting = greeting_by_time()

        # Проверяем, есть ли у пользователя сохраненная группа
        if db_user and db_user.group:
            # Если группа есть - показываем главное меню
            response = (
                f"{greeting}, {message.from_user.first_name}! 👋\n\n"
                f"Рад снова вас видеть! Ваша группа: <b>{db_user.group.group_name}</b>\n\n"
                f"Что вы хотите сделать?"
            )
            inline_keyboard = self.keyboard_manager.main_menu_keyboard()
        else:
            # Если группы нет - предлагаем выбрать
            response = (
                f"{greeting}, {message.from_user.first_name}! 👋\n\n"
                f"Этот бот создан, чтобы помочь студентам всегда иметь под рукой актуальное расписание.\n\n"
                f"Чтобы начать, выберите свое направление из списка!"
            )

            inline_keyboard = self.keyboard_manager.faculties_choose_keyboard()

        await self.message_manager.send_bot_message(
            message, response, inline_keyboard, bot, state
        )
        await state.clear()

    async def help_handler(self, message: types.Message, state: FSMContext, bot: Bot):
        """Команда /help - справка"""
        greeting = greeting_by_time()
        answer = (
            f"{greeting}! 👋\n\n"
            f"<b>Этот бот помогает узнавать расписание занятий.</b>\n\n"
            f"<b>Доступные команды:</b>\n"
            f"• /start - начать работу с ботом\n"
            f"• /mygroup - посмотреть/изменить свою группу\n"
            # f"• /stats - статистика использования бота\n"
            f"• /feedback - отправить отзыв или предложение\n"
            f"• /help - показать эту справку\n\n"
            f"<i>Если возникли проблемы, попробуйте перезапустить бота командой /start</i>"
        )
        await self.message_manager.send_bot_message(message, answer, None, bot, state)

    async def my_group_handler(
        self, message: types.Message, state: FSMContext, bot: Bot, db_user: User = None
    ):
        """Команда /mygroup - показать/изменить группу"""
        if db_user and db_user.group:
            response = (
                f"Ваша текущая группа: <b>{db_user.group.group_name}</b>\n\n"
                f"Чтобы изменить группу, выберите свое направление:"
            )
        else:
            response = "У вас еще не выбрана группа.\n\nВыберите свое направление:"

        inline_keyboard = self.keyboard_manager.faculties_choose_keyboard()
        await self.message_manager.send_bot_message(
            message, response, inline_keyboard, bot, state
        )
        await state.clear()

    async def stats_handler(self, message: types.Message, state: FSMContext, bot: Bot):
        """Команда /stats - статистика бота"""
        async with UnitOfWork() as uow:
            total_users = await uow.users.count_total()
            active_week = await uow.users.count_active(days=7)
            active_day = await uow.users.count_active(days=1)

            # Получаем топ типов запросов
            request_stats = await uow.user_requests.count_by_type(days=7)

        response = (
            f"📊 <b>Статистика бота:</b>\n\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"🟢 Активных сегодня: {active_day}\n"
            f"📅 Активных за неделю: {active_week}\n\n"
        )

        if request_stats:
            response += "<b>Популярные действия за неделю:</b>\n"
            for req_type, count in request_stats[:5]:
                response += f"• {req_type}: {count}\n"

        await message.answer(response)

    async def clear_cache_handler(self, message: types.Message):
        """Команда /clearcache - очистка кэша (может быть полезно для админа)"""
        old_size = self.cache.clear()
        await message.answer(f"🗑 Кэш очищен! Удалено изображений: {old_size}")

    async def feedback_start(self, message: types.Message, state: FSMContext, bot: Bot):
        """Команда /feedback - начало сбора отзыва"""
        response = (
            "💬 <b>Обратная связь</b>\n\n"
            "Мы стараемся улучшать бот! Если у вас есть:\n"
            "• Предложения по улучшению\n"
            "• Обнаруженные ошибки\n"
            "• Пожелания по функциям\n\n"
            "Напишите нам сообщение, и мы обязательно его рассмотрим! 📝"
        )
        await self.message_manager.send_bot_message(message, response, None, bot, state)
        await state.set_state(Feedback.waiting_for_text)

    async def feedback_receive(
        self, message: types.Message, state: FSMContext, bot: Bot, db_user: User = None
    ):
        """Получение отзыва от пользователя"""
        text = message.text

        # Формируем информацию о пользователе
        user_info = (
            f"@{message.from_user.username}"
            if message.from_user.username
            else f"ID: {message.from_user.id}"
        )
        if db_user and db_user.group:
            user_info += f" | Группа: {db_user.group.group_name}"

        # Отправляем админу
        try:
            await bot.send_message(
                ADMIN_ID,
                f"📬 <b>Новый отзыв</b>\n\n"
                f"От: {user_info}\n"
                f"Имя: {message.from_user.first_name}\n\n"
                f"<i>{text}</i>",
            )
        except Exception as e:
            print(f"⚠️ Ошибка отправки отзыва админу: {e}")

        # Ответ пользователю
        await message.answer(
            "✅ Спасибо за ваш отзыв!\n\n"
            "Мы обязательно его рассмотрим и постараемся сделать бот еще лучше! 🚀"
        )
        await state.clear()

    # ========== РЕГИСТРАЦИЯ ПРЕПОДАВАТЕЛЯ ==========

    async def teacher_register_start(
        self, message: types.Message, state: FSMContext, bot: Bot, db_user: User = None
    ):
        """Начало регистрации преподавателя"""
        if db_user and db_user.user_type == "teacher" and db_user.teacher_id:
            status = "✅ Верифицирован" if db_user.is_verified else "⏳ Ожидает верификации"
            await message.answer(
                f"✅ Вы уже зарегистрированы как преподаватель\n\n"
                f"Имя: {db_user.teacher.name}\n"
                f"Статус: {status}"
            )
            return

        response = (
            "👨‍🏫 <b>Регистрация преподавателя</b>\n\n"
            "Введите ваше ФИО точно так, как оно указано в расписании.\n\n"
            "<i>Например: Иванов Иван Иванович</i>"
        )
        await message.answer(response)
        await state.set_state(TeacherRegistration.waiting_for_name)

    async def teacher_register_confirm(
        self, message: types.Message, state: FSMContext, bot: Bot
    ):
        """Подтверждение найденного преподавателя"""
        teacher_name = message.text.strip()

        async with UnitOfWork() as uow:
            teacher = await uow.teachers.get_by_name(teacher_name)

            if not teacher:
                await message.answer(
                    "❌ Преподаватель с таким ФИО не найден в базе.\n\n"
                    "Убедитесь, что вы ввели имя точно как в расписании, "
                    "или обратитесь к администратору."
                )
                return

            # Проверяем, не привязан ли уже этот Teacher к другому User
            result = await uow.session.execute(
                select(User).where(User.teacher_id == teacher.teacher_id)
            )
            existing_user = result.scalar_one_or_none()

            if existing_user:
                await message.answer(
                    "⚠️ Этот преподаватель уже зарегистрирован другим пользователем.\n\n"
                    "Если это ошибка, обратитесь к администратору."
                )
                return

            await state.update_data(
                teacher_id=teacher.teacher_id,
                teacher_name=teacher.name
            )

        builder = InlineKeyboardBuilder()
        builder.add(
            types.InlineKeyboardButton(
                text="✅ Да, это я", callback_data="confirm_teacher"
            )
        )
        builder.add(
            types.InlineKeyboardButton(
                text="❌ Отмена", callback_data="cancel"
            )
        )
        builder.adjust(1)

        await message.answer(
            f"Найден преподаватель:\n\n"
            f"<b>{teacher.name}</b>\n\n"
            f"Это вы?",
            reply_markup=builder.as_markup()
        )
        await state.set_state(TeacherRegistration.waiting_for_confirmation)

    async def teacher_register_complete(
        self, callback: types.CallbackQuery, state: FSMContext, bot: Bot, db_user: User = None
    ):
        """Завершение регистрации преподавателя"""
        data = await state.get_data()
        teacher_id = data["teacher_id"]
        teacher_name = data["teacher_name"]

        async with UnitOfWork() as uow:
            # Обновляем пользователя
            await uow.users.update(
                user_id=callback.from_user.id,
                user_type="teacher",
                teacher_id=teacher_id,
                is_verified=False  # Требуется верификация админом
            )
            await uow.commit()

        # Уведомляем админа
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🆕 <b>Новая регистрация преподавателя</b>\n\n"
                f"ФИО: {teacher_name}\n"
                f"Telegram: @{callback.from_user.username or 'нет username'}\n"
                f"ID: {callback.from_user.id}\n\n"
                f"Требуется верификация!"
            )
        except Exception as e:
            print(f"⚠️ Не удалось уведомить админа: {e}")

        await callback.message.edit_text(
            "✅ <b>Регистрация успешна!</b>\n\n"
            f"Вы зарегистрированы как: {teacher_name}\n\n"
            "⏳ Ожидайте верификации администратором.\n"
            "После одобрения вам станет доступен функционал преподавателя."
        )
        await state.clear()
        await callback.answer()

    # ========== РАСПИСАНИЕ ПРЕПОДАВАТЕЛЯ ==========

    async def teacher_view_schedule(
        self, message: types.Message, state: FSMContext, bot: Bot, db_user: User = None
    ):
        """Просмотр расписания преподавателя"""
        if not db_user or db_user.user_type != "teacher" or not db_user.teacher_id:
            await message.answer(
                "⚠️ Эта команда доступна только преподавателям.\n\n"
                "Используйте /register_teacher для регистрации."
            )
            return

        if not db_user.is_verified:
            await message.answer(
                "⏳ Ваш аккаунт преподавателя ожидает верификации администратором."
            )
            return

        # Клавиатура выбора даты (7 дней вперед)
        builder = InlineKeyboardBuilder()
        today = date.today()

        for i in range(7):
            target_date = today + timedelta(days=i)
            button_text = format_date_readable_manual(target_date)
            if i == 0:
                button_text = f"🔴 Сегодня ({button_text})"
            elif i == 1:
                button_text = f"🟡 Завтра ({button_text})"

            builder.add(
                types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"teacher_date_{target_date.isoformat()}"
                )
            )

        builder.adjust(1)

        await self.message_manager.send_bot_message(
            message,
            "📅 Выберите дату для просмотра ваших занятий:",
            builder.as_markup(),
            bot,
            state
        )
        await state.set_state(TeacherSchedule.choosing_date)

    async def teacher_select_lesson(
        self, callback: types.CallbackQuery, state: FSMContext, bot: Bot, db_user: User = None
    ):
        """Выбор занятия для добавления комментария"""
        date_str = callback.data.split("_")[2]
        target_date = date.fromisoformat(date_str)

        async with UnitOfWork() as uow:
            lessons = await uow.teachers.get_lessons_for_date(
                db_user.teacher_id, target_date
            )

        if not lessons:
            await callback.message.edit_text(
                f"✨ У вас нет занятий {format_date_readable_manual(target_date)}"
            )
            await state.clear()
            await callback.answer()
            return

        # Формируем список занятий с кнопками
        builder = InlineKeyboardBuilder()
        response = f"📚 <b>Ваши занятия {format_date_readable_manual(target_date)}:</b>\n\n"

        for idx, lesson in enumerate(lessons, 1):
            lesson_time = lesson.start_datetime.strftime("%H:%M")
            response += (
                f"{idx}. {lesson_time} - {lesson.subject.name}\n"
                f"   Группа: {lesson.group.group_name}\n"
                f"   Аудитория: {lesson.classroom}\n\n"
            )

            builder.add(
                types.InlineKeyboardButton(
                    text=f"{idx}. {lesson_time} {lesson.subject.name}",
                    callback_data=f"lesson_{lesson.lesson_id}"
                )
            )

        builder.add(
            types.InlineKeyboardButton(
                text="❌ Отмена", callback_data="cancel"
            )
        )
        builder.adjust(1)

        response += "Выберите занятие для добавления комментария:"

        await callback.message.edit_text(response, reply_markup=builder.as_markup())
        await state.update_data(selected_date=target_date)
        await state.set_state(TeacherSchedule.choosing_lesson)
        await callback.answer()


        async def teacher_add_comment_start(
        self, callback: types.CallbackQuery, state: FSMContext, bot: Bot
    ):
        """Начало написания комментария"""
        lesson_id = int(callback.data.split("_")[1])
        await state.update_data(lesson_id=lesson_id)

        async with UnitOfWork() as uow:
            lesson = await uow.lessons.get_by_id(lesson_id)

        response = (
            f"✍️ <b>Добавление комментария</b>\n\n"
            f"📚 {lesson.subject.name}\n"
            f"👥 Группа: {lesson.group.group_name}\n"
            f"🕐 {lesson.start_datetime.strftime('%H:%M')}\n\n"
            f"Напишите комментарий для студентов:"
        )

        await callback.message.edit_text(response)
        await state.set_state(TeacherSchedule.writing_comment)
        await callback.answer()

    async def teacher_add_comment_finish(
        self, message: types.Message, state: FSMContext, bot: Bot, db_user: User = None
    ):
        """Сохранение комментария и отправка уведомлений"""
        data = await state.get_data()
        lesson_id = data["lesson_id"]
        comment_text = message.text.strip()

        async with UnitOfWork() as uow:
            # Создаем комментарий
            comment = await uow.lesson_comments.create(
                lesson_id=lesson_id,
                teacher_id=db_user.teacher_id,
                comment_text=comment_text
            )
            await uow.commit()

            # Получаем занятие с relations
            lesson = await uow.lessons.get_by_id(lesson_id)

        # Отправляем уведомления студентам
        notification_manager = NotificationManager()
        success, failed = await notification_manager.notify_students_about_comment(
            bot, lesson, comment
        )

        await message.answer(
            f"✅ <b>Комментарий добавлен!</b>\n\n"
            f"📚 {lesson.subject.name}\n"
            f"👥 Группа: {lesson.group.group_name}\n\n"
            f"📨 Уведомления отправлены: {success}\n"
            f"{('⚠️ Не удалось отправить: ' + str(failed)) if failed > 0 else ''}"
        )
        await state.clear()



    # ========== ОБРАБОТЧИКИ ГЛАВНОГО МЕНЮ ==========

    async def main_menu(
        self,
        callback: types.CallbackQuery,
        state: FSMContext,
        bot: Bot,
        db_user: User = None,
    ):
        """Показать главное меню"""
        greeting = greeting_by_time()

        if db_user and db_user.group:
            response = (
                f"{greeting}! 👋\n\n"
                f"Ваша группа: <b>{db_user.group.group_name}</b>\n\n"
                f"Что вы хотите сделать?"
            )
        else:
            response = "Выберите свое направление:"
            inline_keyboard = self.keyboard_manager.faculties_choose_keyboard()
            await self.message_manager.send_bot_message(
                callback, response, inline_keyboard, bot, state
            )
            await callback.answer()
            return

        inline_keyboard = self.keyboard_manager.main_menu_keyboard()
        await self.message_manager.send_bot_message(
            callback, response, inline_keyboard, bot, state
        )
        await callback.answer()

    async def view_schedule_handler(
        self,
        callback: types.CallbackQuery,
        state: FSMContext,
        bot: Bot,
        db_user: User = None,
    ):
        """Начать просмотр расписания из главного меню"""
        if not db_user or not db_user.group:
            await callback.answer("⚠️ Сначала выберите группу", show_alert=True)
            return

        # Сохраняем группу в состояние
        await state.update_data(group=db_user.group.group_name)

        response = "📅 Выберите дату, на которую хотите узнать расписание:"
        await self.message_manager.send_bot_message(
            callback, response, self.keyboard_manager.date_choose_keyboard(), bot, state
        )
        await state.set_state(GroupDateChoose.choosing_date)
        await callback.answer()

    async def change_group_handler(
        self, callback: types.CallbackQuery, state: FSMContext, bot: Bot
    ):
        """Изменить группу из главного меню"""
        response = "Выберите свое направление:"
        inline_keyboard = self.keyboard_manager.faculties_choose_keyboard()

        await self.message_manager.send_bot_message(
            callback, response, inline_keyboard, bot, state
        )
        await state.clear()
        await callback.answer()

    async def help_from_menu_handler(
        self, callback: types.CallbackQuery, state: FSMContext, bot: Bot
    ):
        """Показать справку из меню"""
        answer = (
            "<b>📖 Справка</b>\n\n"
            f"<b>Доступные команды:</b>\n"
            f"• /start - главное меню\n"
            f"• /mygroup - посмотреть/изменить свою группу\n"
            f"• /feedback - отправить отзыв или предложение\n"
            f"• /help - показать эту справку\n\n"
            f"<b>Возможности бота:</b>\n"
            f"• Просмотр расписания на любую дату\n"
            f"• Навигация по датам\n"
            f"• Автоматическое сохранение вашей группы\n\n"
            f"<i>Если возникли проблемы, используйте /start</i>"
        )

        # Добавляем кнопку "Назад в меню"
        builder = InlineKeyboardBuilder()
        builder.add(
            types.InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="main_menu")
        )

        await self.message_manager.send_bot_message(
            callback, answer, builder.as_markup(), bot, state
        )
        await callback.answer()

    # ========== ОБРАБОТЧИКИ ВЫБОРА РАСПИСАНИЯ ==========

    async def group_choose(
        self, callback: types.CallbackQuery, state: FSMContext, bot: Bot
    ):
        """Выбор группы после выбора факультета"""
        faculty = callback.data
        response = "Отлично! Теперь выберите свою группу:"
        inline_keyboard = self.keyboard_manager.groups_choose_keyboard(faculty)

        await self.message_manager.send_bot_message(
            callback, response, inline_keyboard, bot, state
        )
        await state.set_state(GroupDateChoose.choosing_group)
        await state.update_data(faculty=faculty)
        await callback.answer()

    async def back_to_faculty(
        self, callback: types.CallbackQuery, state: FSMContext, bot: Bot
    ):
        """Возврат к выбору факультета"""
        response = "Выберите свое направление:"
        inline_keyboard = self.keyboard_manager.faculties_choose_keyboard()

        await self.message_manager.send_bot_message(
            callback, response, inline_keyboard, bot, state
        )
        await state.clear()
        await callback.answer()

    async def date_choose(
        self,
        callback: types.CallbackQuery,
        state: FSMContext,
        bot: Bot,
        db_user: User = None,
    ):
        """Выбор даты после выбора группы"""
        if callback.data == "cancel":
            await self.cancel_handler(callback, state, bot)
            return

        group_name = callback.data

        # Сохраняем группу в профиле пользователя
        if db_user:
            async with UnitOfWork() as uow:
                group = await uow.groups.get_by_name(group_name)
                if group:
                    await uow.users.update_group(db_user.user_id, group.group_id)
                    await uow.commit()

        await state.update_data(group=group_name)
        response = "📅 Теперь выберите дату, на которую хотите узнать расписание:"

        await self.message_manager.send_bot_message(
            callback, response, self.keyboard_manager.date_choose_keyboard(), bot, state
        )
        await state.set_state(GroupDateChoose.choosing_date)
        await callback.answer()

    async def answer(self, callback: types.CallbackQuery, state: FSMContext, bot: Bot):
        """Отображение расписания на выбранную дату"""
        if callback.data == "cancel":
            await self.cancel_handler(callback, state, bot)
            return

        user_data = await state.get_data()
        group_name = user_data.get("group")

        if not group_name:
            await callback.answer("⚠️ Ошибка: группа не выбрана", show_alert=True)
            return

        # Определяем дату
        if callback.data.startswith("date_"):
            date_string = callback.data.split("_")[1]
            selected_date = date.fromisoformat(date_string)
        elif callback.data.startswith("nav_"):
            date_string = callback.data.split("_")[1]
            selected_date = date.fromisoformat(date_string)
        else:
            await callback.answer()
            return

        # Получаем изображение расписания
        try:
            img, caption = await self.image_manager.get_schedule_image(
                selected_date, group_name, self.cache
            )

            photo_file = BufferedInputFile(
                file=img.getvalue(),
                filename="schedule.png",
            )

            kb = self.keyboard_manager.navigation_keyboard(selected_date)

            # Удаляем предыдущее сообщение
            await self.message_manager.delete_last_bot_message(
                state, bot, callback.message.chat.id
            )

            # Отправляем расписание
            sent = await callback.message.answer_photo(
                photo=photo_file,
                caption=caption,
                reply_markup=kb,
            )

            await state.update_data(last_message_id=sent.message_id)
            await state.update_data(selected_date=selected_date)
            await callback.answer()

        except TelegramBadRequest as e:
            if "query is too old" in str(e).lower():
                pass
            else:
                raise

        except Exception as e:
            print(f"⚠️ Ошибка генерации изображения: {e}")
            # Фолбэк - отправляем текстовое расписание
            text = await create_schedule_text(selected_date, group_name)
            kb = self.keyboard_manager.navigation_keyboard(selected_date)
            await callback.message.answer(text, reply_markup=kb)
            await callback.answer()

    async def choose_another_date(
        self, callback: types.CallbackQuery, state: FSMContext, bot: Bot
    ):
        """Выбор другой даты"""
        response = "📅 Выберите дату:"
        await self.message_manager.send_bot_message(
            callback, response, self.keyboard_manager.date_choose_keyboard(), bot, state
        )
        await callback.answer()

    async def cancel_handler(
        self,
        callback: types.CallbackQuery,
        state: FSMContext,
        bot: Bot,
        db_user: User = None,
    ):
        """Отмена и возврат в главное меню"""
        await state.clear()

        if db_user and db_user.group:
            # Если группа есть - возвращаем в главное меню
            response = (
                f"🏠 Главное меню\n\n"
                f"Ваша группа: <b>{db_user.group.group_name}</b>\n\n"
                f"Что вы хотите сделать?"
            )
            inline_keyboard = self.keyboard_manager.main_menu_keyboard()
        else:
            # Если группы нет - предлагаем выбрать
            response = "🏠 Главное меню\n\n" "Чтобы начать, выберите свое направление!"
            inline_keyboard = self.keyboard_manager.faculties_choose_keyboard()

        await self.message_manager.send_bot_message(
            callback, response, inline_keyboard, bot, state
        )
        await callback.answer()

    # ========== ЗАГРУЗКА РАСПИСАНИЯ (АДМИН) ==========

    async def prepare_schedule_start(
        self, message: types.Message, state: FSMContext, bot: Bot
    ):
        """Начало загрузки расписания (только для админа)"""
        # Проверка прав админа
        if str(message.from_user.id) != ADMIN_ID:
            await message.answer("⛔️ У вас нет прав для выполнения этой команды")
            return

        async with UnitOfWork() as uow:
            groups = await uow.groups.get_all()

        builder = InlineKeyboardBuilder()
        for group in groups:
            builder.add(
                types.InlineKeyboardButton(
                    text=group.group_name, callback_data=f"g_{group.group_id}"
                )
            )
        builder.adjust(4)
        kb = builder.as_markup()

        await self.message_manager.send_bot_message(
            message, "Выберите группу:", kb, bot, state
        )
        await state.set_state(ScheduleFSM.choosing_group)

    async def choose_group(
        self, callback: types.CallbackQuery, state: FSMContext, bot: Bot
    ):
        """Выбор группы для загрузки расписания"""
        group_id = int(callback.data[2:])

        async with UnitOfWork() as uow:
            group = await uow.groups.get_by_id(group_id)

        await state.update_data(group_id=group_id, group_name=group.group_name)

        # Клавиатура месяца
        now = datetime.now()
        current_month = now.strftime("%B")
        next_month_num = (now.month % 12) + 1
        next_month = datetime(2000, next_month_num, 1).strftime("%B")

        builder = InlineKeyboardBuilder()
        builder.add(
            types.InlineKeyboardButton(
                text=f"Текущий ({current_month})", callback_data=f"m_{now.month}"
            ),
            types.InlineKeyboardButton(
                text=f"Следующий ({next_month})", callback_data=f"m_{next_month_num}"
            ),
        )
        builder.adjust(2)

        await self.message_manager.send_bot_message(
            callback, "Выберите месяц:", builder.as_markup(), bot, state
        )
        await state.set_state(ScheduleFSM.choosing_month)
        await callback.answer()

    async def choose_month(
        self, callback: types.CallbackQuery, state: FSMContext, bot: Bot
    ):
        """Выбор месяца для загрузки расписания"""
        month_num = int(callback.data[2:])
        month_name = datetime(2000, month_num, 1).strftime("%B")
        await state.update_data(month_num=month_num, month_name=month_name)

        await self.message_manager.send_bot_message(
            callback,
            f"📎 Загрузите файл .doc/.docx с расписанием для месяца <b>{month_name}</b>",
            None,
            bot,
            state,
        )
        await state.set_state(ScheduleFSM.waiting_for_file)
        await callback.answer()

    async def schedule_file_uploaded(
        self, message: types.Message, state: FSMContext, bot: Bot
    ):
        """Обработка загруженного файла расписания"""
        data = await state.get_data()
        group_name = data["group_name"]
        month_name = data["month_name"]

        file_extension = message.document.file_name.split(".")[-1].lower()
        file_name = message.document.file_name

        os.makedirs(f"files/{month_name}", exist_ok=True)
        save_path = f"files/{month_name}/{file_name}"

        # Скачиваем файл
        await bot.download(message.document, destination=save_path)

        # Конвертируем .doc в .docx если нужно
        if file_extension == "doc":
            convert_doc_to_docx(save_path)
            save_path = save_path.rsplit(".", 1)[0] + ".docx"

        try:
            # Парсим расписание
            lessons = parse_docx_schedule(save_path, group_name)

            # Импортируем в БД асинхронно
            async with UnitOfWork() as uow:
                await import_schedule_to_db_async(lessons, uow)
                await uow.commit()

            # Очищаем кэш для этой группы
            self.cache.clear_group(group_name)

            await message.answer(
                f"✅ <b>Расписание успешно загружено!</b>\n\n"
                f"Группа: {group_name}\n"
                f"Месяц: {month_name}\n"
                f"Занятий: {len(lessons)}\n\n"
                f"Кэш для группы очищен."
            )
        except Exception as e:
            await message.answer(f"❌ Ошибка при обработке файла: {e}")
            print(f"⚠️ Ошибка импорта расписания: {e}")

        await state.clear()


# ========== ЭКСПОРТ ==========

# Создание экземпляра бота для использования в основном проекте
schedule_bot = ScheduleBot()
router = schedule_bot.router
