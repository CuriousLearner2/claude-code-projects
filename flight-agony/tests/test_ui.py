"""
tests/test_ui.py

Headless UI tests for web/app.py using Streamlit's AppTest framework.
No browser or running server required — tests run in-process via pytest.

Coverage:
  - App startup and widget presence
  - Form validation (empty fields, bad dates, missing API key)
  - Search results rendering with mocked API responses
  - Score range sanity (all scores 0–100)
  - Empty results handling
  - City/airport name → IATA code resolution (_resolve_iata)

NOT covered here (see manual checklist in PRD.md §10.6):
  - Plotly chart rendering
  - Row-click breakdown interaction
  - Score color-band visual appearance
"""

import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from streamlit.testing.v1 import AppTest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

APP_PATH = str(Path(__file__).parent.parent / "web" / "app.py")
WEB_DIR  = str(Path(__file__).parent.parent / "web")

# Make web/ importable so we can unit-test _resolve_iata directly.
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

# ---------------------------------------------------------------------------
# Fixture: minimal Duffel offers
# ---------------------------------------------------------------------------

def _seg(dep, arr, orig, dest, carrier="BA") -> dict:
    return {
        "departing_at":    dep,
        "arriving_at":     arr,
        "origin":          {"iata_code": orig},
        "destination":     {"iata_code": dest},
        "operating_carrier": {"iata_code": carrier},
    }


def _offer(
    out_dep="2026-06-15T09:00:00",
    out_arr="2026-06-15T17:00:00",
    ret_dep="2026-06-22T10:00:00",
    ret_arr="2026-06-22T18:00:00",
    carrier="BA",
    amount="450.00",
    currency="USD",
    out_dur="PT8H00M",
    ret_dur="PT8H00M",
) -> dict:
    return {
        "slices": [
            {
                "segments": [_seg(out_dep, out_arr, "JFK", "LHR", carrier)],
                "duration": out_dur,
            },
            {
                "segments": [_seg(ret_dep, ret_arr, "LHR", "JFK", carrier)],
                "duration": ret_dur,
            },
        ],
        "total_amount":   amount,
        "total_currency": currency,
    }


# Two distinct itineraries: one nonstop BA (8h), one cheaper but slower AA (10h).
# The AA offer must use out_dur/ret_dur="PT10H00M" so that _process_offers computes
# the correct journey-time penalty (otherwise both get 0 pts since _process_offers
# reads the `duration` field, not the actual dep/arr timestamps).
MOCK_OFFERS = [
    _offer(carrier="BA", amount="450.00"),
    _offer(
        out_dep="2026-06-15T07:00:00",
        out_arr="2026-06-15T17:00:00",
        ret_dep="2026-06-22T08:00:00",
        ret_arr="2026-06-22T18:00:00",
        carrier="AA",
        amount="310.00",
        out_dur="PT10H00M",
        ret_dur="PT10H00M",
    ),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _app() -> AppTest:
    return AppTest.from_file(APP_PATH, default_timeout=20)


def _fill_valid_form(at: AppTest) -> AppTest:
    """Populate origin, destination, and valid dates.

    AppTest orders widgets by area (main before sidebar), so despite the sidebar
    code appearing first in app.py, the actual indices are:
      text_input[0] = From (main)
      text_input[1] = To (main)
      text_input[2] = Extra chaotic hubs (sidebar)
    """
    at.text_input[0].set_value("JFK")   # From
    at.text_input[1].set_value("LHR")   # To
    at.date_input[0].set_value(date(2026, 6, 15))   # Depart
    at.date_input[1].set_value(date(2026, 6, 22))   # Return
    return at


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

class TestAppStartup:
    def test_renders_without_error(self):
        at = _app().run()
        assert not at.exception

    def test_search_button_present(self):
        at = _app().run()
        assert len(at.button) == 1
        assert at.button[0].label == "Search flights"

    def test_preference_sliders_present(self):
        at = _app().run()
        # slider[0] = layover sweet spot, slider[1] = connection weight
        assert len(at.slider) == 2

    def test_penalty_checkboxes_present_and_default_on(self):
        at = _app().run()
        # 4 penalty checkboxes, all default True
        assert len(at.checkbox) == 4
        assert all(cb.value for cb in at.checkbox)

    def test_text_inputs_present(self):
        at = _app().run()
        # extra_hubs (sidebar), From, To
        assert len(at.text_input) == 3


# ---------------------------------------------------------------------------
# Form validation
# ---------------------------------------------------------------------------

class TestFormValidation:
    def test_empty_origin_and_destination_warns(self):
        at = _app().run()
        # Click search with no origin or destination filled in
        at.button[0].click().run()
        assert len(at.warning) > 0

    def test_empty_origin_only_warns(self):
        at = _app().run()
        at.text_input[1].set_value("LHR")  # To is set; From (index 0) left empty
        at.button[0].click().run()
        assert len(at.warning) > 0

    def test_return_before_departure_warns(self):
        at = _app().run()
        at.text_input[1].set_value("JFK")
        at.text_input[2].set_value("LHR")
        at.date_input[0].set_value(date(2026, 6, 22))  # depart later
        at.date_input[1].set_value(date(2026, 6, 15))  # return earlier
        at.button[0].click().run()
        assert len(at.warning) > 0

    def test_missing_api_key_shows_error(self):
        env = {k: v for k, v in os.environ.items() if k != "DUFFEL_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            at = _app().run()
            _fill_valid_form(at)
            at.button[0].click().run()
        assert len(at.error) > 0

    def test_missing_api_key_no_traceback(self):
        """Error state must not surface an unhandled exception."""
        env = {k: v for k, v in os.environ.items() if k != "DUFFEL_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            at = _app().run()
            _fill_valid_form(at)
            at.button[0].click().run()
        assert not at.exception


# ---------------------------------------------------------------------------
# Search results (mocked API)
# ---------------------------------------------------------------------------

class TestSearchResults:
    """
    Patch search_flights.search_flights so no real Duffel call is made.
    AppTest re-executes the app script on each run(), which re-imports
    search_flights — the patch is active for the whole test body.
    """

    @pytest.fixture(autouse=True)
    def mock_search(self):
        with patch("search_flights.search_flights", return_value=MOCK_OFFERS):
            with patch.dict(os.environ, {"DUFFEL_API_KEY": "duffel_test_fake"}):
                yield

    def _run_search(self) -> AppTest:
        at = _app().run()
        _fill_valid_form(at)
        at.button[0].click().run()
        return at

    def test_results_table_renders(self):
        at = self._run_search()
        assert not at.exception
        assert len(at.dataframe) == 1

    def test_results_table_has_expected_columns(self):
        at = self._run_search()
        df = at.dataframe[0].value
        expected = {"Rank", "Airline(s)", "Outbound", "Return",
                    "Agony ↑", "Why ↑", "Agony ↓", "Why ↓", "Avg", "Price"}
        assert expected == set(df.columns)

    def test_results_sorted_by_avg_ascending(self):
        at = self._run_search()
        avgs = at.dataframe[0].value["Avg"].tolist()
        assert avgs == sorted(avgs)

    def test_scores_are_in_valid_range(self):
        at = self._run_search()
        df = at.dataframe[0].value
        for col in ("Agony ↑", "Agony ↓", "Avg"):
            assert df[col].between(0, 100).all(), f"{col} out of 0–100 range"

    def test_summary_text_rendered(self):
        at = self._run_search()
        # The best-pick summary is rendered as st.markdown
        all_md = " ".join(m.value for m in at.markdown)
        assert "Best pick" in all_md

    def test_empty_results_shows_info(self):
        with patch("search_flights.search_flights", return_value=[]):
            with patch.dict(os.environ, {"DUFFEL_API_KEY": "duffel_test_fake"}):
                at = _app().run()
                _fill_valid_form(at)
                at.button[0].click().run()
        assert len(at.info) > 0

    def test_no_exception_on_valid_search(self):
        at = self._run_search()
        assert not at.exception

    def test_results_persist_after_rerun(self):
        """Results table must survive a rerun (e.g. from selectbox change).

        The selectbox fires a rerun without re-clicking Search — the results
        block must still be visible from session state.
        """
        at = self._run_search()
        assert len(at.dataframe) == 1  # results present after search

        at.run()  # simulate a selectbox-driven rerun without clicking Search
        assert not at.exception
        assert len(at.dataframe) == 1  # results must still be present

    def test_row_selection_shows_breakdown(self):
        """Choosing a row in the 'Score breakdown for:' selectbox shows the breakdown.

        Uses AppTest's selectbox API to pick the first real option (index 1,
        since index 0 is the '— select a flight —' placeholder), then verifies
        the Score breakdown subheader appears.
        """
        at = self._run_search()
        # The selectbox is the last one added; find it by label.
        breakdown_sb = next(s for s in at.selectbox if "breakdown" in s.label.lower())
        # options[0] = placeholder, options[1] = first real row label
        first_option = breakdown_sb.options[1]
        breakdown_sb.set_value(first_option).run()
        assert not at.exception
        assert len(at.dataframe) == 1  # results table still present
        subheaders = [s.value for s in at.subheader]
        assert any("Score breakdown" in s for s in subheaders)

    def test_row_selection_shows_correct_rank(self):
        """Selecting row N must display 'rank N' in the breakdown heading.

        Guards against off-by-one bugs in the row_labels index lookup and ensures
        the breakdown content belongs to the selected row, not an adjacent one.
        """
        at = self._run_search()
        breakdown_sb = next(s for s in at.selectbox if "breakdown" in s.label.lower())

        # Select the first real option (rank 1).
        breakdown_sb.set_value(breakdown_sb.options[1]).run()
        assert not at.exception
        headings = [s.value for s in at.subheader]
        assert any("rank 1" in s for s in headings), (
            f"Expected 'rank 1' in subheaders after selecting options[1]: {headings}"
        )

        # Select the second real option (rank 2).
        breakdown_sb = next(s for s in at.selectbox if "breakdown" in s.label.lower())
        breakdown_sb.set_value(breakdown_sb.options[2]).run()
        assert not at.exception
        headings = [s.value for s in at.subheader]
        assert any("rank 2" in s for s in headings), (
            f"Expected 'rank 2' in subheaders after selecting options[2]: {headings}"
        )

    def test_selecting_different_rows_changes_breakdown(self):
        """Switching the selectbox from row 1 to row 2 must update the heading.

        Confirms that selecting a different option changes the displayed breakdown
        heading, ruling out stale rendering where the first row's data is shown
        regardless of which option is picked.
        """
        at = self._run_search()
        breakdown_sb = next(s for s in at.selectbox if "breakdown" in s.label.lower())

        breakdown_sb.set_value(breakdown_sb.options[1]).run()
        heading_row1 = next(
            (s.value for s in at.subheader if "Score breakdown" in s.value), None
        )

        breakdown_sb = next(s for s in at.selectbox if "breakdown" in s.label.lower())
        breakdown_sb.set_value(breakdown_sb.options[2]).run()
        heading_row2 = next(
            (s.value for s in at.subheader if "Score breakdown" in s.value), None
        )

        assert heading_row1 is not None, "No breakdown heading after selecting row 1"
        assert heading_row2 is not None, "No breakdown heading after selecting row 2"
        assert heading_row1 != heading_row2, (
            f"Breakdown heading did not change: row1='{heading_row1}', row2='{heading_row2}'"
        )

    def test_preferences_affect_scores(self):
        """Sidebar preference controls must actually change the computed scores.

        Guards against wire-up bugs such as hardcoded defaults being passed to
        Preferences() instead of using the widget values (e.g., `airport_penalty=True`
        instead of `airport_penalty=airport_penalty`).

        Strategy: disable the time penalty checkbox.  The mock offers have one slower
        itinerary that WOULD receive a time penalty under default prefs.  With the
        penalty disabled, both itineraries should score equally on the time factor —
        so the slower offer's avg score must be lower than with the penalty on.
        """
        # Run with default prefs (time penalty ON).
        at_default = self._run_search()
        avgs_default = at_default.dataframe[0].value["Avg"].tolist()
        # The slower AA offer should have a higher avg when time penalty is active.
        assert max(avgs_default) > min(avgs_default), (
            "Precondition: default prefs should produce at least two distinct avg scores"
        )

        # Run with time penalty OFF.
        at_no_time = _app().run()
        _fill_valid_form(at_no_time)
        # checkbox[3] = Journey time penalty (index 0=airport, 1=interline, 2=redeye, 3=time)
        at_no_time.checkbox[3].set_value(False)
        at_no_time.button[0].click().run()
        assert not at_no_time.exception
        avgs_no_time = at_no_time.dataframe[0].value["Avg"].tolist()

        # With no time penalty, the gap between the two options must be smaller.
        spread_default = max(avgs_default) - min(avgs_default)
        spread_no_time = max(avgs_no_time) - min(avgs_no_time)
        assert spread_no_time < spread_default, (
            f"Disabling time penalty should narrow the avg-score spread "
            f"(default spread {spread_default:.1f} → no-time-penalty spread {spread_no_time:.1f}). "
            "This failure suggests the time_penalty checkbox is not wired to Preferences()."
        )

    def test_re_search_clears_breakdown_selection(self):
        """A new search must clear any stale row selection from the prior search.

        Without the fix, the stale breakdown_selector label persists across searches.
        If that label is absent from the new search's row_labels, row_labels.index()
        raises ValueError and crashes the results block.  Even if the label happens
        to match, the wrong row's breakdown would be shown.
        """
        at = self._run_search()
        breakdown_sb = next(s for s in at.selectbox if "breakdown" in s.label.lower())

        # Select a row so breakdown_selector is populated.
        breakdown_sb.set_value(breakdown_sb.options[1]).run()
        assert any("Score breakdown" in s.value for s in at.subheader), (
            "Precondition failed: breakdown must appear after first row selection"
        )

        # Perform a second search (same fields, mock returns same offers).
        # The breakdown_selector must be cleared regardless of whether labels match.
        at.button[0].click().run()
        assert not at.exception

        breakdown_sb = next(s for s in at.selectbox if "breakdown" in s.label.lower())
        assert breakdown_sb.value == "", (
            f"breakdown_selector not cleared after new search: '{breakdown_sb.value}'"
        )
        assert not any("Score breakdown" in s.value for s in at.subheader), (
            "Stale breakdown still visible after new search"
        )


# ---------------------------------------------------------------------------
# IATA resolution
# ---------------------------------------------------------------------------

class TestResolveIata:
    """Unit tests for _resolve_iata() — the city/airport-name → IATA helper.

    These tests import the function directly rather than going through AppTest
    so they run fast and give precise failure messages.
    """

    @pytest.fixture(autouse=True)
    def _import(self):
        import app as _app_module
        self.resolve = _app_module._resolve_iata

    def test_three_letter_code_passthrough(self):
        assert self.resolve("JFK") == "JFK"
        assert self.resolve("lhr") == "LHR"

    def test_override_table_london(self):
        # London → LON metro (covers LHR, LGW, STN, LCY, LTN)
        assert self.resolve("London") == "LON"

    def test_override_table_paris(self):
        # Paris → PAR metro (covers CDG, ORY)
        assert self.resolve("Paris") == "PAR"

    def test_override_table_new_york(self):
        # New York → NYC metro (covers JFK, EWR, LGA)
        assert self.resolve("New York") == "NYC"

    def test_override_table_tokyo(self):
        # Tokyo → TYO metro (covers NRT, HND)
        assert self.resolve("Tokyo") == "TYO"

    def test_override_table_sydney(self):
        assert self.resolve("Sydney") == "SYD"

    def test_override_table_chicago(self):
        # Chicago → CHI metro (covers ORD, MDW)
        assert self.resolve("Chicago") == "CHI"

    def test_override_case_insensitive(self):
        assert self.resolve("london") == "LON"
        assert self.resolve("LONDON") == "LON"
        assert self.resolve("LoNdOn") == "LON"

    def test_csv_fallback_returns_string(self):
        # San Francisco is not in the override table; must resolve via airports.csv
        result = self.resolve("San Francisco")
        assert result == "SFO"

    def test_unknown_city_uppercases_raw(self):
        # Gibberish city with no CSV match → raw uppercase (graceful degradation)
        result = self.resolve("Xyznotacity")
        assert result == "XYZNOTACITY"


# ---------------------------------------------------------------------------
# Score color banding — _score_bg boundary conditions
# ---------------------------------------------------------------------------

class TestScoreBg:
    """
    _score_bg is a module-level pure function in app.py that applies CSS color
    to Agony score cells in the results table.

    Spec (SPEC.md §13.2):
      0–30   → green   (background #d4edda)
      31–60  → amber   (background #fff3cd)
      61–100 → red     (background #f8d7da)

    These tests pin the exact boundary values and guard against < vs ≤ off-by-one
    bugs that would silently miscolor every result row at score 30 or 60.

    Placed after TestResolveIata (which also imports app directly) so the
    direct `import app` here does not pollute Streamlit state before AppTest runs.
    """

    @pytest.fixture(autouse=True)
    def _import_score_bg(self):
        import app as _app_mod
        self.score_bg = _app_mod._score_bg

    def test_zero_is_green(self):
        assert "d4edda" in self.score_bg(0)

    def test_30_is_green(self):
        """Score 30 is the upper boundary of the green band — must still be green."""
        assert "d4edda" in self.score_bg(30)

    def test_31_is_amber(self):
        """Score 31 crosses into amber — must NOT be green."""
        assert "fff3cd" in self.score_bg(31)
        assert "d4edda" not in self.score_bg(31)

    def test_60_is_amber(self):
        """Score 60 is the upper boundary of amber."""
        assert "fff3cd" in self.score_bg(60)

    def test_61_is_red(self):
        """Score 61 crosses into red — must NOT be amber."""
        assert "f8d7da" in self.score_bg(61)
        assert "fff3cd" not in self.score_bg(61)

    def test_100_is_red(self):
        assert "f8d7da" in self.score_bg(100)

    def test_non_numeric_returns_empty_string(self):
        """Non-numeric values (text columns like Airline(s)) must produce no style."""
        assert self.score_bg("BA") == ""
        assert self.score_bg(None) == ""
