import pandas as pd
import locale
import sqlite3
locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
from datetime import datetime
from tabulate import tabulate
# from sql import create_table_nsi_passport
from handlers.file_utils import download_file

# подключаем модули для dotenv
from config import get_config
cfg = get_config()

class semd_1520():
    def __init__(self):
        self.id = '1.2.643.5.1.13.13.11.1520'
        self.ver = fnsi_version(self.id)
        download_file(self.id, self.ver.latest)
        self.df = pd.read_csv(f"{cfg.paths.files_dir}/{self.id}_{self.ver.latest}_csv.zip", 
                  sep=';', parse_dates=['START_DATE', 'END_DATE'], dayfirst=True)
        self.df = self.df.loc[:,['OID', 'TYPE', 'NAME',\
                                 'START_DATE', 'END_DATE', 'FORMAT']]
    
        self.df['EXPIRED'] = self.df['END_DATE'].\
        apply(lambda x: 'запланирован вывод' if x and x > datetime.now() \
              else ('выведен' if x and x < datetime.now() else x))
        
    def get_semd_versions(self, semd_rev):
        semd_type = self.df[self.df['OID'] == int(semd_rev)]
        semd_versions = self.df[self.df['TYPE'] == semd_type['TYPE'].iloc[0]].copy()
        semd_versions = semd_versions.sort_values('OID')
        semd_versions['START_DATE'] = semd_versions['START_DATE'].dt.strftime('%d.%m.%y')
        semd_versions['END_DATE'] = semd_versions['END_DATE'].dt.strftime('%d.%m.%y')
        name = f"{semd_versions['NAME'].iloc[-1].split('(CDA)')[0]}"
        doc_type = semd_type['TYPE'].iloc[0]
        link_1520 = f"<a href='https://nsi.rosminzdrav.ru/dictionaries/\
1.2.643.5.1.13.13.11.1520/passport/latest#filters=TYPE%7C{doc_type}%7CGTE&filters=TYPE%7C{doc_type}%7CLTE'>🔗</a>"
        link_1522 = f"<a href='https://nsi.rosminzdrav.ru/dictionaries/\
1.2.643.5.1.13.13.11.1522/passport/latest#filters=RECID%7C{doc_type}%7CGTE&filters=RECID%7C{doc_type}%7CLTE'>🔗</a>"
        semd_versions = semd_versions.loc[:,['OID', 'START_DATE', 'END_DATE']].reset_index(drop=True)
        semd_versions = tabulate(semd_versions, showindex=False, \
                                 tablefmt='simple', headers=['ID', 'Start', 'Stop'])
        return name, semd_versions, doc_type, link_1520, link_1522
    
    def get_newest(self, vers_num=1):
        # Формируем список самых свежих версий СЭМД
        newest_ver = self.df.sort_values(['TYPE', 'START_DATE'], ascending=[True, False])
        newest_ver = newest_ver.loc[newest_ver['END_DATE'].isnull()]
        newest_ver = newest_ver.loc[newest_ver['FORMAT'] == 2] #убираем pdf так как не будем их разрабатывать
        newest_ver = newest_ver.groupby('TYPE').head(vers_num)
        return newest_ver
    
class fnsi_version():
    def __init__(self, fnsi) -> None:
        self.fnsi = fnsi
        self.latest = self.get_ver()
        self.rel_notes = self.get_relnotes()

    def get_ver(self):
        con = sqlite3.connect(cfg.paths.fnsi_db_path)
        cur = con.cursor()
        # cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='nsi_passport'")
        # table_exist = cur.fetchone()
        # if not table_exist: create_table_nsi_passport()
        try:
            cur.execute(
                "SELECT \
                    version \
                FROM nsi_passport \
                WHERE ID = ? \
                ORDER by lastUpdate DESC limit 1",
                [self.fnsi]
            )
        except Exception as e:
            print('Warning:', e)
            con.close()
        try:
            ver = cur.fetchone()[0]
        except Exception as e:
            # print('Warning:', e)
            con.close()
            ver = 'empty version'
        con.close()
        return ver
    
    def get_relnotes(self):
        con = sqlite3.connect(cfg.paths.fnsi_db_path)
        cur = con.cursor()
        try:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='nsi_passport'")
        except Exception as e:
                print('Warning:', e)
                # Закрываем подключение к базе
                con.close()
        try:
            cur.execute(
                "SELECT \
                    releaseNotes \
                FROM nsi_passport \
                WHERE ID = ? AND version = ?\
                ORDER by lastUpdate DESC limit 1",
                [self.fnsi, self.latest]
            )
        except Exception as e:
            print('Warning:', e)
        try:
            rel_notes = cur.fetchone()[0]
        except Exception as e:
            # print('Warning:', e)
            con.close()
            rel_notes = 'empty notes'
        con.close()
        return rel_notes
    
if __name__ == '__main__':
    print('This module is not for direct call')
    exit(1)