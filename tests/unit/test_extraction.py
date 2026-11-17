import stat
import zipfile
from pathlib import Path

import pytest

from era5_tunisia.extraction.extractor import (
    CHECKSUM_FILE,
    calculate_sha256,
    extract_archive,
    extract_month,
    get_archive_info,
    is_already_extracted,
    validate_archive,
)


def _expected_members(config: dict) -> dict[str, bytes]:
    return {
        config["validation"]["files"]["instant"]: b"instant-content",
        config["validation"]["files"]["accumulated"]: b"accumulated-content",
    }


def _create_zip(archive_path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def test_extract_valid_zip(
    tmp_path: Path,
    minimal_config: dict,
) -> None:
    archive_path = tmp_path / "archive.zip"
    extracted_dir = tmp_path / "extracted"
    members = _expected_members(minimal_config)

    _create_zip(archive_path, members)

    archive_hash = calculate_sha256(archive_path)
    extract_archive(
        archive_path,
        extracted_dir,
        archive_hash,
        minimal_config,
    )

    for name, content in members.items():
        assert (extracted_dir / name).read_bytes() == content

    assert (extracted_dir / CHECKSUM_FILE).read_text(
        encoding="utf-8"
    ) == archive_hash


def test_zip_slip_is_rejected(
    tmp_path: Path,
    minimal_config: dict,
) -> None:
    archive_path = tmp_path / "zip-slip.zip"
    extracted_dir = tmp_path / "extracted"

    members = _expected_members(minimal_config)
    members["../evil.txt"] = b"evil"
    _create_zip(archive_path, members)

    with pytest.raises(ValueError, match="Chemin dangereux"):
        extract_archive(
            archive_path,
            extracted_dir,
            calculate_sha256(archive_path),
            minimal_config,
        )

    assert not (tmp_path / "evil.txt").exists()
    assert not extracted_dir.exists()


def test_same_hash_is_detected_as_already_extracted(
    tmp_path: Path,
    minimal_config: dict,
) -> None:
    archive_path = tmp_path / "archive.zip"
    extracted_dir = tmp_path / "extracted"

    _create_zip(archive_path, _expected_members(minimal_config))
    archive_hash = calculate_sha256(archive_path)

    extract_archive(
        archive_path,
        extracted_dir,
        archive_hash,
        minimal_config,
    )

    assert is_already_extracted(extracted_dir, archive_hash) is True
    assert is_already_extracted(extracted_dir, "another-hash") is False


def test_corrupted_zip_raises_bad_zip_file(
    tmp_path: Path,
    minimal_config: dict,
) -> None:
    archive_path = tmp_path / "corrupted.zip"
    archive_path.write_bytes(b"this is not a ZIP archive")

    with pytest.raises(zipfile.BadZipFile):
        validate_archive(archive_path, minimal_config)


def test_empty_zip_raises_value_error(
    tmp_path: Path,
    minimal_config: dict,
) -> None:
    archive_path = tmp_path / "empty.zip"

    with zipfile.ZipFile(archive_path, "w"):
        pass

    with pytest.raises(ValueError, match="vide"):
        validate_archive(archive_path, minimal_config)


def test_zip_without_expected_files_raises_value_error(
    tmp_path: Path,
    minimal_config: dict,
) -> None:
    archive_path = tmp_path / "missing-files.zip"
    accumulated_name = minimal_config["validation"]["files"]["accumulated"]

    _create_zip(
        archive_path,
        {
            minimal_config["validation"]["files"]["instant"]: b"instant",
        },
    )

    with pytest.raises(ValueError) as error:
        validate_archive(archive_path, minimal_config)

    assert accumulated_name in str(error.value)


@pytest.mark.parametrize(
    "template",
    [
        "era5_tn_{year}.zip",
        "era5_tn_{month}.zip",
        "era5_tn.zip",
    ],
)
def test_invalid_archive_template_raises_value_error(
    tmp_path: Path,
    template: str,
) -> None:
    archive_path = tmp_path / "era5_tn_2001_01.zip"

    with pytest.raises(ValueError, match="Template"):
        get_archive_info(archive_path, template)


def test_extract_month_skips_then_forces(
    tmp_path: Path,
    minimal_config: dict,
) -> None:
    archive_path = tmp_path / "archive.zip"
    extracted_dir = tmp_path / "2001_01"
    members = _expected_members(minimal_config)

    _create_zip(archive_path, members)

    assert extract_month(
        archive_path,
        extracted_dir,
        minimal_config,
    ) is True

    assert extract_month(
        archive_path,
        extracted_dir,
        minimal_config,
    ) is False

    instant_name = minimal_config["validation"]["files"]["instant"]
    (extracted_dir / instant_name).write_bytes(b"modified")

    assert extract_month(
        archive_path,
        extracted_dir,
        minimal_config,
        force=True,
    ) is True

    assert (extracted_dir / instant_name).read_bytes() == members[instant_name]


def test_extracted_directory_permissions_are_755(
    tmp_path: Path,
    minimal_config: dict,
) -> None:
    archive_path = tmp_path / "archive.zip"
    extracted_dir = tmp_path / "2001_01"

    _create_zip(archive_path, _expected_members(minimal_config))

    extract_month(archive_path, extracted_dir, minimal_config)

    mode = stat.S_IMODE(extracted_dir.stat().st_mode)
    assert mode == 0o755
