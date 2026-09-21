"""
calibration.py — per-microphone UMIK-1 SPL calibration.

Every miniDSP UMIK-1 ships with a unique, factory-measured frequency-
response correction curve (and an overall "Sens Factor" offset) keyed to
that specific physical unit's serial number. This module parses that file
and applies it to compute a calibrated, per-unit-consistent level estimate
for each recording, logged alongside detections for real-world loudness
monitoring across the fleet.

Honest scope, worth being precise about: this corrects for each mic's own
known deviation from a flat frequency response, and aligns different
physical units to the same reference point via their Sens Factor -- so the
resulting `calibrated_level_db` is comparable ACROSS boxes with different
physical UMIK-1 units, which the raw digital (dBFS) level is not. It is
NOT independently traceable to absolute dB-SPL/Pa -- that would need a
physical SPL-reference calibration of the whole capture chain (a
94dB-SPL reference tone at the ADC, or similar), which this fleet doesn't
have. Don't report `calibrated_level_db` to anyone as certified SPL.

Deliberately NOT used for detection/gating -- see project_vocal_recorder
memory: the gate scores relative spectral shape (flatness/harmonic_ratio/
band energy), not absolute level, and applying per-unit calibration there
was a deliberate, still-standing non-goal.

Off-axis (90-degree) calibration files are used fleet-wide, not the
on-axis variant miniDSP also ships -- decided 2026-09-21: a chamber mic's
angle of incidence to a bird isn't fixed the way it would be for a
boom-mounted measurement mic pointed at a fixed source; the bird moves and
sings in whatever direction it's facing, so the diffuse/off-axis response
is the more realistic match than assuming on-axis incidence.

Calibration files and the box->serial mapping are lab-specific, per-device
data and never committed to this (public) repo -- see
feedback_pyoperant_public_repo_boundary memory. Each box's own
panel_config.json (hardware calibration belonging to the physical box, not
whichever bird is assigned to it -- see utils.load_panel_config()) carries
a `mic_serial` key; the actual `<serial>_90deg.txt` file is synced
separately to a fixed local path on that Pi (see scripts/sync_mic_cal.py)
from the fleet's calibration-file registry on magpi.ucsd.edu
(~/minidsp_mic_cal/), the same "small file lives on the server, gets
pulled onto boxes as needed" pattern as panel_subject_behavior.

pyoperant integration
---------------------
    from pyoperant.song_recording.calibration import MicCalibration

    cal = MicCalibration.load("/home/bird/mic_cal.txt")   # None if missing
    level_db = cal.calibrated_level_db(magnitude, freqs, freq_low=1000, freq_high=10000)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

DEFAULT_PATH = "/home/bird/mic_cal.txt"

_SENS_FACTOR_RE = re.compile(r"Sens Factor\s*=\s*([+-]?[0-9.]+)\s*dB", re.IGNORECASE)
_SERNO_RE = re.compile(r"SERNO:\s*([0-9]+)", re.IGNORECASE)


@dataclass
class MicCalibration:
    """One UMIK-1 unit's parsed calibration curve.

    serial         : this unit's serial number, as a string (matches the
                      filename and the SERNO field in the file's own
                      header -- both checked to agree in load()).
    sens_factor_db : overall sensitivity offset vs. miniDSP's reference
                      unit, from the file's header line.
    freqs_hz       : ascending frequency points (Hz) the correction curve
                      was measured at.
    correction_db  : correction (dB) at each corresponding freqs_hz point.
    """
    serial:         str
    sens_factor_db: float
    freqs_hz:       np.ndarray
    correction_db:  np.ndarray

    @classmethod
    def load(cls, path=DEFAULT_PATH) -> "MicCalibration | None":
        """Parse a miniDSP UMIK-1 calibration file.

        Returns None (logged as info, not an error) if the file doesn't
        exist -- a box with no mic_serial configured yet, or one whose
        calibration file hasn't been synced -- so callers degrade
        gracefully to uncalibrated logging, the same pattern as a missing
        noise_model.npz falling back to the fixed-RMS gate.

        Raises nothing else: a corrupt/unparseable file is logged as a
        warning and treated the same as missing (returns None) -- a bad
        calibration file should never crash a recording session, same
        reasoning as utils.load_panel_config().
        """
        p = Path(path)
        if not p.is_file():
            log.info("No mic calibration file at %s -- SPL logging will be uncalibrated.", path)
            return None

        try:
            lines = p.read_text().splitlines()
            header_lines, data_lines = [], []
            for line in lines:
                s = line.strip()
                if not s:
                    continue
                if s.startswith('"'):
                    header_lines.append(s)
                else:
                    data_lines.append(s)

            header = " ".join(header_lines)
            sens_match = _SENS_FACTOR_RE.search(header)
            serno_match = _SERNO_RE.search(header)
            if sens_match is None or serno_match is None:
                raise ValueError(
                    "could not find Sens Factor / SERNO in header: %r" % header
                )
            sens_factor_db = float(sens_match.group(1))
            serial = serno_match.group(1)

            freqs, corrections = [], []
            for line in data_lines:
                parts = line.split()
                if len(parts) != 2:
                    continue
                freqs.append(float(parts[0]))
                corrections.append(float(parts[1]))

            if len(freqs) < 2:
                raise ValueError("fewer than 2 data points parsed")

            return cls(
                serial=serial,
                sens_factor_db=sens_factor_db,
                freqs_hz=np.asarray(freqs, dtype=np.float64),
                correction_db=np.asarray(corrections, dtype=np.float64),
            )
        except Exception as exc:
            log.warning(
                "Could not parse mic calibration file %s (%s) -- SPL "
                "logging will be uncalibrated.", path, exc,
            )
            return None

    def correction_at(self, freqs_hz) -> np.ndarray:
        """Interpolated correction (dB) at arbitrary frequencies, e.g. an
        FFT's own bin frequencies. Linear interpolation against the
        file's own (already log-spaced) points; clamped at the ends
        (numpy's default np.interp behavior) rather than extrapolated,
        since the correction curve is only measured 10Hz-20kHz."""
        return np.interp(freqs_hz, self.freqs_hz, self.correction_db)

    def calibrated_level_db(
        self,
        magnitude:  np.ndarray,
        freqs_hz:   np.ndarray,
        freq_low:   float | None = None,
        freq_high:  float | None = None,
    ) -> float:
        """Calibrated broadband level (dB) for one chunk's rfft magnitude
        spectrum, corrected for this specific unit's frequency response
        and overall sensitivity offset -- see module docstring for what
        this is (and is not) traceable to.

        magnitude/freqs_hz: same rfft magnitude + np.fft.rfftfreq(...)
        arrays the gate's own feature extraction already computes for
        this chunk -- pass those directly rather than recomputing the FFT.
        freq_low/freq_high: restrict to the vocalization band (matches
        gate.py's own band_energy_ratio window) if given; the whole
        spectrum otherwise.
        """
        corr_db     = self.correction_at(freqs_hz)
        corrected   = magnitude * (10.0 ** (corr_db / 20.0))

        if freq_low is not None and freq_high is not None:
            band_mask = (freqs_hz >= freq_low) & (freqs_hz <= freq_high)
            corrected = corrected[band_mask]

        # RMS-equivalent broadband level from the (corrected) magnitude
        # spectrum. Exact normalization constants don't matter for a
        # value that's explicitly relative/self-consistent, not claimed
        # as absolute SPL -- see module docstring.
        power = np.sum(corrected ** 2)
        rms   = np.sqrt(power) / max(len(magnitude), 1)
        level_dbfs = 20.0 * np.log10(max(rms, 1e-12))
        return level_dbfs + self.sens_factor_db


# ---------------------------------------------------------------------------
# Self-test (run directly: python -m pyoperant.song_recording.calibration)
# Synthetic signals + a small embedded fixture matching the real miniDSP
# format -- no real hardware or real calibration file required.
# ---------------------------------------------------------------------------

_FIXTURE_CAL_TEXT = """\
"Sens Factor =-1.500dB, SERNO: 1234567"
"Auto-generated 90-degree calibration file"
500.0\t0.0
1000.0\t0.0
2000.0\t6.0
4000.0\t-3.0
8000.0\t0.0
16000.0\t0.0
"""


def self_test():
    import tempfile

    print("\n=== Calibration self-test ===")

    with tempfile.TemporaryDirectory() as tmp_dir:
        good_path = f"{tmp_dir}/mic_cal.txt"
        with open(good_path, "w") as f:
            f.write(_FIXTURE_CAL_TEXT)

        # --- A: parses a well-formed file correctly ---
        cal = MicCalibration.load(good_path)
        a_ok = (cal is not None and cal.serial == "1234567"
                and abs(cal.sens_factor_db - (-1.5)) < 1e-9
                and len(cal.freqs_hz) == 6)
        print(f"  [{'OK' if a_ok else 'FAIL'}] A: well-formed file parses correctly "
              f"(serial={cal.serial if cal else None} "
              f"sens={cal.sens_factor_db if cal else None} "
              f"n_points={len(cal.freqs_hz) if cal else None})")

        # --- B: missing file returns None, doesn't raise ---
        cal_missing = MicCalibration.load(f"{tmp_dir}/does_not_exist.txt")
        b_ok = cal_missing is None
        print(f"  [{'OK' if b_ok else 'FAIL'}] B: missing file returns None, not raise")

        # --- C: corrupt file returns None, doesn't raise ---
        corrupt_path = f"{tmp_dir}/corrupt.txt"
        with open(corrupt_path, "w") as f:
            f.write("not a calibration file at all\njust garbage\n")
        cal_corrupt = MicCalibration.load(corrupt_path)
        c_ok = cal_corrupt is None
        print(f"  [{'OK' if c_ok else 'FAIL'}] C: corrupt file returns None, not raise")

        # --- D: correction_at interpolates correctly at a known point,
        # and is flat (0dB) where the fixture says it should be ---
        interp_2500 = cal.correction_at(np.array([2500.0]))[0]
        # between (2000, 6.0) and (4000, -3.0) -> linear interp
        expected = 6.0 + (2500.0 - 2000.0) / (4000.0 - 2000.0) * (-3.0 - 6.0)
        d_ok = abs(interp_2500 - expected) < 1e-6
        print(f"  [{'OK' if d_ok else 'FAIL'}] D: correction_at() interpolates linearly "
              f"(at 2500Hz: got={interp_2500:.3f} expected={expected:.3f})")

        # --- E: calibrated_level_db shifts a flat spectrum by exactly the
        # correction + sens_factor at a frequency with a known, nonzero
        # correction (2000Hz -> +6dB in the fixture) vs. one with zero
        # correction (1000Hz) ---
        sr = 48000
        n_fft = 4800
        freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)
        # a flat-magnitude synthetic spectrum (same magnitude at every bin)
        # isolates the correction curve's effect cleanly
        flat_mag = np.ones_like(freqs)

        level_at_1000_band = cal.calibrated_level_db(
            flat_mag, freqs, freq_low=990, freq_high=1010)   # ~0dB correction here
        level_at_2000_band = cal.calibrated_level_db(
            flat_mag, freqs, freq_low=1990, freq_high=2010)  # +6dB correction here
        # +6dB correction on a narrow band centered there should raise the
        # computed level by roughly 6dB vs. the ~0dB-correction band,
        # holding everything else (magnitude, band width) equal
        delta = level_at_2000_band - level_at_1000_band
        e_ok = abs(delta - 6.0) < 0.5
        print(f"  [{'OK' if e_ok else 'FAIL'}] E: a +6dB correction band reads "
              f"~6dB higher than a 0dB-correction band on the same flat input "
              f"(delta={delta:.2f}dB)")

        # --- F: real-file smoke test, if a real fleet calibration file
        # happens to be available locally (optional -- skipped cleanly
        # otherwise, since real cal files never live in this repo) ---
        print("  (F skipped -- no real fleet calibration file bundled in this repo, by design)")


if __name__ == "__main__":
    self_test()
