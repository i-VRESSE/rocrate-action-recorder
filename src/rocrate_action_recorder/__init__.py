"""RO-Crate action recorder for CLI invocations."""

from rocrate_action_recorder.adapters.argparse import (
    record_argparse,
    recorded_argparse,
    IOArgumentNames,
)
from rocrate_action_recorder.core import (
    IOArgumentPath,
    IOArgumentPaths,
    Program,
    record,
    playback,
)

__all__ = [
    "record_argparse",
    "recorded_argparse",
    "record",
    "playback",
    "Program",
    "IOArgumentPath",
    "IOArgumentPaths",
    "IOArgumentNames",
]
