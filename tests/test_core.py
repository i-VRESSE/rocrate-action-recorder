import importlib.metadata
from pathlib import Path

from rocrate_action_recorder.core import detect_software_version


def test_detect_software_version_unknown():
    result = detect_software_version("non_existent_script_12345")
    assert result == ""

def test_detect_software_version_scriptsameaspackage():
    result = detect_software_version("pytest")
    expected = importlib.metadata.version('pytest')
    assert result == expected

def test_detect_software_version_localscript(tmp_path: Path):
    # Create a dummy executable file
    exe_file = tmp_path / "dummy_executable.py"
    exe_file.write_text("#!/usr/bin/env python\nimport sys\nif '--version' in sys.argv:\n    print('v4.2')\n")
    exe_file.chmod(0o755)
    
    result = detect_software_version(str(exe_file))
    assert result == "v4.2"

def test_detect_software_version_localscriptstripped(tmp_path: Path):
    # Create a dummy executable file
    exe_file = tmp_path / "dummy_executable.py"
    exe_file.write_text("#!/usr/bin/env python\nimport sys\nif '--version' in sys.argv:\n    print('dummy_executable.py v4.2')\n")
    exe_file.chmod(0o755)
    
    result = detect_software_version(str(exe_file))
    assert result == "v4.2"

def test_detect_software_version_scriptinpath():
    # `rocrate-validator` script at `.venv/bin/rocrate-validator` 
    # is from `roc-validator` package so cannot use importlib
    result = detect_software_version("rocrate-validator")
    expected = importlib.metadata.version('roc-validator')
    assert expected in result