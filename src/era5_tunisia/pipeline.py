"""Orchestration séquentielle du pipeline mensuel ERA5."""

import calendar
import logging
import time
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class Month:
    """Un mois à traiter."""

    year: int
    month: int

    @property
    def label(self) -> str:
        return f"{self.year}-{self.month:02d}"


@dataclass(frozen=True)
class MonthPaths:
    """Chemins associés à un mois."""

    raw_archive: Path
    interim_dir: Path
    processed_file: Path


@dataclass
class MonthResult:
    """Résultat du traitement d'un mois."""

    month: Month
    status: str
    paths: MonthPaths
    error: str | None = None
    duration: float = 0.0


@dataclass
class PipelineResult:
    """Résultat global du pipeline."""

    results: list[MonthResult] = field(default_factory=list)
    success_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0


def iter_months(start: date, end: date):
    """Itère sur les mois entre deux dates, bornes incluses."""

    if start > end:
        raise ValueError("La date de début doit précéder la date de fin.")

    current = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)

    while current <= last:

        yield Month(current.year, current.month)

        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def resolve_month_paths(config: dict, month: Month) -> MonthPaths:
    """Construit les chemins d'un mois depuis la configuration."""

    naming = config["naming"]
    paths = config["paths"]

    month_text = f"{month.month:02d}"

    raw_archive = PROJECT_ROOT / paths["raw"] / naming["raw_archive"].format(
        year=month.year,
        month=month_text,
    )
    interim_dir = PROJECT_ROOT / paths["interim"] / naming["extracted_dir"].format(
        year=month.year,
        month=month_text,
    )
    processed_file = (
        PROJECT_ROOT
        / paths["processed"]
        / naming["processed_file"].format(
            year=month.year,
            month=month_text,
        )
    )

    return MonthPaths(
        raw_archive=Path(raw_archive),
        interim_dir=Path(interim_dir),
        processed_file=Path(processed_file),
    )


def days_for_month(config: dict, month: Month) -> list[str]:
    """Jours du mois, restreints à la période configurée."""

    first_day = date(month.year, month.month, 1)
    last_day = date(
        month.year,
        month.month,
        calendar.monthrange(month.year, month.month)[1],
    )

    period_start = date.fromisoformat(config["data"]["start_date"])
    period_end = date.fromisoformat(config["data"]["end_date"])

    start = max(period_start, first_day)
    end = min(period_end, last_day)

    if start > end:
        raise ValueError(
            f"Le mois {month.label} est hors de la période configurée."
        )

    return [
        date.fromordinal(ordinal).strftime("%d")
        for ordinal in range(start.toordinal(), end.toordinal() + 1)
    ]


def run_month(
    client,
    config: dict,
    month: Month,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> MonthResult:
    """Traite un mois complet, une seule requête CDS.

    Le fichier traité existant est réutilisé si ``force`` est faux.
    En mode ``dry_run``, rien n'est téléchargé ni écrit.
    """

    started_at = time.perf_counter()
    paths = resolve_month_paths(config, month)

    if not force and paths.processed_file.exists():

        logger.info(
            "Déjà traité, ignoré : %s",
            paths.processed_file.name,
        )

        return MonthResult(
            month=month,
            status=STATUS_SKIPPED,
            paths=paths,
            duration=time.perf_counter() - started_at,
        )

    if dry_run:

        logger.info(
            "[dry-run] Mois %s : téléchargement et écriture simulés.",
            month.label,
        )

        return MonthResult(
            month=month,
            status=STATUS_SKIPPED,
            paths=paths,
            duration=time.perf_counter() - started_at,
        )

    dataset: xr.Dataset | None = None
    status = STATUS_FAILED
    error_message: str | None = None

    try:

        days = days_for_month(config, month)

        archive_path = download_month(
            client,
            config,
            month.year,
            month.month,
            days,
            force=force,
        )

        extract_month(
            archive_path,
            paths.interim_dir,
            config,
            force=force,
        )

        if not validate_month(paths.interim_dir, config):
            raise ValueError(
                f"Validation échouée pour le mois {month.label}."
            )

        dataset = preprocess_month(paths.interim_dir, config)
        dataset = apply_transformations(dataset)

        write_netcdf(
            dataset,
            paths.processed_file,
            overwrite=force,
        )

        status = STATUS_SUCCESS

    except Exception as error:

        logger.exception(
            "Échec du traitement du mois %s",
            month.label,
        )
        error_message = str(error)

    finally:

        if dataset is not None:
            dataset.close()

    return MonthResult(
        month=month,
        status=status,
        paths=paths,
        error=error_message,
        duration=time.perf_counter() - started_at,
    )


def run_pipeline(
    client,
    config: dict,
    months,
    *,
    force: bool = False,
    dry_run: bool = False,
    fail_fast: bool = False,
) -> PipelineResult:
    """Traite les mois séquentiellement et retourne un bilan."""

    pipeline_result = PipelineResult()

    for month in months:

        result = run_month(
            client,
            config,
            month,
            force=force,
            dry_run=dry_run,
        )

        pipeline_result.results.append(result)

        if result.status == STATUS_SUCCESS:
            pipeline_result.success_count += 1
        elif result.status == STATUS_SKIPPED:
            pipeline_result.skipped_count += 1
        else:
            pipeline_result.failed_count += 1

        if result.status == STATUS_FAILED and fail_fast:

            logger.error(
                "Arrêt immédiat après l'échec du mois %s.",
                month.label,
            )
            break

    logger.info(
        "Bilan du pipeline : %s réussis, %s ignorés, %s échoués.",
        pipeline_result.success_count,
        pipeline_result.skipped_count,
        pipeline_result.failed_count,
    )

    return pipeline_result
