from datetime import datetime
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Software:
    name: str
    version: str
    description: str | None = None
    url: str | None = None
    license: str | None = None

@dataclass
class File:
    path: Path
    size: int
    mime_type: str
    description: str | None = None

@dataclass
class Directory:
    path: Path
    description: str | None = None

@dataclass
class Action:
    command:str
    agent:str
    end_time: datetime
    start_time: datetime
    software: Software # instrument
    input_files: list[File]  # object
    output_files: list[File] # result
    input_directories: list[Directory] # object
    output_directories: list[Directory] # result
    description: str | None = None
    dataset_license: str = 'CC-BY-4.0'

def record(action: Action) -> None:
    # Placeholder for action recording logic
    pass