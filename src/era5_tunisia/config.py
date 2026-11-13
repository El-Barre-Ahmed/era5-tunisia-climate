from pathlib import Path
import yaml

# Chemin du projet
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Fichier de configuration
CONFIG_FILE = PROJECT_ROOT / "config" / "config.yaml"


def load_config():

    # Vérifier si le fichier existe
    if not CONFIG_FILE.exists():
        raise FileNotFoundError("config.yaml introuvable")

    
    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    return config