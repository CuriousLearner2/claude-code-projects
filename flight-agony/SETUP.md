# Flight Agony — Setup

Everything needed to get the tool running from scratch.

---

## Prerequisites

- Python 3.10 or later
- A free [Duffel](https://app.duffel.com/signup) account

---

## Install dependencies

```bash
pip install requests streamlit plotly
```

Or once `requirements.txt` is in place:

```bash
pip install -r requirements.txt
```

---

## Duffel API key

Flight Agony uses the [Duffel Air API](https://duffel.com/docs) to fetch real-time flight data.

1. Sign up at https://app.duffel.com/signup
2. In the dashboard go to **Developers** → **Access tokens**
3. Create a new token:
   - `duffel_test_*` — sandbox data (Duffel Airways, a synthetic airline); use this for development and testing
   - `duffel_live_*` — real airline inventory; use this when you want actual results
4. Add the token to your shell config:

```bash
# ~/.zshrc or ~/.bashrc
export DUFFEL_API_KEY="duffel_test_your_token_here"
```

5. Reload your shell:

```bash
source ~/.zshrc
```

The script reads `DUFFEL_API_KEY` from the environment on each run — no token caching or OAuth dance required.

---

## Running the CLI

```bash
python scripts/search_flights.py \
  --origin JFK \
  --destination LHR \
  --depart 2026-06-15 \
  --return 2026-06-22
```

Full list of flags:

| Flag | Default | Description |
|---|---|---|
| `--origin` | required | Origin IATA code |
| `--destination` | required | Destination IATA code |
| `--depart` | required | Outbound date (YYYY-MM-DD) |
| `--return` | required | Return date (YYYY-MM-DD) |
| `--adults` | 1 | Number of passengers |
| `--max` | 20 | Maximum results after deduplication |
| `--sweet-spot-min N` | 90 | Lower bound of comfortable layover window (minutes). Must be > 45. |
| `--sweet-spot-max N` | 180 | Upper bound of comfortable layover window (minutes). Must be ≤ 360. |
| `--connection-weight F` | 1.0 | Multiplier for all connection scores (0.0–2.0) |
| `--no-airport-penalty` | off | Disable the chaotic hub +5 modifier |
| `--no-interline-penalty` | off | Disable the interline +5 modifier |
| `--no-redeye-penalty` | off | Disable the red-eye 10-pt factor |
| `--no-time-penalty` | off | Disable the journey time factor |
| `--extra-chaotic-hubs` | `""` | Comma-separated IATA codes to add to the chaotic hub list at runtime (e.g. `LHR,MAN`) |

When invoked via Claude, natural language preferences are automatically mapped to the appropriate flags — you don't need to type them manually.

---

## Launching the web UI

```bash
python scripts/launch_web.py
```

Or directly:

```bash
streamlit run web/app.py
```

Streamlit opens a browser tab automatically. `DUFFEL_API_KEY` must be set in the environment before launching.

---

## Running tests

```bash
pytest tests/
```

No API key required — all unit tests use synthetic inputs and do not make network calls.

---

## Token types

| Token prefix | Environment | Data |
|---|---|---|
| `duffel_test_*` | Sandbox | Duffel Airways (IATA: ZZ) — synthetic schedules and prices, always available |
| `duffel_live_*` | Production | Real airline inventory — prices and schedules reflect actual availability |

Switch by updating `DUFFEL_API_KEY` in your shell config. No code changes required.
