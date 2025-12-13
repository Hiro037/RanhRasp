"""
Утилиты и вспомогательные функции

Содержит функции для:
- Форматирования дат и времени
- Работы с расписанием (устаревшие, оставлены для совместимости)
- Общие вспомогательные функции
"""

from datetime import date, datetime, timedelta, timezone

# ========== ФОРМАТИРОВАНИЕ ДАТ И ВРЕМЕНИ ==========


def format_date_readable_manual(date_obj: date) -> str:
    """
    Преобразует объект date в строку вида '28 мая'

    Args:
        date_obj: Объект datetime.date

    Returns:
        str: Дата в формате "день месяц"

    Example:
        >>> format_date_readable_manual(date(2025, 5, 28))
        '28 мая'
    """
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


def format_date_full(date_obj: date) -> str:
    """
    Преобразует объект date в полный формат '28 мая 2025 года'

    Args:
        date_obj: Объект datetime.date

    Returns:
        str: Дата в формате "день месяц год"
    """
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
    return f"{date_obj.day} {months_ru[date_obj.month]} {date_obj.year} года"


def format_time(dt_object: datetime) -> str:
    """
    Преобразует объект datetime в строку времени в формате ЧЧ:ММ

    Args:
        dt_object: Объект datetime.datetime

    Returns:
        str: Время в формате "ЧЧ:ММ"

    Example:
        >>> format_time(datetime(2025, 5, 28, 14, 30))
        '14:30'
    """
    return dt_object.strftime("%H:%M")


def format_datetime(dt_object: datetime) -> str:
    """
    Преобразует объект datetime в строку вида '28.05.2025 14:30'

    Args:
        dt_object: Объект datetime.datetime

    Returns:
        str: Дата и время в формате "ДД.ММ.ГГГГ ЧЧ:ММ"
    """
    return dt_object.strftime("%d.%m.%Y %H:%M")


# ========== РАБОТА С ВРЕМЕНЕМ ==========


def greeting_by_time() -> str:
    """
    Возвращает приветствие в зависимости от времени суток

    Использует часовой пояс UTC+5 (Екатеринбург, Пермь)

    Returns:
        str: Приветствие ("Доброе утро", "Добрый день", и т.д.)
    """
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


def get_week_bounds(week_offset: int = 0) -> tuple[date, date]:
    """
    Получить границы недели (понедельник - воскресенье)

    Args:
        week_offset: Смещение в неделях (0 = текущая неделя, 1 = следующая, -1 = предыдущая)

    Returns:
        tuple[date, date]: (начало недели, конец недели)
    """
    today = date.today()
    # Понедельник текущей недели (weekday: 0 = понедельник)
    monday = today - timedelta(days=today.weekday())
    # Смещаем на нужное количество недель
    monday = monday + timedelta(weeks=week_offset)
    sunday = monday + timedelta(days=6)

    return monday, sunday


def is_weekend(target_date: date) -> bool:
    """
    Проверяет, является ли дата выходным днем

    Args:
        target_date: Дата для проверки

    Returns:
        bool: True если суббота или воскресенье
    """
    return target_date.weekday() in [5, 6]  # 5 = суббота, 6 = воскресенье


def get_weekday_name(target_date: date) -> str:
    """
    Получить название дня недели на русском

    Args:
        target_date: Дата

    Returns:
        str: Название дня недели
    """
    weekdays = {
        0: "Понедельник",
        1: "Вторник",
        2: "Среда",
        3: "Четверг",
        4: "Пятница",
        5: "Суббота",
        6: "Воскресенье",
    }
    return weekdays[target_date.weekday()]


# ========== ВАЛИДАЦИЯ ==========


def validate_group_name(group_name: str) -> bool:
    """
    Проверяет корректность названия группы

    Args:
        group_name: Название группы

    Returns:
        bool: True если название корректно
    """
    valid_groups = {
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
    return group_name in valid_groups


def validate_date_range(target_date: date, max_days_ahead: int = 14) -> bool:
    """
    Проверяет, находится ли дата в допустимом диапазоне

    Args:
        target_date: Дата для проверки
        max_days_ahead: Максимальное количество дней вперед

    Returns:
        bool: True если дата в допустимом диапазоне
    """
    today = date.today()
    max_date = today + timedelta(days=max_days_ahead)

    return today <= target_date <= max_date


# ========== ТЕСТИРОВАНИЕ ==========

if __name__ == "__main__":
    # Тестирование функций
    print("🧪 Тестирование утилит...\n")

    today = date.today()
    now = datetime.now()

    print(f"Сегодня: {format_date_readable_manual(today)}")
    print(f"Полная дата: {format_date_full(today)}")
    print(f"Время: {format_time(now)}")
    print(f"Дата и время: {format_datetime(now)}")
    print(f"Приветствие: {greeting_by_time()}")
    print(f"День недели: {get_weekday_name(today)}")
    print(f"Выходной: {'Да' if is_weekend(today) else 'Нет'}")

    monday, sunday = get_week_bounds()
    print(f"\nТекущая неделя:")
    print(f"  Начало: {format_date_readable_manual(monday)}")
    print(f"  Конец: {format_date_readable_manual(sunday)}")

    print(f"\nВалидация:")
    print(f"  'Э-42' валидна: {validate_group_name('Э-42')}")
    print(f"  'Х-99' валидна: {validate_group_name('Х-99')}")
    print(f"  Сегодня в диапазоне: {validate_date_range(today)}")
    print(f"  +30 дней в диапазоне: {validate_date_range(today + timedelta(days=30))}")
