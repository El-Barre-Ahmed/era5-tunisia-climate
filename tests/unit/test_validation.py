from pathlib import Path

import xarray as xr

from era5_tunisia.validation.validator import validate_file


EXPECTED_VARIABLES = ["t2m", "u10", "v10", "tp"]


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
