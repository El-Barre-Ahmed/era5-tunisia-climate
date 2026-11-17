from pathlib import Path

import pytest

from era5_tunisia.config import load_config


def test_load_config_from_temporary_yaml(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "data:\n"
        "  start_date: '2001-01-01'\n"
        "  variables:\n"
        "    - t2m\n",
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config["data"]["start_date"] == "2001-01-01"
    assert config["data"]["variables"] == ["t2m"]


def test_load_config_missing_file(tmp_path: Path) -> None:
    config_file = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError):
        load_config(config_file)


def test_load_config_empty_file(tmp_path: Path) -> None:
    config_file = tmp_path / "empty.yaml"
    config_file.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="dictionnaire"):
        load_config(config_file)


def test_load_config_non_mapping_yaml(tmp_path: Path) -> None:
    config_file = tmp_path / "list.yaml"
    config_file.write_text("- one\n- two\n", encoding="utf-8")

    with pytest.raises(ValueError, match="dictionnaire"):
        load_config(config_file)
