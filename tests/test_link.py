"""`install-cli` links with a symlink, and writes a small script where Windows refuses one."""

import os

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
    assert link.read_text().endswith(f'exec "{target.as_posix()}" "$@"\n')
    assert os.access(link, os.X_OK)
    assert cli._links_to(str(link), str(target))
    assert not cli._links_to(str(link), str(tmp_path / "other"))
