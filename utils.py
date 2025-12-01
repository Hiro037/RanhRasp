# Импорт нужных библиотек
import locale
import datetime

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from create_database import Lesson, Group, Teacher

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import asyncio
import tempfile
import os

# Подключение к базе данных
engine = create_engine('sqlite:///students_lessons.db')
Session = sessionmaker(bind=engine)
session = Session()

def create_answer(date, group) -> str:
    lessons = get_lessons(date, group)
    answer = f'Ваше расписание на {format_date_readable_manual(date)}:\n\n'
    if len(lessons) != 0:
        for lesson in lessons:
            answer += (f"Название предмета: {lesson.subject.name}\n"
                       f"Время начала: {format_time(lesson.start_datetime)}\n"
                       f"Преподаватель: {lesson.teacher.name}\n"
                       f"Аудитория: {lesson.classroom}\n\n")
    else:
        answer += 'У вас нет занятий в этот день.'

    return answer

def get_lessons(date, group):
    group_obj = session.query(Group).filter(Group.group_name == group).first()
    lessons = session.query(Lesson).filter(
        func.date(Lesson.start_datetime) == date,
        Lesson.group_id == group_obj.group_id
    ).order_by(Lesson.start_datetime).all()
    return lessons

def format_date_readable_manual(date_obj: datetime.date) -> str:
    """
    Преобразует объект datetime.date в строку вида '28 мая'
    """
    months_ru = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
    }
    # Получаем день и номер месяца
    day = date_obj.day
    month_name = months_ru[date_obj.month]

    return f"{day} {month_name}"

def format_time(dt_object: datetime.datetime) -> str:
    """
    Преобразует объект datetime.datetime в строку времени
    в формате ЧЧ:ММ.
    """
    # %H - час в 24-часовом формате (00-23)
    # %M - минуты (00-59)
    return dt_object.strftime('%H:%M')


def greeting_by_time():
    # Часовой пояс МСК+2 (МСК = UTC+3, значит МСК+2 = UTC+5)
    msk_plus_2 = datetime.timezone(datetime.timedelta(hours=5))
    # Текущее время с учётом МСК+2
    now = datetime.datetime.now(msk_plus_2)
    hour = now.hour

    if 5 <= hour < 12:
        return "Доброе утро!"
    elif 12 <= hour < 18:
        return "Добрый день!"
    elif 18 <= hour < 23:
        return "Добрый вечер!"
    else:
        return "Доброй ночи!"
