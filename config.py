from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Объявляем переменные и их типы данных
    TG_TOKEN: str
    VK_TOKEN: str
    DATABASE_URL: str
    TG_ADMINS: list[int]
    VK_ADMINS: list[int]

    # Валидатор, который превращает строку "123,456" из .env в список чисел [123, 456]
    @field_validator("TG_ADMINS", "VK_ADMINS", mode="before")
    @classmethod
    def parse_admins(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip().isdigit()]
        return v

    # Указываем Pydantic, откуда читать переменные окружения
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore" # игнорировать другие системные переменные в .env
    )

# Создаем объект настроек, который будем импортировать в другие файлы
settings = Settings()