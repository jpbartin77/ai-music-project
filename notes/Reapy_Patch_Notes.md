## ReaScript / reapy-next Setup — Python 3.13 Compatibility Patches
**Date:** March 14, 2026

### Overview
Getting `reapy-next` working with Python 3.13 and Reaper 7.65 on Windows required
two manual patches to the installed package. These patches are saved in
`.venv-patches/` and can be re-applied using `patch_reapy.bat`.

---

### Background
`reapy` is a Python library that bridges Python scripts to the Reaper DAW via a
WebSocket connection. The original `reapy` package is unmaintained; `reapy-next`
is the community fork.

Neither package is fully compatible with Python 3.13 out of the box. Two bugs
required manual fixes.

---

### Bug 1 — `lib2to3` removed from Python 3.13
**File:** `reapy/core/envelope.py` (line 1)

**Error:**
```
ModuleNotFoundError: No module named 'lib2to3'
```

**Cause:** Python 3.13 removed the `lib2to3` module entirely. `reapy-next`
still imports from it.

**Fix:** Replace the import with the standard library `tokenize` module:
```python
# Before
from lib2to3.pgen2.token import OP

# After
from tokenize import OP
```

---

### Bug 2 — `_UnnamedSection` has no attribute `lower`
**File:** `reapy/config/config.py` — `CaseInsensitiveDict` class (lines 44, 47, 50, 54)

**Error:**
```
AttributeError: '_UnnamedSection' object has no attribute 'lower'
```

**Cause:** Python 3.13's `configparser` passes `_UnnamedSection` objects as
keys in some cases instead of plain strings. The `CaseInsensitiveDict` class
calls `.lower()` directly on keys without type-checking.

**Fix:** Wrap all `.lower()` calls with `str()` to safely convert any key type:
```python
# Before
self._dict[key.lower()] = value

# After
self._dict[str(key).lower()] = value
```

Applied to all four occurrences in the class (`__init__`, `__contains__`,
`__getitem__`, `__setitem__`).

---

### Patch locations
Both fixes must be applied in **two locations**:
- System Python: `C:\Users\jpbar\AppData\Local\Programs\Python\Python313\Lib\site-packages\reapy\`
- Project venv: `<project>\.venv\Lib\site-packages\reapy\`

---

### patch_reapy.bat
Saved in `.venv-patches\patch_reapy.bat`. Copies the two patched files to
both locations in one step.

**When to run it:**
- After any Reaper update (updates can overwrite Python packages)
- After recreating the `.venv`
- After reinstalling `reapy-next`

**How to run:**
1. Right-click `patch_reapy.bat` → Run as Administrator
2. Restart Reaper
3. In Reaper: Actions → Run `enable_reapy.py` once per session

---

### Enabling the dist API
`reapy` communicates with Reaper via a local WebSocket server called the
"distant API." It must be enabled once per Reaper session by running
`enable_reapy.py` inside Reaper's ReaScript environment.

**Script location:** `C:\Users\jpbar\AppData\Roaming\REAPER\Scripts\enable_reapy.py`

**Contents:**
```python
import reapy; reapy.config.enable_dist_api()
```

**Confirmed working test:**
```
python -c "import reapy; reapy.print('hello from Python!')"
```
Expected result: `hello from Python!` appears in Reaper's console output window.

---

### Key lesson
Reaper auto-updates can wipe `site-packages` patches. Consider turning off
auto-update in Reaper preferences, or always re-run `patch_reapy.bat` after
any Reaper update.