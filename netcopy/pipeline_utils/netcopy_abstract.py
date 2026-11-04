from pathlib import Path
from typing import List
from abc import ABC, abstractmethod

try:
    from PySide6 import QtWidgets
except ImportError:
    from PySide2 import QtWidgets


class NetCopy(ABC):
    @abstractmethod
    def export_selection(self, export_name: str, storage_path: Path) -> bool:
        pass

    @abstractmethod
    def import_copy(self, import_path: Path) -> bool:
        pass

    @abstractmethod
    def get_all_copies(self, storage_path: Path) -> List[tuple[Path, str]]:
        pass

    @abstractmethod
    def get_main_window(self) -> QtWidgets.QWidget:
        pass
