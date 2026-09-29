"""SEMD (Structured Electronic Medical Documents) logic and utilities"""

import logging
import sqlite3
import threading
import time
from datetime import datetime

import pandas as pd
from tabulate import tabulate

from config import get_config
from utils.file_utils import download_file

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
                [self.fnsi_id],
            )
            result = cur.fetchone()
            ver = result[0] if result else "empty version"
        except Exception as e:
            logger.warning(f"Warning: {e}")
            ver = "empty version"
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
                [self.fnsi_id, self.latest],
            )
            result = cur.fetchone()
            rel_notes = result[0] if result else "empty notes"
        except Exception as e:
            logger.warning(f"Warning: {e}")
            rel_notes = "empty notes"
        finally:
            con.close()
        return rel_notes


class NsiDictionary:
    """
    FNSI dictionary loaded from its CSV archive.

    The version comes from ``nsi_passport`` (filled by the NSI Update Checker);
    when it changes, the archive of the new version is downloaded and loaded.
    Subclasses set ``SEMD_OID``/``TITLE`` and implement ``_load_data``.
    """

    SEMD_OID = ""
    TITLE = ""
    # Check version at most once per this interval (seconds)
    VERSION_CHECK_INTERVAL = 60

    def __init__(self):
        self.id = self.SEMD_OID
        self.version_fetcher = SEMDVersionFetcher(self.id)
        self.latest_version = self.version_fetcher.latest
        self._last_version_check = 0.0
        # Хендлеры Telegram и планировщик работают в разных потоках
        self._reload_lock = threading.RLock()
        self._load_data()

    @property
    def csv_path(self) -> str:
        return f"{cfg.paths.files_dir}/{self.id}_{self.latest_version}_csv.zip"

    def _download(self) -> None:
        download_file(self.id, self.latest_version)

    def _load_data(self) -> None:
        """Load data of ``self.latest_version``."""
        raise NotImplementedError

    def _check_and_reload_if_needed(self):
        """Check if version has been updated in database and reload data if needed.

        Version check is throttled to once per VERSION_CHECK_INTERVAL seconds
        to avoid excessive database queries on frequent requests.
        """
        now = time.time()
        if now - self._last_version_check < self.VERSION_CHECK_INTERVAL:
            return  # Skip check, too soon since last check

        with self._reload_lock:
            if now - self._last_version_check < self.VERSION_CHECK_INTERVAL:
                return  # другой поток уже проверил
            self._last_version_check = now
            try:
                current_version = self.version_fetcher.get_version()
                if current_version != self.latest_version:
                    logger.info(
                        f"{self.TITLE} version updated: "
                        f"{self.latest_version} → {current_version}"
                    )
                    self.latest_version = current_version
                    self._load_data()
            except Exception as e:
                logger.warning(f"Error checking {self.TITLE} version update: {e}")


_shared_instances: dict = {}
_shared_lock = threading.Lock()


def _shared(cls):
    """One instance of a dictionary per process (lazy, thread-safe)."""
    with _shared_lock:
        if cls not in _shared_instances:
            _shared_instances[cls] = cls()
        return _shared_instances[cls]


def get_semd1520() -> "SEMD1520":
    """Shared SEMD1520 instance (semd_checker, schematron_monitor, semd_reg_tracker)."""
    return _shared(SEMD1520)


def get_semd638() -> "SEMD638":
    """Shared SEMD638 instance."""
    return _shared(SEMD638)


class SEMD638(NsiDictionary):
    """
    SEMD 638 - Registry of SEMD implementation guides (packages).
    Maps a package OID (column GIT_LINK of 1520) to its GitLab URL.
    """

    SEMD_OID = "1.2.643.5.1.13.13.99.2.638"
    TITLE = "SEMD 638"

    def __init__(self):
        self.links: dict[str, str] | None = None
        super().__init__()

    def _load_data(self):
        """Load package -> GitLab URL mapping from the 638 CSV file.

        On failure the previously loaded mapping is kept: a stale mapping is
        better than falling back to the heuristic and resetting baselines.
        """
        if self.latest_version == "empty version":
            logger.warning(
                "SEMD 638: version is not in nsi_passport yet, "
                "GitLab links will be resolved heuristically"
            )
            return
        try:
            self._download()
            df = pd.read_csv(
                self.csv_path,
                sep=";",
                usecols=["OID", "GIT_LINK"],
                dtype=str,
            ).dropna()
            self.links = {
                oid.strip(): link.strip()
                for oid, link in zip(df["OID"], df["GIT_LINK"])
                if link.strip()
            }
            logger.info(
                f"SEMD 638 data loaded successfully (version {self.latest_version})"
            )
        except Exception as e:
            logger.error(f"Error loading SEMD 638 dictionary: {e}")

    def get_git_link(self, package_oid: str) -> str | None:
        """
        Get GitLab URL of a SEMD package.

        Args:
            package_oid: package OID (column GIT_LINK of 1520),
                e.g. "1.2.643.5.1.13.13.15.36.5"

        Returns:
            URL like ``<base>/<project>/-/tree/<ref>`` or None if the package
            is unknown or the dictionary is not loaded.
        """
        self._check_and_reload_if_needed()
        if not self.links or not package_oid:
            return None
        return self.links.get(str(package_oid).strip())


class SEMD1520(NsiDictionary):
    """
    SEMD 1520 - Medical Document Structure Dictionary.
    Handles retrieval and formatting of SEMD versions.
    """

    # Standard FNSI OID for SEMD 1520
    SEMD_OID = "1.2.643.5.1.13.13.11.1520"
    TITLE = "SEMD 1520"

    def __init__(self):
        self.df = None
        super().__init__()

    def _load_data(self):
        """Load SEMD 1520 data from CSV file"""
        try:
            self._download()
            df = pd.read_csv(
                self.csv_path,
                sep=";",
                parse_dates=["START_DATE", "END_DATE"],
                dayfirst=True,
            )
            # GIT_LINK - id пакета СЭМД в GitLab Минздрава (нужен schematron_monitor)
            if "GIT_LINK" not in df.columns:
                df["GIT_LINK"] = None
            # Select only needed columns
            df = df.loc[
                :,
                ["OID", "TYPE", "NAME", "START_DATE", "END_DATE", "FORMAT", "GIT_LINK"],
            ]

            # Add status column
            df["EXPIRED"] = df["END_DATE"].apply(
                lambda x: (
                    "запланирован вывод"
                    if x and x > datetime.now()
                    else ("выведен" if x and x < datetime.now() else "активно")
                )
            )
            # Подменяем целиком: читатели в других потоках видят старую или новую версию
            self.df = df
            logger.info(
                f"SEMD 1520 data loaded successfully (version {self.latest_version})"
            )
        except Exception as e:
            # Прежние данные (если были) остаются — как в SEMD638
            logger.error(f"Error loading SEMD 1520 dictionary: {e}")

    def get_dataframe(self) -> pd.DataFrame | None:
        """Current dictionary data (reloaded if a new version appeared)."""
        self._check_and_reload_if_needed()
        return self.df

    def get_semd_info(self, semd_oid) -> dict | None:
        """
        Get name and GitLab package id for a single SEMD.

        Args:
            semd_oid: SEMD OID from dictionary 1520 (e.g. "331")

        Returns:
            dict with keys OID, NAME, GIT_LINK (None if empty) or None if
            the SEMD is not found or the dictionary is not loaded.
        """
        df = self.get_dataframe()
        if df is None:
            return None

        try:
            rows = df[df["OID"] == int(semd_oid)]
        except (TypeError, ValueError):
            return None
        if rows.empty:
            return None

        row = rows.iloc[0]
        git_link = row["GIT_LINK"]
        return {
            "OID": str(semd_oid),
            "NAME": row["NAME"],
            "GIT_LINK": str(git_link).strip() if pd.notna(git_link) else None,
        }

    def get_semd_versions(self, semd_oid):
        """
        Get all SEMD versions for the document type of a specific SEMD.

        Args:
            semd_oid: SEMD OID to search for

        Returns:
            tuple: (document_name, versions_table, document_type, link_1520, link_1522, dictionary_version)
        """
        df = self.get_dataframe()
        if df is None:
            return (
                None,
                "Ошибка: не удалось загрузить данные СЭМД",
                None,
                None,
                None,
                None,
            )

        try:
            semd_type_row = df[df["OID"] == int(semd_oid)]
            if semd_type_row.empty:
                return None, f"СЭМД с OID {semd_oid} не найдена", None, None, None, None
            doc_type = semd_type_row["TYPE"].iloc[0]
        except Exception as e:
            logger.error(f"Error getting SEMD versions: {e}")
            return None, f"Ошибка при получении версий: {e}", None, None, None, None

        # Тот же снимок df: между вызовами справочник мог перезагрузиться
        return self._versions_by_type(df, doc_type)

    def get_newest_versions(self, count=1):
        """
        Get the newest SEMD versions.

        Args:
            count: Number of newest versions to return per type

        Returns:
            DataFrame with newest SEMD versions
        """
        # Check if version has been updated and reload if needed
        self._check_and_reload_if_needed()

        if self.df is None:
            return None

        try:
            newest = self.df.sort_values(
                ["TYPE", "START_DATE"], ascending=[True, False]
            )
            newest = newest.loc[newest["END_DATE"].isnull()]  # Active versions only
            newest = newest.loc[newest["FORMAT"] == 2]  # Only CDA format (skip PDF)
            newest = newest.groupby("TYPE").head(count)
            return newest
        except Exception as e:
            logger.error(f"Error getting newest SEMD versions: {e}")
            return None

    def search_by_name(
        self, query: str, limit: int | None = None, offset: int = 0
    ) -> tuple:
        """
        Search SEMD documents by name.

        Args:
            query: Search string (case-insensitive)
            limit: Maximum number of unique document types to return (None = all)
            offset: Number of results to skip (for pagination)

        Returns:
            Tuple: (results_list, total_count)
            where results_list is [(TYPE, display_name), ...]
            and total_count is total number of matching document types
        """
        self._check_and_reload_if_needed()

        if self.df is None or not query.strip():
            return [], 0

        try:
            # Case-insensitive search in NAME column
            mask = self.df["NAME"].str.contains(query, case=False, na=False)
            matches = self.df[mask].copy()

            if matches.empty:
                return [], 0

            # Group by TYPE and get one representative NAME per type
            # Take the latest version's name (highest OID within each TYPE)
            grouped = (
                matches.sort_values("OID", ascending=False).groupby("TYPE").first()
            )

            # Create result list with (TYPE, display_name)
            all_results = []
            for doc_type, row in grouped.iterrows():
                # Clean up name: remove "(CDA)" suffix
                display_name = row["NAME"].split("(CDA)")[0].strip()
                # Truncate long names for button display (max ~40 chars)
                if len(display_name) > 40:
                    display_name = display_name[:37] + "..."
                all_results.append((int(doc_type), display_name))

            # Sort by TYPE
            all_results.sort(key=lambda x: x[0])
            total_count = len(all_results)

            # Apply pagination if limit specified
            if limit is not None:
                paginated_results = all_results[offset : offset + limit]
            else:
                paginated_results = all_results[offset:] if offset else all_results

            return paginated_results, total_count

        except Exception as e:
            logger.error(f"Error searching SEMD by name: {e}")
            return [], 0

    def get_semd_versions_by_type(self, doc_type: int):
        """
        Get all SEMD versions for a specific document TYPE.

        Args:
            doc_type: Document type ID

        Returns:
            tuple: (document_name, versions_table, document_type, link_1520, link_1522, dictionary_version)
        """
        df = self.get_dataframe()
        if df is None:
            return (
                None,
                "Ошибка: не удалось загрузить данные СЭМД",
                None,
                None,
                None,
                None,
            )
        return self._versions_by_type(df, doc_type)

    def _versions_by_type(self, df: pd.DataFrame, doc_type: int):
        """Format versions of ``doc_type`` from a snapshot of the dictionary data."""
        try:
            # Find all versions for this TYPE
            semd_versions = df[df["TYPE"] == doc_type].copy()

            if semd_versions.empty:
                return None, f"СЭМД с TYPE {doc_type} не найден", None, None, None, None

            semd_versions = semd_versions.sort_values("OID")

            # Format dates
            semd_versions["START_DATE"] = semd_versions["START_DATE"].dt.strftime(
                "%d.%m.%y"
            )
            semd_versions["END_DATE"] = semd_versions["END_DATE"].dt.strftime(
                "%d.%m.%y"
            )

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
            versions_table_df = semd_versions.loc[
                :, ["OID", "START_DATE", "END_DATE"]
            ].reset_index(drop=True)
            versions_table = tabulate(
                versions_table_df,
                showindex=False,
                tablefmt="simple",
                headers=["ID", "Start", "Stop"],
            )

            return (
                name,
                versions_table,
                doc_type,
                link_1520,
                link_1522,
                self.latest_version,
            )

        except Exception as e:
            logger.error(f"Error getting SEMD versions by type: {e}")
            return None, f"Ошибка при получении версий: {e}", None, None, None, None
