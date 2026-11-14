#Configuration du logging pour era5_tunisia.

import logging.config
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def setup_logging() -> None:
    """Configure le logging dans le terminal et dans un fichier."""

    config_file = PROJECT_ROOT / "config" / "logging.yaml"

    with config_file.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    config["handlers"]["file"]["filename"] = str(
        PROJECT_ROOT / "logs" / "era5_tunisia.log"
    )

    logging.config.dictConfig(config)
