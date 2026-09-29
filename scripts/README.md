# Scripts — Вспомогательные скрипты

Эта директория содержит различные вспомогательные скрипты для разработки и тестирования проекта.

## 📁 Структура

```
scripts/
├── README.md                  # Этот файл
├── database/                  # Скрипты для работы с базами данных
│   ├── README.md              # Документация
│   ├── clean_fnsi_db.py       # Гибкая очистка FNSI базы
│   ├── clean_all_db.py        # Очистка всех баз
│   ├── clean_fnsi_db_quick.sh # Быстрая очистка (без подтверждения)
│   ├── DB_CLEANUP_GUIDE.md    # Полное руководство
│   └── QUICK_REFERENCE.txt    # Быстрая справка
└── testing/                   # Тесты и проверки
    ├── README.md              # Документация
    └── test_architecture.py   # Тест архитектуры
```

## 🗄️ Database Scripts

Скрипты для управления базами данных (FNSI и User) в процессе разработки.

### Database — Быстрый старт

```bash
# Показать информацию о базах
uv run python scripts/database/clean_all_db.py --info

# Удалить FNSI базу с резервной копией
uv run python scripts/database/clean_fnsi_db.py --backup

# Удалить всё
uv run python scripts/database/clean_all_db.py --backup

# Быстро удалить FNSI (без вопросов)
./scripts/database/clean_fnsi_db_quick.sh
```

Подробная документация: [`database/DB_CLEANUP_GUIDE.md`](./database/DB_CLEANUP_GUIDE.md)

## 🧪 Testing Scripts

Скрипты для тестирования архитектуры.

### Быстрый старт

```bash
# Тест архитектуры
uv run python scripts/testing/test_architecture.py
```

Подробная документация: [`testing/README.md`](./testing/README.md)

## 📋 Типичный workflow

```bash
# 1. Очистить БД с резервной копией
uv run python scripts/database/clean_all_db.py --backup

# 2. Запустить архитектурный тест
uv run python scripts/testing/test_architecture.py

# 3. Если тесты пройдены, запустить бота
uv run python main.py
```

## 📝 Как добавить новый скрипт

1. Создайте подпапку в `scripts/` (например, `scripts/utils/`)
2. Добавьте `README.md` в новую папку с описанием
3. Создайте ваши скрипты
4. Убедитесь что bash скрипты исполняемые (`chmod +x`)
5. Обновите главный `scripts/README.md`

---

**Примечание:** Все скрипты должны быть организованы по категориям и хорошо документированы для удобства команды разработки.
