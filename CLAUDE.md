# Volume Group Mixer

A StreamController plugin for the **Stream Deck+** that maps each rotary dial to a named group of PipeWire applications, controlling their volume together.

## Architecture

```
main.py                                    # VolumeGroupMixerPlugin (PluginBase)
actions/VolumeGroupMixer/
  VolumeGroupMixer.py                      # VolumeGroupMixerAction (DialAction)
backend/
  backend.py                               # Backend (BackendBase, runs via RPyC)
```

**Two-process model:** The action runs in the StreamController process; the backend runs as a separate subprocess. They communicate over RPyC. All audio calls go through the backend.

### `main.py`
Registers the `VolumeGroupMixerAction` holder and launches `backend/backend.py` with its own venv at `backend/.venv`.

### `actions/VolumeGroupMixer/VolumeGroupMixer.py`
`VolumeGroupMixerAction` subclasses `DialAction`. Handles:
- Dial CW/CCW → `exposed_adjust_volume` with ±step
- Short press → `exposed_toggle_mute`
- `on_tick` (~1 Hz) and after every action → `_refresh_display`
- `get_config_rows()` → Adwaita config UI with group name, step size (1–20%), app binaries list, and a live "Active audio streams" panel (clickable to add)

Group ID is `str(self.input_ident)` — unique per dial slot.

### `backend/backend.py`
`Backend` subclasses `BackendBase`. Uses **pulsectl** (PulseAudio/PipeWire compatibility) to control sink inputs. Methods prefixed `exposed_` are callable from the action via `self.plugin_base.backend.*`.

| Method | Purpose |
|--------|---------|
| `exposed_register_group(group_id, binaries)` | Register/update group; resolves initial volume |
| `exposed_adjust_volume(group_id, delta)` | Relative volume change; snaps diverged apps to min first |
| `exposed_toggle_mute(group_id)` | Toggle mute for all apps in group |
| `exposed_get_group_state(group_id)` | Returns `(volume: float\|None, all_muted: bool)` |
| `exposed_get_running_binaries()` | Sorted list of running PipeWire app binaries |

State is **in-memory only** — no persistence across launches.

## Key Behaviours

- **Volume snapping:** On first dial turn, if apps have diverged volumes (spread >0.5%), all snap to the quietest before applying delta.
- **Missing apps:** Skipped silently. Display shows `???` when no apps in the group are running.
- **Mute display:** `M 75%` only when all apps in the group are muted.
- **Volume range:** 0–100% (clamped, no boost above 1.0).
- **App matching:** By `application.process.binary` property (e.g. `firefox`, `spotify`). One binary can appear in multiple groups.

## Display (dial key)

- Top label: group name
- Bottom label: `75%` / `M 75%` (muted) / `???` (no apps running)

## Configuration (per dial slot)

| Setting | Default |
|---------|---------|
| Group name | "" |
| Step size (%) | 5 |
| App binaries | [] |

## Coding Guidelines

- Type hints on all function definitions
- No comments
- No logging statements
- Only define functions when there's reusable code
- Concise over verbose — simpler is always better
- Package/env manager: **UV**

## Backend Dependencies

`backend/requirements.txt` (installed into `backend/.venv` via UV):

```
streamcontroller-plugin-tools>=2.0.1
pulsectl
```

This venv is passed to `launch_backend()` as `venv_path` in `main.py`.

## Dev Environment

Devcontainer (Podman) with:
- PulseAudio socket bind-mounted at `/tmp/pulse/native`
- PipeWire socket bind-mounted at `/tmp/pipewire-0`
- Env vars: `XDG_RUNTIME_DIR=/tmp`, `PIPEWIRE_RUNTIME_DIR=/tmp`, `PULSE_SERVER=unix:/tmp/pulse/native`

## Plugin Metadata

- Plugin ID: `net_jesseyoung_volumegroupmixer`
- Action ID: `net_jesseyoung_volumegroupmixer::VolumeGroupMixer`
- Min StreamController version: `1.5.0`
