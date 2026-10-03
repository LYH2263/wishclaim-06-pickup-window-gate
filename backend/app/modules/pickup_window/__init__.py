"""取货时间窗：判定（check）、快照（snapshot）、投影（projection）。"""
from app.modules.pickup_window.check import (
    DAY_NAMES,
    Window,
    WindowError,
    is_open,
    parse_window,
    to_dict,
)
from app.modules.pickup_window.snapshot import (
    DEFAULT_WINDOW,
    default_window,
    resolve_snapshot,
    snapshot_for_create,
)
from app.modules.pickup_window.projection import attach, project, window_label

__all__ = [
    "DAY_NAMES", "Window", "WindowError", "is_open", "parse_window", "to_dict",
    "DEFAULT_WINDOW", "default_window", "resolve_snapshot", "snapshot_for_create",
    "attach", "project", "window_label",
]
