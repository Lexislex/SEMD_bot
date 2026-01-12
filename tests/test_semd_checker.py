"""Tests for SEMD Checker plugin"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


class TestSEMD1520SearchByName:
    """Unit tests for SEMD1520.search_by_name()"""

    @pytest.fixture
    def mock_semd(self):
        """Create SEMD1520 instance with mocked data"""
        with patch(
            "plugins.semd_checker.semd_logic.SEMDVersionFetcher"
        ) as mock_fetcher:
            mock_fetcher.return_value.latest = "1.0"
            mock_fetcher.return_value.get_version.return_value = "1.0"

            with patch("plugins.semd_checker.semd_logic.download_file"):
                with patch("pandas.read_csv") as mock_csv:
                    # Create test DataFrame
                    mock_csv.return_value = pd.DataFrame(
                        {
                            "OID": [1, 2, 3, 4, 5, 6, 7, 8],
                            "TYPE": [1, 1, 2, 3, 4, 5, 6, 7],
                            "NAME": [
                                "Протокол осмотра v1 (CDA)",
                                "Протокол осмотра v2 (CDA)",
                                "Выписка из стационара (CDA)",
                                "Протокол операции (CDA)",
                                "Амбулаторная карта (CDA)",
                                "Рецепт на лекарство (CDA)",
                                "Направление на госпитализацию (CDA)",
                                "Справка о нетрудоспособности (CDA)",
                            ],
                            "START_DATE": [datetime.now()] * 8,
                            "END_DATE": [None] * 8,
                            "FORMAT": [2] * 8,
                        }
                    )

                    from plugins.semd_checker.semd_logic import SEMD1520

                    semd = SEMD1520()
                    yield semd

    def test_search_returns_tuple(self, mock_semd):
        """search_by_name should return (results, total_count) tuple"""
        results, total = mock_semd.search_by_name("протокол")
        assert isinstance(results, list)
        assert isinstance(total, int)

    def test_search_finds_matching_documents(self, mock_semd):
        """Should find documents containing search term"""
        results, total = mock_semd.search_by_name("протокол")
        # Should find: "Протокол осмотра" (TYPE 1) and "Протокол операции" (TYPE 3)
        assert total == 2
        assert len(results) == 2

    def test_search_case_insensitive(self, mock_semd):
        """Search should be case-insensitive"""
        results_lower, total_lower = mock_semd.search_by_name("протокол")
        results_upper, total_upper = mock_semd.search_by_name("ПРОТОКОЛ")
        results_mixed, total_mixed = mock_semd.search_by_name("ПрОтОкОл")

        assert total_lower == total_upper == total_mixed

    def test_search_groups_by_type(self, mock_semd):
        """Should return unique TYPEs, not individual records"""
        results, total = mock_semd.search_by_name("протокол")
        # TYPE 1 has 2 records but should appear once
        types = [r[0] for r in results]
        assert len(types) == len(set(types))  # All unique

    def test_search_respects_limit(self, mock_semd):
        """Should limit results to specified count"""
        results, total = mock_semd.search_by_name("а", limit=3)
        assert len(results) <= 3
        # total should reflect all matches, not limited
        assert total >= len(results)

    def test_search_respects_offset(self, mock_semd):
        """Should skip results based on offset"""
        results_page1, total1 = mock_semd.search_by_name("а", limit=2, offset=0)
        results_page2, total2 = mock_semd.search_by_name("а", limit=2, offset=2)

        assert total1 == total2  # Total should be same
        # Results should be different (if enough data)
        if len(results_page1) > 0 and len(results_page2) > 0:
            assert results_page1[0] != results_page2[0]

    def test_search_empty_query(self, mock_semd):
        """Empty query should return empty results"""
        results, total = mock_semd.search_by_name("")
        assert results == []
        assert total == 0

    def test_search_no_matches(self, mock_semd):
        """Non-matching query should return empty results"""
        results, total = mock_semd.search_by_name("несуществующий_документ_xyz")
        assert results == []
        assert total == 0

    def test_search_truncates_long_names(self, mock_semd):
        """Long names should be truncated for display"""
        # All test names are short, but verify format
        results, total = mock_semd.search_by_name("протокол")
        for doc_type, display_name in results:
            assert len(display_name) <= 40
            assert "(CDA)" not in display_name


class TestSEMD1520GetVersionsByType:
    """Unit tests for SEMD1520.get_semd_versions_by_type()"""

    @pytest.fixture
    def mock_semd(self):
        """Create SEMD1520 instance with mocked data"""
        with patch(
            "plugins.semd_checker.semd_logic.SEMDVersionFetcher"
        ) as mock_fetcher:
            mock_fetcher.return_value.latest = "1.0"
            mock_fetcher.return_value.get_version.return_value = "1.0"

            with patch("plugins.semd_checker.semd_logic.download_file"):
                with patch("pandas.read_csv") as mock_csv:
                    mock_csv.return_value = pd.DataFrame(
                        {
                            "OID": [1, 2, 3],
                            "TYPE": [1, 1, 2],
                            "NAME": [
                                "Протокол осмотра v1 (CDA)",
                                "Протокол осмотра v2 (CDA)",
                                "Выписка (CDA)",
                            ],
                            "START_DATE": pd.to_datetime(
                                ["2023-01-01", "2024-01-01", "2023-06-01"]
                            ),
                            "END_DATE": pd.to_datetime(["2023-12-31", pd.NaT, pd.NaT]),
                            "FORMAT": [2, 2, 2],
                        }
                    )

                    from plugins.semd_checker.semd_logic import SEMD1520

                    semd = SEMD1520()
                    yield semd

    def test_returns_all_versions_for_type(self, mock_semd):
        """Should return all versions for given TYPE"""
        name, versions, doc_type, *rest = mock_semd.get_semd_versions_by_type(1)
        assert name is not None
        assert doc_type == 1
        # versions table should contain both OIDs 1 and 2
        assert "1" in versions
        assert "2" in versions

    def test_returns_none_for_invalid_type(self, mock_semd):
        """Should return None for non-existent TYPE"""
        name, error, *rest = mock_semd.get_semd_versions_by_type(999)
        assert name is None
        assert "999" in error


class TestSearchResultsKeyboard:
    """Unit tests for keyboards.get_search_results_keyboard()"""

    def test_creates_buttons_for_results(self):
        """Should create button for each result"""
        from plugins.semd_checker.keyboards import get_search_results_keyboard

        results = [(1, "Doc 1"), (2, "Doc 2"), (3, "Doc 3")]
        markup = get_search_results_keyboard(results, total_count=3)

        # Should have 3 result buttons + 1 back button
        assert len(markup.keyboard) == 4

    def test_no_pagination_when_not_needed(self):
        """Should not show pagination for small result sets"""
        from plugins.semd_checker.keyboards import get_search_results_keyboard

        results = [(1, "Doc 1"), (2, "Doc 2")]
        markup = get_search_results_keyboard(results, total_count=2, page_size=5)

        # Check no pagination buttons (no semd_p: callbacks)
        all_callbacks = [btn.callback_data for row in markup.keyboard for btn in row]
        pagination_callbacks = [c for c in all_callbacks if c.startswith("semd_p:")]
        assert len(pagination_callbacks) == 0

    def test_shows_pagination_when_needed(self):
        """Should show pagination for large result sets"""
        from plugins.semd_checker.keyboards import get_search_results_keyboard

        results = [(1, "Doc 1"), (2, "Doc 2"), (3, "Doc 3")]
        markup = get_search_results_keyboard(
            results, total_count=10, current_offset=0, page_size=3
        )

        all_callbacks = [btn.callback_data for row in markup.keyboard for btn in row]
        # Should have "next" pagination button
        assert any(c.startswith("semd_p:") for c in all_callbacks)

    def test_shows_prev_button_on_later_pages(self):
        """Should show prev button when offset > 0"""
        from plugins.semd_checker.keyboards import get_search_results_keyboard

        results = [(4, "Doc 4"), (5, "Doc 5")]
        markup = get_search_results_keyboard(
            results, total_count=10, current_offset=5, page_size=5
        )

        all_callbacks = [btn.callback_data for row in markup.keyboard for btn in row]
        # Should have prev button (offset 0)
        assert "semd_p:0" in all_callbacks

    def test_callback_data_format(self):
        """Callback data should follow expected format"""
        from plugins.semd_checker.keyboards import get_search_results_keyboard

        results = [(123, "Test Doc")]
        markup = get_search_results_keyboard(results, total_count=1)

        # First button should be result with semd_t:{TYPE}
        first_btn = markup.keyboard[0][0]
        assert first_btn.callback_data == "semd_t:123"

    def test_back_button_always_present(self):
        """Back to menu button should always be present"""
        from plugins.semd_checker.keyboards import get_search_results_keyboard

        results = [(1, "Doc")]
        markup = get_search_results_keyboard(results, total_count=1)

        all_callbacks = [btn.callback_data for row in markup.keyboard for btn in row]
        assert "back_to_menu" in all_callbacks
