"""
species.py -- which species a box is recording, and the species-specific
parts of the detection pipeline that follow from it.

`song_recording.species` in a bird's config.json selects the species
("starling" by default, so any box that doesn't set it behaves exactly as
before). It does two things:

  1. Layers a per-species preset of config defaults (PRESETS) under the
     bird's own song_recording config -- anything the bird's config.json
     sets explicitly still wins.
  2. Picks the gate factory (GATE_FACTORIES) that builds the
     (gate, extractor) pair for that species.

Gate factory contract
----------------------
A gate factory is `factory(flat_cfg: dict) -> (gate, extractor)`, where
flat_cfg is the flattened pipeline config built by
pyoperant.behavior.lights.Lights._build_pipeline (sample_rate, freq_low,
freq_high, chunk_duration, gate, noise_model, ...). The returned objects
must behave like gate.SongGate / features.FeatureExtractor as the monitor
uses them:

  - gate.evaluate(chunk, extractor) -> gate.GateResult (passed, score,
    features.rms, snr_score, noise_model_ok, sub_*)
  - gate.has_noise_model (bool) and a settable gate.noise_model (the
    per-chamber noise model calibration installs into it)

A different gate can be dropped in without editing this package by
naming it in config.json as `song_recording.gate_factory`, as
"package.module:function" -- it then replaces the species' default
factory.

zebra_finch is currently a STUB: no ZF-specific gate or preset values
exist yet, so it logs a warning and runs the generic gate. Fill in
PRESETS["zebra_finch"] and register a real factory in GATE_FACTORIES
once the ZF code is available.
"""

from __future__ import annotations

import importlib
import logging

log = logging.getLogger(__name__)

STARLING = "starling"
ZEBRA_FINCH = "zebra_finch"
SPECIES = (STARLING, ZEBRA_FINCH)
DEFAULT_SPECIES = STARLING

# Per-species song_recording config defaults, layered UNDER the bird's own
# song_recording config (see apply_preset). Same nested shape as that
# config, e.g. {"monitor": {"freq_low": ...}, "gate": {...}}.
#
# starling is {} on purpose: the existing built-in defaults ARE the
# starling settings, and an empty preset guarantees no behavior change for
# existing boxes.
PRESETS: dict[str, dict] = {
    STARLING: {},
    ZEBRA_FINCH: {},  # TODO: ZF values (freq band, gate weights, ...) -- none known yet
}


class UnknownSpeciesError(ValueError):
    pass


def resolve_species(sr_cfg: dict) -> str:
    """The validated species named by a song_recording config dict."""
    species = sr_cfg.get("species", DEFAULT_SPECIES)
    if species not in SPECIES:
        raise UnknownSpeciesError(
            f"song_recording.species={species!r} is not one of {SPECIES}")
    return species


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def apply_preset(species: str, sr_cfg: dict) -> dict:
    """sr_cfg with the species preset layered underneath (sr_cfg wins)."""
    return _deep_merge(PRESETS[species], sr_cfg)


def _import_factory(spec: str):
    module_name, _, func_name = spec.partition(":")
    if not module_name or not func_name:
        raise ValueError(
            f"song_recording.gate_factory={spec!r} must look like "
            f"'package.module:function'")
    return getattr(importlib.import_module(module_name), func_name)


def _generic_gate_factory(flat_cfg: dict):
    from pyoperant.song_recording.gate import make_gate_from_config
    return make_gate_from_config(flat_cfg)


def _zebra_finch_gate_factory(flat_cfg: dict):
    log.warning(
        "species=zebra_finch: no zebra finch gate is implemented yet -- "
        "using the generic (starling-tuned) gate. Set "
        "song_recording.gate_factory to plug one in.")
    return _generic_gate_factory(flat_cfg)


GATE_FACTORIES = {
    STARLING: _generic_gate_factory,
    ZEBRA_FINCH: _zebra_finch_gate_factory,
}


def make_gate(species: str, flat_cfg: dict, gate_factory: str | None = None):
    """Build the (gate, extractor) pair for `species`, honoring an explicit
    `gate_factory` ("module:function") override if one is configured."""
    if gate_factory:
        log.info("species=%s: using configured gate_factory %s", species, gate_factory)
        return _import_factory(gate_factory)(flat_cfg)
    return GATE_FACTORIES[species](flat_cfg)
