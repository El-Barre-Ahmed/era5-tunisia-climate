#Configuration du logging pour era5_tunisia.

import logging.config
from pathlib import Path

import yaml

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

DEFAULT_LOG_FILE: Path = PROJECT_ROOT / "logs" / "era5_tunisia.log"


def setup_logging(
    level: str | None = None,
    log_file: Path | None = None,
) -> None:
    """Configure le logging dans le terminal et dans un fichier.

    Args:
        level: Niveau de logging à appliquer (par exemple ``"DEBUG"``).
            Si ``None``, les niveaux du fichier YAML sont conservés.
        log_file: Fichier de log à utiliser. Par défaut,
            ``logs/era5_tunisia.log`` à la racine du projet.
    """

    config_file = PROJECT_ROOT / "config" / "logging.yaml"

    with config_file.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    target_log_file = Path(log_file) if log_file is not None else DEFAULT_LOG_FILE

    target_log_file.parent.mkdir(parents=True, exist_ok=True)

    config["handlers"]["file"]["filename"] = str(target_log_file)

    if level is not None:
        config["root"]["level"] = level
        config["handlers"]["console"]["level"] = level
        config["handlers"]["file"]["level"] = level

    logging.config.dictConfig(config)
