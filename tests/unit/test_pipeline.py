import copy
import tempfile
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from era5_tunisia.pipeline import (
    STATUS_FAILED,
    STATUS_SKIPPED,
    STATUS_SUCCESS,
    Month,
    iter_months,
    resolve_month_paths,
    run_month,
    run_pipeline,
)


LATITUDE = np.array([37.75, 37.50, 30.00])
LONGITUDE = np.array([7.50, 11.75])


def _build_month_dataset(year: int, month: int) -> xr.Dataset:
    """Dataset ERA5 synthétique couvrant un mois complet."""

    start = pd.Timestamp(year=year, month=month, day=1)
    end = start + pd.offsets.MonthEnd(0)

    valid_time = pd.date_range(
        start=start,
        end=end + pd.Timedelta(days=1) - pd.Timedelta(hours=1),
        freq="1h",
    )

    shape = (valid_time.size, LATITUDE.size, LONGITUDE.size)

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
            "latitude": LATITUDE,
            "longitude": LONGITUDE,
        },
    )


class FakeCDSClient:
    """Faux client CDS qui écrit un ZIP contenant deux NetCDF."""

    def __init__(self, config: dict, fail_for=()) -> None:
        self.config = config
        self.fail_for = set(fail_for)
        self.calls: list[tuple[str, dict, str]] = []

    def retrieve(self, dataset: str, request: dict, target: str) -> None:
        self.calls.append((dataset, request, target))

        year = int(request["year"][0])
        month = int(request["month"][0])

        if (year, month) in self.fail_for:
            raise RuntimeError(f"CDS indisponible pour {year}-{month:02d}")

        monthly_dataset = _build_month_dataset(year, month)

        files = self.config["validation"]["files"]

        with tempfile.TemporaryDirectory() as temporary:

            instant_path = Path(temporary) / "instant.nc"
            accumulated_path = Path(temporary) / "accumulated.nc"

            monthly_dataset[["t2m", "u10", "v10"]].to_netcdf(instant_path)
            monthly_dataset[["tp"]].to_netcdf(accumulated_path)

            with zipfile.ZipFile(target, "w") as archive:
                archive.write(instant_path, arcname=files["instant"])
                archive.write(accumulated_path, arcname=files["accumulated"])


@pytest.fixture
def pipeline_config(minimal_config: dict) -> dict:
    return copy.deepcopy(minimal_config)


def test_iter_months_spans_years() -> None:
    months = list(iter_months(date(2001, 11, 15), date(2002, 2, 3)))

    assert months == [
        Month(2001, 11),
        Month(2001, 12),
        Month(2002, 1),
        Month(2002, 2),
    ]


def test_iter_months_rejects_reversed_period() -> None:
    with pytest.raises(ValueError):
        list(iter_months(date(2002, 1, 1), date(2001, 12, 31)))


def test_resolve_month_paths(pipeline_config: dict) -> None:
    paths = resolve_month_paths(pipeline_config, Month(2001, 1))

    assert paths.raw_archive == (
        Path(pipeline_config["paths"]["raw"]) / "era5_tn_2001_01.zip"
    )
    assert paths.interim_dir == (
        Path(pipeline_config["paths"]["interim"]) / "2001_01"
    )
    assert paths.processed_file == (
        Path(pipeline_config["paths"]["processed"]) / "era5_tn_2001_01.nc"
    )


def test_run_month_success(pipeline_config: dict) -> None:
    client = FakeCDSClient(pipeline_config)
    month = Month(2001, 1)

    result = run_month(client, pipeline_config, month)

    assert result.status == STATUS_SUCCESS
    assert result.error is None
    assert result.paths.processed_file.is_file()
    assert result.paths.raw_archive.is_file()
    assert result.paths.interim_dir.is_dir()
    assert len(client.calls) == 1

    _, request, _ = client.calls[0]
    assert request["year"] == ["2001"]
    assert request["month"] == ["01"]

    with xr.open_dataset(result.paths.processed_file) as dataset:
        for variable in (
            "temperature_celsius",
            "precipitation_mm",
            "wind_speed",
        ):
            assert variable in dataset.data_vars


def test_run_month_skips_existing_output(pipeline_config: dict) -> None:
    client = FakeCDSClient(pipeline_config)
    month = Month(2001, 1)

    paths = resolve_month_paths(pipeline_config, month)
    paths.processed_file.write_bytes(b"already processed")

    result = run_month(client, pipeline_config, month)

    assert result.status == STATUS_SKIPPED
    assert client.calls == []


def test_run_month_force_redownloads(pipeline_config: dict) -> None:
    client = FakeCDSClient(pipeline_config)
    month = Month(2001, 1)

    first = run_month(client, pipeline_config, month)
    assert first.status == STATUS_SUCCESS

    skipped = run_month(client, pipeline_config, month)
    assert skipped.status == STATUS_SKIPPED

    forced = run_month(client, pipeline_config, month, force=True)
    assert forced.status == STATUS_SUCCESS
    assert len(client.calls) == 2


def test_run_month_dry_run_creates_nothing(pipeline_config: dict) -> None:
    client = FakeCDSClient(pipeline_config)
    month = Month(2001, 1)

    result = run_month(client, pipeline_config, month, dry_run=True)

    assert result.status == STATUS_SKIPPED
    assert client.calls == []

    paths = resolve_month_paths(pipeline_config, month)
    assert not paths.raw_archive.exists()
    assert not paths.interim_dir.exists()
    assert not paths.processed_file.exists()


def test_pipeline_continues_after_failure(pipeline_config: dict) -> None:
    config = copy.deepcopy(pipeline_config)
    config["data"]["end_date"] = "2001-03-31"

    client = FakeCDSClient(config, fail_for={(2001, 2)})
    months = list(iter_months(date(2001, 1, 1), date(2001, 3, 31)))

    result = run_pipeline(client, config, months)

    assert len(result.results) == 3
    assert result.success_count == 2
    assert result.failed_count == 1
    assert result.skipped_count == 0

    statuses = [month_result.status for month_result in result.results]
    assert statuses == [STATUS_SUCCESS, STATUS_FAILED, STATUS_SUCCESS]

    failed = result.results[1]
    assert failed.month == Month(2001, 2)
    assert failed.error is not None

    assert resolve_month_paths(config, Month(2001, 1)).processed_file.is_file()
    assert not resolve_month_paths(config, Month(2001, 2)).processed_file.exists()
    assert resolve_month_paths(config, Month(2001, 3)).processed_file.is_file()


def test_pipeline_fail_fast_stops_after_failure(pipeline_config: dict) -> None:
    config = copy.deepcopy(pipeline_config)
    config["data"]["end_date"] = "2001-03-31"

    client = FakeCDSClient(config, fail_for={(2001, 2)})
    months = list(iter_months(date(2001, 1, 1), date(2001, 3, 31)))

    result = run_pipeline(client, config, months, fail_fast=True)

    assert len(result.results) == 2
    assert result.failed_count == 1
    assert result.results[-1].month == Month(2001, 2)


def test_pipeline_dry_run_processes_nothing(pipeline_config: dict) -> None:
    config = copy.deepcopy(pipeline_config)
    config["data"]["end_date"] = "2001-02-28"

    client = FakeCDSClient(config)
    months = list(iter_months(date(2001, 1, 1), date(2001, 2, 28)))

    result = run_pipeline(client, config, months, dry_run=True)

    assert result.skipped_count == 2
    assert result.success_count == 0
    assert client.calls == []

    for month in months:
        paths = resolve_month_paths(config, month)
        assert not paths.raw_archive.exists()
        assert not paths.interim_dir.exists()
        assert not paths.processed_file.exists()
