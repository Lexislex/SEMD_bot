"""SEMD (Structured Electronic Medical Documents) logic and utilities"""
import pandas as pd
import sqlite3
from datetime import datetime
from tabulate import tabulate
from utils.file_utils import download_file
from config import get_config

import logging

logger = logging.getLogger(__name__)

cfg = get_config()


class SEMDVersionFetcher:
    """Get version information for SEMD documents"""

    def __init__(self, fnsi_id):
        self.fnsi_id = fnsi_id
        self.latest = self.get_version()
        self.release_notes = self.get_release_notes()

    def get_version(self):
        """Get latest version of SEMD from database"""
        con = sqlite3.connect(cfg.paths.fnsi_db_path)
        cur = con.cursor()
        try:
            cur.execute(
                "SELECT version FROM nsi_passport "
                "WHERE ID = ? "
                "ORDER by lastUpdate DESC limit 1",
                [self.fnsi_id]
            )
            ver = cur.fetchone()[0] if cur.fetchone() else 'empty version'
        except Exception as e:
            logger.warning(f'Warning: {e}')
            ver = 'empty version'
        finally:
            con.close()
        return ver

    def get_release_notes(self):
        """Get release notes for latest version"""
        con = sqlite3.connect(cfg.paths.fnsi_db_path)
        cur = con.cursor()
        try:
            cur.execute(
                "SELECT releaseNotes FROM nsi_passport "
                "WHERE ID = ? AND version = ? "
                "ORDER by lastUpdate DESC limit 1",
                [self.fnsi_id, self.latest]
            )
            result = cur.fetchone()
            rel_notes = result[0] if result else 'empty notes'
        except Exception as e:
            logger.warning(f'Warning: {e}')
            rel_notes = 'empty notes'
        finally:
            con.close()
        return rel_notes


class SEMD1520:
    """
    SEMD 1520 - Medical Document Structure Dictionary.
    Handles retrieval and formatting of SEMD versions.
    """

    # Standard FNSI OID for SEMD 1520
    SEMD_OID = '1.2.643.5.1.13.13.11.1520'

    def __init__(self):
        self.id = self.SEMD_OID
        self.version_fetcher = SEMDVersionFetcher(self.id)
        self.latest_version = self.version_fetcher.latest

        # Download and load the dictionary
        try:
            download_file(self.id, self.latest_version)
            self.df = pd.read_csv(
                f"{cfg.paths.files_dir}/{self.id}_{self.latest_version}_csv.zip",
                sep=';',
                parse_dates=['START_DATE', 'END_DATE'],
                dayfirst=True
            )
            # Select only needed columns
            self.df = self.df.loc[:, ['OID', 'TYPE', 'NAME', 'START_DATE', 'END_DATE', 'FORMAT']]

            # Add status column
            self.df['EXPIRED'] = self.df['END_DATE'].apply(
                lambda x: 'запланирован вывод' if x and x > datetime.now()
                else ('выведен' if x and x < datetime.now() else 'активно')
            )
        except Exception as e:
            logger.error(f"Error loading SEMD 1520 dictionary: {e}")
            self.df = None

    def get_semd_versions(self, semd_oid):
        """
        Get all SEMD versions for a specific document type.

        Args:
            semd_oid: SEMD OID to search for

        Returns:
            tuple: (document_name, versions_table, document_type, link_1520, link_1522)
        """
        if self.df is None:
            return None, "Ошибка: не удалось загрузить данные СЭМД", None, None, None

        try:
            # Find document type by OID
            semd_type_row = self.df[self.df['OID'] == int(semd_oid)]
            if semd_type_row.empty:
                return None, f"СЭМД с OID {semd_oid} не найдена", None, None, None

            doc_type = semd_type_row['TYPE'].iloc[0]

            # Get all versions for this document type
            semd_versions = self.df[self.df['TYPE'] == doc_type].copy()
            semd_versions = semd_versions.sort_values('OID')

            # Format dates
            semd_versions['START_DATE'] = semd_versions['START_DATE'].dt.strftime('%d.%m.%y')
            semd_versions['END_DATE'] = semd_versions['END_DATE'].dt.strftime('%d.%m.%y')

            # Get document name
            name = f"{semd_versions['NAME'].iloc[-1].split('(CDA)')[0]}"

            # Create links to NSI
            link_1520 = (
                f"<a href='https://nsi.rosminzdrav.ru/dictionaries/"
                f"1.2.643.5.1.13.13.11.1520/passport/latest"
                f"#filters=TYPE%7C{doc_type}%7CGTE&filters=TYPE%7C{doc_type}%7CLTE'>🔗</a>"
            )
            link_1522 = (
                f"<a href='https://nsi.rosminzdrav.ru/dictionaries/"
                f"1.2.643.5.1.13.13.11.1522/passport/latest"
                f"#filters=RECID%7C{doc_type}%7CGTE&filters=RECID%7C{doc_type}%7CLTE'>🔗</a>"
            )

            # Format as table
            semd_versions = semd_versions.loc[:, ['OID', 'START_DATE', 'END_DATE']].reset_index(drop=True)
            versions_table = tabulate(
                semd_versions,
                showindex=False,
                tablefmt='simple',
                headers=['ID', 'Start', 'Stop']
            )

            return name, versions_table, doc_type, link_1520, link_1522

        except Exception as e:
            logger.error(f"Error getting SEMD versions: {e}")
            return None, f"Ошибка при получении версий: {e}", None, None, None

    def get_newest_versions(self, count=1):
        """
        Get the newest SEMD versions.

        Args:
            count: Number of newest versions to return per type

        Returns:
            DataFrame with newest SEMD versions
        """
        if self.df is None:
            return None

        try:
            newest = self.df.sort_values(['TYPE', 'START_DATE'], ascending=[True, False])
            newest = newest.loc[newest['END_DATE'].isnull()]  # Active versions only
            newest = newest.loc[newest['FORMAT'] == 2]  # Only CDA format (skip PDF)
            newest = newest.groupby('TYPE').head(count)
            return newest
        except Exception as e:
            logger.error(f"Error getting newest SEMD versions: {e}")
            return None
