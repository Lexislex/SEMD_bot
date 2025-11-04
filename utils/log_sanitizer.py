"""
Log Sanitizer - фильтр для очистки логов от чувствительных данных.

Этот модуль предоставляет LogSanitizer фильтр, который удаляет или маскирует
чувствительные данные перед логированием, такие как:
- API ключи и токены
- Email адреса
- Внутренние пути файлов
- Номера телефонов
- Идентификаторы пользователей (в определенных контекстах)
"""

import logging
import re
from typing import Optional
from config import get_config

cfg = get_config()


class LogSanitizer(logging.Filter):
    """
    Фильтр для удаления/маскирования чувствительных данных в логах.

    Маскирует:
    - API ключи (UUID формат): a6600b26-08f8-4d83-9a85-83c223a945ff -> a660****
    - Bot токены: 6376955250:AAGzj98d -> 6376****
    - Email адреса: user@domain.com -> u***@domain.com
    - Пути файлов с /Users/ -> /****/
    """

    # Регулярные выражения для поиска чувствительных данных
    PATTERNS = {
        # UUID ключи (FNSI API ключ)
        'uuid_key': re.compile(
            r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}',
            re.IGNORECASE
        ),
        # Telegram bot token (цифры:буквы)
        'bot_token': re.compile(
            r'\b\d{9,10}:AA[A-Za-z0-9_-]{24,}\b'
        ),
        # Email адреса
        'email': re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        ),
        # Пути /Users/username/
        'user_path': re.compile(
            r'/Users/[^/\s]+'
        ),
        # Пути /home/username/
        'home_path': re.compile(
            r'/home/[^/\s]+'
        ),
        # userKey параметр в URL
        'user_key_param': re.compile(
            r'userKey=[a-f0-9\-]+',
            re.IGNORECASE
        ),
        # URL с query параметрами содержащие ключ
        'url_with_key': re.compile(
            r'https?://[^\s]+(?:key|token|password)=[^\s&]+'
        ),
    }

    @staticmethod
    def _mask_uuid(match) -> str:
        """Маскирует UUID: a6600b26-08f8-4d83-9a85-83c223a945ff -> a660****"""
        key = match.group(0)
        return f"{key[:4]}****" if len(key) >= 4 else "****"

    @staticmethod
    def _mask_bot_token(match) -> str:
        """Маскирует bot token: 6376955250:AAGzj98d -> 6376****"""
        token = match.group(0)
        parts = token.split(':')
        if len(parts) == 2:
            return f"{parts[0][:4]}:****"
        return "****"

    @staticmethod
    def _mask_email(match) -> str:
        """Маскирует email: user@domain.com -> u***@domain.com"""
        email = match.group(0)
        local, domain = email.split('@')
        masked_local = local[0] + '***' if len(local) > 1 else '***'
        return f"{masked_local}@{domain}"

    @staticmethod
    def _mask_path(match) -> str:
        """Маскирует путь: /Users/alexeyalepko -> /***"""
        return "/***"

    @staticmethod
    def _mask_user_key_param(match) -> str:
        """Маскирует userKey параметр: userKey=a6600b26-08f8 -> userKey=****"""
        return "userKey=****"

    @staticmethod
    def _mask_url_with_key(match) -> str:
        """Маскирует URL с ключом: https://api.ru?key=secret -> https://api.ru?key=****"""
        url = match.group(0)
        # Заменяем значение параметра на ****
        return re.sub(r'((?:key|token|password)=)[^\s&]+', r'\1****', url)

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Фильтрует LogRecord и очищает сообщение от чувствительных данных.

        Args:
            record: LogRecord для фильтрации

        Returns:
            True (всегда пропускает запись, но с очищенным сообщением)
        """
        if record.msg:
            msg = str(record.msg)

            # Применяем все регулярные выражения
            msg = self.PATTERNS['uuid_key'].sub(self._mask_uuid, msg)
            msg = self.PATTERNS['bot_token'].sub(self._mask_bot_token, msg)
            msg = self.PATTERNS['email'].sub(self._mask_email, msg)
            msg = self.PATTERNS['user_path'].sub(self._mask_path, msg)
            msg = self.PATTERNS['home_path'].sub(self._mask_path, msg)
            msg = self.PATTERNS['user_key_param'].sub(self._mask_user_key_param, msg)
            msg = self.PATTERNS['url_with_key'].sub(self._mask_url_with_key, msg)

            # Обновляем сообщение в record
            record.msg = msg

        # Также очищаем exc_text если он есть (для исключений)
        if record.exc_text:
            exc_text = record.exc_text

            exc_text = self.PATTERNS['uuid_key'].sub(self._mask_uuid, exc_text)
            exc_text = self.PATTERNS['bot_token'].sub(self._mask_bot_token, exc_text)
            exc_text = self.PATTERNS['email'].sub(self._mask_email, exc_text)
            exc_text = self.PATTERNS['user_path'].sub(self._mask_path, exc_text)
            exc_text = self.PATTERNS['home_path'].sub(self._mask_path, exc_text)
            exc_text = self.PATTERNS['user_key_param'].sub(self._mask_user_key_param, exc_text)

            record.exc_text = exc_text

        return True


def add_sanitizer_to_logger(logger: logging.Logger) -> None:
    """
    Добавляет LogSanitizer фильтр ко всем handlers логгера.

    Args:
        logger: объект Logger, к которому добавить фильтр
    """
    sanitizer = LogSanitizer()
    for handler in logger.handlers:
        handler.addFilter(sanitizer)


def setup_log_sanitizer(root_logger: Optional[logging.Logger] = None) -> None:
    """
    Настраивает санитайзер для всех логгеров в приложении.

    Args:
        root_logger: корневой логгер (если None, используется root logger)
    """
    if root_logger is None:
        root_logger = logging.getLogger()

    sanitizer = LogSanitizer()

    # Добавляем фильтр ко всем handlers корневого логгера
    for handler in root_logger.handlers:
        handler.addFilter(sanitizer)

    # Логируем что санитайзер активирован (но без деталей)
    root_logger.debug("Log sanitizer activated")
