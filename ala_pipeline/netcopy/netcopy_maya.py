from pathlib import Path
from typing import List
import datetime

try:
    from PySide6 import QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtWidgets
    from shiboken2 import wrapInstance

import maya.cmds as cmds
import maya.OpenMayaUI as omui

from pipeline_utils.netcopy_abstract import NetCopy


class MayaNetCopy(NetCopy):
    def export_selection(self, export_name: str, storage_path: Path) -> bool:
        if not storage_path.exists():
            QtWidgets.QMessageBox.warning(
                None,
                "Export Failed",
                "Invalid storage path provided."
            )
            return False
        selection = cmds.ls(selection=True)
        if not selection:
            QtWidgets.QMessageBox.warning(
                None,
                "Export Failed",
                "No objects selected for export."
            )
            return False
        elif not export_name:
            QtWidgets.QMessageBox.warning(
                None,
                "Export Failed",
                "Please provide a name for the export."
            )
            return False
        
        scene_name = cmds.file(q=True, sn=True)
        if not scene_name:
            scene_name = "untitled"

        scene_base = Path(scene_name).stem

        export_path = storage_path / f"{scene_base}_{export_name}.mb"

        if export_path.exists():
            QtWidgets.QMessageBox.warning(
                None,
                "Export Failed",
                f"Export path already exists: {export_path}"
            )
            return False

        try:
            cmds.file(str(export_path), force=True, type="mayaBinary", exportSelected=True)
            QtWidgets.QMessageBox.information(
                None,
                "Export Succeeded",
                f"Exported selection to: {export_path}"
            )
            return True
        except RuntimeError as e:
            if Path(scene_name).suffix == ".ma":
                optimise = self.create_optimise_dialog()
                if optimise:
                    unknown_nodes = cmds.ls(type='unknown')
                    if unknown_nodes:
                        cmds.delete(unknown_nodes)
                    print(f"Deleted {len(unknown_nodes)} unknown nodes.")
                    try:
                        cmds.file(str(export_path), force=True, type="mayaBinary", exportSelected=True)
                        QtWidgets.QMessageBox.information(
                                None,
                                "Export Succeeded",
                                f"Exported selection to: {export_path}"
                        )
                        return True
                    except RuntimeError as e2:
                        QtWidgets.QMessageBox.warning(
                            None,
                            "Export Failed",
                            f"Unable to export selection after optimisation.\n\n{e2}"
                        )
                        return False
            QtWidgets.QMessageBox.warning(
                None,
                "Export Failed",
                f"Failed to export selection.\n\n{e}"
            )
            return False

    def import_copy(self, import_path: Path) -> bool:
        if not import_path.exists():
            QtWidgets.QMessageBox.warning(
                None,
                "Import Failed",
                f"Import path does not exist: {import_path}"
            )
            return False

        try:
            cmds.file(str(import_path), i=True)
            print(f"Imported selection from: {import_path}")
            return True
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                None,
                "Import Failed",
                f"Failed to import file.\n\n{e}"
            )
            return False

    def get_all_copies(self, storage_path: Path) -> dict[Path, str]:
        """Public interface: Retrieve all available copies with their timestamps."""
        file_exts = ["*.mb", "*.ma"]

        copies = []
        for ext in file_exts:
            copies.extend(storage_path.glob(ext))

        copies_and_times = {}

        for copy in copies:
            timestamp = copy.stat().st_mtime
            copies_and_times[copy] = timestamp

        copies_and_times = dict(sorted(copies_and_times.items(), key=lambda item: item[1], reverse=True))

        for copy, date in copies_and_times.items():
            m_date_time = datetime.datetime.fromtimestamp(date)
            formatted_time = m_date_time.strftime("%Y-%m-%d %H:%M:%S")
            copies_and_times[copy] = formatted_time

        return copies_and_times

    def get_main_window(self) -> QtWidgets.QWidget:
        """Public interface: Get the main window instance."""
        main_window_ptr = omui.MQtUtil.mainWindow()
        return wrapInstance(int(main_window_ptr), QtWidgets.QWidget)

    def create_optimise_dialog(self) -> bool:
        reply = QtWidgets.QMessageBox.question(None, 'Error Exporting', 
                                 "Do you want to try optimising the scene by deleting unknown nodes? This action is not undoable!",
                                 QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            return True
        else:
            return False