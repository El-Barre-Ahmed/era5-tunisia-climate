from pathlib import Path

import yaml

# Chemin du projet
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

# Fichier de configuration
CONFIG_FILE: Path = PROJECT_ROOT / "config" / "config.yaml"


def load_config(path: Path | None = None) -> dict:
    """Charge la configuration YAML.

    Args:
        path: Fichier de configuration à charger. Par défaut,
            ``config/config.yaml`` à la racine du projet.

    Raises:
        FileNotFoundError: Si le fichier n'existe pas.
        ValueError: Si le YAML est vide ou ne contient pas un dictionnaire.
    """

    config_file = Path(path) if path is not None else CONFIG_FILE

    # Vérifier si le fichier existe
    if not config_file.exists():
        raise FileNotFoundError(
            f"Fichier de configuration introuvable : {config_file}"
        )

    with config_file.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict):
        raise ValueError(
            f"La configuration doit être un dictionnaire YAML : {config_file}"
        )

    return config