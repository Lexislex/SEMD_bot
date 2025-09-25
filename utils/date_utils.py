import datetime

# Настройка логирования
import logging
logger = logging.getLogger(__name__)

def next_weekday(d, weekday, week):
    days_ahead = weekday - d.weekday()
    days_ahead += (7 * week)
    return d + datetime.timedelta(days_ahead)

if __name__ == '__main__':
    logger.warning('This module is not for direct call')
    exit(1)