"""Orchestration séquentielle du pipeline mensuel ERA5.

Les mois sont représentés par des tuples ``(année, mois)`` et les
résultats par des dictionnaires, sans classe dédiée.
"""

import calendar
import logging
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import xarray as xr

from era5_tunisia.acquisition.downloader import download_month
from era5_tunisia.config import PROJECT_ROOT
from era5_tunisia.extraction.extractor import extract_month
from era5_tunisia.processing.preprocessor import preprocess_month
from era5_tunisia.processing.transformations import apply_transformations
from era5_tunisia.storage.netcdf_writer import write_netcdf
from era5_tunisia.validation.validator import validate_month


logger = logging.getLogger(__name__)

STATUS_SUCCESS = "success"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"


def month_label(month: tuple[int, int]) -> str:
    """Retourne le libellé ``YYYY-MM`` d'un mois."""

    year, month_number = month
    return f"{year}-{month_number:02d}"


def iter_months(start: date, end: date) -> Iterator[tuple[int, int]]:
    """Itère sur les mois entre deux dates, bornes incluses."""

    if start > end:
        raise ValueError("La date de début doit précéder la date de fin.")

    current = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)

    while current <= last:

        yield (current.year, current.month)

        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def resolve_month_paths(config: dict, month: tuple[int, int]) -> dict:
    """Construit les chemins d'un mois depuis la configuration."""

    year, month_number = month
    month_text = f"{month_number:02d}"

    naming = config["naming"]
    paths = config["paths"]

    raw_archive = PROJECT_ROOT / paths["raw"] / naming["raw_archive"].format(
        year=year,
        month=month_text,
    )
    interim_dir = PROJECT_ROOT / paths["interim"] / naming["extracted_dir"].format(
        year=year,
        month=month_text,
    )
    processed_file = (
        PROJECT_ROOT
        / paths["processed"]
        / naming["processed_file"].format(
            year=year,
            month=month_text,
        )
    )

    return {
        "raw_archive": Path(raw_archive),
        "interim_dir": Path(interim_dir),
        "processed_file": Path(processed_file),
    }


def days_for_month(config: dict, month: tuple[int, int]) -> list[str]:
    """Jours du mois, restreints à la période configurée."""

    year, month_number = month

    first_day = date(year, month_number, 1)
    last_day = date(
        year,
        month_number,
        calendar.monthrange(year, month_number)[1],
    )

    period_start = date.fromisoformat(config["data"]["start_date"])
    period_end = date.fromisoformat(config["data"]["end_date"])

    start = max(period_start, first_day)
    end = min(period_end, last_day)

    if start > end:
        raise ValueError(
            f"Le mois {month_label(month)} est hors de la période configurée."
        )

    return [
        date.fromordinal(ordinal).strftime("%d")
        for ordinal in range(start.toordinal(), end.toordinal() + 1)
    ]


def run_month(
    client,
    config: dict,
    month: tuple[int, int],
    *,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    """Traite un mois complet, une seule requête CDS.

    Le fichier traité existant est réutilisé si ``force`` est faux.
    En mode ``dry_run``, rien n'est téléchargé ni écrit.
    """

    started_at = time.perf_counter()
    paths = resolve_month_paths(config, month)

    if not force and paths["processed_file"].exists():

        logger.info(
            "Déjà traité, ignoré : %s",
            paths["processed_file"].name,
        )

        return {
            "month": month,
            "status": STATUS_SKIPPED,
            "paths": paths,
            "error": None,
            "duration": time.perf_counter() - started_at,
        }

    if dry_run:

        logger.info(
            "[dry-run] Mois %s : téléchargement et écriture simulés.",
            month_label(month),
        )

        return {
            "month": month,
            "status": STATUS_SKIPPED,
            "paths": paths,
            "error": None,
            "duration": time.perf_counter() - started_at,
        }

    dataset: xr.Dataset | None = None
    status = STATUS_FAILED
    error_message: str | None = None

    try:

        days = days_for_month(config, month)

        archive_path = download_month(
            client,
            config,
            month[0],
            month[1],
            days,
            force=force,
        )

        extract_month(
            archive_path,
            paths["interim_dir"],
            config,
            force=force,
        )

        if not validate_month(paths["interim_dir"], config):
            raise ValueError(
                f"Validation échouée pour le mois {month_label(month)}."
            )

        dataset = preprocess_month(paths["interim_dir"], config)
        dataset = apply_transformations(dataset)

        write_netcdf(
            dataset,
            paths["processed_file"],
            overwrite=force,
        )

        status = STATUS_SUCCESS

    except Exception as error:

        logger.exception(
            "Échec du traitement du mois %s",
            month_label(month),
        )
        error_message = str(error)

    finally:

        if dataset is not None:
            dataset.close()

    return {
        "month": month,
        "status": status,
        "paths": paths,
        "error": error_message,
        "duration": time.perf_counter() - started_at,
    }


def run_pipeline(
    client,
    config: dict,
    months,
    *,
    force: bool = False,
    dry_run: bool = False,
    fail_fast: bool = False,
) -> dict:
    """Traite les mois séquentiellement et retourne un bilan."""

    summary = {
        "results": [],
        "success_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
    }

    for month in months:

        result = run_month(
            client,
            config,
            month,
            force=force,
            dry_run=dry_run,
        )

        summary["results"].append(result)

        if result["status"] == STATUS_SUCCESS:
            summary["success_count"] += 1
        elif result["status"] == STATUS_SKIPPED:
            summary["skipped_count"] += 1
        else:
            summary["failed_count"] += 1

        if result["status"] == STATUS_FAILED and fail_fast:

            logger.error(
                "Arrêt immédiat après l'échec du mois %s.",
                month_label(month),
            )
            break

    logger.info(
        "Bilan du pipeline : %s réussis, %s ignorés, %s échoués.",
        summary["success_count"],
        summary["skipped_count"],
        summary["failed_count"],
    )

    return summary
