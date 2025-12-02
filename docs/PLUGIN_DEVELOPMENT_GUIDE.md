# Гайд по разработке плагинов для SEMD Bot

**Версия:** 2.1.0
**Последнее обновление:** Ноябрь 2025
**Архитектура:** Plugin-based (Fork + Pull Request)

---

## 📋 Оглавление

1. [Введение](#введение)
2. [Что такое плагин?](#что-такое-плагин)
3. [Требования и подготовка](#требования-и-подготовка)
4. [Процесс разработки](#процесс-разработки)
5. [Структура плагина](#структура-плагина)
6. [API плагина](#api-плагина)
7. [Примеры](#примеры)
8. [Тестирование](#тестирование)
9. [Pull Request](#pull-request)
10. [FAQ](#faq)

---

## Введение

SEMD Bot использует **модульную плагинную архитектуру**, которая позволяет разработчикам добавлять новый функционал без изменения ядра приложения.

### Почему плагины?

- ✅ **Независимость** — каждый плагин изолирован
- ✅ **Масштабируемость** — легко добавлять новые функции
- ✅ **Качество** — код проходит review перед интеграцией
- ✅ **Сообщество** — другие разработчики могут вносить свой вклад

### Процесс разработки

```
Fork репо → Создать плагин → Тестировать → Pull Request → Review → Merge
```

---

## Что такое плагин?

### Определение

**Плагин** — это независимый модуль, который:
- Наследует `BasePlugin` или `ScheduledPlugin`
- Реагирует на команды пользователя (сообщения, кнопки)
- Может выполняться по расписанию
- Полностью изолирован от других плагинов

### Два типа плагинов

#### 1. Плагин с логикой (BasePlugin)

Реагирует на **сообщения и нажатия кнопок** от пользователя.

```python
from plugins.base import BasePlugin

class Plugin(BasePlugin):
    display_name = "🔍 Мой плагин"
    access_level = "all"

    def get_commands(self):
        return [...]  # Команды типа /start

    def get_callbacks(self):
        return [...]  # Обработчики кнопок
```

**Примеры:** SEMDChecker, Statistics

#### 2. Плагин со расписанием (ScheduledPlugin)

Выполняет действия **автоматически по расписанию**.

```python
from plugins.base import ScheduledPlugin

class Plugin(ScheduledPlugin):
    display_name = "⏱️ Проверяльщик"
    access_level = "all"

    def get_schedule_config(self):
        return {'interval': 33, 'unit': 'minutes'}

    def check_updates(self):
        # Выполняется каждые 33 минуты
        pass
```

**Примеры:** NSI Update Checker

---

## Требования и подготовка

### Пререквизиты

- Python 3.10+
- Poetry 2.0+
- Git
- Знание Python
- Понимание телеграм-ботов (основы)

### Подготовка окружения

#### Шаг 1: Fork репозитория

Перейди на https://github.com/Lexislex/SEMD_bot и нажми **Fork**

```bash
# Клонируй свой форк
git clone https://github.com/ВАШ_ЮЗЕР/SEMD_bot.git
cd SEMD_bot
```

#### Шаг 2: Установка Poetry

Если Poetry не установлена:

```bash
# macOS/Linux
curl -sSL https://install.python-poetry.org | python3 -

# Windows (PowerShell)
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -

# Добавь Poetry в PATH (для macOS/Linux)
export PATH="$HOME/.local/bin:$PATH"

# Проверь установку
poetry --version  # должно вывести версию >= 2.0
```

#### Шаг 3: Подготовка папок и конфигурации

Проект требует определённую структуру папок и файлов:

```bash
# Создай необходимые папки
mkdir -p env/data env/crts logs files

# Скопируй файл конфигурации (если есть .env.example)
cp .env.example .env
# или создай .env вручную (см. пример ниже)
```

**Структура папок:**

```
SEMD_bot/
├── env/
│   ├── data/              # Базы данных
│   │   ├── user_data.sqlite
│   │   └── fnsi_data.sqlite
│   ├── crts/              # Сертификаты
│   │   └── rosminzdrav.crt
│   └── SEMD_bot.service   # Systemd unit
├── files/                 # Скачанные файлы
├── logs/                  # Логи приложения
├── .env                   # Переменные окружения
└── ...
```

**Файл .env (создай или скопируй из .env.example):**

```bash
# Telegram Bot Token (получи у @BotFather)
BOT_TOKEN=YOUR_BOT_TOKEN_HERE

# Твой Telegram ID (узнай у @userinfobot)
ADMIN_ID=123456789

# ID'ы чатов/групп для рассылок обновлений (через запятую)
UPDS_MAILING_LIST=123456789,-1001234567890

# API FNSI (если есть)
FNSI_API_URL=https://nsi.rosminzdrav.ru/port/rest/
FNSI_API_KEY=your_api_key_here
FNSI_FILES_URL=https://nsi.rosminzdrav.ru/api/dataFiles/

# Пути к базам данных и файлам
USER_DB=env/data/user_data.sqlite
FNSI_DB=env/data/fnsi_data.sqlite
MZRF_CERT=env/crts/rosminzdrav.crt
FILES_PATH=files/

# Режим окружения
ENV=development  # development | staging | production

# Уровень логирования
LOG_LEVEL=DEBUG  # DEBUG | INFO | WARNING | ERROR | CRITICAL
```

#### Шаг 4: Установка зависимостей

```bash
# Установи все зависимости из pyproject.toml
poetry install

# Для разработки включены dev зависимости
poetry install --with dev
```

**Основные зависимости проекта:**
- `requests` — HTTP запросы к API
- `python-dotenv` — управление переменными окружения
- `pytelegrambotapi` — API Telegram ботов
- `schedule` — планировщик задач
- `tabulate` — форматирование таблиц
- `pandas` — работа с данными в CSV/Excel

---

## Процесс разработки

### Этап 1: Создание папки плагина

```bash
# Убедись что ты в проекте
cd SEMD_bot

# Активируй виртуальное окружение Poetry
poetry shell

# Создай папку плагина в community
mkdir -p plugins/community/my_awesome_plugin
cd plugins/community/my_awesome_plugin
```

### Этап 2: Структура файлов

Создай минимальные файлы:

```
my_awesome_plugin/
├── __init__.py           # Пусто или импорты
├── plugin.py             # Основной класс Plugin
├── handlers.py           # Обработчики команд
├── keyboards.py          # Клавиатуры (кнопки)
└── README.md             # Описание плагина
```

### Этап 3: Реализация

Напиши код плагина (подробнее см. [API плагина](#api-плагина)).

### Этап 4: Регистрация в main.py

**Добавь** в `main.py` загрузку плагина в секцию загрузки плагинов:

```python
# В функции __main__ после загрузки основных плагинов
if core.load_plugin('plugins.community.my_awesome_plugin'):
    logger.info("✓ My Awesome Plugin загружен")
else:
    logger.error("✗ Ошибка загрузки My Awesome Plugin")
```

### Этап 5: Локальное тестирование

```bash
# Убедись что виртуальное окружение активно
poetry shell

# Запусти бота
python main.py

# В Telegram отправь /start и проверь работу плагина
```

---

## Структура плагина

### Файл: `plugin.py`

**Это основной файл плагина.** Здесь определяется класс `Plugin`.

#### Минимальный шаблон

```python
"""My Awesome Plugin - краткое описание"""
import logging
from typing import List, Dict, Any
from plugins.base import BasePlugin
from .handlers import MyHandlers


class Plugin(BasePlugin):
    """Описание плагина"""

    # Метаданные плагина
    access_level = "all"  # "all" или "admin"
    display_name = "🎯 Мой Плагин"  # С эмодзи!
    description = "Полное описание, что делает плагин"

    def __init__(self, bot, config):
        super().__init__(bot, config)
        self.handlers = MyHandlers(bot, config)
        self.logger = logging.getLogger(__name__)

    def get_name(self) -> str:
        """Уникальное имя плагина (без пробелов)"""
        return "MyAwesomePlugin"

    def get_version(self) -> str:
        """Версия плагина"""
        return "1.0.0"

    def initialize(self) -> bool:
        """Инициализация плагина при запуске"""
        try:
            self.logger.info(f"Plugin {self.get_name()} initialized")
            return True
        except Exception as e:
            self.logger.error(f"Error initializing {self.get_name()}: {e}")
            return False

    def get_commands(self) -> List[Dict[str, Any]]:
        """Команды и callback'и, которые обрабатывает плагин"""
        return [
            {
                'params': {'commands': ['mycommand']},
                'handler': self.handlers.handle_my_command
            },
            {
                'params': {'func': lambda call: call.data.startswith('myplugin_')},
                'handler': self.handlers.handle_my_callback
            }
        ]

    def get_callbacks(self) -> List[Dict[str, Any]]:
        """Callback обработчики"""
        return [
            {
                'params': {'func': lambda call: call.data == "back_to_menu"},
                'handler': self.handlers.handle_back
            }
        ]

    def shutdown(self):
        """Завершение работы плагина (опционально)"""
        self.logger.info(f"Plugin {self.get_name()} shutting down")
```

#### Параметры класса

| Параметр | Тип | Описание | Пример |
|---|---|---|---|
| `access_level` | str | Кому доступен плагин | `"all"`, `"admin"` |
| `display_name` | str | Имя в меню (с эмодзи) | `"🔍 Поиск"` |
| `description` | str | Полное описание | `"Поиск информации в базе"` |

### Файл: `handlers.py`

**Здесь обработчики команд и callback'ов.**

```python
"""Handlers for My Awesome Plugin"""
import logging


class MyHandlers:
    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.logger = logging.getLogger(__name__)

    def handle_my_command(self, message):
        """Обработчик команды /mycommand"""
        user_id = message.from_user.id
        text = "Привет! Я твой плагин 🎯"

        self.bot.send_message(message.chat.id, text)

    def handle_my_callback(self, call):
        """Обработчик нажатия кнопки"""
        user_id = call.from_user.id
        text = "Ты нажал кнопку!"

        self.bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        self.bot.answer_callback_query(call.id)

    def handle_back(self, call):
        """Обработчик кнопки 'Назад в меню'"""
        self.bot.answer_callback_query(call.id)
        # Остальная логика...
```

### Файл: `keyboards.py`

**Клавиатуры (кнопки) для плагина.**

```python
"""Keyboards for My Awesome Plugin"""
from telebot import types


def get_my_keyboard():
    """Основная клавиатура плагина"""
    markup = types.InlineKeyboardMarkup()

    # Первая кнопка
    btn1 = types.InlineKeyboardButton(
        text="🔍 Поиск",
        callback_data="myplugin_search"
    )
    markup.add(btn1)

    # Вторая кнопка
    btn2 = types.InlineKeyboardButton(
        text="⚙️ Настройки",
        callback_data="myplugin_settings"
    )
    markup.add(btn2)

    # Кнопка "Назад"
    back_btn = types.InlineKeyboardButton(
        text="« Назад в меню",
        callback_data="back_to_menu"
    )
    markup.add(back_btn)

    return markup
```

### Файл: `README.md`

**Описание плагина для других разработчиков.**

```markdown
# My Awesome Plugin

## Описание

Краткое описание, что делает плагин.

## Команды

- `/mycommand` — описание команды

## Кнопки

- 🔍 Поиск — найти информацию
- ⚙️ Настройки — изменить параметры

## Требования

- Python 3.10+
- pytelegrambotapi (уже в зависимостях проекта)

## Автор

@ВАШ_ЮЗЕР

## Лицензия

MIT
```

---

## API плагина

### Методы BasePlugin

```python
class Plugin(BasePlugin):

    @abstractmethod
    def get_name(self) -> str:
        """Возвращает имя плагина (уникальное, без пробелов)"""
        pass

    @abstractmethod
    def get_version(self) -> str:
        """Возвращает версию плагина (SemVer)"""
        pass

    @abstractmethod
    def initialize(self) -> bool:
        """Инициализация при запуске. True = успех, False = ошибка"""
        pass

    def get_commands(self) -> List[Dict[str, Any]]:
        """Возвращает список команд"""
        return []  # Можно вернуть пусто

    def get_callbacks(self) -> List[Dict[str, Any]]:
        """Возвращает список callback обработчиков"""
        return []  # Можно вернуть пусто

    def shutdown(self):
        """Вызывается при завершении бота"""
        pass  # Опционально

    def has_access(self, user_id: int) -> bool:
        """Проверка доступа пользователя к плагину"""
        if self.access_level == "all":
            return True
        elif self.access_level == "admin":
            return user_id in self.config.accounts.admin_ids
        return False
```

### Методы ScheduledPlugin

Если нужно выполнять действия по расписанию:

```python
from plugins.base import ScheduledPlugin

class Plugin(ScheduledPlugin):

    def get_schedule_config(self) -> Dict[str, Any]:
        """Конфигурация расписания"""
        return {
            'interval': 15,  # каждые 15
            'unit': 'minutes'  # минут
        }
        # Возможные unit: 'seconds', 'minutes', 'hours', 'days', 'weeks'

    def check_updates(self):
        """Выполняется по расписанию"""
        print("Выполняю плановую задачу!")
        # Твоя логика здесь
```

### Доступные объекты в плагине

```python
def __init__(self, bot, config):
    self.bot = bot          # TeleBot объект
    self.config = config    # Конфигурация приложения
```

#### `self.bot` (TeleBot)

```python
# Отправить сообщение
self.bot.send_message(chat_id, text, reply_markup=keyboard)

# Отредактировать сообщение
self.bot.edit_message_text(new_text, chat_id=chat_id, message_id=message_id)

# Ответить на callback
self.bot.answer_callback_query(callback_id)

# Удалить сообщение
self.bot.delete_message(chat_id, message_id)
```

#### `self.config` (Config)

```python
# Доступ к конфигурации
self.config.app.bot_token      # Токен бота
self.config.accounts.admin_ids # ID администраторов
self.config.app.env            # development / production
self.config.paths.data_dir     # Путь к папке данных
```

---

## Примеры

### Пример 1: Простой плагин с командой

```python
# plugin.py
from plugins.base import BasePlugin
from .handlers import HelloHandlers

class Plugin(BasePlugin):
    access_level = "all"
    display_name = "👋 Привет"

    def __init__(self, bot, config):
        super().__init__(bot, config)
        self.handlers = HelloHandlers(bot, config)

    def get_name(self) -> str:
        return "HelloPlugin"

    def get_version(self) -> str:
        return "1.0.0"

    def initialize(self) -> bool:
        return True

    def get_commands(self) -> list:
        return [
            {
                'params': {'commands': ['hello']},
                'handler': self.handlers.handle_hello
            }
        ]
```

### Пример 2: Плагин со расписанием

```python
# plugin.py
from plugins.base import ScheduledPlugin
from .handlers import CheckerHandlers

class Plugin(ScheduledPlugin):
    access_level = "all"
    display_name = "⏰ Проверка"

    def get_name(self) -> str:
        return "CheckerPlugin"

    def get_version(self) -> str:
        return "1.0.0"

    def initialize(self) -> bool:
        return True

    def get_schedule_config(self) -> dict:
        return {'interval': 1, 'unit': 'hours'}

    def check_updates(self):
        self.handlers.check_and_notify()
```

---

## Тестирование

```bash
# Активируй окружение
poetry shell

# Запусти бота
python main.py
```

Проверь в логах:
```
✓ My Awesome Plugin загружен
```

---

## Pull Request

#### 1. Commit и push

```bash
git add plugins/community/my_awesome_plugin/
git add main.py

git commit -m "Add My Awesome Plugin

- Краткое описание функциональности
- Какие команды добавлены
- Для кого доступен (all/admin)"

git push origin main
```

#### 2. Создай PR на GitHub

1. Перейди на https://github.com/ТВОЙ_ЮЗЕР/SEMD_bot
2. Нажми "Compare & pull request"
3. Убедись что идёт в `Lexislex/SEMD_bot`

#### 3. Ожидай review

Будет проверена:
- Качество кода
- Безопасность
- Совместимость с архитектурой

---

## FAQ

### Q: Как плагин появляется в меню?

**A:** Автоматически! RootMenuPlugin показывает все доступные плагины.

### Q: Как сделать плагин только для админов?

**A:** `access_level = "admin"` (только для ID'ов в ADMIN_ID).

### Q: Можно ли получить доступ к другим плагинам?

**A:** Нет, плагины полностью изолированы.

### Q: Какие пакеты уже установлены?

**A:** requests, python-dotenv, pytelegrambotapi, schedule, tabulate, pandas.

---

**Happy coding! 🚀**
