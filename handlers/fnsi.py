import pandas as pd
import locale
locale.setlocale(locale.LC_TIME, 'ru_RU')
from datetime import datetime
from tabulate import tabulate

class semd_1520():
    def __init__(self, version):
        self.df = pd.read_csv(f'files/1.2.643.5.1.13.13.11.1520_{version}_csv.zip', 
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
        name = f"{semd_versions['NAME'].iloc[-1].split('(')[0]}\n(тип док.: {semd_type['TYPE'].iloc[0]})"
        
        semd_versions = semd_versions.loc[:,['OID', 'START_DATE', 'END_DATE']].reset_index(drop=True)
        semd_versions = tabulate(semd_versions, showindex=False, \
                                 tablefmt='rounded_outline', headers=['ID', 'Start', 'Stop'])
        return name, semd_versions
    
    def get_newest(self, vers_num=1):
        # Формируем список самых свежих версий СЭМД
        newest_ver = self.df.sort_values(['TYPE', 'START_DATE'], ascending=[True, False])
        newest_ver = newest_ver.loc[newest_ver['END_DATE'].isnull()]
        newest_ver = newest_ver.loc[newest_ver['FORMAT'] == 2] #убираем pdf так как не будем их разрабатывать
        newest_ver = newest_ver.groupby('TYPE').head(vers_num)
        return newest_ver
    
s = semd_1520('12.65').get_semd_versions(161)
print(f'{s[0]}\n{s[1]}')