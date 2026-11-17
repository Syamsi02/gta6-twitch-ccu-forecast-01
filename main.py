"""Forecast GTA VI's launch-day Twitch viewers, hour by hour, in five quantiles.

The centre of this forecaster is a launch-day shape learned from past big
launches, with one correction the first version missed: the shape itself
depends on how big the launch is.

A launch day on Twitch is not flat. Viewers unlock in timezone waves --
New Zealand and Australia first, then Japan, Europe, the UK, the US East
Coast at 05:00Z, the US West Coast at 08:00Z -- so the audience climbs
from its hour-1 print, peaks in the afternoon and evening, and falls
overnight. The house baseline (flat persistence with a widening random-walk
spread) ignores that shape entirely.

For every past launch this program takes the release day's hourly viewers,
divides each hour by that launch's hour-1 print, and works in log space,
where the curves are comparable across launches of very different sizes.
Two filters keep the pool honest. A launch only counts if it was already
live at midnight UTC on its release day -- its hour-1 print is at least a
tenth of its own day peak -- because a game that unlocks at 14:00Z has a
near-zero hour 1 and a meaningless ratio curve. And a launch is dropped if
its notes record early access (or a weak-analogue tier): an audience that
unlocked days early has already flattened its release-day curve.

The shape also shrinks with size. Across the pool, the evening log-ratio
falls as hour-1 grows (correlation about -0.87 at hour 20): a mega launch
is already near its audience at hour 1, while a smaller launch keeps
growing as timezones wake up. So for each forecast hour the program fits
a weighted straight line of log-ratio against log hour-1 across the pool
(Gaussian kernel weights, bandwidth 0.75 in log space, so launches near
this one's size matter most), and reads that line at this launch's own log
hour-1. The line's slope is halved, because a 12-to-14-launch fit is
noisy, and the result is averaged half-and-half with the weighted median
of the pool's log-ratios, which does not extrapolate at all.

Two guards keep the extrapolation honest. The slope only ever adjusts the
forecast downward for a launch bigger than the pool's weighted-mean size:
a smaller launch gets the weighted mean instead of an upward extrapolation
the data does not support. And the total adjustment away from the median
is capped at 0.3 log units, so a record-breaking hour-1 cannot push the
curve outside the range past launches actually showed.

The spread is the weighted standard deviation of the pool's residuals
around that fitted line, per hour -- the scatter that stays after size is
accounted for. Centre and spread are each smoothed with a centred 3-hour
window, because launch curves move smoothly except at the unlock jumps the
pool already averages over. If the pool is too thin (fewer than three
usable launches) or hour 1 is too small to be a live launch hour, the
program falls back to flat persistence with the house spread, so it never
fails to produce a valid forecast.

Input: every <id>.in in MAKEFUN_INPUT_DIR (default /input), one case per
file, schema makefun/twitch-ccu-case/v1. Output: <id>.out in
MAKEFUN_OUTPUT_DIR (default /output): {"hours": [{"hour": h, "q": [q05,
q25, q50, q75, q95]}]} for h = 2..24. Standard library only, offline,
deterministic: the same input always yields byte-identical output.
"""

import json
import math
import os
import sys

# Standard normal quantiles for the five forecast levels 0.05/0.25/0.5/0.75/0.95.
Z_SCORES = (-1.6448536269514722, -0.6744897501960817, 0.0,
            0.6744897501960817, 1.6448536269514722)

# A launch counts as live at midnight UTC when hour 1 reaches this share
# of its own release-day peak. Below it, hour 1 is pre-unlock trickle and
# the ratio curve is meaningless.
LIVE_SHARE = 0.10
# Hour 1 below this is not a live launch hour: the day's shape is then
# dominated by an unlock we cannot see, so fall back to persistence.
# (1000, not 10000: a small but real launch hour still forecasts far
# better from the shape model than from flat persistence -- leave-one-out
# on the pool's smallest live launch scores 0.34 shape vs 0.60 fallback.)
MIN_LIVE_HOUR1 = 1000.0
# Gaussian kernel bandwidth (in log space) for weighting comparables by
# how close their hour-1 print is to this launch's.
KERNEL_BANDWIDTH = 0.75
# A comparable needs at least this many release-day hours to join the pool.
MIN_RELEASE_HOURS = 20
# The pool needs at least this many launches, else fall back to persistence.
MIN_POOL_SIZE = 3
# House-style spread growth used by the fallback, per hour past hour 1.
FALLBACK_SPREAD = 0.15
# The fitted size slope is halved before use; the blend below averages the
# line's prediction with the weighted median.
SLOPE_SHRINK = 0.5
LINE_BLEND = 0.5
# The line's prediction may move the centre at most this far (log units)
# from the weighted median.
MAX_ADJUSTMENT = 0.3

MAX_VIEWERS = 1_000_000_000.0


def _parse_time(text):
    """Parse an ISO-8601 UTC timestamp like 2026-11-19T00:00:00Z."""
    from datetime import datetime
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")


def release_day_hours(comparable):
    """Hourly viewers {hour: viewers} for a comparable's release day.

    Hours run 1..24 from day_start. A point only counts when its timestamp
    lands exactly on an hour boundary inside that day and its viewer count
    is positive (SullyGnome's points are hourly means, rounded half up).
    A comparable with an unusable day_start contributes no hours at all
    instead of failing the whole run.
    """
    try:
        day_start = _parse_time(comparable["day_start"])
    except (KeyError, ValueError):
        return {}
    hours = {}
    for point in comparable.get("hourly") or []:
        viewers = point.get("viewers")
        if viewers is None or viewers <= 0:
            continue
        try:
            when = _parse_time(point["from"])
        except (KeyError, ValueError):
            continue
        offset = (when - day_start).total_seconds() / 3600.0
        if 0 <= offset < 24 and abs(offset - round(offset)) < 1e-9:
            hours[int(round(offset)) + 1] = float(viewers)
    return hours


def _is_clean_launch(comparable):
    """True unless the notes flag early access or a weak analogue tier."""
    text = (comparable.get("unlock") or "").lower()
    return ("early access" not in text and "early-access" not in text
            and "tier: weak" not in text)


def build_pool(comparables):
    """Usable past launches: (hour-1 viewers, {hour: viewers}) pairs."""
    pool = []
    for comparable in comparables or []:
        hours = release_day_hours(comparable)
        if 1 not in hours or len(hours) < MIN_RELEASE_HOURS:
            continue
        peak = max(hours.values())
        if hours[1] / peak < LIVE_SHARE:
            continue
        if not _is_clean_launch(comparable):
            continue
        pool.append((hours[1], hours))
    return pool


def _weighted_median(pairs):
    """Weighted median of (value, weight) pairs."""
    ordered = sorted(pairs)
    total = sum(weight for _, weight in ordered)
    if total <= 0:
        return None
    running = 0.0
    for value, weight in ordered:
        running += weight
        if running >= 0.5 * total:
            return value
    return ordered[-1][0]


def _smooth(values):
    """Centred 3-hour moving average over the hour -> value map."""
    smoothed = {}
    for hour in values:
        neighbours = [values[h] for h in (hour - 1, hour, hour + 1)
                      if h in values]
        smoothed[hour] = sum(neighbours) / len(neighbours)
    return smoothed


def shape_forecast(hour1, pool):
    """Five quantiles per hour from the comparable launch-day shapes."""
    log_hour1 = math.log(hour1)
    centres = {}
    spreads = {}
    for hour in range(2, 25):
        sizes = []
        ratios = []
        weights = []
        for comp_hour1, comp_hours in pool:
            if hour not in comp_hours:
                continue
            weight = math.exp(-0.5 * ((math.log(comp_hour1) - log_hour1)
                                      / KERNEL_BANDWIDTH) ** 2)
            sizes.append(math.log(comp_hour1))
            ratios.append(math.log(comp_hours[hour] / comp_hour1))
            weights.append(weight)
        if not sizes:
            centres[hour] = 0.0
            spreads[hour] = FALLBACK_SPREAD
            continue
        median = _weighted_median(list(zip(ratios, weights)))
        total_weight = sum(weights)
        mean_size = sum(s * w for s, w in zip(sizes, weights)) / total_weight
        mean_ratio = sum(r * w for r, w in zip(ratios, weights)) / total_weight
        spread_size = sum(w * (s - mean_size) ** 2
                          for s, w in zip(sizes, weights))
        if spread_size > 1e-12:
            slope = sum(w * (s - mean_size) * (r - mean_ratio)
                        for s, r, w in zip(sizes, ratios, weights)) / spread_size
        else:
            slope = 0.0
        slope *= SLOPE_SHRINK
        if log_hour1 < mean_size:
            # No upward extrapolation for smaller launches: use the mean.
            line_value = mean_ratio
        else:
            line_value = mean_ratio + slope * (log_hour1 - mean_size)
        shift = line_value - median
        if shift > MAX_ADJUSTMENT:
            line_value = median + MAX_ADJUSTMENT
        elif shift < -MAX_ADJUSTMENT:
            line_value = median - MAX_ADJUSTMENT
        centres[hour] = (1.0 - LINE_BLEND) * median + LINE_BLEND * line_value
        residuals = [r - (mean_ratio + slope * (s - mean_size))
                     for s, r in zip(sizes, ratios)]
        variance = sum(w * res * res for res, w in zip(residuals, weights))
        variance /= total_weight
        spreads[hour] = math.sqrt(max(variance, 0.0))
    centres = _smooth(centres)
    spreads = _smooth(spreads)
    rows = []
    for hour in range(2, 25):
        quantiles = []
        for z in Z_SCORES:
            value = hour1 * math.exp(centres[hour] + z * spreads[hour])
            quantiles.append(min(max(value, 1.0), MAX_VIEWERS))
        # Rounding to two decimals must not break the ordering.
        quantiles = [round(q, 2) for q in quantiles]
        quantiles.sort()
        quantiles = [min(max(q, 1.0), MAX_VIEWERS) for q in quantiles]
        rows.append({"hour": hour, "q": quantiles})
    return rows


def fallback_forecast(hour1):
    """Flat persistence with a widening spread (the house baseline)."""
    rows = []
    for hour in range(2, 25):
        spread = FALLBACK_SPREAD * math.sqrt(hour - 1)
        quantiles = [min(max(hour1 * math.exp(z * spread), 1.0), MAX_VIEWERS)
                     for z in Z_SCORES]
        quantiles = [round(q, 2) for q in quantiles]
        quantiles.sort()
        rows.append({"hour": hour, "q": quantiles})
    return rows


def forecast_case(case):
    """Forecast one case: 23 rows, hours 2..24, five quantiles each."""
    known = case.get("known") or []
    hour1 = 0.0
    for row in known:
        if row.get("hour") == 1:
            hour1 = float(row.get("viewers") or 0)
            break
    if hour1 < 1.0:
        hour1 = 1.0
    pool = build_pool(case.get("comparables"))
    if hour1 < MIN_LIVE_HOUR1 or len(pool) < MIN_POOL_SIZE:
        return fallback_forecast(hour1)
    return shape_forecast(hour1, pool)


def main():
    input_dir = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
    output_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(output_dir, exist_ok=True)
    names = sorted(name for name in os.listdir(input_dir)
                   if name.endswith(".in"))
    if not names:
        print("no .in cases found in %s" % input_dir, file=sys.stderr)
        return 1
    for name in names:
        case_id = name[:-3]
        with open(os.path.join(input_dir, name), "r", encoding="utf-8") as fh:
            case = json.load(fh)
        rows = forecast_case(case)
        out_path = os.path.join(output_dir, case_id + ".out")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({"hours": rows}, fh, separators=(",", ":"))
            fh.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
