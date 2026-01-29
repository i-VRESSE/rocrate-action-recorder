"""RO-Crate action recorder for CLI invocations."""

from rocrate_action_recorder.adapters.argparse import record_with_argparse
from rocrate_action_recorder.core import (
    IOArgumentPath,
    Program,
    record,
    playback,
)

__all__ = [
    "record_with_argparse",
    "record",
    "playback",
    "Program",
    "IOArgumentPath",
]
