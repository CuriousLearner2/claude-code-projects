---
name: flight-agony
description: Search for round-trip flights between two cities on specific dates and score each itinerary with an "Agony Index" — a 0–100 score measuring ease of travel based on connection quality (layover length relative to a personal sweet spot, airport chaos, and interline carrier changes), total journey time, and red-eye departures. Use this skill whenever the user asks to find flights, compare itineraries, search for flights between cities, or wants to know how painful a flight routing is. Trigger on phrases like "find me flights", "search flights from X to Y", "what flights are there", "flight options", "compare flights", or any mention of wanting to travel between two cities on specific dates.
---

# Flight Agony Search

Find round-trip flights and rank them by how miserable they are to fly.

---

## Reference

Full scoring specification, input/output contracts, and v2 roadmap: **`SPEC.md`**
Any change to scoring logic, preferences, or output format must be reflected in both files.

---

## Design rationale

These decisions are recorded here so future edits don't accidentally undo them.

**Price is excluded from the score.**
The goal is to separate travel pain from cost so users can make their own agony-per-dollar trade-off. A cheap red-eye with two stops might be worth it to one person and not another.

**Scores are per-leg, not combined.**
Outbound and return are scored independently because they can differ dramatically — a great outbound with a nightmare return shouldn't average into "fine". Showing both lets the user spot the asymmetry.

**Connections are scored as a unit, not as separate stop/layover/airport factors.**
Originally stops, tight connections, dead layovers, chaotic hubs, and multi-airline were five separate additive penalties. This was replaced because the same connection scores very differently depending on context: a 60-minute layover at AMS on Lufthansa is routine; a 60-minute layover at ORD on a codeshare is a gamble. Scoring them together captures this interaction.

**Journey time penalty is relative, not absolute.**
A 14-hour nonstop to Tokyo isn't penalised — that's just the physics of the route. The penalty only fires when a routing is meaningfully slower than the fastest option in the same search results (every 25% slower = 5 pts). This avoids punishing long-haul routes unfairly.

**The U-shaped layover curve with a user-defined sweet spot.**
Rather than fixed thresholds (e.g. "under 75 min = bad"), the score rises smoothly outside a personal comfort zone. This lets someone who prefers 2-hour connections and someone who's happy with 90 minutes use the same model — they just shift the curve. Default sweet spot: 90–180 min.

**Chaotic hub list is hardcoded, not dynamic.**
ORD, ATL, CDG, EWR, LAX, JFK, MIA, PHL are included based on widely reported on-time performance and connection complexity. This list should be revisited periodically. Users who don't care about airports can pass `--no-airport-penalty`. For known transient disruptions (strikes, severe weather), individual airports can be added at runtime without editing the script using `--extra-chaotic-hubs LHR,MAN`.

**Connection weight multiplier instead of per-factor weights.**
Rather than exposing 5+ individual weight sliders prematurely, a single `--connection-weight` multiplier lets users express "stops matter more/less to me" without a complex UI. Individual factor weights are a natural next step for the planned web interface.

---

## When you're invoked

The user wants to find flights between two cities on specific dates. Extract:
- **Origin city/airport** (resolve to IATA code — e.g. "New York" → JFK or EWR, ask if ambiguous)
- **Destination city/airport** (resolve to IATA code)
- **Departure date** (outbound leg)
- **Return date**

If any of these are missing or ambiguous, ask before running the search.

---

## Which interface to use

**Use the CLI** (default) when the user asks to find or search for flights — it runs immediately and returns results inline. This is the right path for the vast majority of invocations.

**Suggest the web UI** only when the user explicitly asks for it (e.g. "open the web interface", "use the web UI", "I want to use the browser version"). The web UI is self-contained — once running, Claude is not involved in the session.

---

## Launching the web UI

Run the launcher script and confirm the browser tab opened:

```bash
python /path/to/skills/flight-agony/scripts/launch_web.py
```

The app handles city resolution, preferences, and display — no further Claude involvement needed once it's open.

If the launch fails due to missing dependencies or a missing `DUFFEL_API_KEY`, refer the user to `SETUP.md`.

---

## Credentials check (CLI only)

Before running a CLI search, verify `DUFFEL_API_KEY` is set in the environment. If it isn't, tell the user to follow the instructions in `SETUP.md` and try again.

---

## Listening for preferences

Before building the script command, scan the user's message for any of these signals and map them to flags:

| User says | Flag(s) to add |
|---|---|
| "I don't mind long layovers" / "long layovers are fine" | `--sweet-spot-max 360` |
| "I need at least 2 hours between flights" | `--sweet-spot-min 120` |
| "airports don't bother me" / "I don't care about airports" | `--no-airport-penalty` |
| "I'm fine with red-eyes" / "red-eyes are OK" | `--no-redeye-penalty` |
| "I don't care about stops" / "stops don't bother me" | `--connection-weight 0.5` |
| "I really hate connections" / "I hate stops" | `--connection-weight 1.5` |
| "I don't mind different airlines" | `--no-interline-penalty` |
| "I don't care about travel time" | `--no-time-penalty` |

If no preferences are mentioned, omit all flags — the defaults represent a typical leisure traveler.

## Running the search

Use the bundled script at `scripts/search_flights.py` (path is relative to this skill's directory):

```bash
python /path/to/skills/flight-agony/scripts/search_flights.py \
  --origin JFK \
  --destination LHR \
  --depart 2026-06-15 \
  --return 2026-06-22 \
  --adults 1 \
  --max 20 \
  [--sweet-spot-min 90] [--sweet-spot-max 180] \
  [--no-airport-penalty] [--no-interline-penalty] \
  [--no-redeye-penalty] [--no-time-penalty] \
  [--connection-weight 1.0]
```

The script handles authentication, the API call, agony scoring, and prints the ranked table. Parse its output and present it to the user.

---

## Agony Index scoring

Scores are calculated **per leg** (outbound and return separately). Max 100 = maximum misery.

**Connection quality** (per connection, summed across the leg):

Each connection is scored as a unit on a U-shaped curve: layovers inside the user's sweet spot score 0; too short or too long scores increase toward a cap of 25 pts per connection. Two modifiers add to the base:
- +5 pts for connecting through a chaotic hub (ORD, ATL, CDG, EWR, LAX, JFK, MIA, PHL)
- +5 pts for interline (different airline)

The `--connection-weight` multiplier scales all connection scores before capping.

**Global factors:**

| Factor | Max pts | Rule |
|---|---|---|
| **Journey time penalty** | 20 | +5 pts per 25% over the fastest option in results |
| **Red-eye departure (11pm–5am)** | 10 | Flat 10 pts |

**Default sweet spot:** 90–180 minutes. Users can shift this with natural language (see above).

Overall score is capped at 100.

---

## Output format

Present results as a markdown table ranked by **average agony** (outbound + return), lowest first:

```
## ✈️ JFK → LHR  |  Jun 15 → Jun 22  |  20 itineraries found

| Rank | Airline(s) | Outbound | Return | Agony ↑ | Why ↑ | Agony ↓ | Why ↓ | Avg | Price |
|---|---|---|---|---|---|---|---|---|---|
| 1 | BA | 9:00am nonstop 7h | 2:00pm nonstop 8h | 0 | Clean routing | 0 | Clean routing | 0 | USD 450.00 |
| 2 | AA | 6:30am via BOS 9h20m | 11:00am nonstop 8h | 23 | Tight cnx BOS (52min) | 0 | Clean routing | 12 | USD 310.00 |
...
```

The **Why ↑** and **Why ↓** columns are brief plain-English summaries of what drove each leg's score — keep each to 1–2 short phrases. Good examples:
- "Clean routing"
- "Tight cnx ORD (58 min); multi-airline"
- "Red-eye (11:30pm)"
- "Long layover AMS (5h); slow routing"

After the table, add a 2-sentence summary: name the top pick and call out any interesting trade-off worth knowing (e.g. "The AA option is 40% cheaper but scores 35 — that tight ORD connection is the main culprit").
