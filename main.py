import os

from src.backend.PluginManager.ActionHolder import ActionHolder
from src.backend.PluginManager.PluginBase import PluginBase

from .actions.VolumeGroupMixer.VolumeGroupMixer import VolumeGroupMixerAction


class VolumeGroupMixerPlugin(PluginBase):
    def __init__(self) -> None:
        super().__init__()

        self.action_holder = ActionHolder(
            plugin_base=self,
            action_base=VolumeGroupMixerAction,
            action_id="net_jesseyoung_volumegroupmixer::VolumeGroupMixer",
            action_name="Volume Group Mixer",
        )
        self.add_action_holder(self.action_holder)

        self.register(
            plugin_name="Volume Group Mixer",
            github_repo="https://github.com/jesseryoung/volume_group_mixer",
            plugin_version="0.0.1",
            app_version="1.5.0",
        )

        venv = os.path.join(self.PATH, "backend", ".venv")
        if os.path.exists(venv):
            self.launch_backend(
                backend_path=os.path.join(self.PATH, "backend", "backend.py"),
                venv_path=venv,
                open_in_terminal=False,
            )
