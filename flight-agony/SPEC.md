# Flight Agony — Specification

> **Sync rule**: Any change to scoring logic, preferences, output format, or API behaviour
> must be reflected here, in `SKILL.md`, `PRD.md`, `README.md`, and `scripts/search_flights.py`.
> `SETUP.md` must be updated for any change to dependencies, flags, or environment variables.

---

## 1. Folder structure

```
Claude Code/flight-agony/
├── SPEC.md                  ← this file; scoring model, I/O contracts, roadmap
├── SKILL.md                 ← Claude's invocation instructions + design rationale
├── PRD.md                   ← product requirements and test plan
├── README.md                ← user-facing doc: how to search, interpret scores, express preferences
├── SETUP.md                 ← engineering doc: API key, dependencies, CLI flags, running tests
├── requirements.txt         ← pip dependencies: requests, streamlit, plotly
├── scripts/
│   └── search_flights.py    ← Duffel API call, agony scoring, ranked table output
├── tests/
│   └── test_scoring.py      ← pytest unit tests for scoring and preferences
└── web/
    ├── app.py               ← Streamlit web UI
    └── airports.csv         ← IATA code lookup table for city-name autocomplete
```

All three documents (SPEC.md, SKILL.md, PRD.md) must be kept in sync — see sync rule above.

Planned additions (v2):
```
└── web/
    └── profiles.json        ← saved named preference profiles ("road warrior", etc.)
```

---

## 2. Implementation map

All v1 logic lives in `scripts/search_flights.py`.

| Spec section | What it covers | Function(s) / Class |
|---|---|---|
| §5 Data source | Duffel auth + search | `search_flights()` |
| §5 Session + retry | Shared session with backoff on 429/5xx | `_build_session()` |
| §6 Input | CLI argument parsing | `main()` — argparse block |
| §6 Slice guard | Skip offers without exactly 2 slices | `main()` — offer loop with `if not slices` |
| §6 Deduplication | Remove identical schedules, keep cheapest price | `main()` — `seen` dict keyed on `(out_leg, ret_leg)` |
| §7.1 Connection quality | Per-connection scoring | `connection_score()`, `layover_base_score()` |
| §7.2 Global factors | Journey time + red-eye | `agony_score()` |
| §7.3 Overall cap | Score capping | `agony_score()` — final `min(100, ...)` |
| §8 Preference system | User preference model + validation | `Preferences` dataclass (incl. `extra_chaotic_airports`); `__post_init__` enforces all constraints; flags wired in `main()` |
| §9.1 Table | Ranked output | `print_table()`, `format_leg()` |
| §9.2 Trade-off summary | Best pick + most useful contrast | `_tradeoff_summary()` |
| §9.3 Preference echo | Active prefs header above table | `print_table()` — prefs block |
| §10 Error handling | Credential + API + network errors | `main()` — guard clauses + full exception cascade |
| Parsing helpers | Shared utilities (incl. multi-day ISO 8601) | `parse_duration()` (handles `P1DT2H30M`), `layover_minutes()`, `is_redeye()`, `carrier_code()` |

---

## 3. Purpose

A Claude skill that searches for round-trip flights between two cities on specific dates
and ranks every itinerary by an **Agony Index** — a 0–100 score measuring how miserable
a routing is to fly. Price is excluded from the score so users can make their own
agony-per-dollar trade-off.

---

## 4. Scope

**In scope (v1):**
- Round-trip flights, single date pair
- Natural language input parsed by Claude
- Per-leg agony scoring (outbound + return independently)
- User preference overrides via natural language → CLI flags
- Terminal output: ranked markdown table

**Explicitly out of scope (v1):**
- One-way or multi-city itineraries
- Date flexibility (±N days)
- Price as an agony factor
- Web UI (planned for v2)
- Saved preference profiles (planned for v2)
- Booking or deep-links

---

## 5. Data source

| Item | Value |
|---|---|
| API | Duffel Air — Offer Requests v2 |
| Base URL | `https://api.duffel.com` (same URL for test and live) |
| Auth | Bearer token (`DUFFEL_API_KEY`); `duffel_test_*` for sandbox, `duffel_live_*` for production |
| Endpoint | `POST /air/offer_requests?return_offers=true` |
| Max results | 20 (configurable via `--max`; client-side slice of the response) |
| Currency | As returned by Duffel (`total_currency` on each offer) |

Test environment uses Duffel Airways (IATA: ZZ) — a synthetic airline with reliable but unrealistic schedules and prices. Switch to a `duffel_live_*` token for real airline inventory.

**Note:** Amadeus for Developers self-service portal is being decommissioned July 17, 2026. Duffel is the replacement data source.

---

## 6. Input specification

Claude extracts the following from natural language and passes them to the script:

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `--origin` | IATA code | Yes | Claude resolves city names; asks if ambiguous |
| `--destination` | IATA code | Yes | Same |
| `--depart` | YYYY-MM-DD | Yes | Outbound date |
| `--return` | YYYY-MM-DD | Yes | Return date |
| `--adults` | int | No | Default: 1 |
| `--max` | int | No | Default: 20 |

Plus preference flags — see Section 8.

---

## 7. Agony Index — scoring model

Scores are calculated **per leg** (outbound and return separately). Total is capped at 100.

### 7.1 Connection quality (per connection, summed)

Each connection on a leg is scored independently and the scores are summed. A "connection"
is the gap between two consecutive segments.

**Layover base score** — U-shaped curve:

| Layover length | Base score |
|---|---|
| ≤ 45 min (dangerous) | 18 pts |
| 45 min → sweet_spot_min | Linear: 18 → 0 |
| sweet_spot_min → sweet_spot_max | 0 pts (sweet spot) |
| sweet_spot_max → 360 min | Linear: 0 → 12 |
| ≥ 360 min (very long) | 12 pts |

Default sweet spot: **90–180 minutes**.

**Modifiers** (added to base score):

| Condition | Modifier | Flag to disable |
|---|---|---|
| Connection airport in chaotic list | +5 pts | `--no-airport-penalty` |
| Operating carrier changes (interline) | +5 pts | `--no-interline-penalty` |

**Chaotic airports:** ORD, ATL, CDG, EWR, LAX, JFK, MIA, PHL

**Per-connection cap:** 25 pts

**Connection weight:** `(base + modifiers) × connection_weight`, then capped at 25.
Default `connection_weight` = 1.0.

### 7.2 Global factors

| Factor | Max pts | Rule | Flag to disable |
|---|---|---|---|
| Journey time penalty | 20 | +5 pts per 25% over the fastest option in results | `--no-time-penalty` |
| Red-eye departure | 10 | Flat 10 pts if departure hour is 23:00–04:59 | `--no-redeye-penalty` |

### 7.3 Overall cap

`final_score = min(100, round(sum_of_all_factors))`

---

## 8. Preference system

### 8.1 CLI flags

| Flag | Type | Default | Effect |
|---|---|---|---|
| `--sweet-spot-min N` | int (minutes) | 90 | Lower bound of comfortable layover window. Must be > 45 (= `DANGEROUS_BELOW`); equal or lower causes division-by-zero in layover interpolation. |
| `--sweet-spot-max N` | int (minutes) | 180 | Upper bound of comfortable layover window. Must be > `--sweet-spot-min` and <= 360 (= `LONG_ABOVE`); exceeding 360 inverts the upper interpolation curve. |
| `--no-airport-penalty` | bool flag | off | Disables +5 modifier for chaotic hubs |
| `--no-interline-penalty` | bool flag | off | Disables +5 modifier for carrier changes |
| `--no-redeye-penalty` | bool flag | off | Disables 10-pt red-eye factor |
| `--no-time-penalty` | bool flag | off | Disables journey time factor |
| `--connection-weight F` | float | 1.0 | Scales all per-connection scores. Range: 0.0–2.0 (inclusive). Values outside this range are rejected. |
| `--extra-chaotic-hubs IATA[,IATA...]` | string | `""` | Comma-separated IATA codes added to the built-in chaotic airport list at runtime (e.g. `LHR,MAN`). Case-insensitive; codes are normalised to uppercase. Useful for known disruptions (strikes, severe weather) without editing the script. |

**Validation** — all three constraints are enforced in `Preferences.__post_init__`. Invalid values raise `ValueError` with a descriptive message; the CLI surfaces this via `argparse.error()` (clean exit, no traceback). Multiple violations are reported together.

### 8.2 Natural language → flag mapping (Claude's responsibility)

| User says | Flag(s) |
|---|---|
| "I don't mind long layovers" | `--sweet-spot-max 360` |
| "I need at least 2 hours between flights" | `--sweet-spot-min 120` |
| "airports don't bother me" | `--no-airport-penalty` |
| "I'm fine with red-eyes" | `--no-redeye-penalty` |
| "stops don't bother me" | `--connection-weight 0.5` |
| "I really hate connections" | `--connection-weight 1.5` |
| "I don't mind different airlines" | `--no-interline-penalty` |
| "I don't care about travel time" | `--no-time-penalty` |

### 8.3 Default profile

Represents a typical leisure traveler. No flags required — omit all preference flags to use defaults.

---

## 9. Output specification

### 9.1 Table

Ranked by average agony ((outbound + return) / 2), ascending. Columns:

| Column | Content |
|---|---|
| Rank | 1-based integer |
| Airline(s) | Sorted unique carrier codes, `/`-separated |
| Outbound | Dep time → arr time (duration, stops) |
| Return | Same format |
| Agony ↑ | Outbound score (0–100) |
| Why ↑ | Plain-English explanation of outbound score drivers |
| Agony ↓ | Return score (0–100) |
| Why ↓ | Plain-English explanation of return score drivers |
| Avg | Mean of both scores, 1 decimal place |
| Price | Total price in local currency |

### 9.2 Summary

Two sentences below the table:
1. Name the best pick, its avg score, and price
2. A trade-off observation — look for the most useful contrast among these, in priority order:
   - Best option is not the cheapest: note the cheaper alternative's price saving and what drives its higher agony score
   - Runner-up has a lopsided outbound vs return (gap ≥ 15 pts): flag which leg is worse and suggest swapping
   - Fallback: name the most agonizing option and its primary pain point

Implemented by `_tradeoff_summary()` in `search_flights.py`.

### 9.3 Preference echo

Print the active preferences (sweet spot range + any active flags) above the table so
the user can see what profile was applied.

---

## 10. Error handling

| Condition | Exception caught | Behaviour |
|---|---|---|
| Missing API credentials | — | Print setup instructions and exit before making any request |
| Invalid preferences | `ValueError` from `__post_init__` | `argparse.error()` — clean exit with message, no traceback |
| Request timeout | `requests.Timeout` | Print actionable message ("did not respond in time") and exit 1 |
| DNS / connection failure | `requests.ConnectionError` | Print message with underlying cause and exit 1 |
| HTTP error from Duffel | `requests.HTTPError` | Print HTTP status + first 500 chars of response body and exit 1 |
| Other network failure (SSL, redirect loop, etc.) | `requests.RequestException` | Print message and exit 1 |
| Non-JSON response body | `ValueError` from `resp.json()` | Print "Unexpected response format" and exit 1 |
| No results returned | — | Print "No flights found" and exit 0 |
| Offer missing slices (not exactly 2) | — | Skip the offer, print a warning to stderr naming the count dropped; if all offers are skipped, exit 0 |
| Ambiguous city name | — | Claude asks for clarification before running the script |

---

## 11. Performance

**No token caching needed** — Duffel uses long-lived Bearer tokens (`duffel_test_*` or
`duffel_live_*`) that do not expire on a per-request basis. The token is read from
`DUFFEL_API_KEY` on each invocation — no on-disk cache required.

**Connection pooling + retry logic** — all HTTP calls share a single `requests.Session`
built by `_build_session()`. The session mounts a `urllib3.Retry` adapter that:
- Retries up to 3 times on `{429, 500, 502, 503, 504}` (transient errors)
- Exponential backoff: 0.5 s, 1 s, 2 s between attempts
- Covers both `GET` and `POST`
- Respects `Retry-After` headers on 429 responses
- Returns the bad response after exhausting retries (`raise_on_status=False`) so our own exception handlers deal with the final status code

The session is opened as a context manager in `main()` and passed into `search_flights()`.

---

## 12. Dependencies

```
requests
streamlit
plotly
```

Install:
```bash
pip install requests streamlit plotly
```

---

## 13. Web UI specification

Implemented in `web/app.py` using Streamlit. Run with:
```bash
streamlit run web/app.py
```

### 13.1 Layout

Two-column layout: narrow left sidebar for preferences, wide main area for search and results.

**Sidebar — Preferences**

| Control | Type | Maps to |
|---|---|---|
| Comfortable layover window | Dual-handle slider, 46–360 min, default 90–180 | `--sweet-spot-min`, `--sweet-spot-max` |
| Connection weight | Single slider, 0.0–2.0, default 1.0, step 0.1 | `--connection-weight` |
| Chaotic airport penalty | Checkbox, default on | `--no-airport-penalty` when unchecked |
| Interline penalty | Checkbox, default on | `--no-interline-penalty` when unchecked |
| Red-eye penalty | Checkbox, default on | `--no-redeye-penalty` when unchecked |
| Journey time penalty | Checkbox, default on | `--no-time-penalty` when unchecked |
| Extra chaotic hubs | Text input, comma-separated IATA codes | `--extra-chaotic-hubs` |

No separate "active preferences" echo above the table — the sidebar is the live display of active preferences.

**Main area — Search form**

| Field | Control | Notes |
|---|---|---|
| From | Text input with autocomplete | Resolves city names via `airports.csv` lookup; falls back to raw IATA if not found |
| To | Text input with autocomplete | Same |
| Depart | Date picker | |
| Return | Date picker | |
| Adults | Number input, default 1 | |
| Max results | Number input, default 20 | |

**Main area — Results**

Displayed after a successful search:
1. Ranked table (see §13.2)
2. Two-sentence summary (same logic as CLI `_tradeoff_summary()`)
3. Cost vs agony chart (see §13.3), collapsed by default

### 13.2 Results table

Same columns as CLI output (§9.1): Rank, Airline(s), Outbound, Return, Agony ↑, Why ↑, Agony ↓, Why ↓, Avg, Price.

**Score color-banding** — applied to both Agony ↑ and Agony ↓ columns:

| Range | Color |
|---|---|
| 0–30 | Green |
| 31–60 | Amber |
| 61–100 | Red |

**Row expansion** — selecting a row via the "Score breakdown for:" dropdown reveals a stacked horizontal bar showing the individual factor contributions to that leg's score: layover, hub, interline, time, red-eye. The bar segments are color-coded by factor.

### 13.3 Cost vs agony chart

Scatter plot (Plotly): x = price (numeric), y = avg agony. One dot per deduplicated itinerary. Hovering a dot shows the airline, outbound, return, and both leg scores. The Pareto frontier (cheapest option at each agony level, step-wise) is drawn as a line so the cost-agony trade-off is immediately visible.

Displayed as an expandable section below the results table.

### 13.4 City → IATA lookup

`airports.csv` is a bundled table with at minimum: `iata_code`, `name`, `city`, `country`. When the user types in the From/To fields, the app filters this table to show matching airports. This removes the need for a Claude call to resolve city names in the web UI.

Source: OpenFlights `airports.dat` (public domain, ~7K rows).

---

## 14. Planned for v2

- Named/saved preference profiles ("road warrior", "family travel", etc.)
- Date flexibility (±1 day window)
- Per-factor weights (replace single `--connection-weight` with granular controls)
- One-way search mode
- Refresh the chaotic airports list against OTP data
