"""
Unit tests for Flight Agony scoring functions.

All tests run without an Amadeus API key — every function under test is pure
(takes structured dicts, returns a value) with no network I/O.

Run with:
    cd flight-agony
    pytest tests/
"""

import pytest
import sys
from pathlib import Path

# Make the scripts package importable without installing it.
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from search_flights import (
    DANGEROUS_BELOW,
    LONG_ABOVE,
    BASE_DANGEROUS,
    BASE_LONG,
    MAX_PER_CNX,
    MOD_CHAOTIC,
    MOD_INTERLINE,
    Preferences,
    parse_duration,
    layover_base_score,
    connection_score,
    is_redeye,
    agony_score,
    _agony_breakdown,
    _process_offers,
    _tradeoff_summary,
    carrier_code,
)


# ---------------------------------------------------------------------------
# Helpers — minimal segment / itinerary dicts that satisfy the scorer
# ---------------------------------------------------------------------------

def _seg(dep_at: str, arr_at: str, carrier: str = "AA", arr_airport: str = "BOS") -> dict:
    """Return a minimal Duffel segment dict."""
    return {
        "departing_at":     dep_at,
        "arriving_at":      arr_at,
        "origin":           {"iata_code": "JFK"},
        "destination":      {"iata_code": arr_airport},
        "operating_carrier": {"iata_code": carrier},
    }


def _itinerary(segments: list, duration: str) -> dict:
    """Return a minimal Duffel slice dict."""
    return {"segments": segments, "duration": duration}


def _result(carriers="AA", out_score=0, ret_score=0, price_amount=500.0, why="Clean routing") -> dict:
    """Return a minimal result dict matching what _process_offers() produces."""
    avg = (out_score + ret_score) / 2.0
    return {
        "carriers":     carriers,
        "out_leg":      "9:00am → 5:00pm (8h00m, nonstop)",
        "ret_leg":      "10:00am → 6:00pm (8h00m, nonstop)",
        "out_score":    out_score,
        "ret_score":    ret_score,
        "avg_score":    avg,
        "out_why":      why,
        "ret_why":      "Clean routing",
        "why":          f"Out: {why}  |  Ret: Clean routing",
        "price":        f"USD {price_amount:.2f}",
        "price_amount": price_amount,
    }


# ---------------------------------------------------------------------------
# parse_duration
# ---------------------------------------------------------------------------

class TestParseDuration:
    def test_hours_and_minutes(self):
        assert parse_duration("PT2H30M") == pytest.approx(2.5)

    def test_minutes_only(self):
        assert parse_duration("PT45M") == pytest.approx(0.75)

    def test_hours_only(self):
        assert parse_duration("PT7H") == pytest.approx(7.0)

    def test_multi_day(self):
        assert parse_duration("P1DT2H30M") == pytest.approx(26.5)

    def test_zero(self):
        assert parse_duration("PT0M") == pytest.approx(0.0)

    def test_long_haul(self):
        # 14h 05m
        assert parse_duration("PT14H05M") == pytest.approx(14 + 5 / 60)


# ---------------------------------------------------------------------------
# layover_base_score — default sweet spot 90–180 min
# ---------------------------------------------------------------------------

class TestLayoverBaseScore:
    """U-shaped curve: 0 inside sweet spot, rises to extremes at both ends."""

    @pytest.fixture
    def prefs(self):
        return Preferences()  # sweet_spot_min=90, sweet_spot_max=180

    def test_at_dangerous_floor(self, prefs):
        assert layover_base_score(DANGEROUS_BELOW, prefs) == BASE_DANGEROUS  # 18

    def test_below_dangerous_floor(self, prefs):
        assert layover_base_score(30, prefs) == BASE_DANGEROUS  # still 18

    def test_midpoint_tight_zone(self, prefs):
        # Midpoint of 45→90: t = (67.5-45)/(90-45) = 0.5, score = 18*(1-0.5) = 9
        assert layover_base_score(67, prefs) == pytest.approx(BASE_DANGEROUS * (1 - (67 - 45) / (90 - 45)), abs=0.5)

    def test_at_sweet_spot_min(self, prefs):
        assert layover_base_score(90, prefs) == 0.0

    def test_inside_sweet_spot(self, prefs):
        assert layover_base_score(135, prefs) == 0.0

    def test_at_sweet_spot_max(self, prefs):
        assert layover_base_score(180, prefs) == 0.0

    def test_midpoint_long_zone(self, prefs):
        # Midpoint of 180→360: t = (270-180)/(360-180) = 0.5, score = 12*0.5 = 6
        assert layover_base_score(270, prefs) == pytest.approx(6.0, abs=0.01)

    def test_at_long_floor(self, prefs):
        assert layover_base_score(LONG_ABOVE, prefs) == BASE_LONG  # 12

    def test_above_long_floor(self, prefs):
        assert layover_base_score(400, prefs) == BASE_LONG  # still 12

    def test_custom_sweet_spot(self):
        prefs = Preferences(sweet_spot_min=120, sweet_spot_max=240)
        assert layover_base_score(120, prefs) == 0.0
        assert layover_base_score(180, prefs) == 0.0
        assert layover_base_score(240, prefs) == 0.0
        # 90 min is below sweet_spot_min=120 so should score > 0
        assert layover_base_score(90, prefs) > 0


# ---------------------------------------------------------------------------
# connection_score
# ---------------------------------------------------------------------------

class TestConnectionScore:
    """Per-connection scoring: layover base + optional modifiers, capped at 25."""

    @pytest.fixture
    def prefs(self):
        return Preferences()

    def _cnx(self, arr_at, dep_at, arr_airport="BOS", c_before="AA", c_after="AA"):
        """Build the two segments that bracket a connection."""
        before = _seg("2026-06-15T10:00", arr_at, carrier=c_before, arr_airport=arr_airport)
        after  = _seg(dep_at, "2026-06-15T20:00", carrier=c_after)
        return before, after

    def test_sweet_spot_same_carrier_non_chaotic(self, prefs):
        before, after = self._cnx("2026-06-15T12:00", "2026-06-15T13:30")  # 90 min
        score, _ = connection_score(before, after, prefs)
        assert score == 0.0

    def test_chaotic_hub_adds_modifier(self, prefs):
        before, after = self._cnx("2026-06-15T12:00", "2026-06-15T13:30", arr_airport="ORD")
        score, why = connection_score(before, after, prefs)
        assert score == MOD_CHAOTIC  # base=0 + 5 chaotic
        assert "chaotic hub" in why

    def test_interline_adds_modifier(self, prefs):
        before, after = self._cnx("2026-06-15T12:00", "2026-06-15T13:30",
                                   c_before="AA", c_after="UA")
        score, why = connection_score(before, after, prefs)
        assert score == MOD_INTERLINE  # base=0 + 5 interline
        assert "interline" in why

    def test_both_modifiers(self, prefs):
        before, after = self._cnx("2026-06-15T12:00", "2026-06-15T13:30",
                                   arr_airport="ORD", c_before="AA", c_after="UA")
        score, _ = connection_score(before, after, prefs)
        assert score == MOD_CHAOTIC + MOD_INTERLINE  # 10

    def test_tight_layover_at_chaotic_hub(self, prefs):
        # 30-min layover at ORD, same carrier — base=18 + chaotic=5 = 23, weight 1.0 → 23
        before, after = self._cnx("2026-06-15T12:00", "2026-06-15T12:30", arr_airport="ORD")
        score, why = connection_score(before, after, prefs)
        assert score == pytest.approx(min(MAX_PER_CNX, (BASE_DANGEROUS + MOD_CHAOTIC) * 1.0), abs=0.01)
        assert "dangerous cnx" in why
        assert "chaotic hub" in why

    def test_cap_at_max_per_connection(self, prefs):
        # base=18 + chaotic=5 + interline=5 = 28, should be capped at 25
        before, after = self._cnx("2026-06-15T12:00", "2026-06-15T12:30",
                                   arr_airport="ORD", c_before="AA", c_after="UA")
        score, _ = connection_score(before, after, prefs)
        assert score == MAX_PER_CNX

    def test_connection_weight_zero(self):
        prefs = Preferences(connection_weight=0.0)
        before, after = self._cnx("2026-06-15T12:00", "2026-06-15T12:30",
                                   arr_airport="ORD", c_before="AA", c_after="UA")
        score, _ = connection_score(before, after, prefs)
        assert score == 0.0

    def test_connection_weight_doubles_score(self, prefs):
        prefs2 = Preferences(connection_weight=2.0)
        before, after = self._cnx("2026-06-15T12:00", "2026-06-15T13:30",
                                   arr_airport="ORD")  # base=0 + chaotic=5, weight 2 → 10
        score, _ = connection_score(before, after, prefs2)
        assert score == MOD_CHAOTIC * 2.0

    def test_no_airport_penalty_flag(self):
        prefs = Preferences(airport_penalty=False)
        before, after = self._cnx("2026-06-15T12:00", "2026-06-15T13:30", arr_airport="ORD")
        score, _ = connection_score(before, after, prefs)
        assert score == 0.0  # chaotic suppressed; base=0

    def test_no_interline_penalty_flag(self):
        prefs = Preferences(interline_penalty=False)
        before, after = self._cnx("2026-06-15T12:00", "2026-06-15T13:30",
                                   c_before="AA", c_after="UA")
        score, _ = connection_score(before, after, prefs)
        assert score == 0.0  # interline suppressed; base=0

    def test_extra_chaotic_hub(self):
        prefs = Preferences(extra_chaotic_airports=frozenset({"LHR"}))
        before, after = self._cnx("2026-06-15T12:00", "2026-06-15T13:30", arr_airport="LHR")
        score, why = connection_score(before, after, prefs)
        assert score == MOD_CHAOTIC
        assert "chaotic hub" in why


# ---------------------------------------------------------------------------
# is_redeye
# ---------------------------------------------------------------------------

class TestIsRedeye:
    @pytest.mark.parametrize("dep_at,expected", [
        ("2026-06-15T23:00", True),   # exactly 11pm
        ("2026-06-15T23:59", True),   # late night
        ("2026-06-16T00:00", True),   # midnight
        ("2026-06-15T04:59", True),   # just before 5am
        ("2026-06-15T05:00", False),  # exactly 5am — not a red-eye
        ("2026-06-15T06:00", False),  # morning
        ("2026-06-15T14:00", False),  # afternoon
        ("2026-06-15T22:59", False),  # just before 11pm
    ])
    def test_boundary(self, dep_at, expected):
        assert is_redeye(dep_at) == expected


# ---------------------------------------------------------------------------
# agony_score — whole-leg scenarios
# ---------------------------------------------------------------------------

class TestAgonyScore:
    @pytest.fixture
    def prefs(self):
        return Preferences()

    def _nonstop_itin(self, dep_at="2026-06-15T09:00", arr_at="2026-06-15T17:00",
                      duration="PT8H") -> dict:
        return _itinerary([_seg(dep_at, arr_at)], duration)

    def test_nonstop_daytime_fastest(self, prefs):
        itin = self._nonstop_itin()
        score, why = agony_score(itin, min_duration_hours=8.0, prefs=prefs)
        assert score == 0
        assert why == "Clean routing"

    def test_nonstop_redeye(self, prefs):
        itin = self._nonstop_itin(dep_at="2026-06-15T23:30", arr_at="2026-06-16T07:30")
        score, why = agony_score(itin, min_duration_hours=8.0, prefs=prefs)
        assert score == 10
        assert "red-eye" in why

    def test_nonstop_redeye_suppressed(self):
        prefs = Preferences(redeye_penalty=False)
        itin = self._nonstop_itin(dep_at="2026-06-15T23:30", arr_at="2026-06-16T07:30")
        score, _ = agony_score(itin, min_duration_hours=8.0, prefs=prefs)
        assert score == 0

    def test_journey_time_penalty_25pct_slower(self, prefs):
        # 25% slower than fastest → 5 pts
        itin = self._nonstop_itin(duration="PT10H")
        score, why = agony_score(itin, min_duration_hours=8.0, prefs=prefs)
        assert score == 5
        assert "slow routing" in why

    def test_journey_time_penalty_50pct_slower(self, prefs):
        # 50% slower → 10 pts
        itin = self._nonstop_itin(duration="PT12H")
        score, why = agony_score(itin, min_duration_hours=8.0, prefs=prefs)
        assert score == 10

    def test_journey_time_penalty_capped_at_20(self, prefs):
        # 200% slower — penalty capped at 20 pts
        itin = self._nonstop_itin(duration="PT24H")
        score, _ = agony_score(itin, min_duration_hours=8.0, prefs=prefs)
        assert score == 20

    def test_journey_time_suppressed(self):
        prefs = Preferences(time_penalty=False)
        itin = self._nonstop_itin(duration="PT24H")
        score, _ = agony_score(itin, min_duration_hours=8.0, prefs=prefs)
        assert score == 0

    def test_one_stop_sweet_spot_layover(self, prefs):
        segs = [
            _seg("2026-06-15T09:00", "2026-06-15T11:00"),  # arrive 11:00
            _seg("2026-06-15T12:30", "2026-06-15T17:00"),  # depart 12:30 → 90-min layover
        ]
        itin = _itinerary(segs, "PT8H")
        score, _ = agony_score(itin, min_duration_hours=8.0, prefs=prefs)
        assert score == 0

    def test_one_stop_tight_layover_at_ord(self, prefs):
        segs = [
            _seg("2026-06-15T09:00", "2026-06-15T11:00", arr_airport="ORD"),
            _seg("2026-06-15T11:30", "2026-06-15T17:00"),  # 30-min layover
        ]
        itin = _itinerary(segs, "PT8H")
        score, why = agony_score(itin, min_duration_hours=8.0, prefs=prefs)
        # base=18 + chaotic=5 = 23, capped at 25
        assert score == min(MAX_PER_CNX, BASE_DANGEROUS + MOD_CHAOTIC)
        assert "dangerous cnx" in why
        assert "chaotic hub" in why

    def test_overall_score_capped_at_100(self, prefs):
        # Three tight interline connections at chaotic hubs + red-eye + slow routing.
        # Math: 3 connections × 25 pts (capped) + 20 time + 10 redeye = 105 → capped at 100.
        segs = [
            _seg("2026-06-15T23:00", "2026-06-16T01:00", carrier="AA", arr_airport="ORD"),
            _seg("2026-06-16T01:30", "2026-06-16T03:00", carrier="UA", arr_airport="ATL"),
            _seg("2026-06-16T03:30", "2026-06-16T05:00", carrier="DL", arr_airport="EWR"),
            _seg("2026-06-16T05:30", "2026-06-16T10:00", carrier="B6"),
        ]
        itin = _itinerary(segs, "PT24H")
        score, _ = agony_score(itin, min_duration_hours=8.0, prefs=prefs)
        assert score == 100


# ---------------------------------------------------------------------------
# Preferences validation
# ---------------------------------------------------------------------------

class TestPreferencesValidation:
    """__post_init__ should raise ValueError on invalid inputs."""

    @pytest.mark.parametrize("kwargs,match", [
        ({"sweet_spot_min": 45},          "sweet-spot-min"),
        ({"sweet_spot_min": 44},          "sweet-spot-min"),
        ({"sweet_spot_max": 361},          "sweet-spot-max"),
        ({"sweet_spot_min": 90, "sweet_spot_max": 90},  "sweet-spot-max"),
        ({"sweet_spot_min": 100, "sweet_spot_max": 90}, "sweet-spot-max"),
        ({"connection_weight": -0.1},     "connection-weight"),
        ({"connection_weight": 2.1},      "connection-weight"),
        ({"extra_chaotic_airports": frozenset({"LHRX"})}, "LHRX"),
        ({"extra_chaotic_airports": frozenset({"LH"})},   "LH"),
    ])
    def test_invalid_raises(self, kwargs, match):
        with pytest.raises(ValueError, match=match):
            Preferences(**kwargs)

    @pytest.mark.parametrize("kwargs", [
        {"sweet_spot_min": 46},
        {"sweet_spot_max": 360},
        {"connection_weight": 0.0},
        {"connection_weight": 2.0},
        {"extra_chaotic_airports": frozenset({"LHR", "MAN"})},
    ])
    def test_valid_passes(self, kwargs):
        Preferences(**kwargs)  # should not raise

    def test_extra_chaotic_hubs_normalised_to_uppercase(self):
        prefs = Preferences(extra_chaotic_airports=frozenset({"lhr", "man"}))
        assert "LHR" in prefs.extra_chaotic_airports
        assert "MAN" in prefs.extra_chaotic_airports

    def test_multiple_violations_reported_together(self):
        with pytest.raises(ValueError) as exc_info:
            Preferences(sweet_spot_min=45, connection_weight=3.0)
        msg = str(exc_info.value)
        assert "sweet-spot-min" in msg
        assert "connection-weight" in msg


# ---------------------------------------------------------------------------
# _tradeoff_summary
# ---------------------------------------------------------------------------

class TestTradeoffSummary:
    def test_best_is_not_cheapest(self):
        results = [
            _result("BA", out_score=0,  ret_score=0,  price_amount=600.0),  # best agony
            _result("AA", out_score=20, ret_score=20, price_amount=350.0,
                    why="Out: tight cnx ORD  |  Ret: tight cnx ORD"),       # cheaper but worse
        ]
        summary = _tradeoff_summary(results)
        assert "AA" in summary
        assert "cheaper" in summary.lower() or "%" in summary

    def test_runner_up_lopsided_legs(self):
        results = [
            _result("BA", out_score=0,  ret_score=0,  price_amount=600.0),
            _result("AA", out_score=40, ret_score=10, price_amount=590.0,
                    why="Out: red-eye; tight cnx ORD  |  Ret: clean"),
        ]
        summary = _tradeoff_summary(results)
        assert "outbound" in summary.lower()
        assert "AA" in summary

    def test_fallback_names_worst(self):
        results = [
            _result("BA", out_score=0,  ret_score=0,  price_amount=500.0),
            _result("AA", out_score=60, ret_score=55, price_amount=510.0,
                    why="Out: 3 stops; red-eye  |  Ret: 2 stops"),
        ]
        summary = _tradeoff_summary(results)
        assert "AA" in summary
        assert "57" in summary or "57.5" in summary or "agoniz" in summary.lower()

    def test_single_result_returns_empty(self):
        results = [_result("BA", 0, 0)]
        assert _tradeoff_summary(results) == ""


# ---------------------------------------------------------------------------
# _agony_breakdown — per-factor decomposition used by the stacked bar chart
# ---------------------------------------------------------------------------

class TestAgonyBreakdown:
    """
    _agony_breakdown mirrors agony_score but tracks how many points each factor
    contributed rather than returning a single total.

    Key invariant: for a given leg, the per-factor breakdown values must sum to
    the same connection+time+redeye total used inside agony_score, BEFORE the
    100-cap is applied.  (The 100-cap is intentionally NOT applied to the
    breakdown so the chart can show the raw driver contributions even when the
    headline score is capped.)

    A separate implementation of the same math is a maintenance risk: a bug in
    either function that isn't caught here could make the chart bars disagree
    with the headline score.
    """

    @pytest.fixture
    def prefs(self):
        return Preferences()

    def _nonstop_itinerary(self, dep="2026-06-15T09:00:00", arr="2026-06-15T17:00:00",
                           carrier="BA", arr_airport="LHR", duration="PT8H00M") -> dict:
        seg = {
            "departing_at":     dep,
            "arriving_at":      arr,
            "origin":           {"iata_code": "JFK"},
            "destination":      {"iata_code": arr_airport},
            "operating_carrier": {"iata_code": carrier},
        }
        return {"segments": [seg], "duration": duration}

    def _one_stop_itinerary(self, layover_mins=120, connect_airport="BOS",
                            carrier1="BA", carrier2="BA") -> dict:
        """Two segments with a configurable layover at connect_airport."""
        seg1 = {
            "departing_at":     "2026-06-15T09:00:00",
            "arriving_at":      f"2026-06-15T{9 + 2:02d}:00:00",   # 2 h out
            "origin":           {"iata_code": "JFK"},
            "destination":      {"iata_code": connect_airport},
            "operating_carrier": {"iata_code": carrier1},
        }
        connect_dep_hour = 9 + 2 + layover_mins // 60
        connect_dep_min  = layover_mins % 60
        seg2 = {
            "departing_at":     f"2026-06-15T{connect_dep_hour:02d}:{connect_dep_min:02d}:00",
            "arriving_at":      f"2026-06-15T{connect_dep_hour + 3:02d}:{connect_dep_min:02d}:00",
            "origin":           {"iata_code": connect_airport},
            "destination":      {"iata_code": "LHR"},
            "operating_carrier": {"iata_code": carrier2},
        }
        total_h = 2 + layover_mins / 60 + 3
        h, m = int(total_h), int((total_h % 1) * 60)
        return {"segments": [seg1, seg2], "duration": f"PT{h}H{m:02d}M"}

    def test_nonstop_clean_daytime_all_zeros(self, prefs):
        """A nonstop daytime flight with default prefs has zero breakdown across all factors."""
        it = self._nonstop_itinerary()
        bd = _agony_breakdown(it, min_duration_hours=8.0, prefs=prefs)
        assert bd == {"layover": 0.0, "hub": 0.0, "interline": 0.0, "time": 0.0, "redeye": 0.0}

    def test_redeye_shows_10_in_breakdown(self, prefs):
        """A red-eye nonstop must show exactly 10 pts in the redeye factor."""
        it = self._nonstop_itinerary(dep="2026-06-15T23:30:00", arr="2026-06-16T07:30:00")
        bd = _agony_breakdown(it, min_duration_hours=8.0, prefs=prefs)
        assert bd["redeye"] == 10.0
        assert bd["layover"] == 0.0

    def test_time_penalty_shows_in_breakdown(self, prefs):
        """A leg 25% slower than the fastest produces 5 pts in the time factor."""
        it = self._nonstop_itinerary(
            dep="2026-06-15T07:00:00", arr="2026-06-15T17:00:00",
            duration="PT10H00M",   # must match actual elapsed time so agony_score agrees
        )
        bd = _agony_breakdown(it, min_duration_hours=8.0, prefs=prefs)  # 8h is fastest
        # excess_pct = (10-8)/8 = 25% → 1 * 5 = 5 pts
        assert bd["time"] == 5.0
        assert bd["redeye"] == 0.0

    def test_breakdown_sum_equals_agony_score_uncapped(self, prefs):
        """When the total is well below 100, breakdown sum must equal agony_score.

        This is the core invariant test: both functions must agree on the total
        (before the 100-cap that only agony_score applies).
        """
        it = self._nonstop_itinerary(
            dep="2026-06-15T07:00:00", arr="2026-06-15T17:00:00",
            duration="PT10H00M",
        )
        min_dur = 8.0
        score, _ = agony_score(it, min_dur, prefs)
        bd = _agony_breakdown(it, min_dur, prefs)
        bd_sum = sum(bd.values())
        # Score < 100 here, so the cap hasn't fired; both totals must agree.
        assert score < 100
        assert bd_sum == pytest.approx(score, abs=1.0), (
            f"breakdown sum {bd_sum} disagrees with agony_score {score}: {bd}"
        )

    def test_chaotic_hub_shows_in_breakdown(self, prefs):
        """A sweet-spot layover at ORD must show hub pts and no layover pts."""
        it = self._one_stop_itinerary(layover_mins=120, connect_airport="ORD")
        bd = _agony_breakdown(it, min_duration_hours=8.0, prefs=prefs)
        assert bd["hub"] == MOD_CHAOTIC, f"expected {MOD_CHAOTIC} hub pts: {bd}"
        assert bd["layover"] == 0.0     # sweet spot — no layover pts

    def test_interline_shows_in_breakdown(self, prefs):
        """An interline connection at a non-chaotic airport shows interline pts."""
        it = self._one_stop_itinerary(layover_mins=120, connect_airport="BOS",
                                      carrier1="BA", carrier2="AA")
        bd = _agony_breakdown(it, min_duration_hours=8.0, prefs=prefs)
        assert bd["interline"] == MOD_INTERLINE
        assert bd["hub"] == 0.0

    def test_cap_scales_factors_proportionally(self, prefs):
        """When the per-connection cap (25) fires, all factor contributions are
        scaled down proportionally so they still sum to the capped score."""
        # Dangerous layover (18 pts base) + chaotic hub (5) + interline (5) = 28 raw → capped at 25
        it = self._one_stop_itinerary(layover_mins=20, connect_airport="ORD",
                                      carrier1="BA", carrier2="AA")
        bd = _agony_breakdown(it, min_duration_hours=8.0, prefs=prefs)
        cnx_pts = bd["layover"] + bd["hub"] + bd["interline"]
        assert cnx_pts == pytest.approx(25.0, abs=0.2), (
            f"capped connection contribution should be 25, got {cnx_pts}: {bd}"
        )


# ---------------------------------------------------------------------------
# _process_offers — deduplication and sorting
# ---------------------------------------------------------------------------

def _minimal_offer(out_dep, out_arr, ret_dep, ret_arr, price, carrier="BA",
                   currency="USD", out_dur="PT8H00M", ret_dur="PT8H00M"):
    """Return a minimal 2-slice Duffel offer dict.

    out_dur / ret_dur should match the actual elapsed time so that agony_score's
    journey-time penalty is computed from correct data.
    """
    def _seg(dep, arr, orig, dest):
        return {
            "departing_at":     dep,
            "arriving_at":      arr,
            "origin":           {"iata_code": orig},
            "destination":      {"iata_code": dest},
            "operating_carrier": {"iata_code": carrier},
        }
    return {
        "slices": [
            {"segments": [_seg(out_dep, out_arr, "JFK", "LHR")], "duration": out_dur},
            {"segments": [_seg(ret_dep, ret_arr, "LHR", "JFK")], "duration": ret_dur},
        ],
        "total_amount":   str(price),
        "total_currency": currency,
    }


class TestProcessOffers:

    @pytest.fixture
    def prefs(self):
        return Preferences()

    def test_single_offer_returns_one_result(self, prefs):
        offers = [_minimal_offer(
            "2026-06-15T09:00:00", "2026-06-15T17:00:00",
            "2026-06-22T10:00:00", "2026-06-22T18:00:00",
            price=450,
        )]
        results = _process_offers(offers, prefs)
        assert len(results) == 1

    def test_duplicate_schedule_keeps_cheaper(self, prefs):
        """Two offers with identical schedules must be deduplicated; the cheaper one survives."""
        offers = [
            _minimal_offer(
                "2026-06-15T09:00:00", "2026-06-15T17:00:00",
                "2026-06-22T10:00:00", "2026-06-22T18:00:00",
                price=600,
            ),
            _minimal_offer(
                "2026-06-15T09:00:00", "2026-06-15T17:00:00",
                "2026-06-22T10:00:00", "2026-06-22T18:00:00",
                price=450,     # same schedule, cheaper
            ),
        ]
        results = _process_offers(offers, prefs)
        assert len(results) == 1, "duplicate schedule must be collapsed to one result"
        assert results[0]["price_amount"] == 450.0, "the cheaper duplicate must be kept"

    def test_distinct_schedules_both_returned(self, prefs):
        """Two offers with different departure times must both appear in results."""
        offers = [
            _minimal_offer(
                "2026-06-15T09:00:00", "2026-06-15T17:00:00",
                "2026-06-22T10:00:00", "2026-06-22T18:00:00",
                price=450,
            ),
            _minimal_offer(
                "2026-06-15T07:00:00", "2026-06-15T17:00:00",   # different departure
                "2026-06-22T08:00:00", "2026-06-22T18:00:00",
                price=310,
            ),
        ]
        results = _process_offers(offers, prefs)
        assert len(results) == 2

    def test_results_sorted_by_avg_score_ascending(self, prefs):
        """Results must be ordered lowest agony first.

        The slower offer (10h vs 8h = 25% over fastest) incurs a time penalty,
        so its avg score must be higher.  Results must come out lowest-agony-first.
        """
        offers = [
            _minimal_offer(
                "2026-06-15T07:00:00", "2026-06-15T17:00:00",  # 10h — slower
                "2026-06-22T08:00:00", "2026-06-22T18:00:00",
                price=310,
                out_dur="PT10H00M", ret_dur="PT10H00M",
            ),
            _minimal_offer(
                "2026-06-15T09:00:00", "2026-06-15T17:00:00",  # 8h — faster
                "2026-06-22T10:00:00", "2026-06-22T18:00:00",
                price=450,
            ),
        ]
        results = _process_offers(offers, prefs)
        avgs = [r["avg_score"] for r in results]
        assert avgs == sorted(avgs), f"results not sorted by avg_score: {avgs}"
        # Sanity: the slower offer must actually have a higher score (time penalty fired)
        assert avgs[0] < avgs[1], (
            f"faster offer should score lower: {avgs}. "
            "Time penalty may not be wired in _process_offers."
        )

    def test_non_roundtrip_offers_skipped(self, prefs):
        """Offers without exactly 2 slices must be dropped silently."""
        bad_offer = {
            "slices": [{"segments": [], "duration": "PT8H00M"}],  # only 1 slice
            "total_amount": "400.00",
            "total_currency": "USD",
        }
        good_offer = _minimal_offer(
            "2026-06-15T09:00:00", "2026-06-15T17:00:00",
            "2026-06-22T10:00:00", "2026-06-22T18:00:00",
            price=450,
        )
        results = _process_offers([bad_offer, good_offer], prefs)
        assert len(results) == 1, "malformed offer must be skipped"

    def test_all_non_roundtrip_returns_empty(self, prefs):
        """If every offer is malformed, _process_offers must return an empty list."""
        bad_offer = {
            "slices": [{"segments": [], "duration": "PT8H00M"}],
            "total_amount": "400.00",
            "total_currency": "USD",
        }
        results = _process_offers([bad_offer], prefs)
        assert results == []

    def test_result_contains_breakdown_keys(self, prefs):
        """Every result must carry out_breakdown and ret_breakdown for the chart."""
        offers = [_minimal_offer(
            "2026-06-15T09:00:00", "2026-06-15T17:00:00",
            "2026-06-22T10:00:00", "2026-06-22T18:00:00",
            price=450,
        )]
        results = _process_offers(offers, prefs)
        r = results[0]
        for key in ("out_breakdown", "ret_breakdown"):
            assert key in r, f"missing key: {key}"
            assert set(r[key]) == {"layover", "hub", "interline", "time", "redeye"}

