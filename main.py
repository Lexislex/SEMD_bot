# Загружаем переменные окружения
from config import get_config
cfg = get_config()

# Настройка логирования
from utils.logging_setup import setup_logging
setup_logging(cfg)

import logging
logger = logging.getLogger(__name__)

#Импортируем основную логику
from handlers.fnsi import semd_1520
from handlers.sql import add_log, add_user
from handlers.stat import get_statistics
from handlers.scrap import nsi_passport_updater
from utils.data import NSI_LIST

# Импортируем библитеки расписания
import schedule
import time
from threading import Thread

# подключаем модуль для Телеграма
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

bot = telebot.TeleBot(cfg.app.bot_token)

# приветственный текст
start_txt = 'Привет!\nЭто бот - информатор о версиях СЭМД.\n\
Достаточно ввести ID одной из редаций СЭМД и я покажу все редакции \
этого СЭМД и сроки начала и окончания его регистрации в РЭМД'

markup_inline = InlineKeyboardMarkup(row_width=1)
markup_inline.add(InlineKeyboardButton(text='искать версии СЭМД', callback_data='versions'))

markup_back = InlineKeyboardMarkup(row_width=1)
markup_back.add(InlineKeyboardButton(text='<- назад', callback_data='back'))
# markup_inline.add(item)

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
    
def check_updates():
    for el in NSI_LIST:
        res, upd_msg = nsi_passport_updater(el)
        if res:
            try:
                for chat_id in cfg.accounts.updates_mailing_list:
                    bot.send_message(chat_id, upd_msg, parse_mode='html',
                                    disable_web_page_preview=True)
            except telebot.apihelper.ApiTelegramException as e:
                logger.error(f"Не удалось отправить сообщение пользователю {chat_id}: {e}")
        
def start_schedule():
    if cfg.app.env == 'development':
        schedule.every(1).minutes.do(check_updates,)
    else:
        schedule.every(15).minutes.do(check_updates,)

    while True:
        schedule.run_pending()
        time.sleep(1)

# Запускаем бота
if __name__ == '__main__':
    Thread(target=start_schedule, args=(), daemon=True).start()
    try:
        # Блокирующий запуск с авто‑переподключением
        bot.infinity_polling()
    except KeyboardInterrupt:
        logger.info('Остановка по Ctrl-C')