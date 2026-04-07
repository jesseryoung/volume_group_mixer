# Volume Group Mixer — Plugin Requirements

## Overview

A StreamController plugin for the **Stream Deck+** that lets users define named groups of applications and control their PipeWire volume together via a single rotary dial. Each dial on the Stream Deck+ maps to one group.

---

## Hardware

- **Target device:** Stream Deck+ (4 dials + touch strip)
- **One action instance = one group.** Groups are created by adding the action to a button/dial slot. The number of groups is not fixed — it depends on how many times the user adds the action across pages.

---

## Audio Backend

- **API:** WirePlumber via `python3-gi` (`gi.require_version('Wp', '0.5')`) using two modules: `libwireplumber-module-mixer-api` and `libwireplumber-module-default-nodes-api`. Both must finish loading before proceeding.
- **App identification:** Match nodes by the `application.process.binary` PipeWire property. Only consider nodes where `media.class = "Stream/Output/Audio"` — this excludes physical sinks, sources, and capture streams.
- **Volume representation:** Internally `float 0.0–1.0`; displayed to the user as a rounded integer percentage.
- **Volume scale:** Always set `mixer_api.set_property("scale", Wp.MixerApiVolumeScale.CUBIC)` — cubic scale matches human loudness perception. Linear (the default) is not acceptable.
- **Volume control:** Via the mixer-api `set-volume` signal. The signal requires both `volume` and `mute` keys in every call — always read current state first to preserve the unpublished field.
- **Muting:** Set/clear the PipeWire mute flag on the node — do not set volume to 0.
- **Node watching:** Use `Wp.ObjectManager` with interest in `Wp.Node` to detect nodes being added or removed in real time. Install the ObjectManager only after both plugins have finished loading.
- **Max volume:** 100% (`1.0`) — clamp and do not allow boosting above unity gain.
- **Thread safety:** The GLib main loop runs on a dedicated background thread in the backend process. All WirePlumber and mixer-api calls must be dispatched onto that thread via `GLib.idle_add()` — never called directly from RPyC handler threads.

---

## Group Behaviour

### Volume Changes
- Each dial tick = ±N% (N is configurable per group, set in the action config UI).
- Changes are **relative** — the dial shifts the group volume up or down by N% per tick.

### Volume Snapping
- When a group's apps have differing volumes (e.g. on first use or after external changes), the first dial turn **snaps all apps to the quietest app's current volume**, then applies the delta from there.

### Mute Toggle
- **Pressing the dial** toggles mute for all apps in the group simultaneously using the PipeWire mute flag.
- The muted state is shown on the display only when **all apps in the group are muted** (indicating the group was muted via the dial). Individual app mutes are not tracked or reflected.

### Missing Apps
- If an app in a group is not currently running, **skip it silently**.
- When a new PipeWire node appears, check if its `application.process.binary` matches any group. If so, set its volume to the group's current tracked volume immediately.

---

## Initial Volume Resolution

When the plugin starts (or a new group action loads) and there is no in-memory volume for the group:

1. **One matching app running** → adopt that app's current volume as the group volume.
2. **Multiple matching apps running** → adopt the quietest app's volume as the group volume, and snap all others to match.
3. **No matching apps running** → display `???` for the volume. When the first matching app starts, adopt its volume as the group volume.

The plugin is **stateless between launches** — no volume state is persisted to disk.

---

## Configuration UI (per action)

Shown in the StreamController action config panel when the user clicks the action.

| Setting | Type | Description |
|---------|------|-------------|
| Group name | Text field | Display name shown on the dial key |
| Icon | Asset picker | Static icon shown on the dial key (StreamController standard asset picker) |
| App binaries | Text list | One `application.process.binary` value per entry (e.g. `firefox`, `spotify`) |
| Step size | Number input | Volume % change per dial tick (per group) |

**App entry UX:** Free-text input for binary names. Display a read-only list of currently running PipeWire app binaries alongside the input to help the user identify the correct values.

An app binary can appear in multiple groups.

---

## Display (Dial Key)

The dial key face shows:

- **Group name** (top or center label)
- **Volume %** (e.g. `75%`) or `???` if volume is unknown
- **Static icon** (configured via asset picker)
- **Muted indicator** only when all apps in the group are muted

The display updates in **real time** as volume changes (whether from the dial or an external source).

---

## Plugin Architecture

- **Action class** (`ActionBase` subclass) handles dial events, display updates, and config UI.
- **Backend process** (`BackendBase` subclass via RPyC) handles all WirePlumber communication — node discovery, volume get/set, mute, and signal subscriptions — to avoid blocking the UI thread and to isolate the GLib main loop required by WirePlumber.

---

## Coding Guidelines
- For function definitions, make sure to use type hints as much as possible.
- Don't add any comments
- Only define functions when there's re-usable code
- Don't add any logging statements
- Use UV as the package manager and environment manager
- Less, more concise code is ALWAYS better than verbose code that's easier to read.
- SIMPLER IS BETTER. ALWAYS.
