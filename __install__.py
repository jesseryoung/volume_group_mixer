from streamcontroller_plugin_tools.installation_helpers import create_venv
from os.path import join, abspath, dirname

dirname = dirname(abspath(__file__))
create_venv(
    path=join(dirname, "backend", ".venv"),
    path_to_requirements_txt=join(dirname, "backend", "requirements.txt"),
)
