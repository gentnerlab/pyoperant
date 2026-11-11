import csv
import datetime as dt
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if "pyaudio" not in sys.modules:
    try:
        __import__("pyaudio")
    except ImportError:
        sys.modules["pyaudio"] = MagicMock()

import numpy as np  # noqa: E402

from pyoperant.song_recording.retention import DetectionCounts, RetentionLimiter  # noqa: E402
from pyoperant.song_recording import monitor as mon  # noqa: E402


def T(h, m=0, s=0, d=1):
    return dt.datetime(2026, 1, d, h, m, s)


class LimiterTests(unittest.TestCase):
    def test_unconfigured_is_unlimited(self):
        lim = RetentionLimiter(None)
        self.assertTrue(all(lim.admit("call", T(1)) for _ in range(500)))

    def test_hourly_cap_resets_each_hour(self):
        lim = RetentionLimiter({"call": {"max_per_hour": 2}})
        self.assertEqual([lim.admit("call", T(1, i)) for i in range(4)], [True, True, False, False])
        self.assertTrue(lim.admit("call", T(2)))
        self.assertTrue(lim.admit("song", T(1)))   # other classes unaffected

    def test_daily_cap_and_zero(self):
        lim = RetentionLimiter({"call": {"max_per_day": 3}, "song": {"max_per_hour": 0}})
        got = [lim.admit("call", T(h)) for h in range(5)]
        self.assertEqual(got, [True, True, True, False, False])
        self.assertTrue(lim.admit("call", T(1, d=2)))
        self.assertFalse(lim.admit("song", T(1)))

    def test_bad_config(self):
        for bad in ({"call": {"max_per_hour": -1}}, {"call": {"per_hour": 1}},
                    {"call": 5}, {"call": {"max_per_hour": 1.5}}):
            with self.assertRaises(ValueError):
                RetentionLimiter(bad)


class CountsTests(unittest.TestCase):
    def rows(self, p):
        with open(p) as f:
            return list(csv.DictReader(f))

    def test_flush_rows_and_hour_boundary(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "counts.csv")
        c = DetectionCounts(p, species="zebra_finch", interval_s=600, now=T(10, 55))
        for _ in range(10):
            c.chunk(True, "call")
        c.chunk(False, None)
        c.episode("call", True, 1.5)
        c.episode("call", False, 2.0)
        c.maybe_flush(T(10, 58))          # inside interval and hour: no row
        self.assertEqual(self.rows(p), [])
        c.maybe_flush(T(11, 0, 1))        # hour rolled over
        r = {x["class"]: x for x in self.rows(p)}
        self.assertEqual(r["call"]["episodes"], "2")
        self.assertEqual(r["call"]["saved"], "1")
        self.assertEqual(r["call"]["dropped"], "1")
        self.assertEqual(r["call"]["dropped_s"], "2.0")
        self.assertEqual(r["call"]["cnn_chunks"], "10")
        self.assertEqual(r["all"]["chunks_total"], "11")
        self.assertEqual(r["all"]["gate_pass_chunks"], "10")
        self.assertEqual(r["all"]["interval_end"], "2026-01-01T11:00:00")  # stamped at boundary
        self.assertEqual(r["all"]["species"], "zebra_finch")

    def test_close_flushes_partial_and_empty_writes_nothing(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "counts.csv")
        c = DetectionCounts(p, now=T(1))
        c.close(T(1, 1))
        self.assertEqual(self.rows(p), [])
        c = DetectionCounts(p, now=T(1))
        c.chunk(True, "song")
        c.close(T(1, 2))
        self.assertEqual(len(self.rows(p)), 2)   # song + all (header not duplicated)


class MonitorIntegration(unittest.TestCase):
    def run_monitor(self, retention, n_episodes=4):
        d = tempfile.mkdtemp()
        cfg = {"mode": "gate_cnn", "output_dir": os.path.join(d, "rec"),
               "log_csv": os.path.join(d, "detections.csv"), "retention": retention}
        seq = ([(True, 0.8)] * 20 + [(False, 0.05)] * 140) * n_episodes
        call = {"noise": 0.02, "whistle": 0.01, "call": 0.95, "song": 0.02}
        cnn = [(call, 0.97)] * (20 * n_episodes)
        m = mon.SongMonitor(cfg, audio_input=None, gate=mon._FakeGate(seq),
                            extractor=object(), classifier=mon._FakeClassifier(cnn))
        chunk = np.zeros(m._chunk_len, dtype=np.float32)
        for _ in seq:
            m._process(chunk)
        m._close_logs()
        return d

    def test_cap_limits_files_but_counts_everything(self):
        d = self.run_monitor({"call": {"max_per_day": 2}})
        # (file names are second-resolution, so count saves via the log)
        with open(os.path.join(d, "detections.csv")) as f:
            self.assertEqual(len(list(csv.DictReader(f))), 2)
        with open(os.path.join(d, "counts.csv")) as f:
            r = {x["class"]: x for x in csv.DictReader(f)}
        self.assertEqual(r["call"]["episodes"], "4")
        self.assertEqual(r["call"]["saved"], "2")
        self.assertEqual(r["call"]["dropped"], "2")
        self.assertEqual(r["call"]["cnn_chunks"], "80")
        self.assertEqual(r["all"]["gate_pass_chunks"], "80")
        self.assertEqual(r["all"]["chunks_total"], str(160 * 4))

    def test_default_keeps_everything(self):
        d = self.run_monitor({})
        with open(os.path.join(d, "detections.csv")) as f:
            self.assertEqual(len(list(csv.DictReader(f))), 4)


if __name__ == "__main__":
    unittest.main()
