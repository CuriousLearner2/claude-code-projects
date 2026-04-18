# Flight Agony — Product Requirements Document

## 1. Problem Statement

Booking flights is miserable not because of price comparison sites — those are good — but because price and pain are tangled together. A $300 fare with two stops, a tight connection at ORD, and a 6am departure is not the same as a $400 nonstop, but most search tools present them side by side with no signal for how awful one is to actually fly.

Travelers who care about the *experience* of travel — not just the cost — have no quick way to compare itineraries on that dimension.

---

## 2. Goal

Give travelers a single, transparent score for how miserable a routing is to fly, separated entirely from price — so they can make their own agony-per-dollar trade-off with full information.

---

## 3. Target Users

**Primary:** Leisure travelers who fly a few times a year and care about the travel experience. They're comfortable with a terminal or a simple web UI. They are not travel hackers optimizing for points — they just don't want to be miserable.

**Secondary:** Frequent travelers ("road warriors") who want to quickly surface the least-painful routing without wading through a full itinerary comparison.

Not a commercial product. Built for personal use and sharing with friends.

---

## 4. Success Criteria

| Metric | Target |
|---|---|
| Top-ranked itinerary feels right to a frequent traveler reviewing results | Qualitative validation across ≥5 real searches |
| Agony scores are explainable | Why ↑ and Why ↓ columns are accurate and readable for every result |
| Preferences change results meaningfully | Toggling red-eye/airport/connection flags visibly shifts rankings |
| Setup time for a new user | < 5 minutes (API key + one env var) |

---

## 5. User Stories

**Core:**
- As a traveler, I want to search round-trip flights between two cities on specific dates and see all itineraries ranked by how painful they are to fly, so I can quickly identify which routing to avoid.
- As a traveler, I want to understand *why* a flight scored high, so I can decide if that specific pain point matters to me.
- As a traveler, I want to express my preferences in plain English ("I don't mind long layovers", "I hate stops"), so I don't have to learn a CLI interface.

**Preferences:**
- As a traveler with a bad knee, I want to reduce the penalty for long layovers, so connections over 3 hours don't tank the score.
- As a traveler loyal to one airline for miles, I want interline connections to score worse so single-carrier routings rise to the top. *(v1 partial: `--connection-weight 1.5` amplifies all connection scores including interline; a dedicated interline weight flag is a v2 item)*
- As a traveler who books red-eyes to save days, I want to turn off the red-eye penalty.

**Situational:**
- As a traveler flying during a known disruption (strike at LHR), I want to flag that airport as chaotic at search time without editing any code.

---

## 6. Functional Requirements

### 6.1 Input
- Round-trip only (v1)
- Single departure and return date (v1)
- Origin and destination resolved from city names to IATA codes by Claude
- Ambiguous city names (e.g. "New York") prompt for clarification before running

### 6.2 Agony Index
- Score per leg (outbound and return independently), 0–100
- Price is explicitly excluded

Five scoring factors:

| Factor | Scope | Max pts | Rule |
|---|---|---|---|
| **Layover length** | Per connection | 18 | U-shaped curve: 0 inside sweet spot (default 90–180 min), rising to 18 for dangerous short layovers (≤45 min) or 12 for very long (≥360 min). The U-shape reflects that both extremes are painful but in different ways — too short risks a missed connection, too long means wasted hours in an airport — while the middle is comfortable. The curve rises smoothly from both edges of the sweet spot so there are no harsh scoring cliffs. |
| **Chaotic hub** | Per connection | +5 | Flat modifier when the connecting airport is on the chaotic list (ORD, ATL, CDG, EWR, LAX, JFK, MIA, PHL) |
| **Interline** | Per connection | +5 | Flat modifier when the operating carrier changes across a connection |
| **Journey time** | Per leg | 20 | +5 pts per 25% slower than the fastest option in the same search results |
| **Red-eye departure** | Per leg | 10 | Flat 10 pts if departure is between 11pm and 5am (local time) |

The first three factors are scored together per connection (cap 25 pts each, scaled by `--connection-weight`) and summed across all connections on the leg. Journey time and red-eye are leg-level globals. Overall score is capped at 100.

### 6.3 Preferences
All adjustable via natural language; mapped to CLI flags:

| User intent | Flag |
|---|---|
| Long layovers are fine | `--sweet-spot-max 360` *(minutes)* |
| Need 2+ hours between flights | `--sweet-spot-min 120` *(minutes)* |
| Airports don't bother me | `--no-airport-penalty` |
| Fine with red-eyes | `--no-redeye-penalty` |
| Don't care about stops | `--connection-weight 0.5` *(multiplier; default 1.0)* |
| Hate connections | `--connection-weight 1.5` *(multiplier; default 1.0)* |
| Don't mind mixed airlines | `--no-interline-penalty` |
| Don't care about travel time | `--no-time-penalty` |
| Airport X is a mess right now | `--extra-chaotic-hubs XYZ` *(comma-separated IATA codes, e.g. LHR,MAN)* |

Default profile represents a typical leisure traveler — no flags needed.

### 6.4 Output
- Ranked markdown table: Rank, Airline(s), Outbound, Return, Agony ↑, Why ↑, Agony ↓, Why ↓, Avg, Price — sorted ascending by **average agony** ((outbound score + return score) / 2), so the least miserable itinerary is always first. Outbound and return scores each have their own Why column so the driver of each leg's score is immediately visible without parsing a combined string.
- Two-sentence summary: best pick + a trade-off observation (cheaper-but-worse, lopsided legs, or worst option)
- CLI: preference echo printed above the table so the user knows what flags were applied
- Web UI: no separate preference echo — the sidebar is the live display of active preferences

### 6.5 Data Source
- Duffel Air — Offer Requests API v2 (test environment uses Duffel Airways sandbox; live environment uses real airline inventory)
- Up to 20 results per search (client-side slice of Duffel response)
- Single long-lived Bearer token (`DUFFEL_API_KEY`); no OAuth2 dance or token caching needed

### 6.6 Reliability
- Retry on transient errors (429, 500–504) with exponential backoff
- Clean error messages for missing credentials, network failures, and empty results — no tracebacks

### 6.7 Web UI
- Implemented in Streamlit (`web/app.py`); launched with `streamlit run web/app.py`
- **Search form**: origin and destination text inputs with city-name autocomplete (resolved via bundled `airports.csv`); departure and return date pickers; adults and max-results number inputs
- **Preferences sidebar**: dual-handle slider for the layover sweet spot (46–360 min, default 90–180); single slider for connection weight (0.0–2.0, step 0.1, default 1.0); four checkboxes for airport/interline/red-eye/time penalties (all on by default); text field for extra chaotic hubs. The sidebar is the live display of active preferences — no separate echo above the table.
- **Results table**: same columns as CLI output (§6.4); agony scores color-banded (green 0–30, amber 31–60, red 61–100); row expansion shows per-factor score breakdown as a stacked horizontal bar
- **Cost vs agony chart**: Plotly scatter plot (x = price, y = avg agony), Pareto frontier drawn as a step line, collapsed by default below the table
- **City → IATA lookup**: bundled `airports.csv` (OpenFlights `airports.dat`, ~7 K rows); no Claude call needed in the web UI for city resolution

---

## 7. Non-Functional Requirements

| Requirement | Target |
|---|---|
| Setup complexity | One API key, one env var, one pip install |
| Dependencies | `requests` only (no heavy frameworks) |
| Response time | Dominated by Duffel API latency; no local bottlenecks |
| Portability | Runs anywhere Python 3.10+ is available |
| Observability | Preference echo + Why ↑ / Why ↓ columns make every leg's score auditable |

---

## 8. Out of Scope (v1)

- One-way or multi-city itineraries
- Date flexibility (±N days)
- Price as an agony factor
- Booking links or deep-links
- Saved preference profiles
- Mobile

---

## 9. v2 Roadmap

Listed in priority order based on user feedback:

1. **Web UI** *(in progress)* — preference sliders, color-banded score table, per-factor row expansion, cost vs agony scatter plot. See §6.7 for full spec.
2. **Named preference profiles** — "road warrior", "family travel", save and recall
3. **Agony-targeted date search** — user specifies a target agony score (e.g. "get me to 60 or below") and the system searches a ±N day window around the requested dates, returning the nearest date pair that meets the threshold. Output shows how many days of flexibility were needed and what drove the improvement. This answers: *how much schedule flexibility is my comfort worth?*
4. **Agony-efficiency frontier** — given a set of search results across dates and price points, show the trade-off between cost and agony score. A user can ask "if I pay $200 more, how much agony do I shed?" or "if I add 2 days of date flexibility *and* a $200 budget, where does that land me?" Output is a simple table or chart showing the cost-agony curve: each step up in price, how many agony points are recovered. This keeps price out of the score (the core design principle) while making the agony-per-dollar trade-off explicit and actionable.
5. **Per-factor weights** — replace single `--connection-weight` with granular controls per factor (e.g. `--interline-weight` to strongly penalize mixed-carrier routings for miles-loyal travelers)
6. **One-way search mode**
7. **Chaotic airport refresh** — pull OTP data periodically instead of hardcoded list

Note: features 3 and 4 combine naturally — date flexibility and budget flexibility are two axes of the same trade-off surface. The web UI (feature 1) is the natural home for visualizing this as a 2D chart (cost on x, agony on y, each dot a distinct date pair).

### 9.1 Candidate scoring factors for v2

The following factors are not in the v1 model but are worth evaluating:

| Factor | Rationale | Notes |
|---|---|---|
| **Stop count (explicit)** | A nonstop should always beat a 1-stop regardless of layover quality; currently stops are only penalized indirectly through connection scores | Simple additive penalty per stop; weight TBD |
| **Red-eye arrival** | Landing at 2am is its own misery, currently unpenalized | Same 10-pt flat penalty as red-eye departure; window TBD |
| **Overnight layover** | A 10-hour layover overnight at an airport is qualitatively worse than a long daytime one | Distinct penalty above a time threshold (e.g. >6 hours spanning midnight) |
| **Historical on-time performance (OTP)** | Replaces or supplements the static chaotic-airport list with per-route/carrier OTP data | More precise than hardcoded airport list; requires a separate OTP data source |
| **Terminal change at connection** | Some airports require inter-terminal transit that eats into layover time and adds stress (e.g. JFK T4 → T7) | Data availability varies by airport/API |

---

## 10. Test Plan

Framework: `pytest`. All tests live in `tests/`. No API key required for unit tests — scoring functions are pure and take structured dicts as input.

### 10.1 Unit tests — scoring model

These test the math directly with known inputs and expected outputs.

**`parse_duration()`**

| Input | Expected output |
|---|---|
| `PT2H30M` | 2.5 hours |
| `PT45M` | 0.75 hours |
| `P1DT2H30M` | 26.5 hours (multi-day) |
| `PT0M` | 0.0 hours |

**`layover_base_score()` — default sweet spot 90–180 min**

| Layover (min) | Expected score | Reason |
|---|---|---|
| 30 | 18 | Below dangerous floor (≤45 min) |
| 45 | 18 | At dangerous floor |
| 67.5 | 9 | Midpoint of 45→90 interpolation |
| 90 | 0 | Sweet spot lower bound |
| 135 | 0 | Inside sweet spot |
| 180 | 0 | Sweet spot upper bound |
| 270 | 6 | Midpoint of 180→360 interpolation |
| 360 | 12 | At long-layover floor |
| 400 | 12 | Above long-layover floor, capped |

**`connection_score()` — default preferences**

| Layover | Airport | Same carrier? | Expected score |
|---|---|---|---|
| 60 min | non-chaotic | yes | layover base only |
| 60 min | ORD | yes | layover base + 5 |
| 60 min | ORD | no | layover base + 10 |
| 60 min | ORD | no (weight=2.0) | min(25, (base+10)×2) |
| 60 min | ORD | no (weight=0.0) | 0 |

**`is_redeye()`**

| Input | Expected |
|---|---|
| `2026-06-15T23:00` | True |
| `2026-06-15T04:59` | True |
| `2026-06-16T00:00` | True |
| `2026-06-15T05:00` | False |
| `2026-06-15T22:59` | False |

**`agony_score()` — whole-leg scenarios**

| Scenario | Expected behaviour |
|---|---|
| Nonstop, daytime, fastest in results | 0 pts |
| Nonstop, red-eye departure | 10 pts |
| 1-stop, sweet-spot layover, fastest | 0 connection pts + 0 time pts |
| 1-stop, 30-min layover at ORD, interline | (18+5+5) capped at 25 connection pts |
| Routing 50% slower than fastest | 10 time pts (+5 per 25%) |
| Routing 100% slower than fastest | 20 time pts (max) |

### 10.2 Unit tests — preference validation

`Preferences.__post_init__` should raise `ValueError` for each of these:

| Input | Violation |
|---|---|
| `sweet_spot_min=45` | Must be > 45 min |
| `sweet_spot_min=44` | Must be > 45 min |
| `sweet_spot_max=361` | Must be ≤ 360 min |
| `sweet_spot_max=90, sweet_spot_min=90` | max must be > min |
| `connection_weight=-0.1` | Must be 0.0–2.0 |
| `connection_weight=2.1` | Must be 0.0–2.0 |

And these should pass without error:

| Input | Note |
|---|---|
| `sweet_spot_min=46` | Minimum valid value |
| `sweet_spot_max=360` | Maximum valid value |
| `connection_weight=0.0` | Minimum valid multiplier |
| `connection_weight=2.0` | Maximum valid multiplier |
| `extra_chaotic_hubs="LHR,man"` | Mixed case; should normalise to `{"LHR", "MAN"}` |

### 10.3 Unit tests — trade-off summary

`_tradeoff_summary()` selects from three scenarios in priority order:

| Scenario | Expected summary type |
|---|---|
| Best agony option is not cheapest | Mentions the cheaper option's price saving and score penalty |
| Runner-up has outbound/return gap ≥ 15 pts | Flags the worse leg and suggests investigating it |
| Neither above applies | Names the most agonising option and its primary driver |

### 10.4 CLI tests

Run the script as a subprocess and check exit code and stderr/stdout:

| Invocation | Expected |
|---|---|
| `--sweet-spot-min 45` | Exit 2, error message, no traceback |
| `--sweet-spot-max 361` | Exit 2, error message, no traceback |
| `--connection-weight 3.0` | Exit 2, error message, no traceback |
| Missing `DUFFEL_API_KEY` env var | Exit 1, setup instructions printed |
| `--origin JFK --destination LHR --depart ... --return ...` (valid, no creds) | Graceful error, not an unhandled exception |

### 10.5 Integration tests (requires API credentials)

These are run manually or in CI with credentials set:

| Test | What to verify |
|---|---|
| Live search JFK→LHR | Results returned, table prints, scores are 0–100 |
| `--max 5` | 5 or fewer results returned after deduplication |
| Deduplication | Identical outbound+return schedules collapsed to one row (cheapest price kept) |
| `--extra-chaotic-hubs LHR` | LHR connections score +5 higher than without flag |
| `duffel_test_*` token | Search succeeds against Duffel sandbox (ZZ airline in results) |

### 10.6 Web UI tests

#### Automated — AppTest (`tests/test_ui.py` — 17+ tests, headless, no browser)

| Test | Class | What is verified |
|---|---|---|
| App renders without error | `TestAppStartup` | No exception on cold start |
| Search button present | `TestAppStartup` | `"Search flights"` button exists |
| Preference sliders present | `TestAppStartup` | 2 sliders (sweet spot, connection weight) |
| Penalty checkboxes present and default on | `TestAppStartup` | 4 checkboxes, all `True` by default |
| Text inputs present | `TestAppStartup` | 3 text inputs (From, To, Extra hubs) |
| Empty origin+destination warns | `TestFormValidation` | `st.warning` shown, no search |
| Empty origin only warns | `TestFormValidation` | `st.warning` shown when From is blank |
| Return before departure warns | `TestFormValidation` | `st.warning` shown on inverted dates |
| Missing API key shows error | `TestFormValidation` | `st.error` shown, not a traceback |
| Missing API key no traceback | `TestFormValidation` | `at.exception` is falsy |
| Results table renders | `TestSearchResults` | `st.dataframe` present after mocked search |
| Results table has expected columns | `TestSearchResults` | All 10 columns present |
| Results sorted by avg ascending | `TestSearchResults` | `Avg` column is non-decreasing |
| Scores are in valid range | `TestSearchResults` | `Agony ↑`, `Agony ↓`, `Avg` all in 0–100 |
| Summary text rendered | `TestSearchResults` | `"Best pick"` appears in rendered markdown |
| Empty results shows info | `TestSearchResults` | `st.info` shown when no offers returned |
| No exception on valid search | `TestSearchResults` | `at.exception` is falsy |
| Results persist after rerun | `TestSearchResults` | Results table still present after a bare `run()` with no button click (simulates row-selection rerun) |
| 3-letter code passthrough | `TestResolveIata` | `"JFK"` → `"JFK"`, `"lhr"` → `"LHR"` |
| Override table — metro codes | `TestResolveIata` | London→LON, Paris→PAR, New York→NYC, Tokyo→TYO, Chicago→CHI (multi-airport metros) |
| Override table — single airport | `TestResolveIata` | Sydney→SYD, Dubai→DXB, Singapore→SIN (single-airport cities) |
| Override case-insensitive | `TestResolveIata` | `"london"` / `"LONDON"` / `"LoNdOn"` all → `"LON"` |
| CSV fallback | `TestResolveIata` | `"San Francisco"` → `"SFO"` via airports.csv |
| Unknown city graceful degradation | `TestResolveIata` | Unrecognised input uppercased and passed through |

#### Automated — Playwright (`tests/test_browser.py` — 7 tests, real Chromium)

Uses a local mock HTTP server (`_DuffelMockHandler` on port 9876) so the Streamlit process never calls the real Duffel API. `DUFFEL_BASE_URL` env var points the app at the mock.

| Test | What is verified |
|---|---|
| Search produces results table | Smoke test: form submit → dataframe visible |
| Enter key submits form | `st.form` keyboard submission works |
| Row select keeps results table | Regression: session-state fix prevents results wipeout when selectbox triggers rerun |
| Row select shows breakdown | Choosing a row in the "Score breakdown for:" dropdown shows the per-factor charts |
| Empty form shows warning | Warning message visible in browser when search clicked with no fields |
| City name search resolves and returns results | "New York" / "London" resolve to metro codes and produce results |
| Selecting different rows updates breakdown | Switching the selectbox to a different row changes the breakdown heading |

#### Manual only (no automated equivalent)

| Test | What to verify |
|---|---|
| City autocomplete | Typing "San Francisco" offers SFO; selecting it populates the IATA code |
| Score color-banding | Results table uses green/yellow/red bands matching score thresholds |
| Sweet spot slider | Dragging the handles updates min/max values; search re-run reflects new sweet spot |
| Connection weight slider | Moving to 0.0 flattens connection scores; 2.0 amplifies them |
| Penalty checkboxes effect | Unchecking red-eye removes the 10-pt penalty from known red-eye flights |
| Row expansion | Choosing a row in "Score breakdown for:" reveals per-factor stacked bar totalling the agony score |
| Cost vs agony chart | Toggling chart open shows one dot per itinerary; hover shows airline/score/price |
| Pareto frontier | Cheapest option at each agony level is connected by the step line |

---

## 11. Constraints and Assumptions

- Duffel test environment (`duffel_test_*` token) uses Duffel Airways (ZZ), a synthetic airline — schedules and prices are not realistic. Switch to a `duffel_live_*` token for real airline inventory.
- Duffel returns departure times in local time — this is the correct basis for red-eye detection (traveler experience, not UTC)
- `sweet-spot-min` must be > 45 minutes (below 45 min, any connection is dangerous regardless of preference; the interpolation curve would divide by zero)
- `sweet-spot-max` must be ≤ 360 minutes (above 360 min, the upper scoring curve inverts)
- `connection-weight` range: 0.0–2.0 (dimensionless multiplier applied to all per-connection scores)
