#!/usr/bin/env python3
"""
search_flights.py

Search Duffel API for round-trip flights and score each itinerary with the
Flight Agony Index — a 0–100 score measuring how miserable a routing is to fly.

Spec: ../SPEC.md  (scoring model, flag definitions, and sync rules live there).
Any change to scoring logic or CLI flags must be reflected in SPEC.md and SKILL.md.

Scoring model
-------------
Each connection is scored as a unit (layover length × airport quality × airline
consistency), then summed across all connections on that leg. Two global factors
(journey time and red-eye departure) are added on top.

  Per-connection  max 25 pts  (layover base + chaotic airport + interline modifiers)
  Journey time    max 20 pts  (how much slower than the fastest option in results)
  Red-eye         max 10 pts  (departure between 11 pm and 5 am)

  Total capped at 100.

Usage
-----
    python search_flights.py \\
        --origin BOS --destination LHR \\
        --depart 2026-07-10 --return 2026-07-20 \\
        [--sweet-spot-min 90] [--sweet-spot-max 180] \\
        [--no-airport-penalty] [--no-interline-penalty] \\
        [--no-redeye-penalty]  [--no-time-penalty] \\
        [--connection-weight 1.0] \\
        [--adults 1] [--max 20]
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHAOTIC_AIRPORTS = {"ORD", "ATL", "CDG", "EWR", "LAX", "JFK", "MIA", "PHL"}

# Layover scoring thresholds (minutes)
DANGEROUS_BELOW = 45    # below this: maximum stress score
LONG_ABOVE      = 360   # above this: maximum tedium score

# Base scores at the extremes of the layover curve
BASE_DANGEROUS  = 18    # pts for a dangerously short layover
BASE_LONG       = 12    # pts for a very long layover

# Per-connection modifiers
MOD_CHAOTIC     = 5     # pts added for a chaotic hub connection
MOD_INTERLINE   = 5     # pts added for a different-airline connection
MAX_PER_CNX     = 25    # hard cap per connection

DUFFEL_BASE    = os.environ.get("DUFFEL_BASE_URL", "https://api.duffel.com")
DUFFEL_VERSION = "v2"


# ---------------------------------------------------------------------------
# User preferences
# ---------------------------------------------------------------------------

@dataclass
class Preferences:
    """
    Traveler preferences that shape the agony score.

    All penalty flags default to True (penalties active). Set to False to
    tell the scorer that the traveler doesn't care about that factor.

    Constraints (enforced by __post_init__):
      - sweet_spot_min must be > DANGEROUS_BELOW (45 min). If it equals 45 the
        layover interpolation divides by zero; below 45 the curve inverts.
      - sweet_spot_max must be > sweet_spot_min.
      - connection_weight must be in [0.0, 2.0].
      - extra_chaotic_airports entries must be valid IATA codes (3 ASCII letters).
    """
    sweet_spot_min: int   = 90    # minutes — below this, layover starts getting tight
    sweet_spot_max: int   = 180   # minutes — above this, layover starts getting tedious
    airport_penalty: bool = True  # penalise connections at chaotic hubs
    interline_penalty: bool = True  # penalise multi-airline connections
    redeye_penalty: bool  = True  # penalise red-eye departures
    time_penalty: bool    = True  # penalise slower-than-fastest routings
    connection_weight: float = 1.0   # global multiplier on all connection scores (0–2)
    extra_chaotic_airports: frozenset = frozenset()  # merged with CHAOTIC_AIRPORTS at score time

    def __post_init__(self) -> None:
        # Normalise to uppercase and validate IATA format
        self.extra_chaotic_airports = frozenset(c.upper() for c in self.extra_chaotic_airports)
        invalid_iata = [c for c in self.extra_chaotic_airports if not re.fullmatch(r"[A-Z]{3}", c)]

        errors = []
        if invalid_iata:
            errors.append(
                f"--extra-chaotic-hubs contains invalid IATA code(s): {', '.join(sorted(invalid_iata))}. "
                f"Each code must be exactly 3 letters (e.g. LHR, CDG)."
            )
        if self.sweet_spot_min <= DANGEROUS_BELOW:
            errors.append(
                f"--sweet-spot-min must be > {DANGEROUS_BELOW} min "
                f"(got {self.sweet_spot_min}); lower values cause division-by-zero "
                f"in layover interpolation."
            )
        if self.sweet_spot_max <= self.sweet_spot_min:
            errors.append(
                f"--sweet-spot-max ({self.sweet_spot_max}) must be greater than "
                f"--sweet-spot-min ({self.sweet_spot_min})."
            )
        if self.sweet_spot_max > LONG_ABOVE:
            errors.append(
                f"--sweet-spot-max must be <= {LONG_ABOVE} min "
                f"(got {self.sweet_spot_max}); higher values invert the layover "
                f"interpolation curve above the sweet spot."
            )
        if not 0.0 <= self.connection_weight <= 2.0:
            errors.append(
                f"--connection-weight must be between 0.0 and 2.0 "
                f"(got {self.connection_weight})."
            )
        if errors:
            raise ValueError("Invalid preferences:\n  " + "\n  ".join(errors))


# ---------------------------------------------------------------------------
# Session — connection pooling + retry logic
# ---------------------------------------------------------------------------

# Status codes worth retrying. 429 = rate-limited; 5xx = transient server errors
# common in the Amadeus test environment.
_RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def _build_session() -> requests.Session:
    """
    Return a requests.Session configured with:
      - Retry logic for transient failures (429 and 5xx), with exponential
        backoff (0.5 s, 1 s, 2 s between attempts).
      - POST included in allowed_methods so the token endpoint is also covered.
      - raise_on_status=False so that exhausted retries return the bad response
        to our own exception handlers rather than raising RetryError directly.
      - Respect for Retry-After headers on 429 responses (urllib3 default).

    Both https:// and http:// prefixes are mounted so local test servers work too.
    """
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=_RETRY_STATUS_CODES,
        allowed_methods={"GET", "POST"},
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ---------------------------------------------------------------------------
# Duffel API
# ---------------------------------------------------------------------------

def search_flights(
    session: requests.Session,
    api_key: str,
    origin: str,
    destination: str,
    depart: str,
    return_date: str,
    adults: int,
    max_results: int,
) -> list:
    """
    Search for round-trip offers via the Duffel Offer Requests API.

    Posts a single offer request with two slices (outbound + return) and
    returns up to max_results offer dicts from the response.

    Duffel uses long-lived Bearer tokens (duffel_test_* or duffel_live_*)
    rather than short-lived OAuth2 tokens, so no token caching is needed.
    """
    resp = session.post(
        f"{DUFFEL_BASE}/air/offer_requests",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Duffel-Version": DUFFEL_VERSION,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json={
            "data": {
                "passengers": [{"type": "adult"} for _ in range(adults)],
                "slices": [
                    {"origin": origin, "destination": destination, "departure_date": depart},
                    {"origin": destination, "destination": origin, "departure_date": return_date},
                ],
                "cabin_class": "economy",
            }
        },
        params={"return_offers": "true"},
        timeout=30,
    )
    if not resp.ok:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise requests.HTTPError(
            f"{resp.status_code} {resp.reason} — Duffel detail: {detail}",
            response=resp,
        )
    offers = resp.json().get("data", {}).get("offers", [])
    return offers[:max_results]


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_duration(iso: str) -> float:
    """
    Convert an ISO 8601 duration string to decimal hours.

    Handles the full range of flight durations including multi-day legs
    (e.g. ultra-long-haul routes to Australia or India that exceed 24 hours):
      'PT7H30M'    →  7.5
      'PT14H05M'   → 14.083...
      'P1DT2H30M'  → 26.5

    Only D, H, and M components are extracted — years, months, and seconds
    do not appear in Duffel flight duration strings.
    """
    days = int(m.group(1)) if (m := re.search(r"(\d+)D", iso)) else 0
    h    = int(m.group(1)) if (m := re.search(r"(\d+)H", iso)) else 0
    mins = int(m.group(1)) if (m := re.search(r"(\d+)M", iso)) else 0
    return days * 24 + h + mins / 60.0


def layover_minutes(seg_before: dict, seg_after: dict) -> int:
    """Return the connection time between two adjacent Duffel segments, in minutes."""
    return int(
        (datetime.fromisoformat(seg_after["departing_at"]) -
         datetime.fromisoformat(seg_before["arriving_at"]))
        .total_seconds() / 60
    )


def is_redeye(departure_at: str) -> bool:
    """Return True if the departure hour falls between 11 pm and 5 am.

    Duffel returns departure times in local time, so .hour correctly reflects
    the traveller's experience (e.g. a 23:30 departure in Tokyo is a red-eye
    regardless of UTC offset). This is intentional — do not convert to UTC.
    """
    hour = datetime.fromisoformat(departure_at).hour
    return hour >= 23 or hour < 5


def carrier_code(seg: dict) -> str:
    """Extract the operating carrier IATA code from a Duffel segment dict."""
    return seg.get("operating_carrier", {}).get("iata_code") or "?"


def format_leg(slice_: dict) -> str:
    """Compact human-readable description of one leg (Duffel slice)."""
    segs = slice_["segments"]
    dep  = datetime.fromisoformat(segs[0]["departing_at"])
    arr  = datetime.fromisoformat(segs[-1]["arriving_at"])
    dur  = parse_duration(slice_["duration"])
    h, m = int(dur), int((dur % 1) * 60)
    stops    = len(segs) - 1
    stop_str = "nonstop" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}"
    return (
        f"{dep.strftime('%-I:%M%p').lower()} → "
        f"{arr.strftime('%-I:%M%p').lower()} "
        f"({h}h{m:02d}m, {stop_str})"
    )


# ---------------------------------------------------------------------------
# Per-connection scoring
# ---------------------------------------------------------------------------

def layover_base_score(minutes: int, prefs: Preferences) -> float:
    """
    Score a layover on a U-shaped curve with a flat zero inside the sweet spot.

    Below sweet_spot_min the score rises linearly to BASE_DANGEROUS at
    DANGEROUS_BELOW (and stays there for anything shorter).
    Above sweet_spot_max it rises linearly to BASE_LONG at LONG_ABOVE
    (and stays there for anything longer).

    Preconditions (enforced by Preferences.__post_init__, asserted here):
      - DANGEROUS_BELOW < sweet_spot_min   — denominator (lo - DANGEROUS_BELOW) > 0
      - sweet_spot_min  < sweet_spot_max   — sweet spot has positive width
      - sweet_spot_max  <= LONG_ABOVE      — denominator (LONG_ABOVE - hi) >= 0
    """
    lo, hi = prefs.sweet_spot_min, prefs.sweet_spot_max
    assert lo > DANGEROUS_BELOW, (
        f"sweet_spot_min ({lo}) must be > DANGEROUS_BELOW ({DANGEROUS_BELOW})"
    )
    assert hi > lo, (
        f"sweet_spot_max ({hi}) must be > sweet_spot_min ({lo})"
    )
    assert hi <= LONG_ABOVE, (
        f"sweet_spot_max ({hi}) must be <= LONG_ABOVE ({LONG_ABOVE})"
    )

    if minutes <= DANGEROUS_BELOW:
        return BASE_DANGEROUS

    if minutes < lo:
        # Linearly interpolate: DANGEROUS_BELOW→BASE_DANGEROUS, lo→0
        t = (minutes - DANGEROUS_BELOW) / (lo - DANGEROUS_BELOW)
        return BASE_DANGEROUS * (1 - t)

    if minutes <= hi:
        return 0.0

    if minutes < LONG_ABOVE:
        # Linearly interpolate: hi→0, LONG_ABOVE→BASE_LONG
        t = (minutes - hi) / (LONG_ABOVE - hi)
        return BASE_LONG * t

    return float(BASE_LONG)


def connection_score(seg_before: dict, seg_after: dict, prefs: Preferences) -> tuple[float, str]:
    """
    Score one connection (the gap between two consecutive segments).

    Returns:
        (score, explanation)
    """
    apt      = seg_before["destination"]["iata_code"]
    mins     = layover_minutes(seg_before, seg_after)
    c_before = carrier_code(seg_before)
    c_after  = carrier_code(seg_after)
    interline = c_before != c_after

    base  = layover_base_score(mins, prefs)
    mod   = 0.0
    parts = []

    if base >= BASE_DANGEROUS:
        parts.append(f"dangerous cnx {apt} ({mins}min)")
    elif base > 0 and mins < prefs.sweet_spot_min:
        parts.append(f"tight cnx {apt} ({mins}min)")
    elif base > 0:
        parts.append(f"long layover {apt} ({mins//60}h{mins%60:02d}m)")

    if prefs.airport_penalty and apt in (CHAOTIC_AIRPORTS | prefs.extra_chaotic_airports):
        mod += MOD_CHAOTIC
        parts.append(f"chaotic hub {apt}")

    if prefs.interline_penalty and interline:
        mod += MOD_INTERLINE
        parts.append(f"interline ({c_before}→{c_after})")

    raw   = (base + mod) * prefs.connection_weight
    score = min(MAX_PER_CNX, raw)
    return score, "; ".join(parts) if parts else f"clean cnx {apt} ({mins}min)"


# ---------------------------------------------------------------------------
# Full leg agony score
# ---------------------------------------------------------------------------

def agony_score(
    itinerary: dict,
    min_duration_hours: float,
    prefs: Preferences,
) -> tuple[int, str]:
    """
    Calculate the Agony Index for a single leg.

    Args:
        itinerary: One itinerary dict from the Amadeus response.
        min_duration_hours: Shortest duration found for this direction,
            used to compute the journey-time penalty.
        prefs: Traveler preferences.

    Returns:
        (score, explanation) where score is 0–100.
    """
    segs         = itinerary["segments"]
    total_hours  = parse_duration(itinerary["duration"])
    reasons: list[str] = []
    score = 0.0

    # --- Connection quality (per-connection, summed) ---
    for i in range(len(segs) - 1):
        cnx_score, cnx_why = connection_score(segs[i], segs[i + 1], prefs)
        score += cnx_score
        if cnx_score > 0:
            reasons.append(cnx_why)

    # --- Journey time penalty (max 20) ---
    if prefs.time_penalty and min_duration_hours > 0:
        excess_pct = (total_hours - min_duration_hours) / min_duration_hours
        time_pts   = min(20.0, int(excess_pct / 0.25) * 5)
        score += time_pts
        if time_pts > 0:
            reasons.append(f"slow routing (+{int(time_pts)}pts)")

    # --- Red-eye departure (flat 10) ---
    if prefs.redeye_penalty and is_redeye(segs[0]["departing_at"]):
        score += 10
        dep_str = datetime.fromisoformat(segs[0]["departing_at"]).strftime("%-I:%M%p").lower()
        reasons.append(f"red-eye ({dep_str})")

    final = min(100, int(round(score)))
    explanation = "; ".join(reasons) if reasons else "Clean routing"
    return final, explanation


# ---------------------------------------------------------------------------
# Per-factor breakdown (used by the web UI for the stacked bar chart)
# ---------------------------------------------------------------------------

def _agony_breakdown(
    itinerary: dict,
    min_duration_hours: float,
    prefs: Preferences,
) -> dict:
    """
    Return per-factor agony point contributions for visualization.

    Mirrors agony_score() but tracks how many points each factor contributed
    rather than returning a single total. Useful for the web UI stacked bar.
    Contributions are scaled proportionally when the per-connection cap fires.

    Returns a dict with keys: layover, hub, interline, time, redeye.
    """
    segs        = itinerary["segments"]
    total_hours = parse_duration(itinerary["duration"])

    layover_pts   = 0.0
    hub_pts       = 0.0
    interline_pts = 0.0

    for i in range(len(segs) - 1):
        apt      = segs[i]["destination"]["iata_code"]
        mins     = layover_minutes(segs[i], segs[i + 1])
        c_before = carrier_code(segs[i])
        c_after  = carrier_code(segs[i + 1])

        base    = layover_base_score(mins, prefs)
        hub_mod = MOD_CHAOTIC   if prefs.airport_penalty  and apt in (CHAOTIC_AIRPORTS | prefs.extra_chaotic_airports) else 0.0
        int_mod = MOD_INTERLINE if prefs.interline_penalty and c_before != c_after else 0.0

        raw    = (base + hub_mod + int_mod) * prefs.connection_weight
        capped = min(MAX_PER_CNX, raw)
        scale  = (capped / raw) if raw > 0 else 1.0

        layover_pts   += base    * prefs.connection_weight * scale
        hub_pts       += hub_mod * prefs.connection_weight * scale
        interline_pts += int_mod * prefs.connection_weight * scale

    time_pts = 0.0
    if prefs.time_penalty and min_duration_hours > 0:
        excess_pct = (total_hours - min_duration_hours) / min_duration_hours
        time_pts   = min(20.0, int(excess_pct / 0.25) * 5)

    redeye_pts = 10.0 if prefs.redeye_penalty and is_redeye(segs[0]["departing_at"]) else 0.0

    return {
        "layover":   round(layover_pts, 1),
        "hub":       round(hub_pts, 1),
        "interline": round(interline_pts, 1),
        "time":      round(time_pts, 1),
        "redeye":    round(redeye_pts, 1),
    }


# ---------------------------------------------------------------------------
# Shared processing pipeline (CLI + web UI)
# ---------------------------------------------------------------------------

def _process_offers(offers: list, prefs: Preferences) -> list:
    """
    Score, deduplicate, and sort raw Duffel offer dicts.

    Skips offers that don't have exactly 2 slices (not round-trip).
    Deduplicates by schedule (out_leg, ret_leg), keeping the cheapest price.
    Returns results sorted by avg_score ascending (lowest agony first).

    Each result dict contains:
        carriers, out_leg, ret_leg, out_score, ret_score, avg_score,
        out_why, ret_why, why (combined, for backward compat),
        price, price_amount, out_breakdown, ret_breakdown.
    """
    valid_offers = [o for o in offers if len(o.get("slices", [])) == 2]
    if not valid_offers:
        return []

    min_out = min(parse_duration(o["slices"][0]["duration"]) for o in valid_offers)
    min_ret = min(parse_duration(o["slices"][1]["duration"]) for o in valid_offers)

    results = []
    for offer in valid_offers:
        out_slice = offer["slices"][0]
        ret_slice = offer["slices"][1]

        out_score, out_why = agony_score(out_slice, min_out, prefs)
        ret_score, ret_why = agony_score(ret_slice, min_ret, prefs)

        all_carriers = sorted({carrier_code(s) for s in out_slice["segments"] + ret_slice["segments"]})

        results.append({
            "carriers":      "/".join(all_carriers),
            "out_leg":       format_leg(out_slice),
            "ret_leg":       format_leg(ret_slice),
            "out_score":     out_score,
            "ret_score":     ret_score,
            "avg_score":     (out_score + ret_score) / 2.0,
            "out_why":       out_why,
            "ret_why":       ret_why,
            "why":           f"Out: {out_why}  |  Ret: {ret_why}",
            "price":         f"{offer['total_currency']} {offer['total_amount']}",
            "price_amount":  float(offer["total_amount"]),
            "out_breakdown": _agony_breakdown(out_slice, min_out, prefs),
            "ret_breakdown": _agony_breakdown(ret_slice, min_ret, prefs),
            "out_segments":  out_slice["segments"],
            "ret_segments":  ret_slice["segments"],
        })

    # Deduplicate: same schedule → keep cheapest price
    seen: dict[tuple, dict] = {}
    for r in results:
        key = (r["out_leg"], r["ret_leg"])
        if key not in seen or r["price_amount"] < seen[key]["price_amount"]:
            seen[key] = r

    return sorted(seen.values(), key=lambda x: x["avg_score"])


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _tradeoff_summary(results: list) -> str:
    """
    Build the second sentence of the summary — a plain-English trade-off observation.

    Looks for the most interesting contrast among the top results: a low-agony
    option that costs meaningfully more, a slightly worse option that is notably
    cheaper, or an asymmetric outbound/return score worth flagging.
    """
    best = results[0]

    # Find the cheapest option and the runner-up by agony score.
    def price_float(r: dict) -> float:
        try:
            return float(r["price_amount"])
        except (ValueError, TypeError):
            return 0.0

    best_price  = price_float(best)
    runner_up   = results[1] if len(results) > 1 else None
    cheapest    = min(results, key=price_float)

    # Case 1: best option is NOT the cheapest — note the price premium.
    if cheapest is not best and best_price > 0:
        cheap_price = price_float(cheapest)
        saving      = best_price - cheap_price
        pct         = saving / best_price * 100
        if pct >= 15:
            return (
                f"{cheapest['carriers']} is {pct:.0f}% cheaper ({cheapest['price']}) "
                f"but scores {cheapest['avg_score']:.0f} — {cheapest['out_why']}."
            )

    # Case 2: runner-up has a notably lopsided outbound vs return.
    if runner_up:
        gap = abs(runner_up["out_score"] - runner_up["ret_score"])
        if gap >= 15:
            worse_leg = "outbound" if runner_up["out_score"] > runner_up["ret_score"] else "return"
            return (
                f"The {runner_up['carriers']} option (agony {runner_up['avg_score']:.0f}) "
                f"has a lopsided {worse_leg} — worth checking if one direction can be swapped."
            )

    # Case 3: fallback — contrast best and worst.
    if len(results) > 1:
        worst = results[-1]
        return (
            f"The most agonizing option is {worst['carriers']} at {worst['avg_score']:.0f}/100 "
            f"({worst['price']}) — {worst['out_why']}."
        )

    return ""


def print_table(
    results: list,
    origin: str,
    destination: str,
    depart: str,
    return_date: str,
    prefs: Preferences,
) -> None:
    """Print the ranked agony table as markdown, followed by a 2-sentence summary."""
    # Header
    print(f"\n## ✈️  {origin} → {destination}  |  {depart} → {return_date}  |  {len(results)} itineraries\n")

    # Active preferences
    sweet = f"sweet spot {prefs.sweet_spot_min}–{prefs.sweet_spot_max} min"
    flags = [sweet]
    if not prefs.airport_penalty:   flags.append("airports ignored")
    if not prefs.interline_penalty: flags.append("interline ignored")
    if not prefs.redeye_penalty:    flags.append("red-eye ignored")
    if not prefs.time_penalty:      flags.append("time ignored")
    if prefs.connection_weight != 1.0:
        flags.append(f"connection weight ×{prefs.connection_weight}")
    if prefs.extra_chaotic_airports:
        flags.append(f"extra chaotic hubs: {', '.join(sorted(prefs.extra_chaotic_airports))}")
    print(f"*Preferences: {', '.join(flags)}*\n")

    # Markdown table
    print("| Rank | Airline(s) | Outbound | Return | Agony ↑ | Why ↑ | Agony ↓ | Why ↓ | Avg | Price |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(results, 1):
        print(
            f"| {i} | {r['carriers']} | {r['out_leg']} | {r['ret_leg']} "
            f"| {r['out_score']} | {r['out_why']} | {r['ret_score']} | {r['ret_why']} "
            f"| {r['avg_score']:.1f} | {r['price']} |"
        )

    # 2-sentence summary
    best = results[0]
    sentence1 = (
        f"**Best pick**: {best['carriers']} — avg agony {best['avg_score']:.1f}/100 ({best['price']})."
    )
    sentence2 = _tradeoff_summary(results)
    print(f"\n{sentence1}")
    if sentence2:
        print(sentence2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="Flight Agony Index — powered by Duffel")

    # Search params
    p.add_argument("--origin",       required=True, help="Origin IATA code (e.g. BOS)")
    p.add_argument("--destination",  required=True, help="Destination IATA code (e.g. LHR)")
    p.add_argument("--depart",       required=True, help="Outbound date YYYY-MM-DD")
    p.add_argument("--return",       dest="return_date", required=True, help="Return date YYYY-MM-DD")
    p.add_argument("--adults",       type=int, default=1)
    p.add_argument("--max",          type=int, default=20, dest="max_results")

    # Preference params
    p.add_argument("--sweet-spot-min",      type=int,   default=90,  help="Min comfortable layover (minutes)")
    p.add_argument("--sweet-spot-max",      type=int,   default=180, help="Max comfortable layover (minutes)")
    p.add_argument("--no-airport-penalty",  action="store_true",     help="Don't penalise chaotic hub airports")
    p.add_argument("--no-interline-penalty",action="store_true",     help="Don't penalise multi-airline connections")
    p.add_argument("--no-redeye-penalty",   action="store_true",     help="Don't penalise red-eye departures")
    p.add_argument("--no-time-penalty",     action="store_true",     help="Don't penalise slower routings")
    p.add_argument("--connection-weight",   type=float, default=1.0, help="Multiplier for connection scores (0–2)")
    p.add_argument(
        "--extra-chaotic-hubs",
        default="",
        metavar="IATA[,IATA...]",
        help=(
            "Comma-separated IATA codes to treat as chaotic hubs in addition to the "
            "built-in list (e.g. LHR,MAN). Useful for known disruptions like strikes "
            "or severe weather at a specific airport. Codes are case-insensitive."
        ),
    )

    args = p.parse_args()

    extra_hubs = {c.strip() for c in args.extra_chaotic_hubs.split(",") if c.strip()}

    try:
        prefs = Preferences(
            sweet_spot_min         = args.sweet_spot_min,
            sweet_spot_max         = args.sweet_spot_max,
            airport_penalty        = not args.no_airport_penalty,
            interline_penalty      = not args.no_interline_penalty,
            redeye_penalty         = not args.no_redeye_penalty,
            time_penalty           = not args.no_time_penalty,
            connection_weight      = args.connection_weight,
            extra_chaotic_airports = extra_hubs,
        )
    except ValueError as exc:
        p.error(str(exc))

    api_key = os.environ.get("DUFFEL_API_KEY")
    if not api_key:
        print(
            "ERROR: DUFFEL_API_KEY not set.\n\n"
            "Get your free Duffel API key (takes ~2 minutes):\n"
            "  1. Go to https://app.duffel.com/signup and create a free account\n"
            "  2. In the dashboard, go to Developers → Access tokens\n"
            "  3. Create a test token (starts with duffel_test_)\n"
            "  4. Add it to your shell config (~/.zshrc or ~/.bashrc):\n"
            "       export DUFFEL_API_KEY='duffel_test_your_token_here'\n"
            "  5. Run: source ~/.zshrc   (or restart your terminal)\n"
            "  6. Try again!\n\n"
            "The test environment uses Duffel Airways (ZZ) for sandbox data.\n"
            "Switch to a duffel_live_* token for real airline inventory.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Searching: {args.origin} → {args.destination} | {args.depart} ↔ {args.return_date} …", flush=True)

    with _build_session() as session:
        try:
            offers = search_flights(
                session, api_key, args.origin, args.destination,
                args.depart, args.return_date, args.adults, args.max_results,
            )
        except requests.Timeout:
            print(
                "ERROR: Request timed out — Duffel did not respond in time.\n"
                "Check your network connection and try again.",
                file=sys.stderr,
            )
            sys.exit(1)
        except requests.ConnectionError as exc:
            print(
                f"ERROR: Could not connect to Duffel ({exc}).\n"
                "Check your network connection or DNS.",
                file=sys.stderr,
            )
            sys.exit(1)
        except requests.HTTPError as exc:
            body = exc.response.text[:500] if exc.response is not None else "(no response body)"
            print(
                f"ERROR: Duffel returned HTTP {exc.response.status_code}.\n{body}",
                file=sys.stderr,
            )
            sys.exit(1)
        except requests.RequestException as exc:
            print(f"ERROR: Request failed — {exc}", file=sys.stderr)
            sys.exit(1)
        except ValueError as exc:
            # Raised by resp.json() if Duffel returns non-JSON (e.g. an HTML error page)
            print(f"ERROR: Unexpected response format — {exc}", file=sys.stderr)
            sys.exit(1)

    if not offers:
        print("No flights found for those dates/airports.")
        sys.exit(0)

    # Guard: v1 only handles round-trip offers, which must have exactly 2 slices.
    # Skip any malformed offers and warn so the user knows the result set is partial.
    valid_offers = [o for o in offers if len(o.get("slices", [])) == 2]
    skipped = len(offers) - len(valid_offers)
    if skipped:
        print(
            f"WARNING: {skipped} offer(s) skipped — did not have exactly 2 slices "
            f"(expected for round-trip). Results may be incomplete.",
            file=sys.stderr,
        )
    if not valid_offers:
        print("No valid round-trip offers found after filtering.")
        sys.exit(0)

    results = _process_offers(valid_offers, prefs)
    print_table(results, args.origin, args.destination, args.depart, args.return_date, prefs)


if __name__ == "__main__":
    main()
