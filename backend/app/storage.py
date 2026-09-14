"""How much room the library has left, asked of the kernel.

The mockup labels this figure "ZFS Pool". That is a filesystem question rather
than a ZFS one, and `statvfs` answers it the same way on ext4, on a bind mount
and on a pool, so nothing here knows or cares which it is running on.
"""

import shutil
from pathlib import Path
from typing import Any


def usage(path: Path) -> dict[str, Any]:
    """Total, used and free bytes of the filesystem holding `path`.

    `used` is the filesystem's, not the library folder's: measuring the folder
    means walking every file, which is not something an above-the-fold request
    can afford on a spinning-disk NAS.

    An unmounted or not-yet-created library path is an ordinary state on a
    homelab box, so it is reported rather than raised — a dashboard that 500s
    because a volume is missing hides the nine things that are fine.
    """
    try:
        total, used, free = shutil.disk_usage(path)
    except OSError as exc:
        return {"path": str(path), "available": False, "detail": str(exc)}

    return {
        "path": str(path),
        "available": True,
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "used_pct": round(100 * used / total, 1) if total else 0.0,
    }
