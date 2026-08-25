from datetime import datetime
import zoneinfo

# Фиксируем часовой пояс Екатеринбурга
YEKT_TZ = zoneinfo.ZoneInfo("Asia/Yekaterinburg")

def get_now() -> datetime:
    """Возвращает текущую дату и время в часовом поясе Екатеринбурга."""
    return datetime.now(YEKT_TZ)