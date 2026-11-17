import logging
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from era5_tunisia.config import load_config, PROJECT_ROOT


logger = logging.getLogger(__name__)


def _build_extracted_dir_pattern(extracted_template: str) -> str:
    """Construit le motif regex des dossiers extraits depuis le template."""

    missing_placeholders = [
        placeholder
        for placeholder in ("{year}", "{month}")
        if placeholder not in extracted_template
    ]

    if missing_placeholders:
        raise ValueError(
            "Template de dossier extrait invalide, placeholders manquants : "
            + ", ".join(missing_placeholders)
        )

    pattern = re.escape(extracted_template)
    pattern = pattern.replace(
        re.escape("{year}"),
        r"(?P<year>\d{4})",
    )
    pattern = pattern.replace(
        re.escape("{month}"),
        r"(?P<month>\d{2})",
    )

    return pattern


# --------------------------------------------------
# 1. Validation d'un fichier NetCDF
# --------------------------------------------------

def validate_file(file_path, expected_variables, year, month, config):
    """Vérifie la structure et la qualité d'un fichier NetCDF."""

    file_path = Path(file_path)
    errors = []

    logger.info("Début de validation : %s", file_path.name)

    # Vérifier l'existence du fichier
    if not file_path.is_file():
        logger.error("[ÉCHEC] Fichier introuvable : %s", file_path)
        return False

    logger.info("[OK] Fichier présent : %s", file_path.name)

    try:
        with xr.open_dataset(file_path) as dataset:

            validation_config = config["validation"]
            expected_dimensions = tuple(
                validation_config["dimensions"]
            )

            # 1. Vérifier les dimensions
            for dimension in expected_dimensions:

                if dimension not in dataset.sizes:
                    errors.append(
                        f"Dimension absente : {dimension}"
                    )

                elif dataset.sizes[dimension] == 0:
                    errors.append(
                        f"Dimension vide : {dimension}"
                    )

                else:
                    logger.info(
                        "[OK] Dimension %s : %s",
                        dimension,
                        dataset.sizes[dimension]
                    )

            # 2. Vérifier les variables
            for variable in expected_variables:

                if variable not in dataset.data_vars:
                    errors.append(
                        f"Variable absente : {variable}"
                    )
                    continue

                data = dataset[variable]

                if data.dims != expected_dimensions:
                    errors.append(
                        f"Dimensions incorrectes pour {variable} : "
                        f"{data.dims}"
                    )
                    continue

                values = data.values

                if not np.issubdtype(values.dtype, np.number):
                    errors.append(
                        f"Variable non numérique : {variable}"
                    )
                    continue

                if not np.isfinite(values).all():
                    errors.append(
                        f"Valeurs manquantes ou infinies : {variable}"
                    )
                    continue

                logger.info(
                    "[OK] Variable %s : dimensions=%s, type=%s",
                    variable,
                    data.dims,
                    values.dtype
                )

            # 3. Vérifier les coordonnées
            coordinates = validation_config["coordinates"]

            for name in coordinates.values():

                if name not in dataset.coords:
                    errors.append(
                        f"Coordonnée absente : {name}"
                    )

                else:
                    logger.info(
                        "[OK] Coordonnée présente : %s",
                        name
                    )

            latitude_name = coordinates["latitude"]
            longitude_name = coordinates["longitude"]

            # 4. Vérifier latitude
            if latitude_name in dataset.coords:

                latitude = dataset[latitude_name].values

                if not np.isfinite(latitude).all():
                    errors.append(
                        "Coordonnées latitude invalides"
                    )

                elif len(np.unique(latitude)) != len(latitude):
                    errors.append(
                        "Coordonnées latitude dupliquées"
                    )

                else:
                    logger.info(
                        "[OK] Latitude : min=%.4f, max=%.4f",
                        latitude.min(),
                        latitude.max()
                    )

            # 5. Vérifier longitude
            if longitude_name in dataset.coords:

                longitude = dataset[longitude_name].values

                if not np.isfinite(longitude).all():
                    errors.append(
                        "Coordonnées longitude invalides"
                    )

                elif len(np.unique(longitude)) != len(longitude):
                    errors.append(
                        "Coordonnées longitude dupliquées"
                    )

                else:
                    logger.info(
                        "[OK] Longitude : min=%.4f, max=%.4f",
                        longitude.min(),
                        longitude.max()
                    )

            # 6. Vérifier la zone géographique
            if (
                latitude_name in dataset.coords
                and longitude_name in dataset.coords
            ):

                latitude = dataset[latitude_name].values
                longitude = dataset[longitude_name].values

                if (
                    latitude.size > 0
                    and longitude.size > 0
                    and np.isfinite(latitude).all()
                    and np.isfinite(longitude).all()
                ):

                    north, west, south, east = config["data"]["area"]

                    latitude_valid = (
                        np.isclose(latitude.max(), north, atol=0.001)
                        and np.isclose(latitude.min(), south, atol=0.001)
                    )

                    longitude_valid = (
                        np.isclose(longitude.min(), west, atol=0.001)
                        and np.isclose(longitude.max(), east, atol=0.001)
                    )

                    if latitude_valid and longitude_valid:
                        logger.info(
                            "[OK] Zone géographique conforme : %s",
                            config["data"]["area"]
                        )

                    else:
                        errors.append(
                            "Zone géographique différente de la configuration"
                        )

            # 7. Vérifier la période temporelle
            time_name = coordinates["time"]

            if time_name in dataset.coords:

                times = pd.DatetimeIndex(
                    dataset[time_name].values
                )

                if times.hasnans:
                    errors.append("Dates invalides")

                else:

                    if not times.is_monotonic_increasing:
                        errors.append(
                            "Dates non ordonnées chronologiquement"
                        )

                    if times.has_duplicates:
                        errors.append(
                            "Dates dupliquées"
                        )

                    start = pd.Timestamp(
                        year=year,
                        month=month,
                        day=1
                    )

                    end = start + pd.offsets.MonthEnd(0)

                    frequency = validation_config["expected_frequency"]

                    expected_times = pd.date_range(
                        start=start,
                        end=end + pd.Timedelta(days=1)
                        - pd.Timedelta(hours=1),
                        freq=frequency
                    )

                    if times.equals(expected_times):

                        logger.info(
                            "[OK] Période temporelle : %s → %s",
                            times.min(),
                            times.max()
                        )

                        logger.info(
                            "[OK] Fréquence %s : %s/%s observations",
                            frequency,
                            len(times),
                            len(expected_times)
                        )

                    else:
                        errors.append(
                            f"Période temporelle incorrecte : "
                            f"{len(times)} observations trouvées, "
                            f"{len(expected_times)} attendues"
                        )

    except Exception as error:

        errors.append(
            f"Impossible de lire le fichier : {error}"
        )

    # Résultat final
    if errors:

        for error in errors:
            logger.error(
                "[ÉCHEC] %s : %s",
                file_path.name,
                error
            )

        logger.error(
            "Validation échouée : %s",
            file_path.name
        )

        return False

    logger.info(
        "Validation réussie : %s",
        file_path.name
    )

    return True


# --------------------------------------------------
# 2. Validation d'un mois
# --------------------------------------------------

def validate_month(directory, config):
    """Valide tous les fichiers NetCDF d'un mois."""

    directory = Path(directory)

    logger.info("=" * 60)
    logger.info("VALIDATION DU MOIS : %s", directory.name)
    logger.info("=" * 60)

    extracted_template = config["naming"]["extracted_dir"]
    directory_pattern = _build_extracted_dir_pattern(extracted_template)

    match = re.fullmatch(
        directory_pattern,
        directory.name,
    )

    if not match:
        logger.error(
            "[ÉCHEC] Nom de dossier invalide : %s",
            directory.name
        )
        return False

    year = int(match.group("year"))
    month = int(match.group("month"))

    if not 1 <= month <= 12:
        logger.error(
            "[ÉCHEC] Mois invalide : %s",
            directory.name
        )
        return False

    if not directory.is_dir():
        logger.error(
            "[ÉCHEC] Dossier introuvable : %s",
            directory
        )
        return False

    validation_config = config["validation"]
    results = []

    for file_type, filename in validation_config["files"].items():

        logger.info("Type de fichier : %s", file_type)

        file_path = directory / filename
        variables = validation_config["variables"][file_type]

        result = validate_file(
            file_path,
            variables,
            year,
            month,
            config
        )

        results.append(result)

    if all(results):

        logger.info(
            "[OK] Tous les fichiers du mois %s sont valides",
            directory.name
        )

        return True

    logger.error(
        "[ÉCHEC] Validation du mois %s",
        directory.name
    )

    return False


# --------------------------------------------------
# 3. Validation de tous les mois
# --------------------------------------------------

def validate_all(config: dict | None = None) -> bool:
    """Valide tous les mois attendus dans le dossier interim."""

    if config is None:
        config = load_config()

    interim_directory = (
        PROJECT_ROOT / config["paths"]["interim"]
    )

    logger.info("Dossier à valider : %s", interim_directory)

    start_date = date.fromisoformat(config["data"]["start_date"])
    end_date = date.fromisoformat(config["data"]["end_date"])

    if start_date > end_date:
        logger.error("[ÉCHEC] Période de configuration invalide")
        return False

    expected_months = pd.date_range(
        start=pd.Timestamp(
            year=start_date.year,
            month=start_date.month,
            day=1,
        ),
        end=pd.Timestamp(
            year=end_date.year,
            month=end_date.month,
            day=1,
        ),
        freq="MS",
    )

    extracted_template = config["naming"]["extracted_dir"]

    total_count = len(expected_months)
    valid_count = 0
    missing_count = 0
    invalid_count = 0

    logger.info(
        "Nombre de mois à valider : %s",
        total_count
    )

    for expected_month in expected_months:

        month_name = extracted_template.format(
            year=expected_month.year,
            month=f"{expected_month.month:02d}",
        )

        directory = interim_directory / month_name

        if not directory.is_dir():
            logger.error(
                "[ÉCHEC] Mois manquant : %s",
                month_name,
            )
            missing_count += 1
            continue

        if validate_month(directory, config):
            valid_count += 1
        else:
            invalid_count += 1

    logger.info("=" * 60)
    logger.info("BILAN GLOBAL DE VALIDATION")
    logger.info("Mois valides : %s", valid_count)
    logger.info("Mois manquants : %s", missing_count)
    logger.info("Mois invalides : %s", invalid_count)
    logger.info("Total des mois attendus : %s", total_count)
    logger.info("=" * 60)

    return (
        total_count > 0
        and valid_count == total_count
        and missing_count == 0
        and invalid_count == 0
    )

def main() -> None:
    from era5_tunisia.logging_config import setup_logging

    setup_logging()

    logger.info("Validator started")

    result = validate_all()

    logger.info("Validator finished")

    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()