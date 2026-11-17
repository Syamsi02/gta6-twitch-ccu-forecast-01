# gta6-twitch-ccu-forecast-01

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Syamsi02/gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Syamsi02/gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

A forecaster for the make.fun "Forecast GTA VI's launch-day Twitch viewers
hour by hour" bounty (`gta6-twitch-ccu-forecast-01`). Given one case — the
first hour's Twitch print for the "Grand Theft Auto VI" category plus the
hourly history of past big launches — it predicts hours 2–24 of release day
as five quantiles (5%, 25%, 50%, 75%, 95%) per hour.

## Run it

```sh
python3 main.py
```

It reads every `<id>.in` in `MAKEFUN_INPUT_DIR` (default `/input`) and
writes `<id>.out` to `MAKEFUN_OUTPUT_DIR` (default `/output`).

## How it works

Launch days are not flat: viewers unlock in timezone waves (New Zealand
and Australia first, then Japan, Europe, the UK, the US East Coast at
05:00Z, the US West Coast at 08:00Z), so the audience climbs from its
hour-1 print, peaks in the afternoon/evening, and falls overnight. The
program measures that shape from the case's own comparables: for each past
launch it takes the release day's hourly viewers, divides each hour by that
launch's hour-1 print, and works in log space. Each forecast hour then gets
a centre and a spread, anchored on this launch's own hour-1 print.

Two filters keep the pool honest: a launch only counts if it was already
live at midnight UTC (hour 1 at least a tenth of its own day peak), and
launches flagged for early access are dropped, since an audience that
unlocked days early has already flattened its release-day curve. Games are
weighted by how close their hour-1 print is to this launch's in log space
(Gaussian kernel, bandwidth 0.75).

The shape also shrinks with size: across the pool, the evening log-ratio
falls as hour 1 grows (correlation about -0.87 at hour 20), because a mega
launch is already near its audience at hour 1 while a smaller launch keeps
growing as timezones wake up. So for each hour the program fits a weighted
straight line of log-ratio against log hour-1 across the pool and reads it
at this launch's own log hour-1. The slope is halved, and the line's
prediction is averaged half-and-half with the weighted median of the
pool's log-ratios, which does not extrapolate at all. Two guards keep the
extrapolation honest: the slope only ever adjusts the forecast downward
for a launch bigger than the pool's weighted-mean size, and the total
adjustment away from the median is capped at 0.3 log units. The spread is
the weighted standard deviation of the pool's residuals around that fitted
line, per hour. The centre curve and the spread are smoothed over a
centred 3-hour window. If the pool is too thin or hour 1 is below 1,000
(a pre-unlock trickle, not a live launch hour), it falls back to flat
persistence with a widening spread.

Leave-one-out validation on the 38 comparable launches in the practice
cases: mean pinball loss ~0.19–0.24 depending on the target set (0.197 on
the definition that reproduces the first version's reported ~0.22), against
~0.30–0.33 for flat persistence on the same games. On the three largest
launches, forecast from the rest of the pool -- the regime the final lives
in, since GTA VI's hour-1 print will exceed every comparable -- it scores
0.098 against 0.126 for the first version.

## Files

- `main.py` — the forecaster (Python 3.13, standard library only, single
  file, no local imports, so it runs as `python3 -P -s main.py`).

## License

MIT — see `LICENSE`.

---

<sub>Entered on [make.fun](https://make.fun/?ref=fgwhnby2&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
