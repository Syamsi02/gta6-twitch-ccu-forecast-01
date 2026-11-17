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
the weighted median of those log-ratios as its centre and the weighted
spread as its uncertainty, anchored on this launch's own hour-1 print.

Two filters keep the pool honest: a launch only counts if it was already
live at midnight UTC (hour 1 at least a tenth of its own day peak), and
launches flagged for early access are dropped, since an audience that
unlocked days early has already flattened its release-day curve. Games are
weighted by how close their hour-1 print is to this launch's in log space.
The centre curve and the spread are smoothed over a centred 3-hour window.
If the pool is too thin or hour 1 is not a live launch hour, it falls back
to flat persistence with a widening spread.

Leave-one-out validation on the 38 comparable launches in the practice
cases: mean pinball loss ~0.22–0.23, against ~0.30–0.33 for flat
persistence on the same games.

## Files

- `main.py` — the forecaster (Python 3.13, standard library only, single
  file, no local imports, so it runs as `python3 -P -s main.py`).

## License

MIT — see `LICENSE`.

---

<sub>Entered on [make.fun](https://make.fun/?ref=fgwhnby2&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
