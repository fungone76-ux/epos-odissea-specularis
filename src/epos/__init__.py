"""epos — motore per RPG narrativi single player con LLM Game Master."""

from .resort_runtime_patches import install_resort_runtime_patches
from .resort_npc_action_patch import install_resort_npc_action_patch

install_resort_runtime_patches()
install_resort_npc_action_patch()

__version__ = "0.1.0"
