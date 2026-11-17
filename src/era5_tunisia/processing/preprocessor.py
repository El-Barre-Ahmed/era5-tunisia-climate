"""Préparation des données climatiques ERA5."""

import logging
from pathlib import Path

import xarray as xr


logger = logging.getLogger(__name__)


# --------------------------------------------------
# 1. Identification des fichiers NetCDF
# --------------------------------------------------

def get_monthly_files(
    month_dir: Path,
    config: dict,
) -> tuple[Path, Path]:
    """
    Identifie les fichiers NetCDF instant et accumulated.
    """

    instant_name = config["validation"]["files"]["instant"]
    accumulated_name = config["validation"]["files"]["accumulated"]

    instant_file = month_dir / instant_name
    accumulated_file = month_dir / accumulated_name

    if not instant_file.is_file():
        raise FileNotFoundError(
            f"Fichier instant introuvable : {instant_file}"
        )

    if not accumulated_file.is_file():
        raise FileNotFoundError(
            f"Fichier accumulated introuvable : {accumulated_file}"
        )

    logger.info(
        "Fichiers NetCDF identifiés dans : %s",
        month_dir,
    )

    return instant_file, accumulated_file


# --------------------------------------------------
# 2. Ouverture et fusion des fichiers NetCDF
# --------------------------------------------------

def open_monthly_datasets(
    instant_file: Path,
    accumulated_file: Path,
) -> xr.Dataset:
    """
    Ouvre les fichiers NetCDF et fusionne leurs variables.

    Les coordonnées doivent être identiques.
    """

    logger.info("Ouverture des fichiers NetCDF.")

    with (
        xr.open_dataset(instant_file) as instant,
        xr.open_dataset(accumulated_file) as accumulated,
    ):

        dataset = xr.merge(
            [instant, accumulated],
            join="exact",
            compat="no_conflicts",
        )

        # Charger les données avant la fermeture des fichiers.
        dataset.load()

    logger.info(
        "Fusion des fichiers terminée : %s",
        dataset.sizes,
    )

    return dataset


# --------------------------------------------------
# 3. Préparation d'un mois
# --------------------------------------------------

def preprocess_month(
    month_dir: Path,
    config: dict,
) -> xr.Dataset:
    """
    Prépare les données NetCDF d'un mois.

    Cette fonction identifie les fichiers, les ouvre
    et fusionne leurs variables.

    Elle retourne un Dataset prêt pour les étapes suivantes.
    """

    month_dir = Path(month_dir)

    if not month_dir.is_dir():
        raise NotADirectoryError(
            f"Dossier mensuel introuvable : {month_dir}"
        )

    logger.info(
        "Début du preprocessing : %s",
        month_dir.name,
    )

    # Identifier les fichiers sources.
    instant_file, accumulated_file = get_monthly_files(
        month_dir,
        config,
    )

    # Ouvrir et fusionner les fichiers.
    dataset = open_monthly_datasets(
        instant_file,
        accumulated_file,
    )

    logger.info(
        "Preprocessing terminé : %s",
        month_dir.name,
    )

    return dataset