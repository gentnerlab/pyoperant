"""
retention.py -- limit how many clips are kept per class, and keep a
durable record of how many were detected vs. kept.

Why this exists
---------------
Some species vocalize nearly constantly (zebra finch calls), so "save every
detected episode" can mean most of the day's audio ends up on the card and
then over the network. This module lets a box cap the number of clips it
KEEPS per class per hour/day, while still counting everything the
classifier detected, so the dropped fraction is always known.

Config (config.json, `song_recording.retention`) -- all optional; a class
with no entry is unlimited, and no `retention` key at all means nothing
changes from before:

    "retention": {
        "call": {"max_per_hour": 20, "max_per_day": 200},
        "song": {"max_per_hour": 60}
    }

`max_per_hour` / `max_per_day` count SAVED clips for that class in the
current local clock hour / day. 0 keeps none of that class (it is still
counted). Caps are first-come within the window, so a busy hour keeps its
first N clips; the hourly cap (rather than a daily one alone) keeps a day's
worth spread across the day instead of all in the morning. Counters live
in memory, so a restart starts the current hour/day's budget afresh.

Counts log (`counts.csv`)
-------------------------
Every `counts_interval_s` (default 600 s), at each clock-hour boundary and
on shutdown, DetectionCounts appends one row per class seen in that
interval, plus an `all` row:

    interval_start, interval_end, species, class,
    episodes, saved, dropped, saved_s, dropped_s,   # per class
    cnn_chunks,                                     # 100 ms chunks the CNN labelled this class
    chunks_total, gate_pass_chunks                  # filled on the `all` row only

Rows are DELTAS for their interval and never straddle an hour, so sum them
by hour/day to get totals; `saved / episodes` is the retained fraction.
`cnn_chunks` counts the classifier's per-chunk argmax on gate-passed chunks,
independent of the smoother, so it describes what the CNN saw even when the
episode logic or the caps kept little of it.
"""

from __future__ import annotations

import csv
import datetime
import logging
from pathlib import Path

log = logging.getLogger(__name__)

UNCLASSIFIED = "unclassified"   # gate_only clips carry no CNN class


class RetentionLimiter:
    def __init__(self, retention_cfg: dict | None):
        self._limits: dict[str, dict] = {}
        for cls, lim in (retention_cfg or {}).items():
            if not isinstance(lim, dict):
                raise ValueError(f"retention[{cls!r}] must be a dict, got {lim!r}")
            unknown = set(lim) - {"max_per_hour", "max_per_day"}
            if unknown:
                raise ValueError(f"retention[{cls!r}]: unknown keys {sorted(unknown)}")
            for k, v in lim.items():
                if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v < 0):
                    raise ValueError(f"retention[{cls!r}].{k} must be an integer >= 0 or null, got {v!r}")
            self._limits[cls] = {"max_per_hour": lim.get("max_per_hour"),
                                 "max_per_day": lim.get("max_per_day")}
        self._hour_key = None
        self._day_key = None
        self._hour_n: dict[str, int] = {}
        self._day_n: dict[str, int] = {}

    def admit(self, cls: str, now: datetime.datetime) -> bool:
        """True if a clip of `cls` may be kept now (and counts it against
        the budget); False if a cap is already used up."""
        hour_key = (now.date(), now.hour)
        if hour_key != self._hour_key:
            self._hour_key, self._hour_n = hour_key, {}
        if now.date() != self._day_key:
            self._day_key, self._day_n = now.date(), {}
        lim = self._limits.get(cls)
        if lim:
            mh, md = lim["max_per_hour"], lim["max_per_day"]
            if mh is not None and self._hour_n.get(cls, 0) >= mh:
                return False
            if md is not None and self._day_n.get(cls, 0) >= md:
                return False
        self._hour_n[cls] = self._hour_n.get(cls, 0) + 1
        self._day_n[cls] = self._day_n.get(cls, 0) + 1
        return True


class DetectionCounts:
    FIELDS = ["interval_start", "interval_end", "species", "class",
              "episodes", "saved", "dropped", "saved_s", "dropped_s",
              "cnn_chunks", "chunks_total", "gate_pass_chunks"]

    def __init__(self, csv_path: str, species: str = "starling",
                 interval_s: float = 600.0, now: datetime.datetime | None = None):
        self._path = Path(csv_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self.species = species
        self.interval_s = float(interval_s)
        exists = self._path.exists() and self._path.stat().st_size > 0
        self._f = open(self._path, "a", newline="")
        self._w = csv.DictWriter(self._f, fieldnames=self.FIELDS)
        if not exists:
            self._w.writeheader()
            self._f.flush()
        self._reset(now or datetime.datetime.now())

    def _reset(self, start: datetime.datetime):
        self._start = start
        self._chunks_total = 0
        self._gate_pass = 0
        self._cnn_chunks: dict[str, int] = {}
        self._cls: dict[str, dict] = {}

    def _c(self, cls: str) -> dict:
        return self._cls.setdefault(
            cls, {"episodes": 0, "saved": 0, "dropped": 0, "saved_s": 0.0, "dropped_s": 0.0})

    def chunk(self, gate_passed: bool, cnn_class: str | None = None):
        self._chunks_total += 1
        if gate_passed:
            self._gate_pass += 1
        if cnn_class is not None:
            self._cnn_chunks[cnn_class] = self._cnn_chunks.get(cnn_class, 0) + 1

    def episode(self, cls: str, saved: bool, duration_s: float):
        c = self._c(cls)
        c["episodes"] += 1
        c["saved" if saved else "dropped"] += 1
        c["saved_s" if saved else "dropped_s"] += duration_s

    def maybe_flush(self, now: datetime.datetime):
        if (now.hour != self._start.hour or now.date() != self._start.date()
                or (now - self._start).total_seconds() >= self.interval_s):
            self.flush(now)

    def flush(self, now: datetime.datetime):
        if self._chunks_total == 0 and not self._cls:
            self._start = now
            return
        # A flush at an hour boundary is stamped with the boundary itself so
        # no row straddles two hours (a long quiet gap is just one row).
        end = now
        if now.hour != self._start.hour or now.date() != self._start.date():
            end = now.replace(minute=0, second=0, microsecond=0)
        base = {"interval_start": self._start.isoformat(timespec="seconds"),
                "interval_end": end.isoformat(timespec="seconds"),
                "species": self.species}
        for cls in sorted(set(self._cls) | set(self._cnn_chunks)):
            c = self._cls.get(cls) or self._c(cls)
            self._w.writerow({**base, "class": cls,
                              "episodes": c["episodes"], "saved": c["saved"],
                              "dropped": c["dropped"],
                              "saved_s": round(c["saved_s"], 1),
                              "dropped_s": round(c["dropped_s"], 1),
                              "cnn_chunks": self._cnn_chunks.get(cls, 0)})
        tot = {k: sum(c[k] for c in self._cls.values())
               for k in ("episodes", "saved", "dropped", "saved_s", "dropped_s")}
        self._w.writerow({**base, "class": "all",
                          "episodes": tot["episodes"], "saved": tot["saved"],
                          "dropped": tot["dropped"],
                          "saved_s": round(tot["saved_s"], 1),
                          "dropped_s": round(tot["dropped_s"], 1),
                          "cnn_chunks": sum(self._cnn_chunks.values()),
                          "chunks_total": self._chunks_total,
                          "gate_pass_chunks": self._gate_pass})
        self._f.flush()
        self._reset(now)

    def close(self, now: datetime.datetime | None = None):
        try:
            self.flush(now or datetime.datetime.now())
        finally:
            self._f.close()
