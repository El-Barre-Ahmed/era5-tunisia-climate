import copy
from pathlib import Path

import pytest
import xarray as xr

import era5_tunisia.validation.validator as validator_module
from era5_tunisia.validation.validator import (
    validate_all,
    validate_file,
    validate_month,
)


EXPECTED_VARIABLES = ["t2m", "u10", "v10", "tp"]


def _write_month(
    config: dict,
    dataset: xr.Dataset,
    year: int,
    month: int,
    *,
    invalid_instant: bool = False,
) -> Path:
    month_name = config["naming"]["extracted_dir"].format(
        year=year,
        month=f"{month:02d}",
    )
    month_dir = Path(config["paths"]["interim"]) / month_name
    month_dir.mkdir(parents=True, exist_ok=True)

    instant = dataset[["t2m", "u10", "v10"]]
    if invalid_instant:
        instant = instant.drop_vars("u10")

    instant.to_netcdf(
        month_dir / config["validation"]["files"]["instant"]
    )
    dataset[["tp"]].to_netcdf(
        month_dir / config["validation"]["files"]["accumulated"]
    )

    return month_dir


def test_validate_file_accepts_conforming_file(
    tmp_path: Path,
    minimal_config: dict,
    synthetic_dataset: xr.Dataset,
) -> None:
    file_path = tmp_path / "valid.nc"
    synthetic_dataset.to_netcdf(file_path)

    assert validate_file(
        file_path,
        EXPECTED_VARIABLES,
        2001,
        1,
        minimal_config,
    ) is True


def test_validate_file_rejects_missing_variable(
    tmp_path: Path,
    minimal_config: dict,
    synthetic_dataset: xr.Dataset,
) -> None:
    file_path = tmp_path / "missing-variable.nc"
    synthetic_dataset.drop_vars("tp").to_netcdf(file_path)

    assert validate_file(
        file_path,
        EXPECTED_VARIABLES,
        2001,
        1,
        minimal_config,
    ) is False


def test_validate_file_rejects_incorrect_period(
    tmp_path: Path,
    minimal_config: dict,
    synthetic_dataset: xr.Dataset,
) -> None:
    file_path = tmp_path / "incorrect-period.nc"
    synthetic_dataset.isel(
        valid_time=slice(0, synthetic_dataset.sizes["valid_time"] - 1)
    ).to_netcdf(file_path)

    assert validate_file(
        file_path,
        EXPECTED_VARIABLES,
        2001,
        1,
        minimal_config,
    ) is False


def test_validate_all_accepts_complete_period(
    minimal_config: dict,
    synthetic_dataset: xr.Dataset,
) -> None:
    _write_month(minimal_config, synthetic_dataset, 2001, 1)

    assert validate_all(minimal_config) is True


def test_validate_all_rejects_missing_month(
    minimal_config: dict,
    synthetic_dataset: xr.Dataset,
) -> None:
    config = copy.deepcopy(minimal_config)
    config["data"]["end_date"] = "2001-02-28"

    _write_month(config, synthetic_dataset, 2001, 1)

    assert validate_all(config) is False


def test_validate_all_rejects_invalid_month(
    minimal_config: dict,
    synthetic_dataset: xr.Dataset,
) -> None:
    _write_month(
        minimal_config,
        synthetic_dataset,
        2001,
        1,
        invalid_instant=True,
    )

    assert validate_all(minimal_config) is False


def test_validate_all_uses_injected_config(
    minimal_config: dict,
    synthetic_dataset: xr.Dataset,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_month(minimal_config, synthetic_dataset, 2001, 1)

    def _unexpected_load_config() -> dict:
        raise AssertionError("load_config ne doit pas être appelé")

    monkeypatch.setattr(
        validator_module,
        "load_config",
        _unexpected_load_config,
    )

    assert validate_all(minimal_config) is True


def test_validate_month_uses_configured_directory_template(
    minimal_config: dict,
    synthetic_dataset: xr.Dataset,
) -> None:
    config = copy.deepcopy(minimal_config)
    config["naming"]["extracted_dir"] = "era5_{year}-{month}"

    month_dir = _write_month(config, synthetic_dataset, 2001, 1)

    assert month_dir.name == "era5_2001-01"
    assert validate_month(month_dir, config) is True


@pytest.mark.parametrize(
    ("validation_result", "expected_code"),
    [
        (True, 0),
        (False, 1),
    ],
)
def test_main_exit_code(
    validation_result: bool,
    expected_code: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        validator_module,
        "validate_all",
        lambda: validation_result,
    )
    monkeypatch.setattr(
        "era5_tunisia.logging_config.setup_logging",
        lambda: None,
    )

    with pytest.raises(SystemExit) as error:
        validator_module.main()

    assert error.value.code == expected_code
