import os

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PluginManager.ActionBase import ActionBase


class VolumeGroupMixerAction(ActionBase):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._binary_rows: list[Adw.EntryRow] = []
        self._registered = False

    def _group_id(self) -> str:
        return str(self.input_ident)

    def _binaries(self) -> list[str]:
        return self.get_settings().get("binaries", [])

    def _step(self) -> float:
        return self.get_settings().get("step_size", 5) / 100.0

    def _ensure_registered(self) -> None:
        if self._registered:
            return
        b = self.plugin_base.backend
        if b is None:
            return
        b.exposed_register_group(self._group_id(), self._binaries())
        self._registered = True

    def on_ready(self) -> None:
        self._ensure_registered()
        self._refresh_display()

    def event_callback(self, event, data: dict = None) -> None:
        b = self.plugin_base.backend
        if b is None:
            return
        if event == Input.Dial.Events.TURN_CW:
            b.exposed_adjust_volume(self._group_id(), self._step())
        elif event == Input.Dial.Events.TURN_CCW:
            b.exposed_adjust_volume(self._group_id(), -self._step())
        elif event == Input.Dial.Events.SHORT_UP:
            b.exposed_toggle_mute(self._group_id())
        self._refresh_display()

    def on_tick(self) -> None:
        self._ensure_registered()
        self._refresh_display()

    def _refresh_display(self) -> None:
        b = self.plugin_base.backend
        if b is None:
            return
        s = self.get_settings()
        vol, all_muted = b.exposed_get_group_state(self._group_id())
        self.set_top_label(s.get("group_name", ""))
        if vol is None:
            self.set_bottom_label("???")
        else:
            self.set_bottom_label(f"{'M ' if all_muted else ''}{round(vol * 100)}%")
        icon = s.get("icon_path", "")
        if icon and os.path.exists(icon):
            self.set_media(media_path=icon, size=0.75)

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

        icon_row = Adw.ActionRow(title="Icon")
        icon_btn = Gtk.Button(label="Choose…")
        icon_btn.set_valign(Gtk.Align.CENTER)
        icon_btn.connect("clicked", self._on_icon_clicked)
        icon_row.add_suffix(icon_btn)
        rows.append(icon_row)

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

        running_group = Adw.PreferencesGroup(title="Running apps")
        b = self.plugin_base.backend
        if b is not None:
            for binary in b.exposed_get_running_binaries():
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

    def _on_icon_clicked(self, btn) -> None:
        dialog = Gtk.FileDialog()
        f = Gtk.FileFilter()
        f.add_pixbuf_formats()
        dialog.set_default_filter(f)
        dialog.open(None, None, self._on_icon_chosen)

    def _on_icon_chosen(self, dialog, result) -> None:
        try:
            f = dialog.open_finish(result)
            path = f.get_path()
        except Exception:
            return
        s = self.get_settings()
        s["icon_path"] = path
        self.set_settings(s)
        self._refresh_display()

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
        b = self.plugin_base.backend
        if b is not None:
            b.exposed_register_group(self._group_id(), s["binaries"])
