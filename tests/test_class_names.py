import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

for _mod in ("pyaudio",):
    if _mod not in sys.modules:
        try:
            __import__(_mod)
        except ImportError:
            sys.modules[_mod] = MagicMock()

import numpy as np  # noqa: E402

from pyoperant.song_recording import classifier as clf_mod  # noqa: E402
from pyoperant.song_recording import melspec  # noqa: E402
from pyoperant.song_recording.monitor import DetectionLog  # noqa: E402


def _write_npz(path, n_out, class_names=None):
    rng = np.random.default_rng(0)
    w = {}
    for i, (co, ci) in enumerate([(16, 1), (32, 16), (64, 32)], start=1):
        w["conv%d_weight" % i] = rng.normal(size=(co, ci, 3, 3)).astype(np.float32) * 0.1
        w["conv%d_bias" % i] = np.zeros(co, np.float32)
        w["bn%d_weight" % i] = np.ones(co, np.float32)
        w["bn%d_bias" % i] = np.zeros(co, np.float32)
        w["bn%d_running_mean" % i] = np.zeros(co, np.float32)
        w["bn%d_running_var" % i] = np.ones(co, np.float32)
    w["fc1_weight"] = rng.normal(size=(32, 64)).astype(np.float32) * 0.1
    w["fc1_bias"] = np.zeros(32, np.float32)
    w["fc2_weight"] = rng.normal(size=(n_out, 32)).astype(np.float32) * 0.1
    w["fc2_bias"] = np.zeros(n_out, np.float32)
    if class_names is not None:
        w["class_names"] = np.array(class_names)
    np.savez(path, **w)


class TestClassNames(unittest.TestCase):
    def _classifier(self, n_out, class_names=None, **kw):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "m.npz")
        _write_npz(path, n_out, class_names)
        return clf_mod.SongClassifier(path, capture_sample_rate=melspec.TARGET_SR, **kw)

    def test_starling_npz_without_names_uses_defaults_with_call(self):
        clf = self._classifier(4)
        self.assertEqual(clf.class_names, ["noise", "whistle", "call", "song"])
        self.assertEqual(clf.keep_classes, ["whistle", "call", "song"])
        res = clf.update(np.zeros(int(melspec.TARGET_SR * 0.1), np.float32))
        self.assertEqual(set(res.probs), {"noise", "whistle", "call", "song"})

    def test_three_class_zf_model_reads_names_from_weights(self):
        clf = self._classifier(3, ["noise", "call", "song"])
        self.assertEqual(clf.class_names, ["noise", "call", "song"])
        self.assertEqual(clf.keep_classes, ["call", "song"])
        res = clf.update(np.zeros(int(melspec.TARGET_SR * 0.1), np.float32))
        self.assertEqual(set(res.probs), {"noise", "call", "song"})
        self.assertIn(res.predicted_class, {"noise", "call", "song"})
        self.assertAlmostEqual(res.confidence, 1 - res.probs["noise"], places=6)

    def test_contact_is_an_alias_for_call(self):
        clf = self._classifier(4, keep_classes=["whistle", "contact", "song"])
        self.assertEqual(clf.keep_classes, ["whistle", "call", "song"])
        zf = self._classifier(3, ["noise", "call", "song"], keep_classes=["contact", "song"])
        self.assertEqual(zf.keep_classes, ["call", "song"])

    def test_class_the_model_lacks_is_rejected(self):
        with self.assertRaises(ValueError):
            self._classifier(3, ["noise", "call", "song"], keep_classes=["whistle"])

    def test_names_count_must_match_outputs(self):
        with self.assertRaises(ValueError):
            self._classifier(3, ["noise", "call", "song", "whistle"])

    def test_csv_column_renamed(self):
        self.assertIn("cnn_prob_call", DetectionLog.FIELDS)
        self.assertNotIn("cnn_prob_contact", DetectionLog.FIELDS)


if __name__ == "__main__":
    unittest.main()
