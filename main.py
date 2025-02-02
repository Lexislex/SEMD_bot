# подключаем модули для dotenv
from dotenv import dotenv_values
config = dotenv_values('.env')

#Импортируем основную логику
from handlers.fnsi import semd_1520
import handlers.sql as sql
import handlers.stat as stat_util

# подключаем модуль для Телеграма
import telebot
#from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

bot = telebot.TeleBot(config['BOT_TOKEN'])

# приветственный текст
start_txt = 'Привет!\nЭто бот - информатор о версиях СЭМД.\n\
Достаточно ввести ID одной из редаций СЭМД и я покажу все редакции \
этого СЭМД и сроки начала и окончания его регистрации в РЭМД\n\
\nИспользуйте команду /versions'

# обрабатываем старт бота
@bot.message_handler(commands=['start', 'about'])
def start(message):
    # Регистрация пользователя
    sql.add_user(message.from_user.id, message.from_user.username, \
                 message.from_user.first_name, message.from_user.last_name)
    # Лог активности
    sql.add_log(message)
    # Отправляем приветственное сообщение
    bot.send_message(message.from_user.id, start_txt, parse_mode='Markdown')

@bot.message_handler(commands=['versions'])
def versions(message):
 
    mesg = bot.send_message(message.chat.id, "Введите ID редакции СЭМД:")
    bot.register_next_step_handler(mesg, get_versions)

def get_versions(message):
    # Лог активности
    sql.add_log(message)
    try:
        semd = semd_1520(config['1520_ver']).get_semd_versions(message.text)
        bot.send_message(message.chat.id, f'<b>{semd[0]}</b>\n<pre>{semd[1]}</pre>', parse_mode='html',
                        disable_web_page_preview=True)
    except:
        bot.send_message(message.chat.id, f'ID не найден, попробуйте еще раз:\n/versions', parse_mode='html',
                        disable_web_page_preview=True)
        
@bot.message_handler(commands=['stat'])
def stat(message):
    # Лог активности
    sql.add_log(message)
    # Отправляем список семинаров
    bot.send_message(message.from_user.id, stat_util.get_statistics(), parse_mode='html',
                     disable_web_page_preview=True)
        
@bot.message_handler(content_types=['text'])
def auto_answer(message):
    bot.send_message(message.from_user.id, 'Используйте команду /versions', parse_mode='Markdown')

# Запускаем бота
if __name__ == '__main__':
    while True:
        # в бесконечном цикле постоянно опрашиваем бота — есть ли новые сообщения
        try:
            bot.polling(none_stop=True, interval=0)
        # если возникла ошибка — сообщаем про исключение и продолжаем работу
        except Exception as e:
            print('Сработало исключение!\n', e)