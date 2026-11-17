import copy
import zipfile
from pathlib import Path

import pytest

from era5_tunisia.acquisition.downloader import download_month


class FakeCDSClient:
    """Faux client CDS qui écrit un petit ZIP valide."""

    def __init__(self, content: bytes = b"downloaded-data") -> None:
        self.content = content
        self.calls: list[tuple[str, dict, str]] = []

    def retrieve(self, dataset: str, request: dict, target: str) -> None:
        self.calls.append((dataset, request, target))

        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr("data.nc", self.content)


def _raw_archive(config: dict) -> Path:
    raw_dir = Path(config["paths"]["raw"])
    return raw_dir / config["naming"]["raw_archive"].format(
        year=2001,
        month="01",
    )


def _create_zip(path: Path, content: bytes) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("data.nc", content)


def test_valid_archive_is_reused_without_request(
    minimal_config: dict,
) -> None:
    output_file = _raw_archive(minimal_config)
    _create_zip(output_file, b"existing-data")

    client = FakeCDSClient()

    result = download_month(
        client,
        minimal_config,
        2001,
        1,
        ["01", "02"],
    )

    assert result == output_file
    assert client.calls == []


def test_force_redownloads_existing_archive(
    minimal_config: dict,
) -> None:
    output_file = _raw_archive(minimal_config)
    _create_zip(output_file, b"old-data")

    client = FakeCDSClient(content=b"new-data")

    result = download_month(
        client,
        minimal_config,
        2001,
        1,
        ["01", "02"],
        force=True,
    )

    assert result == output_file
    assert len(client.calls) == 1

    with zipfile.ZipFile(output_file, "r") as archive:
        assert archive.read("data.nc") == b"new-data"


def test_retries_zero_raises_value_error(
    minimal_config: dict,
) -> None:
    config = copy.deepcopy(minimal_config)
    config["acquisition"]["retries"] = 0

    client = FakeCDSClient()

    with pytest.raises(ValueError, match="retries"):
        download_month(
            client,
            config,
            2001,
            1,
            ["01", "02"],
        )

    assert client.calls == []


def test_request_contains_exactly_one_month(
    minimal_config: dict,
) -> None:
    client = FakeCDSClient()

    download_month(
        client,
        minimal_config,
        2001,
        1,
        ["01", "02"],
    )

    assert len(client.calls) == 1

    dataset, request, _ = client.calls[0]

    assert dataset == minimal_config["data"]["dataset"]
    assert request["year"] == ["2001"]
    assert request["month"] == ["01"]
    assert request["day"] == ["01", "02"]
    assert len(request["year"]) == 1
    assert len(request["month"]) == 1
