# WirePlumber / libwireplumber in Python

This document captures implementation knowledge about using libwireplumber from Python, derived from working through a complete implementation using the native C API. It is intended as a reference prompt for AI-assisted development of this plugin.

## Existing Python Projects Worth Knowing About

Before implementing from scratch, be aware of these:

- **`gi.repository.Wp` (direct GI bindings)** — WirePlumber ships GObject Introspection typelib data (`gir1.2-wp-0.5`), so the entire API is available natively in Python via `python3-gi`. This is the right approach for this project — no subprocess or DBus layer needed.
- **Astal / AstalWp** ([github.com/Aylur/astal](https://github.com/Aylur/astal)) — a higher-level GI wrapper around WirePlumber designed for desktop widget systems. Shows real Python GI binding patterns including async init and signal use.
- **`wpctl` subprocess pattern** — the most common community approach. Simple and stable but only suitable for one-shot commands; not appropriate here since we need live event subscriptions.
- **`pipewire_python`** (PyPI) — wraps PipeWire's CLI tools, not WirePlumber's API directly. Not useful for mixer-api access.

The direct `gi.repository.Wp` approach is the right choice here: it gives full access to the mixer-api plugin, ObjectManager, and GObject signals without any subprocess overhead.

---

## Access via GObject Introspection

```python
import gi
gi.require_version('Wp', '0.5')
gi.require_version('GLib', '2.0')
from gi.repository import Wp, GLib
```

Requires `gir1.2-wp-0.5` and `python3-gi` to be installed (both are in the devcontainer). The `Wp` namespace maps 1:1 to the C API — function names drop the `wp_` prefix and become methods/constructors on the corresponding class.

---

## Initialization Sequence

This must happen in a specific order. Getting it wrong results in silent failures or crashes.

### 1. Initialize the library

```python
Wp.init(Wp.InitFlags.ALL)
```

Called once before anything else. `InitFlags.ALL` covers PipeWire init and SPA type registration.

### 2. Create a GLib main context and core

```python
main_loop = GLib.MainLoop()
core = Wp.Core.new(main_loop.get_context(), None)
```

The core must be created with a GLib context. The context drives all async operations — nothing happens without the main loop running.

### 3. Connect to PipeWire

```python
if not core.connect():
    raise RuntimeError("Failed to connect to PipeWire/WirePlumber")
```

Connects via the socket at `$PIPEWIRE_RUNTIME_DIR/pipewire-0` (set to `/tmp/pipewire-0` in the devcontainer, which is bind-mounted from the host).

### 4. Load plugins asynchronously

Two plugins are required:

```python
pending = {'count': 2}

def on_plugin_loaded(core, result, data):
    try:
        core.load_component_finish(result)
    except Exception as e:
        print(f"Plugin load failed: {e}")
        return

    pending['count'] -= 1
    if pending['count'] == 0:
        on_all_plugins_loaded()

core.load_component(
    "libwireplumber-module-mixer-api", "module", None, None, None,
    on_plugin_loaded, None
)
core.load_component(
    "libwireplumber-module-default-nodes-api", "module", None, None, None,
    on_plugin_loaded, None
)
```

**Both plugins must finish loading before proceeding.** Use a counter (as above) to detect when both are done. Plugin loading is async — the callbacks fire on the GLib main loop, so the loop must already be running or started shortly after.

### 5. Set up mixer API (after plugins load)

```python
def on_all_plugins_loaded():
    mixer_api = core.find_plugin("mixer-api")
    
    # Use cubic scale — matches human perception of loudness
    mixer_api.set_property("scale", int(Wp.MixerApiVolumeScale.CUBIC))
    
    # Listen for volume changes on any node
    mixer_api.connect("changed", on_volume_changed)
    
    # Now install the object manager
    core.install_object_manager(object_manager)
```

### 6. Run the main loop

```python
import threading

def run_loop():
    main_loop.run()  # Blocks until main_loop.quit() is called

thread = threading.Thread(target=run_loop, daemon=True)
thread.start()
```

**Critical:** The GLib main loop must run on a dedicated thread. All WirePlumber callbacks fire on that thread. Any calls to mixer-api signals (get-volume, set-volume) must also be invoked from that thread — use `GLib.idle_add()` to schedule work onto the loop thread from other threads.

---

## Node Discovery with ObjectManager

```python
object_manager = Wp.ObjectManager.new()

# Register interest in WpNode objects only
object_manager.add_interest_full(
    Wp.ObjectInterest.new(Wp.Node)
)

# Request minimal features (faster, sufficient for property access)
object_manager.request_object_features(
    Wp.Node, Wp.PipewireObject.FEATURES_MINIMAL
)

object_manager.connect("object-added", on_node_added)
object_manager.connect("object-removed", on_node_removed)
```

The ObjectManager is not active until `core.install_object_manager()` is called — this is intentional and must happen after plugins are loaded.

### Reading node properties

```python
def on_node_added(om, node):
    props = node.get_properties()
    media_class = props.get("media.class")        # e.g. "Stream/Output/Audio"
    app_name = props.get("application.name")      # e.g. "Firefox"
    binary = props.get("application.process.binary")
    node_id = node.get_bound_id()                 # uint32, used with mixer-api
```

Useful `media.class` values for filtering:
- `"Stream/Output/Audio"` — application playback streams (what you usually want)
- `"Stream/Input/Audio"` — application capture streams
- `"Audio/Sink"` — physical/virtual output devices
- `"Audio/Source"` — physical/virtual input devices

---

## Volume Control via mixer-api

Volume is always a `float` in the range `0.0–1.0`. Mute is a separate `bool`. The mixer-api exposes both through GObject signals (not method calls).

### Reading volume

```python
def get_volume(mixer_api, node_id):
    # g_signal_emit_by_name equivalent — returns a GLib.Variant dict
    result, volume_dict = mixer_api.emit("get-volume", node_id)
    if volume_dict is None:
        return None
    volume = volume_dict["volume"]   # float, 0.0–1.0
    muted = volume_dict["mute"]      # bool
    return volume, muted
```

### Setting volume

Always preserve the existing mute state when changing volume (and vice versa):

```python
def set_volume(mixer_api, node_id, new_volume):
    _, current = mixer_api.emit("get-volume", node_id)
    if current is None:
        return
    mixer_api.emit("set-volume", node_id, {
        "volume": GLib.Variant("d", new_volume),
        "mute":   GLib.Variant("b", current["mute"]),
    })

def set_mute(mixer_api, node_id, muted):
    _, current = mixer_api.emit("get-volume", node_id)
    if current is None:
        return
    mixer_api.emit("set-volume", node_id, {
        "volume": GLib.Variant("d", current["volume"]),
        "mute":   GLib.Variant("b", muted),
    })
```

**The `set-volume` signal takes a GVariant dictionary.** In Python gi bindings, this means a dict with `GLib.Variant` values, with GVariant type codes: `"d"` for double, `"b"` for boolean.

**These calls must happen on the GLib main loop thread.** From another thread:

```python
def set_volume_from_thread(mixer_api, node_id, new_volume):
    def _do_set():
        set_volume(mixer_api, node_id, new_volume)
        return False  # Don't repeat
    GLib.idle_add(_do_set)
```

### Listening for volume changes

```python
def on_volume_changed(mixer_api, node_id):
    volume, muted = get_volume(mixer_api, node_id)
    print(f"Node {node_id}: volume={volume:.2f}, muted={muted}")

mixer_api.connect("changed", on_volume_changed)
```

The `"changed"` signal fires whenever volume or mute state changes on any node, including changes made by this process or other applications.

---

## GVariant in Python

Unlike in C, Python's `python3-gi` handles GVariant automatically in most cases. When receiving a GVariant (e.g., from `get-volume`), gi converts it to a Python dict. When sending one (e.g., to `set-volume`), construct it with `GLib.Variant`:

```python
# Type codes:
# "d" = double (float)
# "b" = boolean
# "u" = uint32
# "s" = string
# "a{sv}" = dict of string -> variant (the volume dict type)

volume_dict = GLib.Variant("a{sv}", {
    "volume": GLib.Variant("d", 0.75),
    "mute":   GLib.Variant("b", False),
})
```

This is significantly simpler than the manual marshalling required in the C API.

---

## Key Gotchas

- **Thread safety:** All WirePlumber/GLib calls must happen on the main loop thread. Use `GLib.idle_add()` to dispatch from other threads.
- **Plugin order:** Install the ObjectManager only after both plugins have loaded. Installing it earlier means nodes may be discovered before the mixer-api is ready.
- **Cubic scale:** Always set `mixer_api.set_property("scale", Wp.MixerApiVolumeScale.CUBIC)`. Linear scale is the default but feels wrong to users — volume 0.5 sounds much quieter than 50%.
- **Node IDs:** Use `node.get_bound_id()` (a `uint32`). This is the ID passed to all mixer-api signals.
- **Preserve paired state:** Always read current volume before setting mute (and vice versa) — the `set-volume` signal requires both keys in the dict.
- **Main loop must be running for plugins to load:** Start the loop thread before or immediately after calling `core.load_component()`, since the callbacks fire on the loop.
