"""RO-Crate action recorder for CLI invocations."""

from collections.abc import Callable
from typing import Any

from rocrate_action_recorder.adapters.argparse import (
    IOArgumentNames,
    record_argparse,
    recorded_argparse,
)

try:
    from rocrate_action_recorder.adapters.click import (
        IOArgumentNames as ClickIOArgumentNames,
    )
    from rocrate_action_recorder.adapters.click import (
        record_click,
        recorded_click,
    )
except ModuleNotFoundError as exc:
    if exc.name != "click":
        raise

    def _missing_click_extra(*_: Any, **__: Any) -> Any:
        raise ModuleNotFoundError(
            "Click support requires the optional dependency. Install with 'pip install rocrate-action-recorder[click]'."
        )

    record_click: Callable[..., Any] = _missing_click_extra
    recorded_click: Callable[..., Any] = _missing_click_extra
    ClickIOArgumentNames = None
from rocrate_action_recorder.core import (
    IOArgumentPath,
    IOArgumentPaths,
    Program,
    playback,
    record,
)

__all__ = [
    "record_argparse",
    "recorded_argparse",
    "record_click",
    "recorded_click",
    "record",
    "playback",
    "Program",
    "IOArgumentPath",
    "IOArgumentPaths",
    "IOArgumentNames",
    "ClickIOArgumentNames",
]
