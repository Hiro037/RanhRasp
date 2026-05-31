from typing import List, Dict, Any, Tuple


def get_page_items(items: List[Any], page: int, page_size: int = 8) -> Tuple[List[Any], bool, bool]:
    """
    Разбивает список элементов на страницы.
    Возвращает: (список_элементов_на_странице, есть_ли_предыдущая, есть_ли_следующая)
    """
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    page_items = items[start_idx:end_idx]
    has_prev = page > 1
    has_next = end_idx < len(items)

    return page_items, has_prev, has_next