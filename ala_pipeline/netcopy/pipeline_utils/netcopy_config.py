from pathlib import Path
from dataclasses import dataclass, field

@dataclass(frozen=True)
class NetCopyConfig:
    """
    Immutable configuration for netcopy operations.
    """
    storage_path: Path

