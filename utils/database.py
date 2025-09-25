import sqlite3
from config import get_config
cfg = get_config()
# Настройка логирования
import logging
logger = logging.getLogger(__name__)

def create_table_nsi_passport():
    # Подключение к базе данных
    con = sqlite3.connect(cfg.paths.fnsi_db_path)
    cur = con.cursor()
    try:
        cur.execute("CREATE TABLE nsi_passport"\
                    "(ID, Name, ShortName, lastUpdate, version, "\
                    "releaseNotes, add_date);")
        con.commit()
        # Закрываем подключение к базе
        con.close()
    except Exception as e:
        logger.warning(f'Warning: {e}')
        # Закрываем подключение к базе
        con.close()

if __name__ == '__main__':
    logger.warning('This module is not for direct call')
    exit(1)