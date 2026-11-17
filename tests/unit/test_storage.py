from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from era5_tunisia.storage.netcdf_writer import write_netcdf


def _temporary_files(output_file: Path) -> list[Path]:
    return list(output_file.parent.glob(f".{output_file.stem}_*"))


def test_write_netcdf(
    tmp_path: Path,
    synthetic_dataset: xr.Dataset,
) -> None:
    output_file = tmp_path / "output" / "era5_tn_2001_01.nc"

    result = write_netcdf(synthetic_dataset, output_file)

    assert result == output_file
    assert output_file.is_file()

    with xr.open_dataset(output_file) as dataset:
        assert "t2m" in dataset.data_vars

    assert _temporary_files(output_file) == []


def test_existing_file_raises_without_overwrite(
    tmp_path: Path,
    synthetic_dataset: xr.Dataset,
) -> None:
    output_file = tmp_path / "existing.nc"
    write_netcdf(synthetic_dataset, output_file)

    with pytest.raises(FileExistsError):
        write_netcdf(synthetic_dataset, output_file)

    assert _temporary_files(output_file) == []


def test_overwrite_replaces_existing_file(
    tmp_path: Path,
    synthetic_dataset: xr.Dataset,
) -> None:
    output_file = tmp_path / "overwrite.nc"
    write_netcdf(synthetic_dataset, output_file)

    modified_dataset = synthetic_dataset.copy(deep=True)
    modified_dataset["t2m"] = modified_dataset["t2m"] + 1.0

    write_netcdf(modified_dataset, output_file, overwrite=True)

    with xr.open_dataset(output_file) as dataset:
        value = dataset["t2m"].isel(
            valid_time=0,
            latitude=0,
            longitude=0,
        ).item()

    assert np.isclose(value, 274.15)
    assert _temporary_files(output_file) == []
