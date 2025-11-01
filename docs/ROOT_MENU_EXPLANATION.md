# Root Menu Plugin - Объяснение архитектуры

## Проблема

При наличии только одного интерактивного плагина (SEMD Checker) всё просто:
- `/start` → SEMD Checker
- Всё работает

Но когда будет несколько интерактивных плагинов:
- `/start` → куда отправить? В SEMD Checker? Statistics? Settings?
- Конфликт! Нужна координация.

## Решение: Root Menu Plugin

Создаем **главный плагин**, который:
1. Обрабатывает `/start` и показывает главное меню
2. Направляет пользователя в нужный плагин через callback кнопки
3. Позволяет вернуться в меню из любого плагина

## Архитектура

```
Пользователь
     ↓
   /start
     ↓
🏠 Root Menu Plugin (ГЛАВНЫЙ)
     ├─ Показывает меню
     ├─ Кнопка "📋 SEMD Checker"
     ├─ Кнопка "📊 Statistics"
     ├─ Кнопка "⚙️ Settings"
     └─ Кнопка "❓ Help"
     ↓
   callback_data = "menu_semd"
     ↓
📋 SEMD Checker Plugin (ФУНКЦИОНАЛЬНЫЙ)
     ├─ Обрабатывает поиск версий
     ├─ Показывает информацию
     └─ Кнопка "← Назад"
     ↓
   callback_data = "back"
     ↓
🏠 Root Menu Plugin (снова ГЛАВНЫЙ)
     └─ Показывает меню снова
```

## Реализация

### Root Menu Plugin обрабатывает:

```python
class RootMenuPlugin(BasePlugin):
    def get_commands(self):
        return [
            {
                'params': {'commands': ['start', 'menu']},
                'handler': self.show_main_menu
            }
        ]

    def get_callbacks(self):
        return [
            {
                'params': {'func': lambda call: call.data.startswith('menu_')},
                'handler': self.route_to_plugin  # menu_semd → SEMD Plugin
            },
            {
                'params': {'func': lambda call: call.data == 'back'},
                'handler': self.back_to_menu  # Вернуться в меню
            }
        ]
```

### SEMD Checker обрабатывает:

```python
class SEMDCheckerPlugin(BasePlugin):
    def get_callbacks(self):
        return [
            {
                'params': {'func': lambda call: call.data == 'back'},
                'handler': self.back_to_menu  # Кнопка "назад" в меню
            }
        ]

    def back_to_menu(self, call):
        # Удалить текущее сообщение
        # Root Menu обработает callback и покажет меню
        pass
```

## Flow

```
1. Пользователь отправляет /start
   ↓
2. RootMenuPlugin.show_main_menu() вызывается
   ↓
3. Показывается меню:
   🏠 Главное меню
   [📋 SEMD]
   [📊 Statistics]
   [⚙️ Settings]
   ↓
4. Пользователь нажимает "SEMD"
   callback_data = "menu_semd"
   ↓
5. RootMenuPlugin.route_to_plugin() вызывается
   ↓
6. SEMDCheckerPlugin.show_semd_interface() вызывается
   ↓
7. Показывается:
   Введите ID СЭМД:
   [← Назад]
   ↓
8. Пользователь нажимает "Назад"
   callback_data = "back"
   ↓
9. RootMenuPlugin.back_to_menu() вызывается
   ↓
10. Показывается меню снова (шаг 3)
```

## Важные моменты

### 1. Root Menu загружается ПЕРВЫМ

```python
# main.py
core.load_plugin('plugins.root_menu')      # ПЕРВЫМ!
core.load_plugin('plugins.semd_checker')   # ПОТОМ
core.load_plugin('plugins.statistics')     # ПОТОМ
core.load_plugin('plugins.nsi_updater')    # ПОТОМ
```

### 2. Callback data конвенция

- `menu_*` → маршрутизируется Root Menu
- `back` → возврат в меню (обрабатывается Root Menu)
- `semd_*` → специфичные для SEMD Checker
- `stat_*` → специфичные для Statistics

### 3. Каждый плагин имеет кнопку "← Назад"

```python
keyboard = InlineKeyboardMarkup()
keyboard.add(InlineKeyboardButton("← Назад", callback_data="back"))
```

## Плюсы этой архитектуры

✅ **Масштабируемость**: Легко добавлять новые плагины
✅ **Организованность**: Главное меню централизовано
✅ **Навигация**: Пользователь всегда может вернуться в меню
✅ **Разделение ответственности**: Каждый плагин за своё
✅ **Без конфликтов**: Нет спора за `/start`

## Минусы и как их избежать

⚠️ **Root Menu должен быть прост**
- Не добавлять бизнес-логику в Root Menu
- Только маршрутизация и навигация

⚠️ **Callback data должна быть уникальна**
- Использовать разные префиксы для разных плагинов
- `menu_semd`, `menu_stat`, `semd_search`, `stat_graph` и т.д.

⚠️ **Не перегружать меню**
- Максимум 5-6 кнопок в меню
- Если много - создать подменю

## Пример callback data маршрутизации

```
callback_data             │ Обработчик
─────────────────────────┼──────────────────────────
menu_semd                │ RootMenuPlugin → SEMDCheckerPlugin
menu_stat                │ RootMenuPlugin → StatisticsPlugin
menu_config              │ RootMenuPlugin → ConfigPlugin
menu_help                │ RootMenuPlugin → Help display
back                      │ RootMenuPlugin.back_to_menu()
semd_search_<query>       │ SEMDCheckerPlugin.search()
semd_next_page            │ SEMDCheckerPlugin.next_page()
stat_graph_day            │ StatisticsPlugin.show_day_graph()
stat_export               │ StatisticsPlugin.export()
```

## Расширение: Подменю

Если меню становится слишком большим:

```
Root Menu
├─ Features (подменю)
│  ├─ SEMD Checker
│  └─ Statistics
├─ User (подменю)
│  ├─ Profile
│  └─ Settings
└─ Help
```

Это реализуется через дополнительные callback'ы:

```python
def get_callbacks(self):
    return [
        {
            'params': {'func': lambda call: call.data == 'menu_features'},
            'handler': self.show_features_submenu
        },
        {
            'params': {'func': lambda call: call.data == 'submenu_back'},
            'handler': self.show_main_menu
        }
    ]
```

