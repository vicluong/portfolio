from pathlib import Path
import datetime

try:
    from PySide6 import QtWidgets
except ImportError:
    from PySide2 import QtWidgets

import hou

from pipeline_utils.netcopy_abstract import NetCopy


class HoudiniNetCopy(NetCopy):
    def export_selection(self, export_name: str, storage_path: Path) -> bool:
        selected = hou.selectedNodes()
        print(f"Selected nodes: {[n.name() for n in selected]}")

        if not selected:
            hou.ui.displayMessage("No node is selected for export.", severity=hou.severityType.Warning)
            return False
        elif not export_name.strip():
            hou.ui.displayMessage("Please provide a name for the export.", severity=hou.severityType.Warning)
            return False
        
        # Ensure all selected nodes share the same parent
        parent = selected[0].parent()
        if any(n.parent() != parent for n in selected):
            hou.ui.displayMessage("Please select nodes under the same parent network.", severity=hou.severityType.Warning)
            return False
        
        scene_name = hou.hipFile.basename()
        scene_name_base = scene_name.rsplit('.', 1)[0]
        export_path = storage_path / f"{scene_name_base}_{export_name}.cpio"

        if export_path.exists():
            hou.ui.displayMessage(f"Export path already exists: {export_path}", severity=hou.severityType.Warning)
            return False

        parent.saveItemsToFile(selected, str(export_path))
        hou.ui.displayMessage(f"Exported selection to: {export_path}")
        
        return True

    def import_copy(self, import_path: Path) -> bool:
        pane = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)

        if pane is not None:
            current_network = pane.pwd()
        else:
            current_network = hou.node("/obj")

        if not import_path.exists():
            hou.ui.displayMessage(f"Import path does not exist: {import_path}", severity=hou.severityType.Warning)
            return False

        try:
            before_items = set(current_network.allItems())

            with hou.undos.group("NetCopy Import"):
                current_network.loadItemsFromFile(str(import_path))

            print(f"Imported selection from: {import_path}")
            return True

        except hou.OperationFailed as exc:
            try:
                hou.undos.performUndo()
            except hou.OperationFailed:
                pass

            after_undo_items = set(current_network.allItems())

            # If hou.undo() fully undid all nodes
            if after_undo_items == before_items:
                hou.ui.displayMessage(
                    f"Import failed and was fully undone.\n\n{exc}",
                    severity=hou.severityType.Warning,
                )
                return False

            # If hou,undo() left behind new items, select these new items
            new_items = tuple(after_undo_items - before_items)

            hou.clearAllSelected()

            for item in new_items:
                item.setSelected(True)

            hou.ui.displayMessage(
                f"Import failed. Undo did not fully restore the network.\n"
                f"The following items have been created.\n"
                f"{new_items}.\n\n"
                f"Please review the selected items.\n\n{exc}",
                severity=hou.severityType.Warning,
            )

            return False

    def get_all_copies(self, storage_path: Path) -> dict[Path, str]:
        file_exts = ["*.cpio"]

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
        return hou.qt.mainWindow()
