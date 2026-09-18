# MagPi–Open Ephys Chronic Behavior Integration Notes

**Status:** Living engineering note  
**Last updated:** 2026-09-18  
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

Validated chronic wiring:

```text
J6 pin 1  -> OneBox ADC0 -> left IR
J6 pin 3  -> OneBox ADC1 -> center IR
J6 pin 4  -> OneBox ADC2 -> right IR
J6 pin 6  -> OneBox ADC3 -> hopper IR
J6 pin 8  -> OneBox GND
```

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

Validated chronic wiring:

```text
J7 pin 1 -> OneBox ADC11 signal
J7 pin 5 -> OneBox ADC11 ground
```

ADC11 is an **electrical copy of the MagPi audio output**, not a microphone recording. It provides electrical playback onset/offset and a copy of the commanded waveform.

---

## 4. OneBox / Open Ephys configuration

### 4.1 Validated channel map

| OneBox channel | Physical signal | Use |
|---|---|---|
| `ADC0` | Left IR state | Left response timing |
| `ADC1` | Center IR state | Trial initiation / center-peck timing |
| `ADC2` | Right IR state | Right response timing |
| `ADC3` | Hopper IR state | Physical hopper-up / hopper-down timing |
| `ADC11` | Left electrical audio copy | Electrical playback onset/offset |

Earlier development notes sometimes used `IO0`, `IO1`, etc. Saved Open Ephys continuous data and `structure.oebin` label these channels as `ADC0` ... `ADC11`. Analysis code should prefer recorded `ADC#` names or robustly resolve either naming convention.

### 4.2 Input modes

In the OneBox ADC/DAC settings:

- `ADC0`–`ADC3`: Digital Input mode ON;
- `ADC11`: analog input; Digital Input mode OFF.

`ADC0`–`ADC3` carry binary behavioral states. `ADC11` must remain analog because it carries a waveform.

### 4.3 Sample rate

The tested OneBox ADC continuous stream reported **30,300.5 Hz**, approximately 0.033 ms per sample.

---

## 5. Authoritative timing hierarchy

### 5.1 Event definitions

- Center initiation: `ADC1` rising edge
- Left response: `ADC0` rising edge
- Right response: `ADC2` rising edge
- Electrical playback onset: onset detected from the analog `ADC11` waveform
- Hopper physically available: `ADC3` high interval

The authoritative reaction time is:

```text
RT_hardware = t_response(ADC0 or ADC2) - t_audio_onset(ADC11)
```

Both terms therefore live on the OneBox continuous acquisition timebase.

### 5.2 Electrical versus acoustic onset

ADC11 is an electrical playback copy. It is not the actual sound pressure waveform at the bird. A future chamber microphone channel should provide acoustic ground truth when actual acoustic onset at the animal is required.

Recommended hierarchy:

| Event / quantity | Authoritative source | Do not substitute |
|---|---|---|
| Center initiation | ADC1 rising edge | Message Center center event |
| Electrical playback onset | ADC11 waveform onset | `speaker.play()` timestamp or MC `stim_on` |
| Left response | ADC0 rising edge | PyOperant software RT |
| Right response | ADC2 rising edge | PyOperant software RT |
| Reaction time | ADC0/ADC2 − ADC11 | Message Center timestamp differences |
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

### 8.1 Current observation

J7 → ADC11 produces a clear sustained copy of stimulus playback, but testing also revealed large onset and offset transients. The transients can serve as obvious playback boundaries, but their electrical cause has not yet been established.

Small onset-associated deflections have also been observed on ADC8, ADC9, and ADC10. These channels are not used for reconstruction and may reflect pickup/crosstalk; that remains unverified.

### 8.2 Current hardware hypothesis

The Rev D schematic shows trim pots `R43` and `R44` in the analog-audio interface. The hardware designer's working hypothesis is that the HiFiBerry differential legs (`L+`/`L-` or `R+`/`R-`) may not switch with perfectly matched transients, and imperfect trim-pot centering could leave a transient in the single-ended `AUDIO_OUT_L` / `AUDIO_OUT_R` signal.

This is a **hypothesis**, not yet a validated cause.

### 8.3 Planned oscilloscope test

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

- **ADC11 / J7 electrical copy:** what the MagPi commanded electrically and when playback started/stopped in the electronics path;
- **microphone:** what was actually present acoustically in the chamber, including playback verification and bird vocalizations.

---

## 9. Software and validation utilities

Current development utilities include behavior-like playback/IR tests, Message Center latency benchmarking, and post-hoc event recovery.

Important conventions:

- instantiate the Rev D panel through `pyoperant.local_pi_revd.PANELS`;
- use the public speaker API (`queue`, `play`, `stop`);
- for early response termination, use `panel.speaker.stop()` rather than reaching into the underlying PyAudio stream;
- avoid low-level PyAudio stream reset/cleanup in the behavioral control path unless a separately validated failure mode requires it.

`recover_open_ephys_events.py` still needs to be made canonical for the chronic rig. Its default map should resolve:

```text
left   = ADC0
center = ADC1
right  = ADC2
hopper = ADC3
audio  = ADC11
```

It also needs explicit analog ADC11 onset detection rather than relying on a Message Center stimulus event.

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

- [ ] Finalize chronic-rig Git deployment while preserving the dedicated asfour ↔ MagPi Open Ephys network.
- [ ] Scope the J7 left-channel differential/single-ended path and characterize the ADC11 onset/offset transients.
- [ ] Test `R43` adjustment only under measurement.
- [ ] Add a chamber microphone channel to OneBox and document its channel assignment/calibration.
- [ ] Update `recover_open_ephys_events.py` to the validated ADC0–ADC3 mapping.
- [ ] Add robust ADC11 analog onset detection to the recovery script.
- [ ] Finalize the compact Message Center event schema.
- [ ] Integrate compact Open Ephys metadata into `song_recognition_early_resp_subset_first_valid`.
- [ ] Ensure no blocking HTTP call delays stimulus onset, response polling, audio stop, or reward.
- [ ] Test ADC11 onset detection across real birdsong, clean stimuli, and noise mixtures.
- [ ] Verify whether the Message Center ↔ OneBox timestamp offset remains similar across sessions/configurations. This is QC only; analysis should not depend on correcting it.
- [ ] Characterize the small ADC8/ADC9/ADC10 onset artifacts if they become relevant.
- [ ] Decide final placement in the main manual once the chronic workflow stabilizes.
- [ ] Convert stable procedures into manual-ready setup instructions and diagrams.

---

## 13. Changelog

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
