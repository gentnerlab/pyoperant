# Python 3 Migration Notes

All changes needed to migrate pyoperant from Python 2 to Python 3. All 22 unit tests pass on Python 3.14 after applying these changes.

---

## Phase 1 — Packaging

**Replace `setup.py` with `pyproject.toml`.**

Delete `setup.py` and create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "pyoperant"
version = "0.1.2"
authors = [
    {name = "Justin Kiggins", email = "justin.kiggins@gmail.com"},
]
description = "hardware interface and controls for operant conditioning"
readme = "docs/README.rst"
license = {text = "BSD"}
requires-python = ">=3.9"
dependencies = [
    "ephem",
    "numpy",
]
classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Console",
    "Intended Audience :: Science/Research",
    "License :: OSI Approved :: BSD License",
    "Natural Language :: English",
    "Operating System :: Unix",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Scientific/Engineering",
]

[tool.setuptools]
script-files = [
    "scripts/behave",
    "scripts/pyoperantctl",
    "scripts/mutate_config_file",
    "scripts/tune_servo.py",
]
```

Note: `pyoperantctl` is a Perl script, so it cannot use `[project.scripts]` entry points and must remain as a raw script file.

---

## Phase 2 — Syntax (hard errors in Python 3)

### `print` statements → `print()` calls

| File | Line | Change |
|---|---|---|
| `pyoperant/utils.py` | 201 | `print "box number..."` → `print("box number...")` |
| `pyoperant/utils.py` | 204 | `print "subject number..."` → `print("subject number...")` |
| `pyoperant/behavior/three_ac_matching.py` | 128 | `print parameters` → `print(parameters)` |
| `pyoperant/behavior/three_ac_matching.py` | 129 | `print PANELS` → `print(PANELS)` |
| `pyoperant/behavior/TargObjObj.py` | 47 | `print e` → `print(e)` |
| `pyoperant/interfaces/console_.py` | 18 | `print value` → `print(value)` |

Note: `pyoperant/local_vogel.py` already uses `print(...)` with parentheses — no change needed.

### `except E, e:` → `except E as e:`

| File | Line | Change |
|---|---|---|
| `pyoperant/utils.py` | 104 | `except Exception, e:` → `except Exception as e:` |
| `pyoperant/behavior/TargObjObj.py` | 46 | `except Exception, e:` → `except Exception as e:` |

### Relative imports in `pyoperant/behavior/__init__.py`

```python
# Before
from two_alt_choice import *
from lights import *
from place_pref import PlacePrefExp
from place_pref_24hr import PlacePrefExp24hr

# After
from .two_alt_choice import *
from .lights import *
from .place_pref import PlacePrefExp
from .place_pref_24hr import PlacePrefExp24hr
```

---

## Phase 3 — Built-ins and stdlib

### `xrange` → `range`

| File | Lines |
|---|---|
| `pyoperant/behavior/three_ac_matching.py` | 26, 28 |
| `pyoperant/behavior/TargObjObj.py` | 55, 82, 86, 87, 90, 91 |

Simple global find-and-replace of `xrange` with `range` in both files.

### `raw_input` → `input`

| File | Line |
|---|---|
| `pyoperant/panels.py` | 58 |
| `pyoperant/interfaces/console_.py` | 13 |
| `scripts/tune_servo.py` | 92 |
| `scripts/test_panel.py` | 69 |

### `cPickle` → `pickle`

**`pyoperant/queues.py` line 3:**
```python
# Before
import cPickle as pickle
# After
import pickle
```

**`pyoperant/behavior/text_markov.py` line 17:**
```python
# Before
import cPickle
# After
import pickle as cPickle  # preserves all downstream cPickle.load/dump calls
```

### `basestring` → `str`

**`pyoperant/utils.py` line 150:**
```python
# Before
if isinstance(command, basestring):
# After
if isinstance(command, str):
```

---

## Phase 4 — Behavior changes requiring care

### `string.maketrans` / two-arg `str.translate` in `pyoperant/utils.py`

The `check_cmdline_params` function used the Python 2-only two-argument form of `str.translate` to strip non-digit characters. Replace the entire function:

```python
# Before
def check_cmdline_params(parameters, cmd_line):
    # if someone is using red bands they should ammend the checks I perform here
    allchars=string.maketrans('','')
    nodigs=allchars.translate(allchars, string.digits)
    if not ('box' not in cmd_line or cmd_line['box'] == int(parameters['panel_name'].encode('ascii','ignore').translate(allchars, nodigs))):
        print "box number doesn't match config and command line"
        return False
    if not ('subj' not in cmd_line or int(cmd_line['subj'].encode('ascii','ignore').translate(allchars, nodigs)) == int(parameters['subject'].encode('ascii','ignore').translate(allchars, nodigs))):
        print "subject number doesn't match config and command line"
        return False
    return True

# After
def check_cmdline_params(parameters, cmd_line):
    # if someone is using red bands they should ammend the checks I perform here
    def digits_only(s):
        return ''.join(c for c in s if c.isdigit())
    if not ('box' not in cmd_line or cmd_line['box'] == int(digits_only(parameters['panel_name']))):
        print("box number doesn't match config and command line")
        return False
    if not ('subj' not in cmd_line or int(digits_only(cmd_line['subj'])) == int(digits_only(parameters['subject']))):
        print("subject number doesn't match config and command line")
        return False
    return True
```

Also remove `import string` from the top of `utils.py` — it is only used in this function.

### `dict.items()` indexing in `pyoperant/behavior/three_ac_matching.py`

In Python 3, `dict.items()` returns a view, not a list, so it cannot be indexed directly.

```python
# Before (line 35)
motif_names, motif_files = zip(*[self.parameters['stims'].items()[mid] for mid in mids])

# After
motif_names, motif_files = zip(*[list(self.parameters['stims'].items())[mid] for mid in mids])
```

### `unicode()` calls in `pyoperant/behavior/text_markov.py`

All strings are unicode by default in Python 3. Replace all `unicode("...", "utf-8")` calls with plain string literals (lines 103–124):

```python
# Before
stim_dict[unicode("class", "utf-8")] = ...
stim_dict[unicode("stim_name", "utf-8")] = ...
stim_dict[unicode("seq", "utf-8")] = ...
stim_dict[unicode("order", "utf-8")] = ...
stim_dict[unicode("syll_time_lens", "utf-8")] = ...

# After
stim_dict["class"] = ...
stim_dict["stim_name"] = ...
stim_dict["seq"] = ...
stim_dict["order"] = ...
stim_dict["syll_time_lens"] = ...
```
