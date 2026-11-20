# fxscanner

Trend-pullback forex scanner. Scans configured symbols on a higher timeframe
(trend + support/resistance) and a lower one (trigger candle) and prints setups
with entry, stop, target and suggested lot size. **It places no orders; execution is a separate stage.**

Rules: buy in an uptrend after a pullback to support, sell in a downtrend after
a bounce to resistance, otherwise do nothing.

## Layout

```
src/fxscanner/
  core/        pure functions: pivots, trend, zones, triggers, sizing, rules
  adapters/    CandleSource protocol; MT5 (Windows), fake (tests)
  scanner/     scan loop + de-duplication state
  config.py    strategy/risk settings and broker profiles (TOML)
  cli.py       `fxscan scan`
tests/         pytest; core is tested with hand-built candle fixtures
```

`core/` has no I/O and no broker imports, so it runs and tests anywhere.
Only `adapters/mt5.py` needs Windows plus the MT5 terminal.

## Setup (Windows, with MT5 installed and logged in once)

```
py -m venv .venv && .venv\Scripts\activate
pip install -e ".[mt5,dev]"
copy config.example.toml config.toml     # fill in server names
set FUSION_MT5_LOGIN=12345678
set FUSION_MT5_PASSWORD=your-demo-password
fxscan scan --broker fusion               # once
fxscan scan --broker fusion --interval 600
```

### Sending signals to the hub

Add a `[hub]` section (see `config.example.toml`) and set the shared secret:

```
set FX_HUB_SECRET=<same value as FX_HMAC_SECRET on the hub>
```

Each scan then delivers new signals and a heartbeat. If the hub is unreachable, signals wait
in `hub_outbox.json` and are retried first on the next scan, so nothing is lost. A wrong secret
or a badly skewed PC clock stops the run with a clear error instead of queueing forever.

Brokers are profiles in `config.toml`: server, credential env-var names, symbol
suffix/map and server UTC offset. Adding a broker is config only, no code change.
Credentials are read from environment variables, never from the file.

## Development (any OS)

```
pip install -e ".[dev]"
pytest && ruff check . && mypy
```

## Known limitations

- `pip_size` is a heuristic (JPY pairs vs the rest). Metals/indices need explicit sizes.
- `pip_value_per_lot` is one configured number. Real values differ for JPY and cross
  pairs; the executor stage should read it from the broker's symbol info.
- Break-and-retest trigger is not implemented yet (pin bar and engulfing are).
- MT5 adapter is unit-tested against a stub only. Verify it once on a real demo terminal.
- Candle times are normalised with `server_utc_offset_hours`; check it against a chart.

## Next stages

1. Backtester reusing `core/` unchanged.
2. Demo-only executor that claims orders from the hub, with guards (account type check,
   lot sizing from real symbol info, max open trades).
