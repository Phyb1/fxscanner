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

`core/` has no I/O and no broker imports, so it runs and tests anywhere (the only dependency,
python-decouple, is used for `.env` loading outside `core/`).
Only `adapters/mt5.py` needs Windows plus the MT5 terminal.

## Setup (Windows, with MT5 installed and logged in once)

```
py -m venv .venv && .venv\Scripts\activate
pip install -e ".[mt5,dev]"
copy config.example.toml config.toml     # fill in server names
copy .env.example .env                    # then edit .env (or use attach = true: no password)
fxscan scan --broker fusion               # once
fxscan scan --broker fusion --interval 600
fxscan scan --broker fusion --interval 600 --verbose   # one explanatory line per pair
```

### Sending signals to the hub

Add a `[hub]` section (see `config.example.toml`) and set the shared secret:

```
FX_HUB_SECRET="<same value as FX_HMAC_SECRET on the hub>"   # in .env
```

Each scan then delivers new signals and a heartbeat. If the hub is unreachable, signals wait
in `hub_outbox.json` and are retried first on the next scan, so nothing is lost. A wrong secret
or a badly skewed PC clock stops the run with a clear error instead of queueing forever.

**No password needed:** set `attach = true` in the broker profile and the scanner uses whichever
account your MT5 terminal is already logged in to. Log in inside MT5 first.

Brokers are profiles in `config.toml`: server, credential env-var names, symbol
suffix/map and server UTC offset. Adding a broker is config only, no code change.
Credentials live in a `.env` file (loaded with python-decouple from the folder where you run
`fxscan`) or in real environment variables, which take priority. `config.toml` only holds the
*names* of those variables. Quote values with special characters: `FUSION_MT5_PASSWORD="p&ss^1"`.

## Backtesting

```
fxscan backtest --broker fusion               # downloads ~2 years, caches CSVs in data/, reports
fxscan backtest --offline --spread 1.0        # rerun from the cache, no MT5, fixed spread
fxscan backtest --broker fusion --years 3 --symbols EURUSD GBPUSD
```

It replays history candle by candle through the same `core/` rules the live scanner uses.
A higher-timeframe candle is only visible once it has closed, and pivots only count once
confirmed, so nothing is known before it could have been. Costs: live spread (or a fixed one)
plus slippage (`[backtest] slippage_pips`). If one candle touches both stop and target, the
stop is assumed to hit first. One trade per pair at a time. Trades are saved to
`backtest_trades.csv`. Fewer than 50 trades is flagged as too few to conclude anything.

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
- MT5 adapter is unit-tested against a stub; it has been verified on a real Fusion demo terminal.
- `server_utc_offset_hours = "auto"` detects the broker's time zone from a live tick (it follows
  daylight saving). At weekends no fresh tick exists, so `offset_fallback_hours` applies.

## Next stages

1. Demo-only executor that claims orders from the hub, with guards (account type check,
   lot sizing from real symbol info, max open trades).
