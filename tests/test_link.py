"""`install-cli` links with a symlink, and writes a small script where Windows refuses one."""

import os
import shlex
import shutil
import subprocess

import pytest

from agentltl_codex import cli


def test_a_symlink_where_allowed(tmp_path):
    target = tmp_path / "agentltl"
    target.write_text("#!/bin/sh\n")
    cli._link(str(target), str(tmp_path / "link"))
    assert os.path.islink(tmp_path / "link")
    assert cli._links_to(str(tmp_path / "link"), str(target))


def test_a_script_where_symlinks_are_refused(tmp_path, monkeypatch):
    def refuse(*args):
        raise OSError("A required privilege is not held by the client")

    monkeypatch.setattr(os, "symlink", refuse)
    target = tmp_path / "agentltl"
    target.write_text("#!/bin/sh\n")
    link = tmp_path / "link"
    cli._link(str(target), str(link))
    assert not os.path.islink(link)
    assert link.read_text().splitlines()[0] == "#!/usr/bin/env bash"
    assert link.read_text().endswith(f"exec {shlex.quote(target.as_posix())} \"$@\"\n")
    assert os.access(link, os.X_OK)
    assert cli._links_to(str(link), str(target))
    assert not cli._links_to(str(link), str(tmp_path / "other"))


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_the_script_runs_a_target_whose_path_has_shell_characters(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "symlink", lambda *a: (_ for _ in ()).throw(OSError("no privilege")))
    folder = tmp_path / "plug-$HOME-`touch pwned`-$(touch pwned2)"
    folder.mkdir()
    target = folder / "agentltl"
    target.write_text('#!/usr/bin/env bash\necho ran "$@"\n')
    target.chmod(0o755)
    link = tmp_path / "link"
    cli._link(str(target), str(link))
    out = subprocess.run(["bash", str(link), "a"], capture_output=True, text=True, cwd=tmp_path)
    assert out.stdout == "ran a\n", out.stderr
    assert not (tmp_path / "pwned").exists() and not (tmp_path / "pwned2").exists()


def test_a_link_made_meanwhile_is_not_written_through(tmp_path, monkeypatch):
    """Another install-cli created the link between the check and the symlink call."""
    target = tmp_path / "agentltl"
    target.write_text("the real launcher\n")
    link = tmp_path / "link"
    link.symlink_to(target)

    def exists(*args):
        raise FileExistsError(17, "File exists")

    monkeypatch.setattr(os, "symlink", exists)
    with pytest.raises(FileExistsError):
        cli._link(str(target), str(link))
    assert target.read_text() == "the real launcher\n"
