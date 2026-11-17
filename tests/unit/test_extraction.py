import zipfile
from pathlib import Path

import pytest

from era5_tunisia.extraction.extractor import (
    CHECKSUM_FILE,
    calculate_sha256,
    extract_archive,
    is_already_extracted,
    validate_archive,
)


def _create_zip(archive_path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def test_extract_valid_zip(tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.zip"
    extracted_dir = tmp_path / "extracted"
    content = b"netcdf-content"

    _create_zip(
        archive_path,
        {"data_stream-oper_stepType-instant.nc": content},
    )

    archive_hash = calculate_sha256(archive_path)
    extract_archive(archive_path, extracted_dir, archive_hash)

    assert (
        extracted_dir / "data_stream-oper_stepType-instant.nc"
    ).read_bytes() == content
    assert (extracted_dir / CHECKSUM_FILE).read_text(
        encoding="utf-8"
    ) == archive_hash


def test_zip_slip_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "zip-slip.zip"
    extracted_dir = tmp_path / "extracted"

    _create_zip(archive_path, {"../evil.txt": b"evil"})

    with pytest.raises(ValueError, match="Chemin dangereux"):
        extract_archive(
            archive_path,
            extracted_dir,
            calculate_sha256(archive_path),
        )

    assert not (tmp_path / "evil.txt").exists()
    assert not extracted_dir.exists()


def test_same_hash_is_detected_as_already_extracted(tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.zip"
    extracted_dir = tmp_path / "extracted"

    _create_zip(archive_path, {"data.nc": b"content"})
    archive_hash = calculate_sha256(archive_path)

    extract_archive(archive_path, extracted_dir, archive_hash)

    assert is_already_extracted(extracted_dir, archive_hash) is True
    assert is_already_extracted(extracted_dir, "another-hash") is False


def test_corrupted_zip_raises_bad_zip_file(tmp_path: Path) -> None:
    archive_path = tmp_path / "corrupted.zip"
    archive_path.write_bytes(b"this is not a ZIP archive")

    with pytest.raises(zipfile.BadZipFile):
        validate_archive(archive_path)
