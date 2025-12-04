from aiogram import types, F, Router, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
import datetime
import os
from pathlib import Path
import hashlib
from io import BytesIO
from typing import Dict, Tuple, Optional

from dotenv import load_dotenv

from test_parse import convert_doc_to_docx, parse_docx_schedule, import_schedule_to_db
from utils import create_answer, format_date_readable_manual, greeting_by_time
from create_database import session, Group

from jinja_renderer import render_html, html_to_image

load_dotenv()

ADMIN_ID = os.getenv('ADMIN_ID')


class ScheduleImageCache:
    """Класс для управления кэшем изображений расписания"""

    def __init__(self, max_size: int = 100, ttl_hours: int = 24):
        self._cache: Dict[str, Tuple[BytesIO, str, datetime.datetime]] = {}
        self.max_size = max_size
        self.ttl_hours = ttl_hours

    def _generate_cache_key(self, selected_date: datetime.date, group: str) -> str:
        """Генерирует ключ для кэша на основе даты и группы"""
        date_str = selected_date.isoformat()
        return hashlib.md5(f"{date_str}_{group}".encode()).hexdigest()

    def get(self, selected_date: datetime.date, group: str) -> Optional[Tuple[BytesIO, str]]:
        """Получить расписание из кэша если оно есть и не устарело"""
        cache_key = self._generate_cache_key(selected_date, group)

        if cache_key in self._cache:
            image_data, caption, timestamp = self._cache[cache_key]

            # Проверяем не устарело ли изображение
            if datetime.datetime.now() - timestamp < datetime.timedelta(hours=self.ttl_hours):
                return image_data, caption

        return None

    def set(self, selected_date: datetime.date, group: str, image_data: BytesIO, caption: str):
        """Сохранить расписание в кэш"""
        cache_key = self._generate_cache_key(selected_date, group)

        # Очищаем кэш если он превысил максимальный размер
        if len(self._cache) >= self.max_size:
            # Удаляем самые старые записи
            oldest_keys = sorted(
                self._cache.keys(),
                key=lambda k: self._cache[k][2]
            )[:self.max_size // 4]  # Удаляем 25% самых старых записей

            for key in oldest_keys:
                del self._cache[key]

        # Сохраняем новую запись
        self._cache[cache_key] = (image_data, caption, datetime.datetime.now())

    def clear(self) -> int:
        """Очистить весь кэш и вернуть количество удаленных элементов"""
        old_size = len(self._cache)
        self._cache.clear()
        return old_size

    def clear_group(self, group_name: str):
        """Очистить кэш для конкретной группы"""
        keys_to_remove = [
            key for key in self._cache.keys()
            if key.endswith(f"_{group_name}")
        ]
        for key in keys_to_remove:
            del self._cache[key]


class BotMessageManager:
    """Класс для управления отправкой сообщений бота"""

    def __init__(self, image_manager: 'ImageManager'):
        self.image_manager = image_manager

    async def send_bot_message(
            self,
            target: types.Message | types.CallbackQuery,
            text: str,
            reply_markup: InlineKeyboardMarkup = None,
            bot: Bot = None,
            state: FSMContext = None,
            with_image: bool = True
    ) -> types.Message:
        """
        Универсальная функция для отправки сообщений бота с управлением историей
        """
        chat_id = target.message.chat.id if isinstance(target, types.CallbackQuery) else target.chat.id
        message_to_edit = target.message if isinstance(target, types.CallbackQuery) else None

        # Удаляем предыдущее сообщение бота если есть
        await self.delete_last_bot_message(state, bot, chat_id)

        try:
            if with_image:
                file_id = await self.image_manager.get_or_upload_middle_image(bot, chat_id)
                if file_id:
                    if message_to_edit:
                        # Пытаемся отредактировать существующее сообщение
                        try:
                            sent = await message_to_edit.edit_media(
                                media=types.InputMediaPhoto(media=file_id, caption=text),
                                reply_markup=reply_markup
                            )
                            await state.update_data(last_message_id=sent.message_id)
                            return sent
                        except Exception:
                            # Если редактирование не удалось, отправляем новое
                            pass

                    # Отправляем новое сообщение с фото
                    sent = await bot.send_photo(
                        chat_id,
                        file_id,
                        caption=text,
                        reply_markup=reply_markup
                    )
                else:
                    # Если картинка недоступна, отправляем текстовое сообщение
                    if message_to_edit:
                        try:
                            sent = await message_to_edit.edit_text(text, reply_markup=reply_markup)
                            await state.update_data(last_message_id=sent.message_id)
                            return sent
                        except Exception:
                            pass

                    sent = await bot.send_message(chat_id, text, reply_markup=reply_markup)
            else:
                # Отправка без картинки (для расписания и т.д.)
                if message_to_edit:
                    try:
                        sent = await message_to_edit.edit_text(text, reply_markup=reply_markup)
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
            print(f"Ошибка отправки сообщения: {e}")
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
                # Сообщение уже удалено или недоступно - игнорируем ошибку
                pass


class ImageManager:
    """Класс для управления изображениями"""

    def __init__(self):
        self.middle_image_file_id = None

    async def get_or_upload_middle_image(self, bot: Bot, chat_id: int) -> str:
        """Получить file_id картинки middle.svg, при необходимости загрузить ее"""
        if self.middle_image_file_id:
            return self.middle_image_file_id

        image_path = Path("image/middle.png")
        if not image_path.exists():
            # Если файл не существует, создаем простую заглушку
            image_path.parent.mkdir(exist_ok=True)
            # Можно создать простой SVG или использовать другую картинку
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
            return self.middle_image_file_id
        except Exception as e:
            print(f"Ошибка загрузки картинки: {e}")
            return None

    async def get_schedule_image(self, selected_date: datetime.date, group: str, cache: ScheduleImageCache) -> Tuple[
        BytesIO, str]:
        """Получить изображение расписания (из кэша или сгенерировать новое)"""
        # Пытаемся получить из кэша
        cached = cache.get(selected_date, group)
        if cached:
            return cached

        # Генерируем новое изображение
        html = render_html(selected_date, group)
        img = await html_to_image(html)
        caption = f"Расписание на {format_date_readable_manual(selected_date)}"

        # Сохраняем в кэш
        cache.set(selected_date, group, img, caption)

        return img, caption


class KeyboardManager:
    """Класс для управления клавиатурами"""

    VALID_FACULTIES = {"Экономика", "Менеджмент", "ГМУ", "Юриспруденция"}
    VALID_GROUPS = {"Э-42", "Э-43", "Э-44", "М-42", "М-43", "М-44", "ГМУ-41", "ГМУ-42", "ГМУ-43", "ГМУ-44", "Ю-41",
                    "Ю-42", "Ю-43", "Ю-44"}

    @staticmethod
    def faculties_choose_keyboard() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for faculty in KeyboardManager.VALID_FACULTIES:
            builder.add(types.InlineKeyboardButton(text=faculty, callback_data=faculty))

        builder.add(types.InlineKeyboardButton(
            text="Выход в главное меню",
            callback_data="cancel"
        ))
        builder.adjust(2)
        return builder.as_markup()

    @staticmethod
    def groups_choose_keyboard(path) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        if path == "Экономика":
            builder.add(types.InlineKeyboardButton(
                text="Э-42",
                callback_data="Э-42"
            ),
                types.InlineKeyboardButton(
                    text="Э-43",
                    callback_data="Э-43"
                ),
                types.InlineKeyboardButton(
                    text="Э-44",
                    callback_data="Э-44"
                ))
        elif path == "Менеджмент":
            builder.add(types.InlineKeyboardButton(
                text="М-42",
                callback_data="М-42"
            ),
                types.InlineKeyboardButton(
                    text="М-43",
                    callback_data="М-43"
                ),
                types.InlineKeyboardButton(
                    text="М-44",
                    callback_data="М-44"
                ))
        elif path == "ГМУ":
            builder.add(types.InlineKeyboardButton(
                text="ГМУ-41",
                callback_data="ГМУ-41"
            ),
                types.InlineKeyboardButton(
                    text="ГМУ-42",
                    callback_data="ГМУ-42"
                ),
                types.InlineKeyboardButton(
                    text="ГМУ-43",
                    callback_data="ГМУ-43"
                ),
                types.InlineKeyboardButton(
                    text="ГМУ-44",
                    callback_data="ГМУ-44"
                ))
        elif path == "Юриспруденция":
            builder.add(types.InlineKeyboardButton(
                text="Ю-41",
                callback_data="Ю-41"
            ),
                types.InlineKeyboardButton(
                    text="Ю-42",
                    callback_data="Ю-42"
                ),
                types.InlineKeyboardButton(
                    text="Ю-43",
                    callback_data="Ю-43"
                ),
                types.InlineKeyboardButton(
                    text="Ю-44",
                    callback_data="Ю-44"
                ))
        builder.add(types.InlineKeyboardButton(
            text="Выход в главное меню",
            callback_data="cancel"
        ))
        builder.adjust(2)
        return builder.as_markup()

    @staticmethod
    def date_choose_keyboard() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        today = datetime.date.today()

        # Создаем кнопки на 8 дней вперед, включая сегодня
        for i in range(8):
            delta = datetime.timedelta(days=i)
            target_date = today + delta

            builder.add(types.InlineKeyboardButton(
                text=format_date_readable_manual(target_date),
                callback_data=f"date_{target_date.isoformat()}"
            ))
        builder.add(types.InlineKeyboardButton(
            text="Выход в главное меню",
            callback_data="cancel"
        ))
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def navigation_keyboard(selected_date: datetime.date) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        today = datetime.date.today()
        max_date = today + datetime.timedelta(days=13)  # с учетом today — 2 недели
        left_enabled = selected_date > today
        right_enabled = selected_date < max_date
        adjust = 0

        # Левая стрелка (назад)
        if left_enabled:
            builder.add(types.InlineKeyboardButton(
                text="⬅️",
                callback_data=f"nav_{(selected_date - datetime.timedelta(days=1)).isoformat()}"
            ))
            adjust += 1

        # Правая стрелка (вперед)
        if right_enabled:
            builder.add(types.InlineKeyboardButton(
                text="➡️",
                callback_data=f"nav_{(selected_date + datetime.timedelta(days=1)).isoformat()}"
            ))
            adjust += 1

        builder.add(types.InlineKeyboardButton(
            text="Выход в главное меню",
            callback_data="cancel"
        ))
        builder.adjust(adjust)
        return builder.as_markup()


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
        self.router.message(Command("clearcache"))(self.clear_cache_handler)
        self.router.message(Command("feedback"))(self.feedback_start)
        self.router.message(Command("prepareschedule"))(self.prepare_schedule_start)

        # Обработчики состояний
        self.router.callback_query(StateFilter(None), F.data.in_(self.keyboard_manager.VALID_FACULTIES))(
            self.group_choose)
        self.router.callback_query(GroupDateChoose.choosing_group, F.data.in_(self.keyboard_manager.VALID_GROUPS))(
            self.date_choose)
        self.router.callback_query(GroupDateChoose.choosing_date, F.data)(self.answer)
        self.router.callback_query(StateFilter("*"), F.data == "cancel")(self.cancel_handler)

        # Обработчики FSM
        self.router.callback_query(ScheduleFSM.choosing_group, F.data.startswith("g_"))(self.choose_group)
        self.router.callback_query(ScheduleFSM.choosing_month, F.data.startswith("m_"))(self.choose_month)
        self.router.message(ScheduleFSM.waiting_for_file, F.document)(self.schedule_file_uploaded)
        self.router.message(Feedback.waiting_for_text)(self.feedback_receive)

    async def start(self, message: types.Message, state: FSMContext, bot: Bot):
        greeting = greeting_by_time()
        response = f"{greeting}\nЭтот бот был создан, чтоб помочь студентам всегда иметь возможность легко узнать свое расписание.\n\nЧтоб начать, выберите свое направление из списка!"
        inline_keyboard = self.keyboard_manager.faculties_choose_keyboard()

        await self.message_manager.send_bot_message(message, response, inline_keyboard, bot, state)
        await state.clear()

    async def group_choose(self, callback: types.CallbackQuery, state: FSMContext, bot: Bot):
        response = "Отлично! Теперь выберите свою группу!"
        inline_keyboard = self.keyboard_manager.groups_choose_keyboard(callback.data)

        await self.message_manager.send_bot_message(callback, response, inline_keyboard, bot, state)
        await state.set_state(GroupDateChoose.choosing_group)
        await callback.answer()

    async def date_choose(self, callback: types.CallbackQuery, state: FSMContext, bot: Bot):
        if callback.data == "cancel":
            await state.clear()
            response = "Главное меню. Чтобы начать заново, введите /start."
            await self.message_manager.send_bot_message(callback, response, None, bot, state)
            await callback.answer()
            return

        await state.update_data(group=callback.data)
        response = 'Теперь выберите дату, на которую хотите узнать расписание.'

        await self.message_manager.send_bot_message(callback, response, self.keyboard_manager.date_choose_keyboard(),
                                                    bot, state)
        await state.set_state(GroupDateChoose.choosing_date)
        await callback.answer()

    async def answer(self, callback: types.CallbackQuery, state: FSMContext, bot: Bot):
        if callback.data == "cancel":
            await state.clear()
            response = "Главное меню. Чтобы начать заново, введите /start."
            await self.message_manager.send_bot_message(callback, response, None, bot, state)
            await callback.answer()
            return

        user_data = await state.get_data()
        if callback.data.startswith("date_"):
            date_string = callback.data.split('_')[1]
            selected_date = datetime.date.fromisoformat(date_string)
        elif callback.data.startswith("nav_"):
            date_string = callback.data.split('_')[1]
            selected_date = datetime.date.fromisoformat(date_string)
        else:
            await callback.answer()
            return

        # Получаем изображение расписания (из кэша или генерируем новое)
        img, caption = await self.image_manager.get_schedule_image(selected_date, user_data["group"], self.cache)

        photo_file = BufferedInputFile(
            file=img.getvalue(),
            filename="card.png",
        )

        kb = self.keyboard_manager.navigation_keyboard(selected_date)

        # Удаляем предыдущее сообщение бота
        await self.message_manager.delete_last_bot_message(state, bot, callback.message.chat.id)

        # Отправляем расписание как новое сообщение с фото
        sent = await callback.message.answer_photo(
            photo=photo_file,
            caption=caption,
            reply_markup=kb,
        )

        await state.update_data(last_message_id=sent.message_id)
        await state.update_data(selected_date=selected_date)
        await callback.answer()

    async def cancel_handler(self, callback: types.CallbackQuery, state: FSMContext, bot: Bot):
        await state.clear()
        response = "Главное меню. Чтобы начать заново, введите /start."
        await self.message_manager.send_bot_message(callback, response, None, bot, state)
        await callback.answer()

    async def help_handler(self, message: types.Message, state: FSMContext, bot: Bot):
        greeting = greeting_by_time()
        answer = (
            f"{greeting}.\n\nЭтот бот был создан, чтоб помочь студентам проще узнавать о своем расписании на каждый день.\n"
            f"Для работы с ботом Вы можете использовать несколько команд:\n\n"
            f"- /start - запуск/перезапуск бота (если возникают проблемы, попробуйте сначала пару раз его перезапустить)\n"
            f"- /feedback - команда для Вашей обратной связи (мы всегда открыты к новым идеям и предложениям)\n"
            f"- /help - показывает список всех команд")

        await self.message_manager.send_bot_message(message, answer, None, bot, state)

    async def clear_cache_handler(self, message: types.Message):
        """Команда для очистки кэша (может быть полезно при обновлении расписания)"""
        old_size = self.cache.clear()
        await message.answer(f"Кэш очищен! Удалено {old_size} изображений.")

    async def feedback_start(self, message: types.Message, state: FSMContext, bot: Bot):
        response = "Мы стараемся улучшить работу бота, поэтому если Вы столкнулись с проблемой или у вас есть предложения, то можете написать об этом:"
        await self.message_manager.send_bot_message(message, response, None, bot, state)
        await state.set_state(Feedback.waiting_for_text)

    async def feedback_receive(self, message: types.Message, state: FSMContext, bot: Bot):
        text = message.text
        # Отправка админу
        await bot.send_message(
            ADMIN_ID,
            f"Новый отзыв от @{message.from_user.username or message.from_user.id}:\n{text}"
        )

        # Ответ пользователю (без картинки, так как это быстрый ответ)
        await message.answer("Спасибо за ваш отзыв!")
        await state.clear()

    async def prepare_schedule_start(self, message: types.Message, state: FSMContext, bot: Bot):
        groups = session.query(Group).order_by(Group.group_name.asc()).all()
        builder = InlineKeyboardBuilder()
        for group in groups:
            builder.add(types.InlineKeyboardButton(text=group.group_name, callback_data=f"g_{group.group_id}"))
        builder.adjust(4)
        kb = builder.as_markup()

        await self.message_manager.send_bot_message(message, "Выберите группу:", kb, bot, state)
        await state.set_state(ScheduleFSM.choosing_group)

    async def choose_group(self, callback: types.CallbackQuery, state: FSMContext, bot: Bot):
        group_id = int(callback.data[2:])
        group = session.query(Group).filter_by(group_id=group_id).first()
        await state.update_data(group_id=group_id, group_name=group.group_name)

        # Клавиатура месяца
        now = datetime.datetime.now()
        months = [
            (now.strftime('%B'), now.month),
            ((now.replace(month=now.month % 12 + 1)).strftime('%B'), (now.month % 12) + 1)
        ]
        builder = InlineKeyboardBuilder()
        for name, idx in months:
            builder.add(types.InlineKeyboardButton(text=name, callback_data=f"m_{idx}"))
        builder.adjust(2)

        await self.message_manager.send_bot_message(callback, "Выберите месяц (this/next):", builder.as_markup(), bot,
                                                    state)
        await state.set_state(ScheduleFSM.choosing_month)
        await callback.answer()

    async def choose_month(self, callback: types.CallbackQuery, state: FSMContext, bot: Bot):
        month_num = int(callback.data[2:])
        month_name = datetime.datetime(2000, month_num, 1).strftime("%B")
        await state.update_data(month_num=month_num, month_name=month_name)

        await self.message_manager.send_bot_message(callback, f"Загрузите файл .doc/.docx с расписанием", None, bot,
                                                    state)
        await state.set_state(ScheduleFSM.waiting_for_file)
        await callback.answer()

    async def schedule_file_uploaded(self, message: types.Message, state: FSMContext, bot: Bot):
        data = await state.get_data()
        group_name = data["group_name"]
        month_name = data["month_name"]

        file_extension = message.document.file_name.split(".")[-1].lower()
        file_name = message.document.file_name

        os.makedirs(f"files/{month_name}", exist_ok=True)
        save_path = f"files/{month_name}/{file_name}"

        await bot.download(message.document, destination=save_path)

        if file_extension == "doc":
            convert_doc_to_docx(save_path)
            save_path = save_path.rsplit(".", 1)[0] + ".docx"

        lessons = parse_docx_schedule(save_path, group_name)
        import_schedule_to_db(lessons=lessons)

        # Очищаем кэш для этой группы, так как расписание обновилось
        self.cache.clear_group(group_name)

        await message.answer(f"✅ Расписание загружено! Кэш очищен для группы {group_name}.")
        await state.clear()


# Состояния остаются как есть (они не требуют перевода в ООП)
class GroupDateChoose(StatesGroup):
    choosing_group = State()
    choosing_date = State()


class Feedback(StatesGroup):
    waiting_for_text = State()


class ScheduleFSM(StatesGroup):
    choosing_group = State()
    choosing_month = State()
    waiting_for_file = State()


# Создание экземпляра бота для использования в основном проекте
schedule_bot = ScheduleBot()
router = schedule_bot.router