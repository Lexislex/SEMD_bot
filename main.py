# Загружаем переменные окружения
from config import get_config
cfg = get_config()

# Настройка логирования
from utils.logging_setup import setup_logging
setup_logging(cfg)

import logging
logger = logging.getLogger(__name__)

# Импортируем основной класс архитектуры
from core.bot import SEMDBotCore

#Импортируем основную логику для SEMD Checker (временно в монолите)
from handlers.fnsi import semd_1520
from handlers.sql import add_log, add_user
from handlers.stat import get_statistics
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Создаём ядро бота с поддержкой плагинов
core = SEMDBotCore(cfg)
bot = core.bot

# приветственный текст
start_txt = 'Привет!\nЭто бот - информатор о версиях СЭМД.\n\
Достаточно ввести ID одной из редаций СЭМД и я покажу все редакции \
этого СЭМД и сроки начала и окончания его регистрации в РЭМД'

markup_inline = InlineKeyboardMarkup(row_width=1)
markup_inline.add(InlineKeyboardButton(text='искать версии СЭМД', callback_data='versions'))

markup_back = InlineKeyboardMarkup(row_width=1)
markup_back.add(InlineKeyboardButton(text='<- назад', callback_data='back'))

# обрабатываем старт бота
@bot.message_handler(commands=['start', 'about'])
def start(message):
    # Регистрация пользователя
    add_user(message.from_user.id, message.from_user.username, \
                 message.from_user.first_name, message.from_user.last_name)
    # Лог активности
    add_log(message)

    # Отправляем приветственное сообщение
    bot.send_message(message.from_user.id, start_txt, parse_mode='Markdown', reply_markup=markup_inline)

def get_versions(message):
    try:
        semd = semd_1520().get_semd_versions(message.text)
        bot.send_message(message.chat.id,\
                        f'<b>{semd[0]}</b> {semd[3]}<pre>{semd[1]}</pre>Тип документа:  {semd[2]}  {semd[4]}',\
                        parse_mode='html', disable_web_page_preview=True)
    except:
        bot.send_message(message.chat.id, f'ID не найден, попробуйте еще раз', parse_mode='html',
                        disable_web_page_preview=True)

    bot.register_next_step_handler(
        bot.send_message(message.chat.id, f"Введите ID редакции СЭМД:", reply_markup=markup_back),
        get_versions
        )

#Ответ на кнопки
@bot.callback_query_handler(func=lambda call: True)
def answer(call):
    # Лог активности
    add_log(call)

    bot.answer_callback_query(call.id, text="")

    if call.data == 'versions':
        bot.register_next_step_handler(
            bot.send_message(call.message.chat.id, f"Введите ID редакции СЭМД:", reply_markup=markup_back),
            get_versions
            )

    elif call.data == 'back':
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        bot.send_message(call.message.chat.id, start_txt, parse_mode='Markdown', reply_markup=markup_inline)

@bot.message_handler(commands=['stat'])
def stat(message):
    # Лог активности
    add_log(message)
    
    bot.send_message(message.from_user.id, get_statistics(), parse_mode='html',
                     disable_web_page_preview=True)
        
@bot.message_handler(content_types=['text'])
def auto_answer(message):
    start(message)
    
# Запускаем бота
if __name__ == '__main__':
    try:
        logger.info("=" * 50)
        logger.info("Запуск SEMD Bot v2.0 (Миграция на модульную архитектуру)")
        logger.info("=" * 50)

        # Загружаем плагины
        logger.info("Загрузка плагинов...")
        core.load_plugin('plugins.nsi_update_checker')
        logger.info("✓ NSI Update Checker загружен")

        logger.info("Все плагины загружены успешно!")
        logger.info("=" * 50)

        # Запускаем бота (включает планировщик и polling)
        core.start()

    except KeyboardInterrupt:
        logger.info('Остановка по Ctrl+C')
        core.shutdown()
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}", exc_info=True)
        core.shutdown()
        raise