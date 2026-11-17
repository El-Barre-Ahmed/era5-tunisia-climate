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
