"""Portable tests for Windows collector authorization and privacy boundaries."""

from pathlib import Path

import pytest

from collector.windows_collector import normalize_authorized_folders


def test_authorized_folders_are_resolved_and_deduplicated(tmp_path):
    folder = tmp_path / "project"
    folder.mkdir()
    assert normalize_authorized_folders([folder, folder])[0] == folder.resolve()


def test_missing_authorized_folder_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        normalize_authorized_folders([tmp_path / "missing"])


def test_empty_authorized_folders_are_rejected():
    with pytest.raises(ValueError, match="At least one"):
        normalize_authorized_folders([])
