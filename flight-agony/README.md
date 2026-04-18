# Flight Agony

Find round-trip flights and rank them by how miserable they are to fly — separately from price, so you can make your own trade-off.

---

## What it does

Flight Agony scores every itinerary on a 0–100 **Agony Index** and ranks them from least painful to most. The score has nothing to do with price — it measures the actual experience of flying that routing.

You get a table like this:

| Rank | Airline(s) | Outbound | Return | Agony ↑ | Why ↑ | Agony ↓ | Why ↓ | Avg | Price |
|---|---|---|---|---|---|---|---|---|---|
| 1 | BA | 9:00am nonstop 7h | 2:00pm nonstop 8h | 0 | Clean routing | 0 | Clean routing | 0.0 | USD 450.00 |
| 2 | AA | 6:30am via BOS 9h20m | 11:00am nonstop 8h | 23 | Tight cnx BOS (52 min); multi-airline | 0 | Clean routing | 11.5 | USD 310.00 |

The **Why** columns tell you exactly what drove each leg's score, so you can decide whether that specific pain point matters to you.

---

## How to search

Just describe what you want in plain English:

> "Find me flights from San Francisco to New York, leaving April 23rd, returning the 27th."

Or with preferences:

> "Search JFK to London June 15th returning June 22nd — I don't mind long layovers and red-eyes are fine."

> "Flights from SJC to Tucson next Thursday, back Sunday. I really hate connections."

---

## Understanding the Agony Index

The score is built from five factors, applied independently to the outbound and return legs:

| Factor | Max pts | What it measures |
|---|---|---|
| **Layover length** | 18 | Too short risks a missed connection; too long means wasted hours. Scores 0 inside your comfort window, rising toward the edges. |
| **Chaotic hub** | +5 | Connecting through airports known for delays and complexity (ORD, ATL, CDG, EWR, LAX, JFK, MIA, PHL). |
| **Interline** | +5 | Connecting flights on different airlines — your bags and your gate agent are no longer on the same team. |
| **Journey time** | 20 | How much slower this routing is compared to the fastest option in the results. Nonstops are never penalised for route physics — only for being slower than alternatives. |
| **Red-eye departure** | 10 | Departing between 11pm and 5am. |

Scores are capped at 100. A nonstop daytime flight on the fastest routing scores 0.

---

## Expressing preferences

You don't need to learn any settings — just say what you care about:

| If you say… | What changes |
|---|---|
| "I don't mind long layovers" | Long layovers stop being penalised |
| "I need at least 2 hours between flights" | Short connections score higher |
| "Airports don't bother me" | Chaotic hub penalty removed |
| "I'm fine with red-eyes" | Red-eye penalty removed |
| "I don't care about stops" | Connection scores reduced |
| "I really hate connections" | Connection scores amplified |
| "I don't mind different airlines" | Interline penalty removed |
| "I don't care about travel time" | Journey time penalty removed |

---

## Using the web UI

Open the web interface for an interactive view with sliders, visual scores, and a cost vs agony chart:

> "Open the web UI."

The browser tab will open automatically. From there you can adjust preferences with sliders and checkboxes and see results update without typing any commands.

---

## Interpreting the results

**Low score (0–30):** Comfortable routing — good connections, reasonable hours, not dramatically slower than alternatives.

**Mid score (31–60):** Worth reading the Why column. Something is suboptimal but may not matter to you.

**High score (61–100):** Genuinely painful routing. Check whether the price saving justifies it.

**The two-sentence summary** below the table names the best pick and calls out the most useful trade-off — usually "this cheaper option scores X higher because of Y" or "the return leg is the problem here."

**Avg column** is the mean of outbound and return scores. Sorting by this keeps lopsided itineraries (great outbound, nightmare return) from hiding near the top.
