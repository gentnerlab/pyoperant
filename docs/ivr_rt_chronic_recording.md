# Configured Open Ephys recording for ivr_rt_pilot

Prepared 2026-09-25. Candidate software, offline tested; **not installed or validated on magpi101**.

Review: [py-behaviors draft PR #12](https://github.com/gentnerlab/py-behaviors/pull/12),
commit `5d061f1718940489afe62aa9f204d86ea814cc97`. All 18 offline tests passed.

## Behavior and recording scope

`ivr_rt_chronic` extends the full `ivr_rt_pilot` on py-behaviors master
(`3d7e5f2630cb07752942e8673087fea68820099d`). It uses the existing first-valid
response, sampling, corrections, reinforcement and punishment settings. This
first integration records ordinary trials; the separate 80/10/10 continuation
candidate is not activated by this launch name.

Code is in `glab_behaviors/ivr_rt_chronic.py` and `open_ephys_recorder.py`, with the
class registered in `glab_behaviors/__init__.py`. The helper uses Python's standard
library; there is no new runtime package dependency or pyoperant core modification.
Project/deployment notes remain in song_in_noise and open_ephys_nt.

## Subject JSON

Merge the `open_ephys` object from
[`configs/open_ephys.fragment.example.json`](https://github.com/gentnerlab/py-behaviors/blob/codex/ivr-rt-chronic-recording/configs/open_ephys.fragment.example.json)
into a **copy of the reviewed test-subject config**. This is a fragment, not a
replacement for stimulus paths, reinforcement, schedules or other animal settings.

| Setting | Meaning |
| --- | --- |
| `enabled` | Required boolean. `true` requires recording before trials; `false` explicitly runs without Open Ephys. Missing/unknown settings fail validation. |
| `host`, `port` | Open Ephys GUI HTTP server; current chronic link is asfour `192.168.1.100:37497`. |
| `recording_parent_directory` | Path **on the Open Ephys PC**, not MagPi. `null` retains current Record Node directories. A supplied path is applied to each Record Node and read back before recording. |
| `recording_name_prefix` | Prefix for a unique prefix/subject/session-UUID directory name. Existing GUI prepend/base/append naming is replaced for this run. |
| `journal_subdirectory` | Subdirectory of the subject's experiment path; default `open_ephys`. |
| `request_timeout_s`, `drain_timeout_s` | HTTP socket timeout and metadata barrier/worker-shutdown timeouts. Defaults 2 and 10 seconds. |
| `status_interval_s` | Background check that the GUI remains in RECORD, default 1 second. |
| `final_message_wait_s` | Delay after final metadata delivery before stopping recording, default 1 second; bench-verify final messages are saved. |
| `queue_size` | Bounded metadata queue, default 256. Overflow inhibits further trials. |
| `channel_map` | Provenance only; does not configure OneBox channels, ranges, thresholds or digital modes. |

The example records the **planned rewiring**: ADC0/1/2/3 left/center/right/hopper,
ADC10 left audio, ADC11 right audio. Verify those mappings after rewiring; the
historical validated left-audio channel was ADC11. Keep audio inputs analog.
TXD is not needed for this HTTP metadata path and remains unwired.

## Lifecycle and failure behavior

1. A scheduled behavior session checks the GUI is IDLE or ACQUIRE and has a Record
   Node. It refuses an already-running recording without changing its mode.
2. It configures a unique recording name, enters RECORD, reads the mode back, and
   delivers `session_start` before accepting trials. One recording covers that
   session, including its normal/correction trials and intertrial intervals.
3. Before lighting the center port for each trial, it delivers `trial_prepared`
   and verifies RECORD. This boundary can wait for HTTP. Once center is detected,
   only the worker's latched health flag is checked before playback. No HTTP,
   metadata construction or journal writes occur in the onset/response/stop/reward
   path. This does not make Python a hard-real-time controller.
4. After consequences, saving the existing CSV queues `trial_result`. Software
   onset, RT, stop/food/punishment command times are reported retrospectively.
   Events are compact JSON, at most 512 UTF-8 bytes; oversized messages are
   rejected rather than truncated. The worker writes full local metadata and
   delivery acknowledgments to JSONL. HTTP acknowledgments do not prove disk
   persistence by Open Ephys; check the actual recording in the bench test.
5. Session end, idle/free-food transition or the existing SIGINT/SIGTERM shutdown
   hook drains messages, then restores the GUI's previous IDLE/ACQUIRE mode.
   Recording and JSONL get new UUIDs at the next scheduled session. Idle, shaping
   and free-food operation are outside this recording scope.

Network, queue, journal or unexpected-mode failures latch. A trial already in
progress can finish; subsequent trials pause until deliberate restart. Failures
detected while waiting for center prevent playback at the next health check.
Status is sampled, so a short undetected recording interruption is still possible.
The existing light/session/free-food eligibility is preserved while trials are
inhibited. No automatic unrecorded fallback, message retry, recording takeover or
reconnection is attempted. Check the subject log and GUI before restarting.
Power loss/SIGKILL cannot run cleanup; the GUI may still be recording. A shutdown
HTTP failure is logged for manual resolution. Keep a single recording controller;
concurrent manual/API recording control cannot be arbitrated by this API.

## Joining records and interpreting timestamps

- Behavioral CSV adds `oe_session_id`; its existing `trial_uid` identifies each
  presentation, including corrections. Ordinary CSV fields remain intact.
- `session_start` includes run ID, subject and SHA-256 of the runtime config;
  `<experiment_path>/open_ephys/<session_uuid>.jsonl` contains the full config,
  effective recorder settings, observed Record Node state, complete stimulus
  provenance and local send/ack/failure records. Archive it with CSV and ephys.
- Join Message Center `session` + `trial_uid` to CSV `oe_session_id` + `trial_uid`.
  A prepared trial without a result may have been cancelled before presentation.
- `onset_mono` is the MagPi monotonic play-command timestamp. `rt`, `stop_rt`,
  `food_rt` and `punish_rt` are seconds relative to that command; they are not
  Open Ephys sample timestamps. JSONL flushes are not a power-failure durability
  guarantee.
- Use physical OneBox peck/hopper and electrical audio for timing. These semantic
  messages intentionally arrive before or after trials. They are not immediate
  TTL events or a fixed-latency synchronization mechanism.

## Deployment and commissioning

The code is prepared on `codex/ivr-rt-chronic-recording`, targeting py-behaviors
master. Review/merge before pulling master on the rig. No live config or service
has been changed. Preserve the chronic acquisition network; its `.100` is asfour,
not the normal behavioral-room Git server. Verify the actual deployment remote.

For a reviewed dummy subject config named `config_chronic_test.json`:

```bash
python3 ~/pyoperant/scripts/behave -P 1 -S B3507 -c config_chronic_test.json ivr_rt_chronic
```

Use one controller. Start the GUI with the intended OneBox/Record Node signal
chain and storage directory, initially IDLE or ACQUIRE. First confirm recording
starts **before** a center peck. Exercise correct/incorrect, premature, omission,
correction and stop/restart cases; then inspect the actual binary recording,
Message Center JSON, CSV joins and JSONL acknowledgments. Verify ADC0–3 and both
audio channels, plus return to the prior GUI mode after Ctrl-C. Test a disconnected
HTTP link and confirm trials pause and the selected free-food schedule is still
eligible. Existing CSV/header and full stimulus/config checks still apply.

Offline tests use real pinned behavior/core source, simulated IO/time and a local
HTTP server. All exercised core modules match pyoperant open_ephys_nt
`d4fe081cd8787821beb2c42406b3f321ae0d1ef8` by Git blob SHA. Reproduce with:

```bash
PYOPERANT_CHECKOUT=/path/to/pyoperant python3 -m unittest discover -s tests -v
```

Offline coverage is not evidence of GUI-version compatibility, physical timing,
OneBox routing, neural stability or animal performance.

API reference: [Open Ephys remote control](https://open-ephys.github.io/gui-docs/User-Manual/Remote-control.html).
