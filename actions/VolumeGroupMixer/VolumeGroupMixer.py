import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PluginManager.InputBases import DialAction


class VolumeGroupMixerAction(DialAction):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._binary_rows: list[Adw.EntryRow] = []

    def _group_id(self) -> str:
        return str(self.input_ident)

    def _binaries(self) -> list[str]:
        return self.get_settings().get("binaries", [])

    def _step(self) -> float:
        return self.get_settings().get("step_size", 5) / 100.0

    def on_backend_ready(self) -> None:
        self.plugin_base.backend.exposed_register_group(self._group_id(), self._binaries())
        self._refresh_display()

    def event_callback(self, event, data: dict = None) -> None:
        b = self.plugin_base.backend
        if event == Input.Dial.Events.TURN_CW:
            b.exposed_adjust_volume(self._group_id(), self._step())
        elif event == Input.Dial.Events.TURN_CCW:
            b.exposed_adjust_volume(self._group_id(), -self._step())
        elif event == Input.Dial.Events.SHORT_UP:
            b.exposed_toggle_mute(self._group_id())
        self._refresh_display()

    def on_tick(self) -> None:
        self._refresh_display()

    def _refresh_display(self) -> None:
        s = self.get_settings()
        vol, all_muted = self.plugin_base.backend.exposed_get_group_state(self._group_id())
        self.set_top_label(s.get("group_name", ""))
        self.set_bottom_label(f"{'M ' if all_muted else ''}{round(vol * 100)}%" if vol is not None else "???")

    def get_config_rows(self) -> list:
        s = self.get_settings()
        rows = []

        name_row = Adw.EntryRow(title="Group name")
        name_row.set_text(s.get("group_name", ""))
        name_row.connect("notify::text", self._on_name_changed)
        rows.append(name_row)

        step_row = Adw.SpinRow.new_with_range(1, 20, 1)
        step_row.set_title("Step size (%)")
        step_row.set_value(s.get("step_size", 5))
        step_row.connect("notify::value", self._on_step_changed)
        rows.append(step_row)

        binaries_group = Adw.PreferencesGroup(title="App binaries")
        self._binary_rows = []
        for binary in s.get("binaries", []):
            row = self._make_binary_row(binary)
            binaries_group.add(row)
            self._binary_rows.append(row)
        add_btn = Gtk.Button(label="Add binary")
        add_btn.connect("clicked", lambda _: self._add_binary_row(binaries_group))
        rows.append(binaries_group)
        rows.append(add_btn)

        running_group = Adw.PreferencesGroup(title="Active audio streams")
        for binary in self.plugin_base.backend.exposed_get_running_binaries():
            running_group.add(Adw.ActionRow(title=binary))
        rows.append(running_group)

        return rows

    def _on_name_changed(self, entry, _) -> None:
        s = self.get_settings()
        s["group_name"] = entry.get_text()
        self.set_settings(s)
        self._refresh_display()

    def _on_step_changed(self, spin, _) -> None:
        s = self.get_settings()
        s["step_size"] = int(spin.get_value())
        self.set_settings(s)

    def _make_binary_row(self, value: str) -> Adw.EntryRow:
        row = Adw.EntryRow(title="Binary name")
        row.set_text(value)
        row.connect("notify::text", lambda *_: self._save_binaries())
        return row

    def _add_binary_row(self, group: Adw.PreferencesGroup) -> None:
        row = self._make_binary_row("")
        group.add(row)
        self._binary_rows.append(row)

    def _save_binaries(self) -> None:
        s = self.get_settings()
        s["binaries"] = [r.get_text() for r in self._binary_rows if r.get_text()]
        self.set_settings(s)
        self.plugin_base.backend.exposed_register_group(self._group_id(), s["binaries"])
