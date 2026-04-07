# StreamController Plugin Development Guide

> Source: [StreamController docs](https://streamcontroller.github.io/docs/latest/) and [PluginTemplate](https://github.com/StreamController/PluginTemplate)

## Overview

StreamController plugins are Python packages that register one or more **actions**. Each action maps to a button (or dial/touchscreen zone) on a Stream Deck. The framework is GTK4-based; the app runs on Linux using PipeWire/WirePlumber for audio.

Testing without physical hardware is supported via **FakeDecks**: Settings → Developer Settings → configure FakeDecks (max 3).

---

## File Layout

```
my-plugin/
├── main.py                        # Plugin entry point (PluginBase subclass)
├── manifest.json                  # Plugin metadata
├── about.json                     # Human-readable description
├── attribution.json               # Credits / licenses
├── assets/                        # Icons, images used by actions
├── locales/                       # i18n strings (optional)
└── actions/
    └── MyAction/
        ├── MyAction.py            # Action class (ActionBase subclass)
        └── backend/               # Optional: separate process via RPyC
            └── backend.py
```

---

## Base Classes

All base classes are imported from `src.backend.PluginManager.*` (when running inside StreamController) or from `streamcontroller_plugin_tools` (installed separately for standalone use).

### `PluginBase`

The plugin entry point. Subclass this in `main.py`.

```python
from src.backend.PluginManager.PluginBase import PluginBase
from src.backend.PluginManager.ActionHolder import ActionHolder
from .actions.MyAction.MyAction import MyAction

class MyPlugin(PluginBase):
    def __init__(self):
        super().__init__()

        self.my_action_holder = ActionHolder(
            plugin_base=self,
            action_base=MyAction,
            action_id="com_example_MyPlugin::MyAction",  # reverse-domain, underscores
            action_name="My Action",
        )
        self.add_action_holder(self.my_action_holder)

        self.register(
            plugin_name="My Plugin",
            github_repo="https://github.com/example/my-plugin",
            plugin_version="1.0.0",
            app_version="1.1.1-alpha",
        )
```

**Key `PluginBase` methods:**

| Method | Purpose |
|--------|---------|
| `register(plugin_name, github_repo, plugin_version, app_version)` | Register plugin metadata |
| `add_action_holder(holder)` | Register an action with the plugin |
| `get_settings()` / `set_settings(settings)` | Persist plugin-level settings to `plugin_dir/settings.json` |
| `add_css_stylesheet(path)` | Load CSS for action config UIs (prefix all class names uniquely) |
| `launch_backend(backend_path, venv_path, open_in_terminal)` | Start a plugin-wide backend subprocess |
| `on_uninstall()` | Cleanup hook — disconnect/terminate backends |

---

### `ActionBase`

Subclass this for each action. One instance is created per button that uses the action.

```python
from src.backend.PluginManager.ActionBase import ActionBase
import os
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

class MyAction(ActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_ready(self) -> None:
        # Called after app is fully loaded — safe to update display here
        icon_path = os.path.join(self.plugin_base.PATH, "assets", "icon.png")
        self.set_media(media_path=icon_path, size=0.75)

    def on_key_down(self) -> None:
        # Called (in a thread) when the button is pressed
        pass

    def on_key_up(self) -> None:
        # Called (in a thread) when the button is released
        pass

    def on_tick(self) -> None:
        # Called ~every second on the main thread — keep it fast, no blocking
        pass
```

**Key `ActionBase` methods:**

| Method | Purpose |
|--------|---------|
| `on_ready()` | App loaded — set initial display here, not in `__init__` |
| `on_key_down()` | Button pressed (runs in thread) |
| `on_key_up()` | Button released (runs in thread) |
| `on_tick()` | ~1 Hz update tick (main thread, non-blocking only) |
| `set_media(image=None, media_path=None, size=1.0, valign=0, halign=0, loop=True, fps=30, update=True)` | Set button image/GIF/video |
| `set_label(text, position, color, stroke_width, font_family, font_size, update)` | Text overlay on button |
| `set_top_label(text, ...)` / `set_center_label(text, ...)` / `set_bottom_label(text, ...)` | Convenience label setters |
| `set_background_color(color, update=True)` | Set button background color |
| `show_error(duration=-1)` / `hide_error()` | Display error state on button |
| `get_settings()` / `set_settings(settings)` | Persist per-button settings as JSON |
| `get_config_rows()` | Return list of `Adw.PreferencesRow` for settings UI |
| `get_custom_config_area()` | Return custom GTK widget for settings UI |
| `connect(signal, callback)` | Subscribe to a StreamController signal |
| `launch_backend(backend_path, venv_path=None, open_in_terminal=False)` | Start action's backend subprocess |
| `get_own_key()` | Get the `ControllerKey` object for this button |
| `get_is_multi_action()` | Whether this action is part of a multi-action |

**Class attribute:**

```python
HAS_CONFIGURATION = True  # Auto-opens config UI when button is added (default: False)
```

---

### `BackendBase`

Use when an action needs a separate process — e.g. heavy third-party libraries or conflicting dependencies.

```python
from streamcontroller_plugin_tools import BackendBase

class Backend(BackendBase):
    def __init__(self):
        super().__init__()
        self.counter: int = 0

    def get_count(self) -> int:
        return self.counter

    def increase_count(self) -> None:
        self.counter += 1

backend = Backend()  # Must instantiate at module level
```

Launch from the action's `__init__`:

```python
import os

class MyAction(ActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        backend_path = os.path.join(
            self.plugin_base.PATH, "actions", "MyAction", "backend", "backend.py"
        )
        self.launch_backend(backend_path=backend_path, open_in_terminal=False)

    def on_key_down(self):
        try:
            self.backend.increase_count()
            self.set_center_label(str(self.backend.get_count()))
        except Exception as e:
            self.show_error()
```

The action calls backend methods via `self.backend.method_name()` over RPyC (localhost RPC).

---

## `manifest.json`

Minimal format (all fields required for store submission):

```json
{
    "version": "1.0.0",
    "thumbnail": "assets/thumbnail.png",
    "id": "com_example_MyPlugin",
    "name": "My Plugin"
}
```

The `id` uses reverse-domain notation with **underscores** (not dots). Action IDs follow the pattern `{plugin_id}::{ActionClassName}`.

---

## Settings UI (GTK4 / Adwaita)

Override `get_config_rows()` in your action to add settings that appear when the user clicks the action in the UI:

```python
def get_config_rows(self):
    self.label_row = Adw.EntryRow(title="Label text")
    settings = self.get_settings()
    self.label_row.set_text(settings.get("label", ""))
    self.label_row.connect("notify::text", self.on_label_changed)
    return [self.label_row]

def on_label_changed(self, entry, _):
    settings = self.get_settings()
    settings["label"] = entry.get_text()
    self.set_settings(settings)
```

For a fully custom UI, override `get_custom_config_area()` and return any GTK widget.

---

## Plugin-Level vs. Action-Level Settings

| Scope | Class | Storage |
|-------|-------|---------|
| Plugin-wide | `PluginBase` | `plugin_dir/settings.json` |
| Per-button | `ActionBase` | Per-button JSON in page data |

---

## Directory Reference

- `self.plugin_base.PATH` — absolute path to the plugin directory
- Assets: `os.path.join(self.plugin_base.PATH, "assets", "icon.png")`
- Backend: `os.path.join(self.plugin_base.PATH, "actions", "MyAction", "backend", "backend.py")`

---

## Quick Reference: Minimal Plugin

**`main.py`**
```python
from src.backend.PluginManager.PluginBase import PluginBase
from src.backend.PluginManager.ActionHolder import ActionHolder
from .actions.SimpleAction.SimpleAction import SimpleAction

class PluginTemplate(PluginBase):
    def __init__(self):
        super().__init__()
        self.simple_action_holder = ActionHolder(
            plugin_base=self,
            action_base=SimpleAction,
            action_id="dev_core447_Template::SimpleAction",
            action_name="Simple Action",
        )
        self.add_action_holder(self.simple_action_holder)
        self.register(
            plugin_name="Template",
            github_repo="https://github.com/StreamController/PluginTemplate",
            plugin_version="1.0.0",
            app_version="1.1.1-alpha",
        )
```

**`actions/SimpleAction/SimpleAction.py`**
```python
from src.backend.PluginManager.ActionBase import ActionBase
import os

class SimpleAction(ActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_ready(self) -> None:
        icon_path = os.path.join(self.plugin_base.PATH, "assets", "info.png")
        self.set_media(media_path=icon_path, size=0.75)

    def on_key_down(self) -> None:
        print("Key down")

    def on_key_up(self) -> None:
        print("Key up")
```

---

## Resources

- [Official Docs](https://streamcontroller.github.io/docs/latest/)
- [Plugin Template](https://github.com/StreamController/PluginTemplate)
- [streamcontroller-plugin-tools](https://github.com/StreamController/streamcontroller-plugin-tools)
- [Example: Counter plugin](https://github.com/StreamController/Counter)
- [Example: OBS plugin](https://github.com/StreamController/OBSPlugin)
