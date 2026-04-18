"""
Flight Agony — Streamlit web UI.

Run with:
    streamlit run web/app.py
    # or via the launcher:
    python scripts/launch_web.py

Requires DUFFEL_API_KEY in the environment. See SETUP.md.
"""

import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Import scoring engine
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from search_flights import (
    DANGEROUS_BELOW,
    LONG_ABOVE,
    Preferences,
    _build_session,
    _process_offers,
    _tradeoff_summary,
    search_flights as _duffel_search,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Flight Agony",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Airport lookup — optional; app works without it
# ---------------------------------------------------------------------------

AIRPORTS_CSV = Path(__file__).parent / "airports.csv"


@st.cache_data
def _load_airports() -> "pd.DataFrame | None":
    if not AIRPORTS_CSV.exists():
        return None
    try:
        df = pd.read_csv(
            AIRPORTS_CSV,
            usecols=["iata_code", "name", "municipality", "iso_country", "type"],
            dtype=str,
        )
        # Keep only airports with scheduled service (large/medium/small) and valid IATA codes
        df = df[
            df["iata_code"].notna()
            & (df["iata_code"] != "\\N")
            & (df["iata_code"].str.len() == 3)
            & df["type"].isin(["large_airport", "medium_airport", "small_airport"])
        ].rename(columns={"municipality": "city", "iso_country": "country"})
        return df.reset_index(drop=True)
    except Exception:
        return None


_airports = _load_airports()


# City → IATA code overrides.
# Where a city has multiple airports, use the IATA metropolitan area code so
# Duffel fans out across all airports in the metro (e.g. NYC = JFK+EWR+LGA).
# Single-airport cities use the airport code directly.
_CITY_OVERRIDES: dict[str, str] = {
    # Multi-airport metros → metro code
    "london": "LON", "london uk": "LON", "london england": "LON",  # LHR+LGW+STN+LCY+LTN
    "paris": "PAR", "paris france": "PAR",                          # CDG+ORY
    "new york": "NYC", "new york city": "NYC", "nyc": "NYC",        # JFK+EWR+LGA
    "tokyo": "TYO", "tokyo japan": "TYO",                           # NRT+HND
    "chicago": "CHI", "chicago illinois": "CHI",                    # ORD+MDW
    "washington": "WAS", "washington dc": "WAS", "dc": "WAS",       # IAD+DCA+BWI
    "milan": "MIL",                                                  # MXP+LIN+BGY
    "osaka": "OSA",                                                  # KIX+ITM
    "rome": "ROM",                                                   # FCO+CIA
    "buenos aires": "BUE",                                           # EZE+AEP
    "sao paulo": "SAO",                                              # GRU+CGH+VCP
    # Single-airport cities → airport code
    "los angeles": "LAX", "la": "LAX",
    "sydney": "SYD", "sydney australia": "SYD",
    "miami": "MIA",
    "dallas": "DFW",
    "houston": "IAH",
    "boston": "BOS",
    "seattle": "SEA",
    "denver": "DEN",
    "atlanta": "ATL",
    "amsterdam": "AMS",
    "frankfurt": "FRA",
    "madrid": "MAD",
    "barcelona": "BCN",
    "munich": "MUC",
    "zurich": "ZRH",
    "dubai": "DXB",
    "singapore": "SIN",
    "hong kong": "HKG",
    "toronto": "YYZ",
    "montreal": "YUL",
    "vancouver": "YVR",
    "mexico city": "MEX",
    "johannesburg": "JNB",
    "cairo": "CAI",
    "istanbul": "IST",
    "bangkok": "BKK",
    "kuala lumpur": "KUL",
    "jakarta": "CGK",
    "beijing": "PEK",
    "shanghai": "PVG",
    "seoul": "ICN",
    "mumbai": "BOM", "bombay": "BOM",
    "delhi": "DEL", "new delhi": "DEL",
    "melbourne": "MEL",
}


def _resolve_iata(text: str) -> str:
    """
    Return the best IATA code for the given input.
    - 3-letter alphabetic input → uppercased and returned as-is.
    - Known city name → override table (handles CDG/LHR disambiguation).
    - Otherwise → search airports.csv by city or airport name (first match).
    - If airports.csv is absent → uppercase the raw input and return it.
    """
    text = text.strip()
    if len(text) == 3 and text.isalpha():
        return text.upper()
    override = _CITY_OVERRIDES.get(text.lower())
    if override:
        return override
    if _airports is not None:
        mask = (
            _airports["city"].str.contains(text, case=False, na=False)
            | _airports["name"].str.contains(text, case=False, na=False)
        )
        matches = _airports[mask]
        if not matches.empty:
            # Rank by: (1) airport size, (2) exact city match beats name-only match
            # This ensures "London" → LHR (city=London, large) not LTN (city=Luton, large)
            type_rank = {"large_airport": 0, "medium_airport": 1, "small_airport": 2}
            matches = matches.copy()
            matches["_type_rank"] = matches["type"].map(type_rank).fillna(3)
            exact = matches["city"].str.lower() == text.lower()
            matches["_city_exact"] = (~exact).astype(int)  # 0 = exact match, 1 = name match
            return matches.sort_values(["_type_rank", "_city_exact"]).iloc[0]["iata_code"]
    return text.upper()


# ---------------------------------------------------------------------------
# Sidebar — Preferences
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Preferences")

    sweet_min, sweet_max = st.slider(
        "Comfortable layover window (min)",
        min_value=DANGEROUS_BELOW + 1,
        max_value=LONG_ABOVE,
        value=(90, 180),
        step=5,
        help=(
            "Layovers inside this window score 0. "
            "Too short risks a missed connection; too long means wasted hours in an airport."
        ),
    )

    connection_weight = st.slider(
        "Connection weight",
        min_value=0.0,
        max_value=2.0,
        value=1.0,
        step=0.1,
        help="Scales all connection scores. 1.0 = default; 0.0 = ignore connections; 2.0 = double penalty.",
    )

    st.divider()

    airport_penalty = st.checkbox(
        "Chaotic airport penalty",
        value=True,
        help="ORD, ATL, CDG, EWR, LAX, JFK, MIA, PHL each add +5 pts per connection through them.",
    )
    interline_penalty = st.checkbox(
        "Interline penalty",
        value=True,
        help="Connecting flights on different airlines add +5 pts.",
    )
    redeye_penalty = st.checkbox(
        "Red-eye penalty",
        value=True,
        help="Departures between 11 pm and 5 am add 10 pts.",
    )
    time_penalty = st.checkbox(
        "Journey time penalty",
        value=True,
        help="Each 25% slower than the fastest option in results adds 5 pts (max 20).",
    )

    st.divider()

    extra_hubs_input = st.text_input(
        "Extra chaotic hubs",
        placeholder="LHR,MAN",
        help="Comma-separated IATA codes to add to the chaotic hub list — useful for known disruptions.",
    )

# ---------------------------------------------------------------------------
# Main — header + search form
# ---------------------------------------------------------------------------

st.title("✈️ Flight Agony")
st.caption("Rank round-trip flights by how miserable they are to fly — price not included in the score.")

with st.form("search_form"):
    col1, col2 = st.columns(2)
    with col1:
        origin_input = st.text_input("From", placeholder="SFO  or  San Francisco")
    with col2:
        dest_input = st.text_input("To", placeholder="JFK  or  New York")

    col3, col4, col5, col6 = st.columns([2, 2, 1, 1])
    with col3:
        depart_date = st.date_input("Depart", value=date.today() + timedelta(days=14))
    with col4:
        return_date = st.date_input("Return", value=date.today() + timedelta(days=21))
    with col5:
        adults = st.number_input("Adults", min_value=1, max_value=9, value=1)
    with col6:
        max_results = st.number_input(
            "Max results", min_value=1, max_value=50, value=20,
            help="Maximum itineraries to retrieve from Duffel.",
        )

    search_clicked = st.form_submit_button("Search flights", type="primary")

# ---------------------------------------------------------------------------
# Run search — store results in session state so row-selection reruns
# don't wipe the results block.
# ---------------------------------------------------------------------------

if search_clicked:
    if not origin_input.strip() or not dest_input.strip():
        st.warning("Enter an origin and a destination.")
        st.stop()

    if depart_date >= return_date:
        st.warning("Return date must be after departure date.")
        st.stop()

    origin      = _resolve_iata(origin_input)
    destination = _resolve_iata(dest_input)

    api_key = os.environ.get("DUFFEL_API_KEY")
    if not api_key:
        st.error(
            "**DUFFEL_API_KEY is not set.** "
            "Follow the instructions in SETUP.md to get your free API key, "
            "then restart the app."
        )
        st.stop()

    extra_set = {c.strip().upper() for c in extra_hubs_input.split(",") if c.strip()}
    try:
        prefs = Preferences(
            sweet_spot_min=sweet_min,
            sweet_spot_max=sweet_max,
            airport_penalty=airport_penalty,
            interline_penalty=interline_penalty,
            redeye_penalty=redeye_penalty,
            time_penalty=time_penalty,
            connection_weight=connection_weight,
            extra_chaotic_airports=extra_set,
        )
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    with st.spinner(f"Searching {origin} → {destination} …"):
        try:
            with _build_session() as session:
                offers = _duffel_search(
                    session, api_key,
                    origin, destination,
                    depart_date.isoformat(), return_date.isoformat(),
                    int(adults), int(max_results),
                )
        except Exception as exc:
            st.error(f"Search failed: {exc}")
            st.stop()

    if not offers:
        st.info("No flights found for those dates and airports.")
        st.stop()

    results = _process_offers(offers, prefs)

    if not results:
        st.info("No valid round-trip itineraries found.")
        st.stop()

    # Persist results and context so row-selection reruns keep everything.
    st.session_state["results"] = results
    st.session_state["origin"] = origin
    st.session_state["destination"] = destination
    st.session_state["depart_date"] = depart_date
    st.session_state["return_date"] = return_date
    st.session_state["search_header"] = (
        f"**{origin} → {destination}**  |  "
        f"{depart_date.strftime('%b %d')} → {return_date.strftime('%b %d')}  |  "
        f"{len(results)} itineraries — ranked lowest agony first"
    )
    # Clear any stale row selection from a prior search.
    st.session_state["selected_row_idx"] = None

# ---------------------------------------------------------------------------
# Score color-banding helper — module-level so tests can import it directly.
#
# Spec §13.2:  0–30 = green,  31–60 = amber,  61–100 = red
# ---------------------------------------------------------------------------

def _score_bg(val: object) -> str:
    """Return a CSS background+text style string for a score cell."""
    if not isinstance(val, (int, float)):
        return ""
    if val <= 30:
        return "background-color: #d4edda; color: #155724"
    if val <= 60:
        return "background-color: #fff3cd; color: #856404"
    return "background-color: #f8d7da; color: #721c24"


# ---------------------------------------------------------------------------
# Results display — rendered on every run (search or row-selection rerun)
# ---------------------------------------------------------------------------

if "results" in st.session_state:
    results     = st.session_state["results"]
    origin      = st.session_state["origin"]
    destination = st.session_state["destination"]
    depart_date = st.session_state["depart_date"]
    return_date = st.session_state["return_date"]

    st.success(st.session_state["search_header"])

    # -----------------------------------------------------------------------
    # Results table — manual rows so the detail panel expands inline
    # immediately below the selected row.
    # -----------------------------------------------------------------------

    def _score_badge(val: float) -> str:
        if val <= 30:
            bg, fg = "#d4edda", "#155724"
        elif val <= 60:
            bg, fg = "#fff3cd", "#856404"
        else:
            bg, fg = "#f8d7da", "#721c24"
        return (
            f'<span style="background:{bg};color:{fg};padding:2px 8px;'
            f'border-radius:4px;font-weight:600">{val}</span>'
        )

    def _render_segments(segs: list) -> None:
        for i, seg in enumerate(segs):
            dep  = datetime.fromisoformat(seg["departing_at"])
            arr  = datetime.fromisoformat(seg["arriving_at"])
            orig = seg["origin"]["iata_code"]
            dest = seg["destination"]["iata_code"]
            carrier = seg.get("operating_carrier", {}).get("iata_code", "?")
            fnum    = seg.get("operating_carrier_flight_number", "")
            st.markdown(
                f"**{dep.strftime('%-I:%M %p')}** {orig} → "
                f"**{arr.strftime('%-I:%M %p')}** {dest}"
                f"&nbsp; · &nbsp;{carrier}{fnum}"
            )
            if i < len(segs) - 1:
                nxt_dep = datetime.fromisoformat(segs[i + 1]["departing_at"])
                layover_min = int((nxt_dep - arr).total_seconds() // 60)
                h, m = divmod(layover_min, 60)
                st.markdown(
                    f"<div style='color:#888;padding-left:1rem;font-size:0.9em'>"
                    f"↕ layover at {dest}: {h}h {m:02d}m</div>",
                    unsafe_allow_html=True,
                )

    # Column proportions: btn | # | airline | outbound | return | ↑ | why↑ | ↓ | why↓ | avg | price
    _C = [0.35, 0.35, 0.5, 2.3, 2.3, 0.45, 2.2, 0.45, 2.2, 0.45, 1.1]

    hcols = st.columns(_C)
    for hcol, label in zip(hcols, ["", "#", "Airline", "Outbound", "Return",
                                    "↑", "Why ↑", "↓", "Why ↓", "Avg", "Price"]):
        hcol.markdown(f"**{label}**")
    st.divider()

    sel_idx = st.session_state.get("selected_row_idx", None)

    for i, r in enumerate(results, 1):
        row_idx = i - 1
        is_sel  = sel_idx == row_idx

        rcols = st.columns(_C)
        if rcols[0].button("☑" if is_sel else "☐", key=f"rowbtn_{row_idx}"):
            st.session_state["selected_row_idx"] = None if is_sel else row_idx
            st.rerun()

        rcols[1].write(i)
        rcols[2].write(r["carriers"])
        rcols[3].write(r["out_leg"])
        rcols[4].write(r["ret_leg"])
        rcols[5].markdown(_score_badge(r["out_score"]), unsafe_allow_html=True)
        rcols[6].write(r["out_why"])
        rcols[7].markdown(_score_badge(r["ret_score"]), unsafe_allow_html=True)
        rcols[8].write(r["ret_why"])
        rcols[9].markdown(_score_badge(round(r["avg_score"], 1)), unsafe_allow_html=True)
        rcols[10].write(r["price"])

        if is_sel:
            with st.container(border=True):
                st.caption(f"✈️  {r['carriers']}  ·  rank {i}  ·  {r['price']}")
                seg_col1, seg_col2 = st.columns(2)
                with seg_col1:
                    st.markdown("**Outbound ↑**")
                    _render_segments(r["out_segments"])
                with seg_col2:
                    st.markdown("**Return ↓**")
                    _render_segments(r["ret_segments"])

                st.markdown("")
                factors = ["layover", "hub", "interline", "time", "redeye"]
                labels  = ["Layover", "Chaotic hub", "Interline", "Journey time", "Red-eye"]
                colors  = ["#4a90d9", "#e07b39", "#9b59b6", "#27ae60", "#e74c3c"]
                for bcol, (leg_label, breakdown, score) in zip(
                    st.columns(2),
                    [("Outbound ↑", r["out_breakdown"], r["out_score"]),
                     ("Return ↓",   r["ret_breakdown"], r["ret_score"])],
                ):
                    with bcol:
                        pts = [breakdown[f] for f in factors]
                        fig = go.Figure(go.Bar(
                            x=pts, y=labels, orientation="h",
                            marker_color=colors,
                            text=[f"{p:.1f}" if p > 0 else "" for p in pts],
                            textposition="outside",
                        ))
                        fig.update_layout(
                            title=f"{leg_label} — {score}/100",
                            xaxis=dict(range=[0, 26], title="Points"),
                            yaxis=dict(autorange="reversed"),
                            height=260,
                            margin=dict(l=10, r=40, t=40, b=10),
                            showlegend=False,
                        )
                        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # -----------------------------------------------------------------------
    # Two-sentence summary
    # -----------------------------------------------------------------------

    best = results[0]
    st.markdown(
        f"**Best pick:** {best['carriers']} — avg agony **{best['avg_score']:.1f}/100** ({best['price']})."
    )
    tradeoff = _tradeoff_summary(results)
    if tradeoff:
        st.markdown(tradeoff)

    # -----------------------------------------------------------------------
    # Cost vs agony scatter chart
    # -----------------------------------------------------------------------

    with st.expander("Cost vs agony chart"):
        chart_df = pd.DataFrame(
            [
                {
                    "Price":      r["price_amount"],
                    "Avg Agony":  r["avg_score"],
                    "Airline(s)": r["carriers"],
                    "Outbound":   r["out_leg"],
                    "Return":     r["ret_leg"],
                    "Agony ↑":   r["out_score"],
                    "Agony ↓":   r["ret_score"],
                    "Price label": r["price"],
                }
                for r in results
            ]
        )

        # Pareto frontier: cheapest price at each agony level (step-wise)
        pareto_rows = []
        min_agony = float("inf")
        for _, row in chart_df.sort_values("Price").iterrows():
            if row["Avg Agony"] < min_agony:
                min_agony = row["Avg Agony"]
                pareto_rows.append(row)
        pareto_df = pd.DataFrame(pareto_rows)

        currency = results[0]["price"].split()[0]
        fig = px.scatter(
            chart_df,
            x="Price",
            y="Avg Agony",
            hover_data=["Airline(s)", "Outbound", "Return", "Agony ↑", "Agony ↓", "Price label"],
            labels={"Price": f"Price ({currency})", "Avg Agony": "Avg Agony (0–100)"},
            title=f"{origin} ↔ {destination}  |  "
                  f"{depart_date.strftime('%b %d')} → {return_date.strftime('%b %d')}",
        )

        if len(pareto_df) > 1:
            fig.add_trace(
                go.Scatter(
                    x=pareto_df["Price"],
                    y=pareto_df["Avg Agony"],
                    mode="lines",
                    name="Pareto frontier",
                    line=dict(color="rgba(120,120,120,0.5)", width=1, dash="dot"),
                    hoverinfo="skip",
                )
            )

        fig.update_layout(height=420)
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Each dot is one itinerary. The dotted line is the Pareto frontier — "
            "the cheapest option at each agony level. Points above and to the right are dominated."
        )
