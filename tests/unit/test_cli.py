import zipfile
from pathlib import Path

import pytest
import yaml

import main as cli


@pytest.fixture
def config_file(tmp_path: Path, minimal_config: dict) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(minimal_config, sort_keys=False),
        encoding="utf-8",
    )
    return path


@pytest.fixture(autouse=True)
def _disable_file_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "setup_logging", lambda level=None: None)


def test_parser_parses_run_options() -> None:
    args = cli.build_parser().parse_args(
        [
            "--log-level",
            "DEBUG",
            "run",
            "--start",
            "2001-01",
            "--end",
            "2001-03",
            "--force",
            "--dry-run",
            "--fail-fast",
        ]
    )

    assert args.command == "run"
    assert args.log_level == "DEBUG"
    assert args.start == (2001, 1)
    assert args.end == (2001, 3)
    assert args.force is True
    assert args.dry_run is True
    assert args.fail_fast is True


def test_parser_rejects_invalid_month() -> None:
    with pytest.raises(SystemExit) as error:
        cli.build_parser().parse_args(["status", "--start", "2001-13"])

    assert error.value.code == cli.EXIT_USAGE


def test_status_reports_month_state_without_writing(
    config_file: Path,
    minimal_config: dict,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw_archive = (
        Path(minimal_config["paths"]["raw"])
        / "era5_tn_2001_01.zip"
    )
    raw_archive.write_bytes(b"zip")
    (
        Path(minimal_config["paths"]["interim"]) / "2001_01"
    ).mkdir()

    before = set(config_file.parent.rglob("*"))

    code = cli.main(
        [
            "--config",
            str(config_file),
            "status",
            "--start",
            "2001-01",
            "--end",
            "2001-01",
        ]
    )

    output = capsys.readouterr().out

    assert code == cli.EXIT_SUCCESS
    assert (
        "2001-01: zip=oui extrait=oui traité=non" in output
    )
    assert set(config_file.parent.rglob("*")) == before


def test_run_dry_run_creates_no_client_and_no_files(
    config_file: Path,
    minimal_config: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _unexpected_client(*args, **kwargs):
        raise AssertionError(
            "Le client CDS ne doit pas être créé en dry-run."
        )

    monkeypatch.setattr(cli, "create_cds_client", _unexpected_client)

    before = set(config_file.parent.rglob("*"))

    code = cli.main(
        [
            "--config",
            str(config_file),
            "run",
            "--start",
            "2001-01",
            "--end",
            "2001-01",
            "--dry-run",
        ]
    )

    assert code == cli.EXIT_SUCCESS
    assert set(config_file.parent.rglob("*")) == before

    for key in ("raw", "interim", "processed"):
        directory = Path(minimal_config["paths"][key])
        assert list(directory.iterdir()) == []


def test_run_returns_failure_when_a_month_fails(
    config_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "create_cds_client", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        cli,
        "run_pipeline",
        lambda *args, **kwargs: {"failed_count": 1},
    )

    code = cli.main(
        [
            "--config",
            str(config_file),
            "run",
            "--start",
            "2001-01",
            "--end",
            "2001-01",
        ]
    )

    assert code == cli.EXIT_FAILURE


def test_run_returns_success_when_all_months_succeed(
    config_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "create_cds_client", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        cli,
        "run_pipeline",
        lambda *args, **kwargs: {"success_count": 1, "failed_count": 0},
    )

    code = cli.main(
        [
            "--config",
            str(config_file),
            "run",
            "--start",
            "2001-01",
            "--end",
            "2001-01",
        ]
    )

    assert code == cli.EXIT_SUCCESS


def test_missing_config_returns_usage_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = cli.main(
        [
            "--config",
            str(tmp_path / "missing.yaml"),
            "status",
        ]
    )

    assert code == cli.EXIT_USAGE
    assert "Erreur de configuration" in capsys.readouterr().err


def test_incomplete_year_month_returns_usage_error(
    config_file: Path,
) -> None:
    code = cli.main(
        [
            "--config",
            str(config_file),
            "status",
            "--year",
            "2001",
        ]
    )

    assert code == cli.EXIT_USAGE


def test_download_command_downloads_month(
    config_file: Path,
    minimal_config: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict] = []
    received_configs: list[dict] = []

    class FakeCDSClient:
        def retrieve(self, dataset: str, request: dict, target: str) -> None:
            requests.append(request)

            with zipfile.ZipFile(target, "w") as archive:
                archive.writestr("data.nc", b"downloaded")

    def _fake_create_client(config: dict) -> FakeCDSClient:
        received_configs.append(config)
        return FakeCDSClient()

    monkeypatch.setattr(cli, "create_cds_client", _fake_create_client)

    code = cli.main(
        [
            "--config",
            str(config_file),
            "download",
            "--start",
            "2001-01",
            "--end",
            "2001-01",
        ]
    )

    assert code == cli.EXIT_SUCCESS
    assert len(received_configs) == 1
    assert received_configs[0]["acquisition"]["timeout_seconds"] == 10

    archive = (
        Path(minimal_config["paths"]["raw"])
        / "era5_tn_2001_01.zip"
    )
    assert archive.is_file()

    with zipfile.ZipFile(archive) as downloaded:
        assert downloaded.testzip() is None

    assert len(requests) == 1
    assert requests[0]["year"] == ["2001"]
    assert requests[0]["month"] == ["01"]
    assert requests[0]["day"][0] == "01"
    assert requests[0]["day"][-1] == "31"
