"""RO-Crate action recorder for CLI invocations."""

from rocrate_action_recorder.adapters.argparse import record_with_argparse
from rocrate_action_recorder.core import (
    IOArgument,
    IOs,
    Info,
    Program,
    record,
)

__all__ = [
    "record_with_argparse",
    "record",
    "Program",
    "IOArgument",
    "Info",
    "IOs",
]
