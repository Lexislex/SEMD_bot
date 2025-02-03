import datetime
import handlers.sql as sql
import pandas as pd
from tabulate import tabulate
# подключаем модули для dotenv
from dotenv import dotenv_values
config = dotenv_values('.env')

def next_weekday(d, weekday, week):
    days_ahead = weekday - d.weekday()
    days_ahead += (7 * week)
    return d + datetime.timedelta(days_ahead)

def get_statistics(week=-3):
    message = ''
    start_date = next_weekday(datetime.datetime.now().date(), 0, week)
    stop_date = start_date + datetime.timedelta(21)
    df = pd.DataFrame(sql.get_activity(start_date, stop_date),
                      columns=['user_id', 'activity', 'date_time'])
    df['date_time'] = pd.to_datetime(df['date_time'])
    df = df[df['user_id'] != int(config['ADMIN_ID'])]
    df['week'] = df['date_time'].dt.isocalendar().week
    df = df.pivot_table(index=['activity'], columns='week', values='user_id', aggfunc='count')
    df.index.name = None
    df = df.fillna(0)
    message += f"Статистика активности по неделям:\n\
        <pre>{tabulate(df, headers='keys', tablefmt='psql')}</pre>"

    return message

if __name__ == '__main__':
    print('This module is not for direct call')
    exit(1)