"""Transformations scientifiques des données climatiques ERA5."""

import logging

import numpy as np
import xarray as xr


logger = logging.getLogger(__name__)


def convert_temperature(dataset: xr.Dataset) -> xr.Dataset:
    """
    Convertit la température de Kelvin en degrés Celsius.
    """

    if "t2m" not in dataset.data_vars:
        raise ValueError("Variable t2m absente du Dataset.")

    dataset["temperature_celsius"] = dataset["t2m"] - 273.15

    dataset["temperature_celsius"].attrs = {
        "long_name": "2 metre air temperature",
        "units": "°C",
        "description": "Temperature converted from Kelvin to Celsius.",
    }

    logger.info("Conversion de température terminée.")

    return dataset


def convert_precipitation(dataset: xr.Dataset) -> xr.Dataset:
    """
    Convertit les précipitations de mètres en millimètres.
    """

    if "tp" not in dataset.data_vars:
        raise ValueError("Variable tp absente du Dataset.")

    dataset["precipitation_mm"] = dataset["tp"] * 1000

    dataset["precipitation_mm"].attrs = {
        "long_name": "Total precipitation",
        "units": "mm",
        "description": (
            "Accumulated precipitation converted from metres "
            "to millimetres. Original accumulation period preserved."
        ),
    }

    logger.info("Conversion des précipitations terminée.")

    return dataset


def calculate_wind_speed(dataset: xr.Dataset) -> xr.Dataset:
    """
    Calcule la vitesse du vent à 10 mètres.

    Formule : sqrt(u10² + v10²)
    """

    for variable in ["u10", "v10"]:
        if variable not in dataset.data_vars:
            raise ValueError(
                f"Variable {variable} absente du Dataset."
            )

    dataset["wind_speed"] = np.hypot(
        dataset["u10"],
        dataset["v10"],
    )

    dataset["wind_speed"].attrs = {
        "long_name": "10 metre wind speed",
        "units": "m s-1",
        "description": (
            "Wind speed calculated from horizontal "
            "and vertical wind components."
        ),
    }

    logger.info("Calcul de la vitesse du vent terminé.")

    return dataset


def apply_transformations(dataset: xr.Dataset) -> xr.Dataset:
    """
    Applique toutes les transformations scientifiques.
    """

    logger.info("Début des transformations.")

    dataset = convert_temperature(dataset)
    dataset = convert_precipitation(dataset)
    dataset = calculate_wind_speed(dataset)

    logger.info("Transformations terminées.")

    return dataset
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