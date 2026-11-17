from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from era5_tunisia.processing.preprocessor import preprocess_month
from era5_tunisia.processing.transformations import (
    apply_transformations,
    calculate_wind_speed,
    convert_precipitation,
    convert_temperature,
)


def test_convert_temperature() -> None:
    dataset = xr.Dataset({"t2m": ("point", [273.15])})

    result = convert_temperature(dataset)

    assert result is dataset
    assert np.isclose(result["temperature_celsius"].item(), 0.0)


def test_convert_precipitation() -> None:
    dataset = xr.Dataset({"tp": ("point", [0.001])})

    result = convert_precipitation(dataset)

    assert result is dataset
    assert np.isclose(result["precipitation_mm"].item(), 1.0)


def test_calculate_wind_speed() -> None:
    dataset = xr.Dataset(
        {
            "u10": ("point", [3.0]),
            "v10": ("point", [4.0]),
        }
    )

    result = calculate_wind_speed(dataset)

    assert result is dataset
    assert np.isclose(result["wind_speed"].item(), 5.0)


def test_missing_variables_raise_clear_errors() -> None:
    with pytest.raises(ValueError, match="t2m"):
        convert_temperature(xr.Dataset())

    with pytest.raises(ValueError, match="tp"):
        convert_precipitation(xr.Dataset())

    with pytest.raises(ValueError, match="u10"):
        calculate_wind_speed(xr.Dataset({"v10": ("point", [4.0])}))


def test_apply_transformations_chain() -> None:
    dataset = xr.Dataset(
        {
            "t2m": ("point", [273.15]),
            "tp": ("point", [0.001]),
            "u10": ("point", [3.0]),
            "v10": ("point", [4.0]),
        }
    )

    result = apply_transformations(dataset)

    assert np.isclose(result["temperature_celsius"].item(), 0.0)
    assert np.isclose(result["precipitation_mm"].item(), 1.0)
    assert np.isclose(result["wind_speed"].item(), 5.0)


def test_preprocess_month(
    tmp_path: Path,
    minimal_config: dict,
    synthetic_dataset: xr.Dataset,
) -> None:
    month_dir = tmp_path / "2001_01"
    month_dir.mkdir()

    small_dataset = synthetic_dataset.isel(valid_time=slice(0, 3))

    instant_file = (
        month_dir / minimal_config["validation"]["files"]["instant"]
    )
    accumulated_file = (
        month_dir / minimal_config["validation"]["files"]["accumulated"]
    )

    small_dataset[["t2m", "u10", "v10"]].to_netcdf(instant_file)
    small_dataset[["tp"]].to_netcdf(accumulated_file)

    result = preprocess_month(month_dir, minimal_config)

    assert result.sizes["valid_time"] == 3

    for variable in ("t2m", "u10", "v10", "tp"):
        xr.testing.assert_equal(
            result[variable],
            small_dataset[variable],
        )
