"""What differs between operating systems; Windows behavior is checked by simulating it here and
for real by the Windows CI job."""

import json
import os
import threading
import time
from pathlib import Path

import pytest

from swfactory import system
from swfactory.output import FactoryError


def test_tool_command_from_path_or_override(monkeypatch):
    monkeypatch.delenv("SWFACTORY_ORCA", raising=False)
    monkeypatch.setattr(system, "WINDOWS", False)
    assert system.tool_command("orca", "SWFACTORY_ORCA") == ["orca"]
    monkeypatch.setenv("SWFACTORY_ORCA", "/opt/orca/bin/orca")
    assert system.tool_command("orca", "SWFACTORY_ORCA") == ["/opt/orca/bin/orca"]
    monkeypatch.setenv("SWFACTORY_ORCA", json.dumps(["python", "fake orca"]))
    assert system.tool_command("orca", "SWFACTORY_ORCA") == ["python", "fake orca"]


@pytest.mark.parametrize("value", ["[not json", "[]", "[1, 2]"])
def test_invalid_override_is_a_usage_error(monkeypatch, value):
    monkeypatch.setenv("SWFACTORY_ORCA", value)
    with pytest.raises(FactoryError) as exc:
        system.tool_command("orca", "SWFACTORY_ORCA")
    assert exc.value.code == "invalid_override"


def test_on_windows_the_native_exe_wins_over_a_cmd_shim(monkeypatch):
    monkeypatch.delenv("SWFACTORY_ORCA", raising=False)
    monkeypatch.setattr(system, "WINDOWS", True)
    found = {"orca.exe": r"C:\Orca\bin\orca.exe", "orca": r"C:\npm\orca.cmd"}
    monkeypatch.setattr(system.shutil, "which", found.get)
    assert system.tool_command("orca", "SWFACTORY_ORCA") == [r"C:\Orca\bin\orca.exe"]
    del found["orca.exe"]
    assert system.tool_command("orca", "SWFACTORY_ORCA") == [r"C:\npm\orca.cmd"]


@pytest.mark.parametrize("arg", ['say "hi"', "a & b", "50%", "line\nbreak", "a | b", "a > b"])
def test_batch_shims_never_get_text_cmd_would_reinterpret(arg):
    with pytest.raises(FactoryError) as exc:
        system.check_batch_arguments([r"C:\npm\orca.cmd"], ["worktree", "set", "--comment", arg])
    assert exc.value.code == "unsafe_batch_arguments"
    system.check_batch_arguments([r"C:\Orca\orca.exe"], ["--comment", arg])  # a real program is fine


def test_check_commands_on_posix_are_split_like_a_shell(monkeypatch):
    monkeypatch.setattr(system, "WINDOWS", False)
    assert system.command_line('python -c "print(1)" tests/x.py') == ["python", "-c", "print(1)", "tests/x.py"]


def test_check_commands_on_windows_keep_their_text(monkeypatch):
    monkeypatch.setattr(system, "WINDOWS", True)
    monkeypatch.setattr(system.shutil, "which", lambda name: r"C:\Program Files\Py\python.exe")
    line = system.command_line(r'python -c "print(1)" tests\x.py')
    assert line == r'"C:\Program Files\Py\python.exe" -c "print(1)" tests\x.py'  # backslashes kept
    with pytest.raises(ValueError):
        system.command_line("   ")


def test_same_path():
    assert system.same_path("/work/a/../repo", "/work/repo")
    assert not system.same_path("/work/repo", "/work/other")
    assert not system.same_path(None, "/work/repo")


def test_exclusive_lock_lets_one_holder_at_a_time(tmp_path):
    lock, inside, overlaps = tmp_path / "x.mutex", [0], []

    def hold():
        with system.exclusive_lock(lock):
            inside[0] += 1
            overlaps.append(inside[0])
            time.sleep(0.02)
            inside[0] -= 1

    threads = [threading.Thread(target=hold) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert overlaps == [1] * 5


def test_replace_retries_while_windows_says_the_file_is_busy(tmp_path, monkeypatch):
    monkeypatch.setattr(system, "WINDOWS", True)
    monkeypatch.setattr(system, "RETRY_SECONDS", 0)
    source, target = tmp_path / "new", tmp_path / "old"
    source.write_text("new")
    target.write_text("old")
    real, calls = os.replace, []

    def busy_twice(a, b):
        calls.append(1)
        if len(calls) <= 2:
            raise PermissionError("in use")
        real(a, b)

    monkeypatch.setattr(system.os, "replace", busy_twice)
    system.replace(source, target)
    assert target.read_text() == "new" and len(calls) == 3


def test_replace_does_not_hide_errors_elsewhere(tmp_path, monkeypatch):
    monkeypatch.setattr(system, "WINDOWS", False)
    monkeypatch.setattr(system.os, "replace", lambda a, b: (_ for _ in ()).throw(PermissionError("no")))
    with pytest.raises(PermissionError):
        system.replace(Path(tmp_path / "a"), Path(tmp_path / "b"))


def test_detached_process_options():
    options = system.detached()
    assert ("creationflags" in options) if system.WINDOWS else options == {"start_new_session": True}
