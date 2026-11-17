from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr


@pytest.fixture
def minimal_config(tmp_path: Path) -> dict:
    """Configuration minimale dont les chemins pointent vers tmp_path."""

    raw_dir = tmp_path / "raw"
    interim_dir = tmp_path / "interim"
    processed_dir = tmp_path / "processed"

    for directory in (raw_dir, interim_dir, processed_dir):
        directory.mkdir()

    return {
        "project": {
            "name": "ERA5 Tunisia Climate Test",
            "code": "ERA5-TN-TEST",
            "version": "0.0.0",
        },
        "data": {
            "dataset": "reanalysis-era5-single-levels",
            "product_type": "reanalysis",
            "start_date": "2001-01-01",
            "end_date": "2001-01-31",
            "area": [37.75, 7.50, 30.00, 11.75],
            "variables": ["t2m", "tp", "u10", "v10"],
            "time_reference": "UTC",
        },
        "acquisition": {
            "unit": "month",
            "data_format": "netcdf",
            "download_format": "zip",
            "retries": 1,
            "retry_base_seconds": 0,
            "retry_max_seconds": 0,
            "timeout_seconds": 10,
        },
        "validation": {
            "files": {
                "instant": "data_stream-oper_stepType-instant.nc",
                "accumulated": "data_stream-oper_stepType-accum.nc",
            },
            "variables": {
                "instant": ["t2m", "u10", "v10"],
                "accumulated": ["tp"],
            },
            "dimensions": ["valid_time", "latitude", "longitude"],
            "coordinates": {
                "time": "valid_time",
                "latitude": "latitude",
                "longitude": "longitude",
            },
            "expected_frequency": "1h",
        },
        "naming": {
            "raw_archive": "era5_tn_{year}_{month}.zip",
            "extracted_dir": "{year}_{month}",
            "processed_file": "era5_tn_{year}_{month}.nc",
        },
        "paths": {
            "raw": str(raw_dir),
            "interim": str(interim_dir),
            "processed": str(processed_dir),
        },
    }


@pytest.fixture
def synthetic_dataset() -> xr.Dataset:
    """Mini-dataset ERA5 synthétique couvrant janvier 2001."""

    valid_time = pd.date_range(
        start="2001-01-01",
        end="2001-01-31 23:00",
        freq="1h",
    )
    latitude = np.array([37.75, 37.50, 30.00])
    longitude = np.array([7.50, 11.75])

    shape = (valid_time.size, latitude.size, longitude.size)

    return xr.Dataset(
        data_vars={
            "t2m": (
                ("valid_time", "latitude", "longitude"),
                np.full(shape, 273.15),
            ),
            "u10": (
                ("valid_time", "latitude", "longitude"),
                np.full(shape, 3.0),
            ),
            "v10": (
                ("valid_time", "latitude", "longitude"),
                np.full(shape, 4.0),
            ),
            "tp": (
                ("valid_time", "latitude", "longitude"),
                np.full(shape, 0.001),
            ),
        },
        coords={
            "valid_time": valid_time,
            "latitude": latitude,
            "longitude": longitude,
        },
    )
