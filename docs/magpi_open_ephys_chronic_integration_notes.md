# MagPi–Open Ephys Chronic Behavior Integration Notes

**Status:** Living engineering note  
**Last updated:** 2026-09-30  
**Scope:** Rev D MagPi chronic behaving setup with Open Ephys / OneBox  
**Primary background reference:** `pyoperant_manual.md` (especially the standard MagPi hardware and deployment sections)  
**Purpose:** Record the actual wiring, tested timing behavior, software conventions, deployment state, and unresolved issues for the chronic Open Ephys integration. This file should remain updateable during development and can later be folded into the main RPiOperant manual.

> **Source-of-truth convention**
>
> `pyoperant_manual.md` remains the source of truth for standard MagPi hardware, GPIO assignments, panel components, and normal PyOperant operation. This note documents the additional Open Ephys integration and measurements made on the chronic recording rig. A value measured on one chronic rig should not be generalized to every MagPi unless independently verified.

---

## 1. Integration design

The chronic recording setup uses the Rev D MagPi's existing front-panel signals to send physical behavioral events directly to a OneBox while PyOperant continues to control the experiment.

The central design rule is:

**Use physical MagPi/OneBox signals for timing; use Open Ephys Message Center for semantic metadata.**

That means:

- peck-port and hopper events are timed from physical IR-state signals recorded by the OneBox;
- playback onset/offset is timed from the electrical audio copy recorded by the OneBox;
- reaction time is reconstructed entirely from OneBox-recorded physical signals;
- Message Center carries information that cannot be inferred from those physical lines, especially exact stimulus identity and trial identity;
- Message Center timestamps are not treated as authoritative event timing.

This separation prevents network, HTTP, Python scheduling, Open Ephys buffering, or Message Center timestamp behavior from contaminating neural alignment or behavioral RT estimates.

---

## 2. Current chronic deployment

As of 2026-09-18, there is one deployed chronic MagPi system.

### 2.1 Network identity

- Chronic MagPi hostname: `magpi101`
- Chronic MagPi Ethernet: `192.168.1.101/24` on `eth0`
- Open Ephys PC: `asfour`
- asfour chronic-rig Ethernet: `192.168.1.100/24`
- MagPi default route: via `192.168.1.100` on `eth0`

The local MagPi → asfour link is operational. During validation on 2026-09-18:

```bash
curl http://192.168.1.100:37497/api/status
```

returned:

```json
{"mode":"IDLE"}
```

The MagPi does **not currently have working internet access through asfour**. Direct traffic to `8.8.8.8` failed, `github.com` could not be resolved, and direct GitHub HTTPS access therefore failed. The missing piece is internet forwarding/NAT on asfour, not the local Open Ephys link.

This chronic network is physically separate from the normal behavioral-room network. On the normal behavioral network, `192.168.1.100` is the central MagPi server. On the chronic network, `192.168.1.100` is **asfour**. The duplicate address is acceptable because the networks are isolated.

**Do not blindly use the normal behavioral-room Git remote `bird@192.168.1.100:~/code/...` on the chronic rig.** On this network that address resolves to asfour, not the central MagPi server.

### 2.2 Chronic box and commutator

The current rig is referred to as **chronic box 1** and uses a **Doric AERJ_24_Harwin assisted commutator**.

### 2.3 Current Git state

Validated on 2026-09-18:

- `~/pyoperant` is a real Git repository, clean on `master`;
- its current `origin` is `bird@192.168.1.100:~/code/pyoperant`;
- `~/py-behaviors` is a real Git repository, clean on `master`, using a sparse checkout;
- its current `origin` is `bird@192.168.1.100:~/code/py-behaviors`;
- those origins match the normal behavioral-room topology but are not valid chronic-rig deployment remotes because `192.168.1.100` is asfour here;
- direct GitHub access from `magpi101` is not currently available.

The Open Ephys acquisition link has priority over reproducing the behavioral-room network topology. Git deployment should be finalized without renumbering or otherwise disturbing the validated `192.168.1.100` ↔ `192.168.1.101` acquisition network. An asfour-side Git relay/mirror is one candidate; controlled forwarding is another. This remains a setup TODO.

Development for the chronic integration is tracked on the `open_ephys_nt` branch of `gentnerlab/pyoperant`.

### 2.4 Preferred transfer workflow (September 25 follow-up; setup pending)

Nathan proposed cloning/pulling on asfour and transferring onward to MagPi. Use
**GitHub → asfour → magpi101** as the preferred code-deployment route, with
stimuli transferred separately. The earlier relay/mirror discussion was a
candidate rather than a completed setup; no working relay or new SSH account is
claimed yet.

- **Code:** keep pyoperant and py-behaviors as Git repositories on both machines.
  Asfour fetches reviewed upstream changes; MagPi fetches/pulls the asfour copies
  over SSH. Verify the actual asfour login and repository paths before setting
  remotes; `.100` is asfour on this network. Use `git pull --ff-only` on the
  intended deployment branch, preserving the master behavior workflow. This
  refuses divergent updates instead of making an unintended merge. Keep any
  development branch choice explicit and record both installed commit SHAs.
- **Transport fallback:** if asfour has no SSH server, create Git bundles on
  asfour, send them to MagPi using its existing SSH/SCP connection, and fetch/pull
  the bundles locally. This preserves committed Git history; it does not transfer
  uncommitted edits. Asfour's OS, SSH-server availability and paths still need
  inspection before producing machine-specific commands.
- **Stimuli:** copy WAV directories and their manifests separately to the agreed
  local stimulus root. Prefer resumable rsync when available at both ends; a
  direct reachable storage-to-MagPi transfer is also fine. Preserve relative
  paths, verify counts/checksums and manifest resolution, and avoid deleting or
  replacing the active stimulus set during behavior/recording.
- **Configuration/data:** keep live subject JSONs, logs, trial CSVs and sampling
  state under `~/opdat/<subject>`. Code updates do not replace these. Before an
  update, check working-tree status and the actual glab_behaviors import/symlink
  location; after it, confirm versions and perform a short dummy-subject check.
  Preserve the current acquisition network and perform code updates between runs.

References: [Git pull](https://git-scm.com/docs/git-pull),
[Git bundles](https://git-scm.com/docs/git-bundle),
[rsync manual](https://download.samba.org/pub/rsync/rsync.1).

---

## 3. Rev D hardware used by the chronic rig

### 3.1 Primary operant IR signals

The principal Rev D IR inputs are:

| Behavioral signal | Raspberry Pi physical pin | BCM GPIO | Direction |
|---|---:|---:|---|
| Hopper IR | 29 | GPIO5 | Input |
| Left IR | 31 | GPIO6 | Input |
| Center IR | 33 | GPIO13 | Input |
| Right IR | 37 | GPIO26 | Input |

The codebase uses BCM GPIO numbering.

### 3.2 Front-panel digital HDMI (J6)

Relevant J6 signals from the Rev D schematic:

| J6 pin | Signal |
|---:|---|
| 1 (`DATA2+`) | `LFT_IR_STATE` |
| 3 (`DATA2-`) | `CTR_IR_STATE` |
| 4 (`DATA1+`) | `RGT_IR_STATE` |
| 6 (`DATA1-`) | `HOPPER_IR_STATE` |
| 7 (`DATA0+`) | `TXD` |
| 9 (`DATA0-`) | `AUX_IR_1_STATE` |
| 10 (`CLOCK+`) | `AUX_IR_2_STATE` |
| 12 (`CLOCK-`) | `GPIO_16` |
| 2, 5, 8, 11, 17, 20–23 | GND / shield |
| 18 | VCC — do not connect to OneBox ADC/GND |

The digital HDMI is now connected through the Open Ephys HDMI-to-BNC breakout. On that breakout, the BNC center conductors expose the HDMI signal lines while the BNC shells are tied to DGND by the breakout board.

**Validated chronic digital wiring (2026-09-30):**

| Open Ephys breakout BNC | J6 signal | OneBox channel | Behavioral signal |
|---|---|---|---|
| `IO1` | J6 pin 1 / `LFT_IR_STATE` | `ADC0` | `left_ir` |
| `IO2` | J6 pin 3 / `CTR_IR_STATE` | `ADC1` | center peck port |
| `IO3` | J6 pin 4 / `RGT_IR_STATE` | `ADC2` | right peck port |
| `IO4` | J6 pin 6 / `HOPPER_IR_STATE` | `ADC3` | `hopper_ir` |

Equivalent signal path:

```text
MagPi J6 digital HDMI
    -> Open Ephys HDMI-to-BNC breakout
        IO1 -> OneBox ADC0 -> left_ir
        IO2 -> OneBox ADC1 -> center peck port
        IO3 -> OneBox ADC2 -> right peck port
        IO4 -> OneBox ADC3 -> hopper_ir
```

The four channels were functionally tested after wiring and produced the expected behavioral-state transitions. The remaining breakout channels corresponding to `TXD`, `AUX_IR_1_STATE`, `AUX_IR_2_STATE`, and `GPIO_16` are not used for the current chronic behavior integration.

Observed polarity in the OneBox recordings:

- idle / beam unbroken = LOW;
- beam break = HIGH;
- rising edge = beam break;
- falling edge = release.

### 3.3 Front-panel analog HDMI (J7)

Relevant J7 signals:

| J7 pin | Signal |
|---:|---|
| 1 (`DATA2+`) | `AUDIO_OUT_L` |
| 3 (`DATA2-`) | `AUDIO_OUT_R` |
| 4 (`DATA1+`) | `TXD` |
| 2, 5, 8, 11, 17, 20–23 | GND / shield |
| 18 | VCC |

Historically validated chronic wiring:

```text
J7 pin 1 -> OneBox ADC11 signal
J7 pin 5 -> OneBox ADC11 ground
```

ADC11 in those recordings is an **electrical copy of the MagPi audio output**, not a microphone recording. It provides electrical playback onset/offset and a copy of the commanded waveform.

---

### 3.4 Breakout/BNC wiring status

The digital J6 wiring is now complete and validated using the Open Ephys HDMI-to-BNC breakout and standard BNC cables to OneBox. The canonical digital map is `IO1–IO4 -> ADC0–ADC3 -> left/center/right/hopper` as listed in Section 3.2.

For analog audio, the September 25 plan remains to use the analog breakout for stereo monitoring: J7 pin 1 / `AUDIO_OUT_L` to OneBox IO10 (`ADC10`) and J7 pin 3 / `AUDIO_OUT_R` to IO11 (`ADC11`) via BNC. That planned stereo map should not be treated as verified until a recording confirms both channels. Historical recordings used left audio on ADC11.

After any analog rewiring, repeat a short audio recording check and record the final channel map in this note. The HiFiBerry Amp2 speaker terminals are a separate bridged output; neither speaker terminal is a BNC ground return.

---

## 4. OneBox / Open Ephys configuration

### 4.1 Current behavioral-state channel map

The digital behavior-state map below was re-validated with the HDMI-to-BNC breakout on 2026-09-30:

| OneBox channel | Breakout BNC | Physical signal | Use |
|---|---|---|---|
| `ADC0` | `IO1` | Left IR state | Left response timing |
| `ADC1` | `IO2` | Center IR state | Trial initiation / center-peck timing |
| `ADC2` | `IO3` | Right IR state | Right response timing |
| `ADC3` | `IO4` | Hopper IR state | Physical hopper-up / hopper-down timing |

Earlier development notes sometimes used `IO0`, `IO1`, etc. for OneBox input labels. Saved Open Ephys continuous data and `structure.oebin` label these acquisition channels as `ADC0` ... `ADC11`. The `IO1–IO4` labels in the table above refer specifically to the four BNCs on the HDMI breakout board, not the saved Open Ephys channel names.

Historical recordings used left electrical audio on `ADC11`. The September 25 planned stereo mapping changes audio to **left ADC10, right ADC11**. Record and verify the final wiring before applying that new audio map in analysis. Historical recordings retain their original map. `TXD` is separate from the HTTP metadata path and remains unwired for the current integration.

### 4.2 Input modes

In the OneBox ADC/DAC settings:

- `ADC0`–`ADC3`: Digital Input mode ON;
- historical `ADC11` audio: analog input; Digital Input mode OFF.

`ADC0`–`ADC3` carry binary behavioral states. Audio channels must remain analog because they carry waveforms.

After the planned stereo audio rewire, **both ADC10 and ADC11 must have Digital Input mode OFF**. The software config's channel map records provenance only and does not change these GUI settings.

### 4.3 Sample rate

The tested OneBox ADC continuous stream reported **30,300.5 Hz**, approximately 0.033 ms per sample.

---

## 5. Authoritative timing hierarchy

### 5.1 Event definitions

- Center initiation: `ADC1` rising edge
- Left response: `ADC0` rising edge
- Right response: `ADC2` rising edge
- Electrical playback onset: onset detected from the active analog audio channel in that recording
- Hopper physically available: `ADC3` high interval

For historical recordings with left audio on ADC11, the authoritative reaction time is:

```text
RT_hardware = t_response(ADC0 or ADC2) - t_audio_onset(ADC11)
```

Both terms therefore live on the OneBox continuous acquisition timebase. Future analysis should resolve the actual audio channel from each recording's documented channel map rather than hard-coding ADC11 once the stereo rewire is commissioned.

### 5.2 Electrical versus acoustic onset

The J7 audio signal is an electrical playback copy. It is not the actual sound pressure waveform at the bird. A future chamber microphone channel should provide acoustic ground truth when actual acoustic onset at the animal is required.

Recommended hierarchy:

| Event / quantity | Authoritative source | Do not substitute |
|---|---|---|
| Center initiation | ADC1 rising edge | Message Center center event |
| Electrical playback onset | active J7 analog waveform channel | `speaker.play()` timestamp or MC `stim_on` |
| Left response | ADC0 rising edge | PyOperant software RT |
| Right response | ADC2 rising edge | PyOperant software RT |
| Reaction time | ADC0/ADC2 − active audio channel onset | Message Center timestamp differences |
| Hopper physically available | ADC3 high interval | raw `panel.reward()` duration |
| Exact stimulus filename | Message Center / local log | waveform alone |
| Trial semantics / labels | Message Center / local log | ADC identity alone |

---

## 6. Hardware validation results

### 6.1 Three-trial behavior-like test

A three-trial simulation used:

1. center IR break to initiate;
2. playback of `bird_test.wav`;
3. first left/right response to stop playback;
4. 2 s reward on left responses;
5. repeat for three trials.

Observed choices were left, timeout, and right.

Hardware-derived RT:

| Trial | Response | ADC11 onset | Response event | Hardware RT | Software RT | Software − hardware |
|---:|---|---:|---|---:|---:|---:|
| 1 | Left | 3.077639 s | ADC0 @ 6.497154 s | 3.4195 s | 3.4355 s | ~16.0 ms |
| 2 | None | 13.614594 s | — | — | — | — |
| 3 | Right | 28.652729 s | ADC2 @ 30.216069 s | 1.5633 s | 1.5806 s | ~17.3 ms |

The software RT was about 16–17 ms later than the RT reconstructed entirely from OneBox physical signals.

### 6.2 Response-to-audio-stop latency

Physical ADC11 playback termination followed the response edge by approximately:

- left trial: ~1.2 ms;
- right trial: ~2.5 ms.

Thus early-response playback termination was effectively immediate on the timescale relevant to the experiment.

### 6.3 Hopper timing

For the rewarded left trial:

- ADC3 high: 6.721539 s
- ADC3 low: 8.867279 s
- physical hopper-high interval: **2.146 s**
- requested reward interval: 2.0 s
- full `panel.reward(2.0)` call: approximately 3.26 s because servo movement is included in the call duration.

ADC3 therefore gives the meaningful physical food-access interval.

### 6.4 Digital-breakout validation (2026-09-30)

The permanent HDMI-to-BNC digital breakout path was functionally tested after wiring. The observed BNC-to-OneBox mapping was:

```text
breakout IO1 -> ADC0 -> left_ir
breakout IO2 -> ADC1 -> center peck port
breakout IO3 -> ADC2 -> right peck port
breakout IO4 -> ADC3 -> hopper_ir
```

All four channels behaved as expected during physical port/hopper activation. This supersedes the temporary direct-wire implementation for the digital behavioral-state lines.

---

## 7. Message Center

### 7.1 Intended role

Message Center is for compact semantic metadata that cannot be recovered from physical channels. The most important field is exact stimulus identity.

Recommended compact forms:

```json
{"e":"trial","i":384}
```

```json
{"e":"stim","i":384,"s":"A_D012_T0345_snr-10.wav"}
```

```json
{"e":"resp","i":384,"r":"L"}
```

```json
{"e":"rew","i":384}
```

```json
{"e":"end","i":384}
```

Suggested keys:

- `e`: event type
- `i`: trial index
- `s`: stimulus filename
- `r`: response (`L`, `R`, `N`)

The local MagPi behavioral log should retain full human-readable detail.

### 7.2 512-character limit

Open Ephys displayed:

```text
Broadcast message length exceeds maximum; truncating message to 512 characters
```

A verbose `session_start` payload was confirmed to be truncated and became invalid JSON. Earlier test messages were already approaching the limit (`stimulus_selected` ~393 characters, `stim_on` ~478, `response` ~458–465).

**Rule:** keep Message Center payloads deliberately compact.

### 7.3 Message Center is not the timing source

A dedicated 100-event center-IR benchmark produced 100/100 matched physical and Message Center events, but the saved Message Center timestamp was systematically earlier than the ADC1 timestamp:

| Statistic | MC timestamp − ADC1 rising edge |
|---|---:|
| n | 100 |
| Minimum | −51.682 ms |
| Median | **−40.445 ms** |
| Mean | −42.437 ms |
| SD | 4.716 ms |
| p95 | −37.905 ms |
| p99 | −34.844 ms |
| Maximum | −30.858 ms |

This is not a real negative network latency. It demonstrates a systematic offset between saved Message Center and OneBox continuous streams.

Do **not** correct this by blindly adding ~40.445 ms. The offset may depend on Open Ephys buffering or processor/recording configuration. Use physical channels for timing and Message Center for trial association/metadata.

### 7.4 HTTP latency benchmark

MagPi `time.perf_counter_ns()` measurements:

**Detection → HTTP send start**

- minimum: 0.017 ms
- median: **0.020 ms**
- mean: 0.021 ms
- SD: 0.002 ms
- p95: 0.025 ms
- p99: 0.026 ms
- maximum: 0.028 ms

**HTTP round-trip time**

- minimum: 3.777 ms
- median: **4.093 ms**
- mean: 4.348 ms
- SD: 1.869 ms
- p95: 4.603 ms
- p99: 9.342 ms
- maximum: 21.936 ms
- 96/100 requests were ≤5 ms
- all 100 requests succeeded while Open Ephys was in `RECORD`

The benchmark supports Message Center as a metadata path, not a precise timing path.

---

## 8. ADC11 / J7 analog-audio artifact investigation

**Resolved as reported by Nathan on 2026-09-25:** the oscilloscope investigation is complete and both MagPi audio potentiometers have been adjusted/fixed. The onset/offset issue is no longer a blocker. Final scope captures, residual transient amplitudes, and potentiometer positions were not supplied with this update; the earlier working hypothesis below is retained as history rather than a proven circuit-level explanation.

### 8.1 Historical observation (before resolution)

J7 → ADC11 produces a clear sustained copy of stimulus playback, but testing also revealed large onset and offset transients. The transients can serve as obvious playback boundaries, but their electrical cause has not yet been established.

Small onset-associated deflections have also been observed on ADC8, ADC9, and ADC10. These channels are not used for reconstruction and may reflect pickup/crosstalk; that remains unverified.

### 8.2 Historical hardware hypothesis

The Rev D schematic shows trim pots `R43` and `R44` in the analog-audio interface. The hardware designer's working hypothesis is that the HiFiBerry differential legs (`L+`/`L-` or `R+`/`R-`) may not switch with perfectly matched transients, and imperfect trim-pot centering could leave a transient in the single-ended `AUDIO_OUT_L` / `AUDIO_OUT_R` signal.

This is a **hypothesis**, not yet a validated cause.

### 8.3 Investigation procedure (completed; retained for reference)

For the left channel, inspect around playback start and stop:

1. `L+`;
2. `L-`;
3. scope math `L+ - L-`;
4. resulting `AUDIO_OUT_L` / J7 signal.

With an earth-referenced oscilloscope, both probe ground clips should go to board ground. Do **not** attach a scope ground clip to `L-`; it is a differential signal leg, not ground.

If the transient depends on common-mode cancellation, adjust `R43` empirically while monitoring the output and preserving normal waveform amplitude/noise/clipping. Do not treat an adjustment as canonical until measured and documented.

### 8.4 Relation to the old `open_ephys_ts` branch

The older `open_ephys_ts` implementation contains a `play_open_ephys()` path that toggles a GPIO around playback with configurable WAV padding. Current interpretation is that this GPIO was intended as a stimulus start/stop timing marker. It should **not** be treated as evidence that the GPIO/padding mechanism caused or solved the J7 analog transient.

### 8.5 Microphone channel

A separate chamber microphone should be routed to another OneBox analog input.

The two audio-related channels then have distinct roles:

- **J7 electrical copy:** what the MagPi commanded electrically and when playback started/stopped in the electronics path;
- **microphone:** what was actually present acoustically in the chamber, including playback verification and bird vocalizations.

---

## 9. Software and validation utilities

Current development utilities include behavior-like playback/IR tests, Message Center latency benchmarking, and post-hoc event recovery.

Important conventions:

- instantiate the Rev D panel through `pyoperant.local_pi_revd.PANELS`;
- use the public speaker API (`queue`, `play`, `stop`);
- for early response termination, use `panel.speaker.stop()` rather than reaching into the underlying PyAudio stream;
- avoid low-level PyAudio stream reset/cleanup in the behavioral control path unless a separately validated failure mode requires it.

`recover_open_ephys_events.py` still needs to be made canonical for the chronic rig. Its default digital map should resolve:

```text
left   = ADC0
center = ADC1
right  = ADC2
hopper = ADC3
```

Its audio onset detector should use the actual audio channel documented for each recording rather than assuming a fixed channel across historical and post-rewire sessions.

---

## 10. Behavior-integration constraints

The target behavior for integration is currently:

```text
song_recognition_early_resp_subset_first_valid
```

The goal is to extend the existing working behavior rather than create an unrelated replacement behavior.

Synchronous HTTP calls should not be allowed to perturb latency-critical behavior. Particularly avoid blocking network calls:

- between center initiation and `speaker.play()`;
- between stimulus onset and response polling;
- between response detection and immediate stimulus termination;
- between response detection and reward actuation.

Preferred architecture:

1. select stimulus and establish trial identity before the latency-critical onset path;
2. keep physical ADC channels as the timing source;
3. send compact metadata without delaying behavioral control;
4. stop audio immediately after a valid response when running in stop-on-response mode;
5. reward immediately according to behavior logic;
6. send noncritical semantic/end-of-trial information outside the critical path where possible.

A useful future addition is to include Git provenance in the local session log, for example the active `pyoperant` and `py-behaviors` branch names and commit SHAs. Any Message Center version should remain compact enough to stay well below the 512-character limit.

---

## 11. Git / documentation workflow

September 25 implementation: `ivr_rt_chronic` and its standard-library recorder helper are prepared together in py-behaviors on `codex/ivr-rt-chronic-recording`, targeting master. Keeping this first integration together avoids an extra core-branch deployment dependency; the generic helper can move into pyoperant when stable. The ordinary `ivr_rt_pilot` source is unchanged. See [configuration, lifecycle and commissioning instructions](ivr_rt_chronic_recording.md). Eighteen offline tests pass against pinned real behavior/core sources with simulated hardware and a local HTTP server; no MagPi/Open Ephys deployment or physical test is claimed. The standalone center-port diagnostic remains separate. The new wrapper records ordinary trials; activating continuation/silence probes is a subsequent behavior change.

The chronic rig should ultimately follow the same principle as the rest of the lab: production behavior comes from version-controlled code rather than ad-hoc files on the Raspberry Pi.

Recommended repository split:

```text
gentnerlab/pyoperant
    generic Open Ephys client/helpers
    generic event hooks
    Rev D / reusable hardware integration
    this integration documentation

gentnerlab/py-behaviors
    song_recognition_early_resp_subset_first_valid
    experiment-specific Open Ephys behavior logic
    experiment configs/manifests
```

Temporary diagnostics can remain under `~/open_ephys_tests` while the integration is being validated, but they should not become the production behavior path.

The current living document is intentionally posted on `open_ephys_nt` so other lab members can see the current state before the feature is ready for `master`.

---

## 12. Open questions / TODO

- [ ] **Make a Neuropixels-to-Doric commutator patch cable/adapter.** Establish the exact connector/pin mapping and ground/shield connections, provide strain relief, verify continuity/isolation before connecting equipment, and check recording integrity during commutator rotation. Requested September 25; exact cable specification and compatibility remain to establish.
- [ ] Implement the preferred asfour Git relay and separate stimulus-transfer workflow in section 2.4; verify account/paths/import locations and capture installed commits. No relay setup has been performed by these documentation updates.

- [x] Prepare config-driven session recording and queued semantic metadata in the actual `ivr_rt_pilot` inheritance path; offline implementation tested, awaiting review/merge and commissioning.
- [ ] Deploy and bench-test `ivr_rt_chronic` with a dummy subject config; verify real recorded messages, CSV joins, mode restoration, disconnect handling and free-food eligibility.
- [x] Obtain and install the digital HDMI-to-BNC breakout for J6 behavioral-state signals.
- [x] Validate permanent digital mapping: breakout IO1→ADC0 left, IO2→ADC1 center, IO3→ADC2 right, IO4→ADC3 hopper.
- [ ] Verify the planned stereo audio map: left audio ADC10, right audio ADC11; both analog.

- [ ] Finalize chronic-rig Git deployment while preserving the dedicated asfour ↔ MagPi Open Ephys network.
- [x] Complete the oscilloscope investigation of the audio onset/offset issue — Nathan reported it resolved on 2026-09-25.
- [x] Adjust/fix both MagPi audio potentiometers (`R43`/`R44`) — reported complete on 2026-09-25.
- [x] Replace the temporary digital wire-to-wire hookup with HDMI-to-BNC breakout → BNC → OneBox wiring.
- [ ] Complete/verify the final analog-audio breakout wiring and update the active audio channel map.
- [ ] Add a chamber microphone channel to OneBox and document its channel assignment/calibration.
- [ ] Update `recover_open_ephys_events.py` to the validated ADC0–ADC3 mapping.
- [ ] Add robust audio onset detection to the recovery script, using each recording's channel map (historical left ADC11; planned left ADC10/right ADC11).
- [x] Prepare version-1 compact session/trial metadata schema; validate actual saved GUI messages during commissioning.
- [x] Integrate metadata into the selected full `ivr_rt_pilot` path via `ivr_rt_chronic`, superseding the older subset-behavior target. Review/merge and hardware validation remain open.
- [x] Keep HTTP/journal work outside onset, response polling, audio stop and reward paths in the candidate; verify physical timing under load on the rig.
- [ ] Test electrical audio onset detection across real birdsong, clean stimuli, and noise mixtures using the final channel map.
- [ ] Verify whether the Message Center ↔ OneBox timestamp offset remains similar across sessions/configurations. This is QC only; analysis should not depend on correcting it.
- [ ] Characterize the small ADC8/ADC9/ADC10 onset artifacts if they become relevant.
- [ ] Decide final placement in the main manual once the chronic workflow stabilizes.
- [ ] Convert stable procedures into manual-ready setup instructions and diagrams.

---

## 13. Changelog

### 2026-09-30

Completed and functionally validated the permanent digital behavioral-state wiring through the Open Ephys HDMI-to-BNC breakout. Canonical mapping is now:

- breakout `IO1` → OneBox `ADC0` → `left_ir`;
- breakout `IO2` → OneBox `ADC1` → center peck port;
- breakout `IO3` → OneBox `ADC2` → right peck port;
- breakout `IO4` → OneBox `ADC3` → `hopper_ir`.

All four channels produced the expected state changes during physical testing. Updated Sections 3–4 and the hardware TODOs to treat this as the current validated digital wiring rather than a future breakout-board task.

### 2026-09-25

Follow-up: recorded the planned left/right audio rewire to ADC10/ADC11 and the extra breakout board needed for the digital BNC route. Added the config-driven `ivr_rt_chronic` implementation/commissioning guide. This candidate uses session recording ownership, retrospective trial metadata, local JSONL, CSV session IDs, and a failure latch preserving configured free-food eligibility. Eighteen offline checks pass; real GUI/OneBox commissioning remains open.

Nathan reported that the scope investigation is completely resolved and both MagPi potentiometers are fixed. Marked the scope/potentiometer tasks complete and retained the earlier artifact observations and hypothesis as historical context. Added the short-term breakout-board-to-BNC wiring task, a post-wiring functional check, and the long-term HDMI-to-BNC plan, pending availability of the required breakout boards.

### 2026-09-18

Updated deployment/network/Git status and posted the living integration note to the `open_ephys_nt` development branch.

Validated:

- `magpi101` remains at `192.168.1.101/24` and reaches the Open Ephys REST API on asfour at `192.168.1.100`;
- MagPi default route points to asfour, but asfour is not currently forwarding/NATing internet traffic;
- `~/pyoperant` and `~/py-behaviors` are valid clean Git repositories on `master`;
- both current origins still point to `bird@192.168.1.100:~/code/...`, which is correct in the normal behavioral-room topology but incorrect on the chronic network;
- Open Ephys networking remains the priority and should not be renumbered simply to reproduce the normal fleet topology.

Also documented the current J7/ADC11 transient investigation, the `R43`/`R44` hardware hypothesis, the planned oscilloscope test, the distinction from the old `open_ephys_ts` GPIO timing marker, and the plan for a chamber microphone channel.

### 2026-09-16

Initial chronic MagPi–Open Ephys validation documented.

Established:

- one deployed chronic MagPi at `192.168.1.101`;
- chronic MagPi connected directly to asfour for Open Ephys control/metadata;
- chronic box 1 with Doric AERJ_24_Harwin assisted commutator;
- Rev D front-panel digital behavioral-state routing to OneBox;
- ADC0 = left, ADC1 = center, ADC2 = right, ADC3 = hopper;
- ADC0–ADC3 configured as Digital Inputs;
- ADC11 retained as analog electrical audio copy;
- OneBox ADC rate = 30,300.5 Hz;
- hardware RT reconstruction from ADC11 → ADC0/ADC2;
- ~1.2–2.5 ms physical response-to-audio-stop latency in test trials;
- 2.146 s physical hopper-high interval for a requested 2.0 s reward;
- Message Center 512-character truncation behavior;
- compact Message Center payload recommendation;
- 100-event center-IR / Message Center latency benchmark;
- ~0.020 ms median Python detection-to-send initiation;
- ~4.093 ms median HTTP RTT;
- ~−40.445 ms median saved-stream offset between Message Center and ADC1;
- decision that physical OneBox channels are authoritative timing and Message Center is metadata only.