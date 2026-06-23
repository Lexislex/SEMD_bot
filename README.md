# SEMD Bot 🤖

**Телеграм-бот для мониторинга версий СЭМД (Структурированные Электронные Медицинские Документы) и обновлений справочников НСИ**

Версия: **2.2.0** | Архитектура: **Модульная с системой плагинов (Plugin-based)** | Community: **Fork + Pull Request**

## 📋 Описание

SEMD Bot - это продвинутый Telegram-бот для мониторинга и управления:
- 📋 **СЭМД версии** - Структурированные электронные медицинские документы
- 📚 **НСИ справочники** - справочники Проекта НСИ МЗ РФ (40+ справочников на мониторинге)

## 🚀 Быстрый старт

```bash
# Установка зависимостей
poetry install

# Получение сертификата Минздрава для FNSI API
poetry run python scripts/fetch_fnsi_cert.py

# Очистка базы данных (если требуется)
poetry run python scripts/database/clean_all_db.py --backup

# Запуск архитектурного теста
poetry run python scripts/testing/test_architecture.py

# Запуск бота
poetry run python main.py
```

## 📁 Структура проекта

```
SEMD_bot/
├── core/                      # Ядро приложения
│   ├── bot.py                # SEMDBotCore - главный класс
│   ├── plugin_manager.py      # Управление плагинами
│   └── scheduler.py           # Планировщик задач
│
├── plugins/                   # Система плагинов
│   ├── base.py               # Базовые классы (BasePlugin, ScheduledPlugin)
│   ├── root_menu/            # Главное меню и маршрутизация
│   ├── semd_checker/         # Поиск версий СЭМД
│   ├── nsi_update_checker/   # Мониторинг обновлений НСИ (ScheduledPlugin)
│   ├── semd_reg_tracker/     # Отслеживание регистрации СЭМД (ScheduledPlugin) ⭐ NEW
│   ├── statistics/           # Статистика активности (админ)
│   ├── admin_logs/           # Логи системы (админ, в разработке)
│   ├── plugin_manager/       # Управление плагинами (админ, в разработке)
│   └── community/            # Место для плагинов от разработчиков
│
├── services/                  # Сервисы
│   └── fnsi_client.py        # Клиент FNSI API
│
├── utils/                     # Утилиты
│   ├── logging_setup.py      # Настройка логирования
│   ├── message_manager.py    # Управление сообщениями
│   ├── database.py           # Работа с БД
│   └── ...
│
├── scripts/                   # Вспомогательные скрипты
│   ├── database/             # Управление БД
│   └── testing/              # Тесты и проверки
│
├── env/                       # Конфигурация и данные
│   ├── data/                 # SQLite базы данных
│   └── crts/                 # Сертификаты
│
├── docs/                      # Документация
│   ├── ARCHITECTURE_MERMAID.md    # Архитектура с диаграммами
│   └── PLUGIN_DEVELOPMENT_GUIDE.md # Гайд для разработчиков плагинов
│
├── config.py                  # Конфигурация проекта
├── main.py                    # Точка входа
└── README.md                  # Этот файл
```

## 🔌 Плагины (v2.2.0)

### Плагины ядра (Core)

#### 📋 Root Menu
- Главное меню и маршрутизация между плагинами
- Команда `/start` для открытия меню
- Автоматически показывает все доступные пользователю плагины

#### 🔍 SEMD Checker
- Поиск версий СЭМД по OID или названию документа
- Текстовый поиск с выбором из топ-5 результатов
- Получение информации о редакциях
- Сроки начала и окончания регистрации
- Команда `/about` для информации

#### 📚 NSI Update Checker (ScheduledPlugin)
- Автоматическая проверка обновлений 40+ справочников
- Интеллектуальное форматирование уведомлений (3 уровня: important, normal, minor)
- Умное определение режима отправки (со звуком/без звука)
- Автоматический "тихий режим" ночью (22:00-08:00)
- Генерация хэштегов для архивирования обновлений
- Интервал проверки:
  - Development: каждую минуту
  - Production: каждые 33 минуты

#### 📊 SEMD Registration Tracker (ScheduledPlugin) ⭐ NEW
- Отслеживание регистрации СЭМД в РЭМД
- Ежемесячные и ежеквартальные сводки
- Группировка по датам начала/окончания регистрации
- Интеллектуальное форматирование с эмодзи
- Отправка в список рассылки `UPDS_MAILING_LIST`
- Приоритет квартальной сводки на начало квартала
- Интервал проверки:
  - Development: каждую минуту (месячная) / каждые 3 минуты (квартальная)
  - Production: 1 число месяца / 1 число квартала в 10:00 MSK
- 📖 [Полная документация](plugins/semd_reg_tracker/README.md)

#### 📊 Statistics (Admin)
- Статистика активности пользователей
- Анализ использования плагинов
- Генерация отчётов
- Доступен только для администраторов

### Плагины в разработке (WIP)

#### 📋 Admin Logs (Admin)
- Просмотр логов системы
- Фильтрация по различным критериям
- Команда `/logs`

#### 🔌 Plugin Manager (Admin)
- Управление загруженными плагинами
- Просмотр версий и статуса
- Команда `/plugins`

## 👥 Разработка плагинов (Community)

SEMD Bot имеет **открытую архитектуру для разработчиков**! 🎉

### Процесс: Fork + Pull Request

1. **Fork** репозитория: https://github.com/Lexislex/SEMD_bot
2. **Создай плагин** в папке `plugins/community/my_plugin/`
3. **Тестируй локально**
4. **Создай Pull Request** в основной репозиторий
5. **Code Review** и интеграция

### Быстрый старт для разработчиков

```bash
# Полный гайд с примерами кода и пошаговыми инструкциями
cat docs/PLUGIN_DEVELOPMENT_GUIDE.md
```

**Что можно разрабатывать:**
- Интеграции с внешними API
- Утилиты и инструменты
- Расширение функциональности
- Специализированные плагины

**Требования:**
- Python 3.10+
- Наследование от `BasePlugin` или `ScheduledPlugin`
- README.md с описанием
- Тестирование на локальной машине

### Примеры существующих плагинов

- [`plugins/root_menu/`](plugins/root_menu/) — Главное меню (шаблон BasePlugin)
- [`plugins/semd_checker/`](plugins/semd_checker/) — Поиск СЭМД (BasePlugin с командами)
- [`plugins/nsi_update_checker/`](plugins/nsi_update_checker/) — Мониторинг НСИ (ScheduledPlugin)
- [`plugins/semd_reg_tracker/`](plugins/semd_reg_tracker/) — Отслеживание регистрации СЭМД (ScheduledPlugin с месячным/квартальным расписанием) ⭐ NEW
- [`plugins/statistics/`](plugins/statistics/) — Статистика (Админский плагин)

## 🛠️ Инструменты для разработки

### Database Scripts (управление БД)

```bash
# Информация о базах
poetry run python scripts/database/clean_all_db.py --info

# Очистка FNSI базы с резервной копией
poetry run python scripts/database/clean_fnsi_db.py --backup

# Очистка данных, сохранение схемы
poetry run python scripts/database/clean_fnsi_db.py --keep-schema
```

### Testing Scripts (тесты)

```bash
# Тест архитектуры (проверка всех компонентов)
poetry run python scripts/testing/test_architecture.py
```

Подробная документация в [`scripts/README.md`](scripts/README.md)

## 🏗️ Архитектура

### Модульная система плагинов

- Каждый плагин - независимый модуль с четким interface'ом
- Две базовые архитектуры:
  - **BasePlugin** — реагирует на команды и callback'и пользователя
  - **ScheduledPlugin** — выполняется по расписанию (интервалы)
- Автоматическая регистрация обработчиков команд и callbacks
- Система управления доступом (`access_level = "all"` или `"admin"`)

### Многопоточность

- **Главный поток**: обработка сообщений от Telegram API
- **Отдельный поток**: выполнение планируемых задач (по расписанию)

Подробная архитектурная документация: [`docs/ARCHITECTURE_MERMAID.md`](docs/ARCHITECTURE_MERMAID.md)

## 📊 Последние изменения (Nov 2025, v2.2.0)

### ⭐ NEW: Плагин SEMD Registration Tracker

- **Новый ScheduledPlugin для отслеживания регистрации СЭМД в РЭМД**
- Ежемесячные и ежеквартальные автоматические сводки
- Группировка информации по датам с компактным форматом
- Отправка в список рассылки `UPDS_MAILING_LIST`
- Приоритизация квартальной сводки на начало квартала
- Полная документация: [`plugins/semd_reg_tracker/README.md`](plugins/semd_reg_tracker/README.md)
- ✅ Полностью протестирован и готов к production

### ✅ Расширение системы планирования (core/scheduler.py)

- Добавлена поддержка месячного расписания (`unit='months'`)
- Добавлена поддержка квартального расписания (`unit='quarters'`)
- Параметр `at` для указания конкретного времени выполнения ("HH:MM")
- Вспомогательные методы: `is_first_of_month()`, `is_first_of_quarter()`, `get_current_quarter()`

### ✅ Предыдущие релизы (v2.1.0)

- Модульная архитектура с поддержкой community плагинов
- Root Menu Plugin — центральная маршрутизация
- Полный гайд для разработчиков
- Интеллектуальное форматирование НСИ уведомлений
- Автоматический "тихий режим" ночью (22:00-08:00)

## 🧪 Тестирование

```bash
# Запустить архитектурный тест
poetry run python scripts/testing/test_architecture.py

# Ожидаемый результат:
# ✅ SEMDBotCore создан успешно
# ✅ Плагины загружены успешно
# ✅ Задачи добавлены в планировщик
# ✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!
```

## 📚 Документация

- [`docs/ARCHITECTURE_MERMAID.md`](docs/ARCHITECTURE_MERMAID.md) — Детальная архитектура с диаграммами
- [`docs/PLUGIN_DEVELOPMENT_GUIDE.md`](docs/PLUGIN_DEVELOPMENT_GUIDE.md) — **Полный гайд для разработчиков плагинов**
- [`scripts/README.md`](scripts/README.md) — Справка по вспомогательным скриптам
- [`scripts/database/README.md`](scripts/database/README.md) — Управление базами данных
- [`scripts/testing/README.md`](scripts/testing/README.md) — Тесты

## 🔧 Требования

- Python 3.10+
- Poetry 2.0+ для управления зависимостями
- SQLite3 (встроенный в Python)
- Telegram Bot API token

### Зависимости проекта

- `requests` (2.32.5+) — HTTP запросы к API
- `python-dotenv` (1.1.1+) — управление переменными окружения
- `pytelegrambotapi` (4.29.1+) — API Telegram ботов
- `schedule` (1.2.2+) — планировщик задач
- `tabulate` (0.9.0+) — форматирование таблиц
- `pandas` (2.3.2+) — работа с данными в CSV/Excel

## 📝 Конфигурация

### Настройка окружения

Проект требует файла `.env` с конфигурацией:

```bash
# Создайте .env файл в корне проекта
```

### Обязательные переменные

```env
# Сертификат Минздрава для FNSI API (получить/обновить: poetry run python scripts/fetch_fnsi_cert.py)
# Ожидается по пути env/crts/rosminzdrav.crt

# Telegram Bot API (получите от @BotFather на Telegram)
BOT_TOKEN=your_telegram_bot_token

# Ваш Telegram ID (администратор бота)
ADMIN_ID=your_telegram_id

# Список чатов/групп для рассылки уведомлений
UPDS_MAILING_LIST=11111111,-1111111111

# FNSI API конфигурация (для плагина NSI Update Checker)
FNSI_API_KEY=your_fnsi_api_key
FNSI_API_URL=https://nsi.rosminzdrav.ru/port/rest/
FNSI_FILES_URL=https://nsi.rosminzdrav.ru/api/dataFiles/
```

### Опциональные переменные

```env
# Режим окружения: development | staging | production
ENV=production

# Уровень логирования: DEBUG | INFO | WARNING | ERROR | CRITICAL
LOG_LEVEL=INFO
```

**⚠️ ВАЖНО:** Файл `.env` содержит чувствительные учетные данные и **НЕ должен коммититься** в систему контроля версий.

Полная конфигурация в [`config.py`](config.py)

## 🤝 Разработка

### Типичный workflow

```bash
# 1. Очистить БД
poetry run python scripts/database/clean_all_db.py --backup

# 2. Запустить архитектурный тест
poetry run python scripts/testing/test_architecture.py

# 3. Если тесты пройдены - запустить бота
poetry run python main.py
```

### Разработка плагина для community

**Начни здесь:** [`docs/PLUGIN_DEVELOPMENT_GUIDE.md`](docs/PLUGIN_DEVELOPMENT_GUIDE.md)

Краткая схема:

1. Fork репо: https://github.com/Lexislex/SEMD_bot
2. Создай папку `plugins/community/my_plugin/`
3. Напиши код (BasePlugin или ScheduledPlugin)
4. Добавь README.md в папку плагина
5. Тестируй локально: `poetry run python main.py`
6. Создай Pull Request

Все детали и примеры кода в гайде! 📖

## 📄 Лицензия

MIT License - см. LICENSE файл

---

**Последнее обновление:** Nov 2025 | **Версия:** 2.2.0 | **Статус:** ✅ Production Ready

**Вопросы или идеи?** Создай [Issue](https://github.com/Lexislex/SEMD_bot/issues) или [Pull Request](https://github.com/Lexislex/SEMD_bot/pulls)! 🚀
