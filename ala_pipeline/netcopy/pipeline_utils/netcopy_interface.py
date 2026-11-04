from pathlib import Path

from pipeline_utils.netcopy_config import NetCopyConfig
from pipeline_utils.netcopy_ui import NetCopyDialog


class NetCopyInterface:
    """Interface for Netcopy operations."""
    storage_path = Path("/mnt/ala/mav/2026/jobs/s126/library/netcopy/")

    def __init__(self, dcc: str):
        self._config = NetCopyConfig(
            storage_path = self.storage_path
        )

        dcc_key = dcc.lower()
        self._netcopy = self._get_netcopy(dcc_key)

        if not self._netcopy:
            raise ModuleNotFoundError("The specificed DCC could not be imported properly.")

    def create_ui(self):
        NetCopyDialog.show_dialog(self._netcopy, self._config.storage_path)

    def _get_netcopy(self, dcc: str):
        if dcc == "maya":
            from  maya_pipeline.ala_tools.netcopy_maya import MayaNetCopy
            return MayaNetCopy()
        elif dcc == "houdini":
            from houdini_pipeline.houdini_tools.netcopy_houdini import HoudiniNetCopy
            return HoudiniNetCopy()
        elif dcc == "nuke":
            from nuke_pipeline.netcopy_nuke import NukeNetCopy
            return NukeNetCopy()
        elif dcc == "katana":
            from katana_pipeline.ALA_Utils.NetcopyKatana import KatanaNetCopy
            return KatanaNetCopy()
        else:
            raise ValueError(f"DCC '{dcc}' is not supported by NetCopy.")
