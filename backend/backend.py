import threading

import pulsectl
from streamcontroller_plugin_tools import BackendBase


class Backend(BackendBase):
    def __init__(self) -> None:
        self._groups: dict[str, list[str]] = {}
        self._group_volume: dict[str, float | None] = {}
        self._lock = threading.Lock()
        self._pulse = pulsectl.Pulse("volume-group-mixer")
        super().__init__()

    def _pulse_op(self, fn):
        try:
            return fn()
        except Exception:
            self._pulse = pulsectl.Pulse("volume-group-mixer")
            return fn()

    def _sink_inputs_for_group(self, group_id: str, all_sis: list | None = None) -> list:
        binaries = self._groups.get(group_id, [])
        sis = all_sis if all_sis is not None else self._pulse_op(lambda: self._pulse.sink_input_list())
        return [si for si in sis if si.proplist.get("application.process.binary") in binaries]

    def _get_vol(self, si) -> tuple[float, bool]:
        return (self._pulse_op(lambda: self._pulse.volume_get_all_chans(si)), bool(si.mute))

    def _set_vol(self, si, vol: float) -> None:
        self._pulse_op(lambda: self._pulse.volume_set_all_chans(si, vol))

    def _resolve_initial_volume(self, group_id: str) -> None:
        sis = self._sink_inputs_for_group(group_id)
        if not sis:
            return
        min_vol = min(self._get_vol(si)[0] for si in sis)
        self._group_volume[group_id] = min_vol
        for si in sis:
            self._set_vol(si, min_vol)

    def exposed_register_group(self, group_id: str, binaries: list[str]) -> None:
        with self._lock:
            self._groups[group_id] = list(binaries)
            tracked = self._group_volume.get(group_id)
            if tracked is not None:
                for si in self._sink_inputs_for_group(group_id):
                    self._set_vol(si, tracked)
            else:
                self._group_volume[group_id] = None
                self._resolve_initial_volume(group_id)

    def exposed_adjust_volume(self, group_id: str, delta: float) -> None:
        with self._lock:
            all_sis = self._pulse_op(lambda: self._pulse.sink_input_list())
            sis = self._sink_inputs_for_group(group_id, all_sis)
            if not sis:
                return
            vols = [self._get_vol(si)[0] for si in sis]
            tracked = self._group_volume.get(group_id)
            base = tracked if tracked is not None and (max(vols) - min(vols) <= 0.005) else min(vols)
            new_vol = max(0.0, min(1.0, base + delta))
            self._group_volume[group_id] = new_vol
            for si in sis:
                self._set_vol(si, new_vol)

    def exposed_toggle_mute(self, group_id: str) -> None:
        with self._lock:
            all_sis = self._pulse_op(lambda: self._pulse.sink_input_list())
            sis = self._sink_inputs_for_group(group_id, all_sis)
            if not sis:
                return
            new_mute = not all(self._get_vol(si)[1] for si in sis)
            for si in sis:
                self._pulse_op(lambda s=si: self._pulse.mute(s, new_mute))

    def exposed_get_group_state(self, group_id: str) -> tuple[float | None, bool]:
        with self._lock:
            sis = self._sink_inputs_for_group(group_id)
            if not sis:
                return (self._group_volume.get(group_id), False)
            states = [self._get_vol(si) for si in sis]
            return (min(s[0] for s in states), all(s[1] for s in states))

    def exposed_get_running_binaries(self) -> list[str]:
        with self._lock:
            return sorted({
                si.proplist.get("application.process.binary")
                for si in self._pulse_op(lambda: self._pulse.sink_input_list())
                if si.proplist.get("application.process.binary")
            })


backend = Backend()
