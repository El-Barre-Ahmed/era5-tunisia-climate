
import argparse
import calendar
import logging
import time

from datetime import date, timedelta
from pathlib import Path
from zipfile import ZipFile, BadZipFile

from era5_tunisia.config import load_config, PROJECT_ROOT
from era5_tunisia.logging_config import setup_logging
from era5_tunisia.acquisition.cds_client import create_cds_client


# Logger du module
logger = logging.getLogger(__name__)


# Correspondance entre les noms courts et les noms CDS
VARIABLE_MAPPING = {
    "t2m": "2m_temperature",
    "tp": "total_precipitation",
    "u10": "10m_u_component_of_wind",
    "v10": "10m_v_component_of_wind",
}


def generate_months(start_date, end_date):
    """Générer les périodes mensuelles entre deux dates."""

    current = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    if current > end:
        raise ValueError("La date de début doit précéder la date de fin.")

    while current <= end:

        year = current.year
        month = current.month

        last_day = calendar.monthrange(year, month)[1]

        first_day = date(year, month, 1)
        last_date = date(year, month, last_day)

        period_start = max(current, first_day)
        period_end = min(end, last_date)

        days = [
            (period_start + timedelta(days=i)).strftime("%d")
            for i in range((period_end - period_start).days + 1)
        ]

        yield year, month, days

        current = last_date + timedelta(days=1)


def build_request(config, year, month, days):
    """Construire la requête CDS pour un mois."""

    data = config["data"]
    acquisition = config["acquisition"]

    variables = [
        VARIABLE_MAPPING[variable]
        for variable in data["variables"]
    ]

    request = {
        "product_type": [data["product_type"]],
        "variable": variables,
        "year": [str(year)],
        "month": [f"{month:02d}"],
        "day": days,
        "time": [f"{hour:02d}:00" for hour in range(24)],
        "area": data["area"],
        "data_format": acquisition["data_format"],
        "download_format": acquisition["download_format"],
    }

    return request


def is_valid_zip(file_path):
    """Vérifier l'intégrité d'une archive ZIP."""

    try:
        with ZipFile(file_path, "r") as archive:

            return (
                archive.testzip() is None
                and len(archive.namelist()) > 0
            )

    except (BadZipFile, OSError):
        return False


def download_month(
    client,
    config,
    year,
    month,
    days,
    *,
    force: bool = False,
) -> Path:
    """Télécharger les données ERA5 pour un mois.

    Si ``force`` est vrai, une archive existante est supprimée puis
    téléchargée à nouveau. Sinon, une archive valide est réutilisée.
    """

    raw_dir = PROJECT_ROOT / config["paths"]["raw"]
    raw_dir.mkdir(parents=True, exist_ok=True)

    filename = config["naming"]["raw_archive"].format(
        year=year,
        month=f"{month:02d}"
    )

    output_file = raw_dir / filename
    temp_file = output_file.with_name(output_file.name + ".part")

    acquisition = config["acquisition"]

    retries = acquisition["retries"]
    if retries <= 0:
        raise ValueError(
            "acquisition.retries doit être supérieur ou égal à 1."
        )

    base_delay = acquisition["retry_base_seconds"]
    max_delay = acquisition["retry_max_seconds"]

    # Vérifier si le fichier existe déjà
    if output_file.exists():

        if not force and is_valid_zip(output_file):
            logger.info("Already downloaded: %s", output_file.name)
            return output_file

        if force:
            logger.info(
                "Forced download, removing existing archive: %s",
                output_file.name,
            )
        else:
            logger.warning("Invalid archive: %s", output_file.name)

        output_file.unlink()

    dataset = config["data"]["dataset"]
    request = build_request(config, year, month, days)

    # Télécharger avec plusieurs tentatives
    for attempt in range(1, retries + 1):

        try:
            logger.info(
                "Downloading ERA5 %04d-%02d (attempt %d/%d)",
                year, month, attempt, retries
            )

            if temp_file.exists():
                temp_file.unlink()

            client.retrieve(
                dataset,
                request,
                str(temp_file)
            )

            # Vérifier l'archive téléchargée
            if not is_valid_zip(temp_file):
                raise ValueError("Downloaded ZIP archive is invalid.")

            # Déplacer le fichier temporaire vers sa destination finale
            temp_file.replace(output_file)

            logger.info("Download completed: %s", output_file.name)

            return output_file

        except Exception:

            logger.exception(
                "Download failed for %04d-%02d (attempt %d/%d)",
                year, month, attempt, retries
            )

            if temp_file.exists():
                temp_file.unlink()

            if attempt == retries:
                raise

            delay = min(
                base_delay * (2 ** (attempt - 1)),
                max_delay
            )

            logger.info("Retrying in %d seconds", delay)
            time.sleep(delay)


def download_period(client, year=None, month=None):
    """Télécharger toute la période ou un mois spécifique."""

    config = load_config()

    start_date = date.fromisoformat(config["data"]["start_date"])
    end_date = date.fromisoformat(config["data"]["end_date"])

    if config["acquisition"]["unit"] != "month":
        raise ValueError("Only monthly acquisition is supported.")

    if (year is None) != (month is None):
        raise ValueError("Year and month must be provided together.")

    # Mode 1 : téléchargement d'un mois spécifique
    if year is not None:

        if not 1 <= month <= 12:
            raise ValueError("Month must be between 1 and 12.")

        month_start = date(year, month, 1)

        month_end = date(
            year,
            month,
            calendar.monthrange(year, month)[1]
        )

        period_start = max(start_date, month_start)
        period_end = min(end_date, month_end)

        if period_start > period_end:
            raise ValueError("Selected month is outside configured period.")

        days = [
            (period_start + timedelta(days=i)).strftime("%d")
            for i in range((period_end - period_start).days + 1)
        ]

        logger.info("Starting ERA5 acquisition for %04d-%02d", year, month)

        download_month(
            client,
            config,
            year,
            month,
            days
        )

        logger.info("Monthly acquisition completed.")

        return

    # Mode 2 : téléchargement de toute la période
    logger.info("Starting ERA5 acquisition")
    logger.info("Period: %s to %s", start_date, end_date)

    months_processed = 0

    for year, month, days in generate_months(
        str(start_date),
        str(end_date)
    ):

        download_month(
            client,
            config,
            year,
            month,
            days
        )

        months_processed += 1

    logger.info(
        "Acquisition completed. Months processed: %d",
        months_processed
    )


def main():
    """Point d'entrée du module Downloader."""

    parser = argparse.ArgumentParser(
        description="ERA5 monthly data downloader"
    )

    parser.add_argument(
        "--year",
        type=int,
        help="Année à télécharger"
    )

    parser.add_argument(
        "--month",
        type=int,
        help="Mois à télécharger (1-12)"
    )

    args = parser.parse_args()

    if (args.year is None) != (args.month is None):
        parser.error("--year et --month doivent être fournis ensemble.")

    setup_logging()

    logger.info("ERA5 Downloader started")

    client = create_cds_client()

    download_period(
        client,
        year=args.year,
        month=args.month
    )

    logger.info("ERA5 Downloader finished")


if __name__ == "__main__":
    main()