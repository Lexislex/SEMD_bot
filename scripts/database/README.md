# Database Cleanup Scripts

Набор скриптов для управления базами данных SEMD Bot (FNSI и User) в процессе разработки и тестирования.

## 📊 Базы данных

- **fnsi_data.sqlite** — справочники ФНСИ (таблица `nsi_passport`)
- **user_data.sqlite** — пользователи и активность (таблицы `users`, `users_activity`)

Путь: `env/data/`

## 🔧 Инструменты

### 1. `clean_fnsi_db.py` — Гибкая очистка FNSI

Полнофункциональный скрипт с опциями.

**Команды:**
```bash
# Информация о базе
uv run python clean_fnsi_db.py --info

# Удалить базу целиком
uv run python clean_fnsi_db.py

# С резервной копией
uv run python clean_fnsi_db.py --backup

# Сохранить схему, удалить только данные
uv run python clean_fnsi_db.py --keep-schema
```

### 2. `clean_all_db.py` — Очистка всех баз

Удаляет FNSI и User базы одновременно.

**Команды:**
```bash
# Информация
uv run python clean_all_db.py --info

# Удалить обе базы
uv run python clean_all_db.py

# С резервными копиями
uv run python clean_all_db.py --backup
```

### 3. `clean_fnsi_db_quick.sh` — Быстрая очистка

Самый быстрый способ (без подтверждения).

**Команды:**
```bash
./clean_fnsi_db_quick.sh
# или
bash clean_fnsi_db_quick.sh
```

## 📖 Документация

- **DB_CLEANUP_GUIDE.md** — полное руководство с примерами
- **QUICK_REFERENCE.txt** — быстрая справка команд

## 💡 Рекомендуемые сценарии

### Отладка проблем

```bash
# 1. Посмотреть текущее состояние
uv run python clean_fnsi_db.py --info

# 2. Очистить
uv run python clean_fnsi_db.py

# 3. Запустить бота
uv run python main.py
```

### Полное тестирование

```bash
# 1. Информация
uv run python clean_all_db.py --info

# 2. Резервная копия + удаление
uv run python clean_all_db.py --backup

# 3. Тест архитектуры
uv run python test_architecture.py

# 4. Запуск бота
uv run python main.py
```

### CI/CD интеграция

```bash
# Быстро удалить без вопросов
./scripts/database/clean_fnsi_db_quick.sh

# Запустить тесты
uv run python test_architecture.py
```

## ⚙️ Технические детали

- **Python 3.8+** (используется встроенный sqlite3)
- **uv** — для запуска (опционально, можно использовать python из `.venv` напрямую)
- **Нет внешних зависимостей** — используются только стандартные модули

## 🛡️ Резервные копии

Формат имён:
```
{db_name}_backup_YYYYMMDD_HHMMSS.sqlite

Примеры:
  fnsi_data_backup_20251101_145000.sqlite
  user_data_backup_20251101_145000.sqlite
```

Сохраняются в: `env/data/`

## ⚠️ Важно

- Скрипты требуют **подтверждение** перед удалением (введите `да`)
- `clean_fnsi_db_quick.sh` **удаляет без подтверждения** (для автоматизации)
- При удалении без `--backup` данные теряются безвозвратно
- БД пересоздаются при следующем запуске бота

---

**Версия:** 1.0.0
**Последнее обновление:** 2025-11-01
