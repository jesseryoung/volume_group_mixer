import os
import threading

import gi
gi.require_version('Wp', '0.5')
gi.require_version('GLib', '2.0')
from gi.repository import GLib, Wp
from loguru import logger as log
from streamcontroller_plugin_tools import BackendBase

log.add(os.path.join(os.path.dirname(__file__), "backend.log"), level="DEBUG", rotation="1 MB")


class Backend(BackendBase):
    def __init__(self) -> None:
        self._nodes: dict[int, str] = {}
        self._groups: dict[str, list[str]] = {}
        self._group_volume: dict[str, float | None] = {}
        self._group_state: dict[str, tuple[float | None, bool]] = {}
        self._mixer_api = None
        self._loop: GLib.MainLoop | None = None
        self._core: Wp.Core | None = None
        self._om: Wp.ObjectManager | None = None

        log.info("Backend starting")
        self._start_wireplumber()
        super().__init__()
        log.info("Backend ready")

    def _start_wireplumber(self) -> None:
        log.info("Connecting to PipeWire")
        Wp.init(Wp.InitFlags.ALL)
        self._loop = GLib.MainLoop()
        self._core = Wp.Core.new(self._loop.get_context(), None)
        if not self._core.connect():
            raise RuntimeError("Cannot connect to PipeWire")
        log.info("Connected to PipeWire, loading plugins")

        pending = {"n": 2}

        def on_loaded(core, result, _):
            try:
                core.load_component_finish(result)
            except Exception as e:
                log.error(f"Plugin load failed: {e}")
                return
            pending["n"] -= 1
            log.info(f"Plugin loaded, {pending['n']} remaining")
            if pending["n"] == 0:
                self._on_plugins_ready()

        self._core.load_component(
            "libwireplumber-module-mixer-api", "module", None, None, None, on_loaded, None
        )
        self._core.load_component(
            "libwireplumber-module-default-nodes-api", "module", None, None, None, on_loaded, None
        )
        threading.Thread(target=self._loop.run, daemon=True, name="wp-loop").start()

    def _on_plugins_ready(self) -> None:
        log.info("Plugins ready, setting up mixer API and object manager")
        self._mixer_api = Wp.Plugin.find(self._core, "mixer-api")
        self._mixer_api.set_property("scale", 1)  # 1 = CUBIC scale
        self._mixer_api.connect("changed", self._on_volume_changed)

        om = Wp.ObjectManager.new()
        om.add_interest_full(Wp.ObjectInterest.new_type(Wp.Node))
        om.request_object_features(Wp.Node, Wp.ProxyFeatures.PROXY_FEATURE_BOUND | Wp.ProxyFeatures.PIPEWIRE_OBJECT_FEATURE_INFO)
        om.connect("object-added", self._on_node_added)
        om.connect("object-removed", self._on_node_removed)
        self._om = om
        self._core.install_object_manager(om)

    def _on_node_added(self, _om, node: Wp.Node) -> None:
        props = Wp.PipewireObject.get_properties(node)
        if props.get("media.class") != "Stream/Output/Audio":
            return
        binary = props.get("application.process.binary")
        if not binary:
            return
        node_id = node.get_bound_id()
        log.info(f"Node added: {binary} (id={node_id})")
        self._nodes[node_id] = binary
        for group_id, binaries in self._groups.items():
            if binary not in binaries:
                continue
            vol = self._group_volume.get(group_id)
            if vol is not None:
                self._set_vol(node_id, vol)
            else:
                self._resolve_initial_volume(group_id)
        self._update_all_caches()

    def _on_node_removed(self, _om, node: Wp.Node) -> None:
        node_id = node.get_bound_id()
        binary = self._nodes.pop(node_id, None)
        log.info(f"Node removed: {binary} (id={node_id})")
        self._update_all_caches()

    def _on_volume_changed(self, _api, node_id: int) -> None:
        self._update_all_caches()

    def _node_ids_for_group(self, group_id: str) -> list[int]:
        binaries = self._groups.get(group_id, [])
        return [nid for nid, b in self._nodes.items() if b in binaries]

    def _get_vol(self, node_id: int) -> tuple[float, bool] | None:
        if self._mixer_api is None:
            return None
        d = self._mixer_api.emit("get-volume", node_id)
        if d is None:
            return None
        return (float(d["volume"]), bool(d["mute"]))

    def _set_vol(self, node_id: int, volume: float) -> None:
        state = self._get_vol(node_id)
        if state is None:
            return
        self._mixer_api.emit("set-volume", node_id, {
            "volume": GLib.Variant("d", max(0.0, min(1.0, volume))),
            "mute":   GLib.Variant("b", state[1]),
        })

    def _resolve_initial_volume(self, group_id: str) -> None:
        node_ids = self._node_ids_for_group(group_id)
        states = [self._get_vol(nid) for nid in node_ids]
        states = [s for s in states if s is not None]
        if not states:
            return
        min_vol = min(s[0] for s in states)
        log.info(f"Resolved initial volume for group {group_id!r}: {round(min_vol * 100)}%")
        self._group_volume[group_id] = min_vol
        for nid in node_ids:
            self._set_vol(nid, min_vol)

    def _update_all_caches(self) -> None:
        for group_id in self._groups:
            node_ids = self._node_ids_for_group(group_id)
            states = [self._get_vol(nid) for nid in node_ids]
            states = [s for s in states if s is not None]
            if not states:
                self._group_state[group_id] = (self._group_volume.get(group_id), False)
            else:
                self._group_state[group_id] = (
                    min(s[0] for s in states),
                    all(s[1] for s in states),
                )

    def exposed_register_group(self, group_id: str, binaries: list[str]) -> None:
        log.info(f"Registering group {group_id!r} with binaries {binaries}")
        self._groups[group_id] = list(binaries)
        if group_id not in self._group_volume:
            self._group_volume[group_id] = None

        def _work():
            self._resolve_initial_volume(group_id)
            self._update_all_caches()
            return False

        GLib.idle_add(_work)

    def exposed_adjust_volume(self, group_id: str, delta: float) -> None:
        done = threading.Event()

        def _work():
            node_ids = self._node_ids_for_group(group_id)
            states = {nid: self._get_vol(nid) for nid in node_ids}
            states = {nid: s for nid, s in states.items() if s is not None}
            if states:
                tracked = self._group_volume.get(group_id)
                volumes = [s[0] for s in states.values()]
                if tracked is not None and (max(volumes) - min(volumes) <= 0.005):
                    base = tracked
                else:
                    base = min(volumes)
                new_vol = max(0.0, min(1.0, base + delta))
                log.info(f"Adjusting group {group_id!r}: {round(base * 100)}% -> {round(new_vol * 100)}%")
                self._group_volume[group_id] = new_vol
                for nid in node_ids:
                    self._set_vol(nid, new_vol)
            self._update_all_caches()
            done.set()
            return False

        GLib.idle_add(_work)
        done.wait(timeout=0.2)

    def exposed_toggle_mute(self, group_id: str) -> None:
        def _work():
            node_ids = self._node_ids_for_group(group_id)
            states = [self._get_vol(nid) for nid in node_ids]
            states = [s for s in states if s is not None]
            if not states:
                return False
            new_mute = not all(s[1] for s in states)
            log.info(f"Toggling mute for group {group_id!r}: mute={new_mute}")
            for nid in node_ids:
                s = self._get_vol(nid)
                if s is None:
                    continue
                self._mixer_api.emit("set-volume", nid, {
                    "volume": GLib.Variant("d", s[0]),
                    "mute":   GLib.Variant("b", new_mute),
                })
            self._update_all_caches()
            return False

        GLib.idle_add(_work)

    def exposed_get_group_state(self, group_id: str) -> tuple[float | None, bool]:
        return self._group_state.get(group_id, (None, False))

    def exposed_get_running_binaries(self) -> list[str]:
        return sorted(set(self._nodes.values()))


backend = Backend()
