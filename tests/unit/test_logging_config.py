import logging
from pathlib import Path

from era5_tunisia.logging_config import PROJECT_ROOT, setup_logging


def test_setup_logging_uses_custom_file(tmp_path: Path) -> None:
    real_log_file = PROJECT_ROOT / "logs" / "era5_tunisia.log"
    real_log_size_before = (
        real_log_file.stat().st_size
        if real_log_file.exists()
        else None
    )

    log_file = tmp_path / "nested" / "custom.log"

    setup_logging(level="DEBUG", log_file=log_file)

    logger = logging.getLogger("era5_tunisia.test_logging")
    logger.debug("message de test")

    assert log_file.is_file()
    assert "message de test" in log_file.read_text(encoding="utf-8")

    real_log_size_after = (
        real_log_file.stat().st_size
        if real_log_file.exists()
        else None
    )
    assert real_log_size_after == real_log_size_before
