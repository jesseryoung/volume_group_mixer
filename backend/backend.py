import os
import threading

import pulsectl
from loguru import logger
from streamcontroller_plugin_tools import BackendBase

logger.add(os.path.join(os.path.dirname(__file__), "backend.log"))


class Backend(BackendBase):
    def __init__(self) -> None:
        self._groups: dict[str, list[str]] = {}
        self._group_volume: dict[str, float | None] = {}
        self._group_state: dict[str, tuple[float | None, bool]] = {}
        self._callbacks: dict[str, object] = {}
        self._lock = threading.Lock()
        self._pulse = pulsectl.Pulse("volume-group-mixer")
        threading.Thread(target=self._event_loop, daemon=True).start()
        logger.info("Backend initialized")
        super().__init__()

    def _event_loop(self) -> None:
        new_indices: list[int] = []

        def on_event(ev) -> None:
            if ev.facility == pulsectl.PulseEventFacilityEnum.sink_input and ev.t == pulsectl.PulseEventTypeEnum.new:
                new_indices.append(ev.index)
            pulse.event_listen_stop()

        with pulsectl.Pulse("volume-group-mixer-events") as pulse:
            pulse.event_mask_set("sink_input")
            pulse.event_callback_set(on_event)
            while True:
                new_indices.clear()
                pulse.event_listen(timeout=5)
                for index in list(new_indices):
                    self._on_new_sink_input(index)

    def _on_new_sink_input(self, index: int) -> None:
        callbacks_to_call = []
        with self._lock:
            si = next((s for s in self._pulse.sink_input_list() if s.index == index), None)
            if si is None:
                return
            binary = si.proplist.get("application.process.binary")
            if not binary:
                return
            for group_id, binaries in self._groups.items():
                if binary in binaries:
                    tracked = self._group_volume.get(group_id)
                    if tracked is not None:
                        self._set_vol(si, tracked)
                        logger.info("New sink input {} ({}): snapped to group {} volume {:.2f}", index, binary, group_id, tracked)
                    if group_id in self._callbacks:
                        callbacks_to_call.append(self._callbacks[group_id])
        for cb in callbacks_to_call:
            try:
                cb()
            except Exception:
                pass

    def _sink_inputs_for_group(self, group_id: str) -> list:
        binaries = self._groups.get(group_id, [])
        return [si for si in self._pulse.sink_input_list()
                if si.proplist.get("application.process.binary") in binaries]

    def _get_vol(self, si) -> tuple[float, bool]:
        return (self._pulse.volume_get_all_chans(si), bool(si.mute))

    def _set_vol(self, si, vol: float) -> None:
        self._pulse.volume_set_all_chans(si, max(0.0, min(1.0, vol)))

    def _resolve_initial_volume(self, group_id: str) -> None:
        sis = self._sink_inputs_for_group(group_id)
        if not sis:
            return
        min_vol = min(self._get_vol(si)[0] for si in sis)
        self._group_volume[group_id] = min_vol
        for si in sis:
            self._set_vol(si, min_vol)

    def _update_cache(self, group_id: str) -> None:
        sis = self._sink_inputs_for_group(group_id)
        if not sis:
            self._group_state[group_id] = (self._group_volume.get(group_id), False)
            return
        states = [self._get_vol(si) for si in sis]
        self._group_state[group_id] = (
            min(s[0] for s in states),
            all(s[1] for s in states),
        )

    def exposed_register_group(self, group_id: str, binaries: list[str], on_state_change=None) -> None:
        with self._lock:
            self._groups[group_id] = list(binaries)
            if on_state_change is not None:
                self._callbacks[group_id] = on_state_change
            if group_id not in self._group_volume:
                self._group_volume[group_id] = None
                self._resolve_initial_volume(group_id)
                logger.info("Registered group {} with binaries {}, initial volume={}", group_id, binaries, self._group_volume[group_id])
            else:
                logger.info("Updated group {} binaries={}", group_id, binaries)
            self._update_cache(group_id)

    def exposed_adjust_volume(self, group_id: str, delta: float) -> None:
        with self._lock:
            sis = self._sink_inputs_for_group(group_id)
            if not sis:
                return
            vols = [self._get_vol(si)[0] for si in sis]
            tracked = self._group_volume.get(group_id)
            base = tracked if tracked is not None and (max(vols) - min(vols) <= 0.005) else min(vols)
            new_vol = max(0.0, min(1.0, base + delta))
            self._group_volume[group_id] = new_vol
            for si in sis:
                self._set_vol(si, new_vol)
            self._update_cache(group_id)

    def exposed_toggle_mute(self, group_id: str) -> None:
        with self._lock:
            sis = self._sink_inputs_for_group(group_id)
            if not sis:
                return
            new_mute = not all(self._get_vol(si)[1] for si in sis)
            for si in sis:
                self._pulse.mute(si, new_mute)
            self._update_cache(group_id)

    def exposed_get_group_state(self, group_id: str) -> tuple[float | None, bool]:
        with self._lock:
            self._update_cache(group_id)
            return self._group_state.get(group_id, (None, False))

    def exposed_get_running_binaries(self) -> list[str]:
        with self._lock:
            return sorted({
                si.proplist.get("application.process.binary")
                for si in self._pulse.sink_input_list()
                if si.proplist.get("application.process.binary")
            })


backend = Backend()
