# подключаем модули для dotenv
from dotenv import dotenv_values
config = dotenv_values('.env')

#Импортируем основную логику
from handlers.fnsi import semd_1520
from handlers.sql import add_log, add_user
from handlers.stat import get_statistics
from handlers.scrap import nsi_passport_updater

# Импортируем библитеки расписания
import schedule
import time
from threading import Thread

# подключаем модуль для Телеграма
import telebot
#from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

bot = telebot.TeleBot(str(config['BOT_TOKEN']))

# приветственный текст
start_txt = 'Привет!\nЭто бот - информатор о версиях СЭМД.\n\
Достаточно ввести ID одной из редаций СЭМД и я покажу все редакции \
этого СЭМД и сроки начала и окончания его регистрации в РЭМД\n\
\nИспользуйте команду /versions'

# обрабатываем старт бота
@bot.message_handler(commands=['start', 'about'])
def start(message):
    # Регистрация пользователя
    add_user(message.from_user.id, message.from_user.username, \
                 message.from_user.first_name, message.from_user.last_name)
    # Лог активности
    add_log(message)
    # Отправляем приветственное сообщение
    bot.send_message(message.from_user.id, start_txt, parse_mode='Markdown')

@bot.message_handler(commands=['versions'])
def versions(message):
    # Лог активности
    add_log(message) 
    mesg = bot.send_message(message.chat.id, f"Введите ID редакции СЭМД:")
    bot.register_next_step_handler(mesg, get_versions)

def get_versions(message):
    try:
        semd = semd_1520().get_semd_versions(message.text)
        bot.send_message(message.chat.id,\
                         f'<b>{semd[0]}</b> {semd[3]}<pre>{semd[1]}</pre>Тип документа:  {semd[2]}  {semd[4]}',\
                        parse_mode='html', disable_web_page_preview=True)
        versions(message)        
    except:
        bot.send_message(message.chat.id, f'ID не найден, попробуйте еще раз:\n/versions', parse_mode='html',
                        disable_web_page_preview=True)
        
@bot.message_handler(commands=['stat'])
def stat(message):
    # Лог активности
    add_log(message)
    # Отправляем список семинаров
    bot.send_message(message.from_user.id, get_statistics(), parse_mode='html',
                     disable_web_page_preview=True)
        
@bot.message_handler(content_types=['text'])
def auto_answer(message):
    bot.send_message(message.from_user.id, 'Используйте команду /versions', parse_mode='Markdown')

def check_updates():
    # send_list = [config['ADMIN_ID']]
    check_list = ['1.2.643.5.1.13.13.11.1520']
    for el in check_list:
        res, upd_msg = nsi_passport_updater(el)
        if res:
            try:
                for chat_id in config['UPDS_MAILING_LIST'].split(','):
                    bot.send_message(chat_id, upd_msg, parse_mode='html',
                                    disable_web_page_preview=True)
            except telebot.apihelper.ApiTelegramException as e:
                print(f"Не удалось отправить сообщение пользователю {chat_id}: {e}")
        
def start_schedule():
    schedule.every(15).minutes.do(check_updates,)

    while True:
        schedule.run_pending()
        time.sleep(1)


# Запускаем бота
if __name__ == '__main__':
    #Thread(target=start_schedule, args=()).start()
    while True:
        # в бесконечном цикле постоянно опрашиваем бота — есть ли новые сообщения
        try:
            bot.polling(none_stop=True, interval=0)
        # если возникла ошибка — сообщаем про исключение и продолжаем работу
        except Exception as e:
            print('Сработало исключение!\n', e)
