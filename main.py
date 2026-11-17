"""Interface en ligne de commande du projet ERA5 Tunisia Climate."""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from era5_tunisia.acquisition.cds_client import create_cds_client
from era5_tunisia.acquisition.downloader import download_month
from era5_tunisia.config import load_config
from era5_tunisia.extraction.extractor import extract_month
from era5_tunisia.logging_config import setup_logging
from era5_tunisia.pipeline import (
    days_for_month,
    iter_months,
    month_label,
    resolve_month_paths,
    run_pipeline,
)
from era5_tunisia.processing.preprocessor import preprocess_month
from era5_tunisia.processing.transformations import apply_transformations
from era5_tunisia.storage.netcdf_writer import write_netcdf
from era5_tunisia.validation.validator import validate_month


logger = logging.getLogger(__name__)

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2


def _month_type(value: str) -> tuple[int, int]:
    """Convertit une valeur ``YYYY-MM`` en tuple (année, mois)."""

    try:
        parsed = date.fromisoformat(f"{value}-01")
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"Mois invalide, format attendu YYYY-MM : {value}"
        ) from error

    return (parsed.year, parsed.month)


def _add_month_options(parser: argparse.ArgumentParser) -> None:
    """Ajoute les options de sélection des mois à un sous-parseur."""

    parser.add_argument(
        "--start",
        type=_month_type,
        default=None,
        metavar="YYYY-MM",
        help="Premier mois à traiter.",
    )
    parser.add_argument(
        "--end",
        type=_month_type,
        default=None,
        metavar="YYYY-MM",
        help="Dernier mois à traiter.",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Année d'un mois unique.",
    )
    parser.add_argument(
        "--month",
        type=int,
        default=None,
        help="Mois (1-12) d'un mois unique.",
    )


def _add_execution_options(parser: argparse.ArgumentParser) -> None:
    """Ajoute les options d'exécution communes."""

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force le retéléchargement et la réécriture.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simule sans télécharger ni écrire.",
    )


def build_parser() -> argparse.ArgumentParser:
    """Construit le parseur de la CLI."""

    parser = argparse.ArgumentParser(
        prog="era5-tunisia",
        description="Acquisition et préparation des données ERA5.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Fichier de configuration YAML.",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="Niveau de logging (DEBUG, INFO, WARNING, ...).",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Exécute le pipeline complet sur une période.",
    )
    _add_month_options(run_parser)
    _add_execution_options(run_parser)
    run_parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Arrête le pipeline au premier échec.",
    )

    status_parser = subparsers.add_parser(
        "status",
        help="Affiche l'état des mois attendus.",
    )
    _add_month_options(status_parser)

    download_parser = subparsers.add_parser(
        "download",
        help="Télécharge les archives mensuelles.",
    )
    _add_month_options(download_parser)
    _add_execution_options(download_parser)

    extract_parser = subparsers.add_parser(
        "extract",
        help="Extrait les archives mensuelles.",
    )
    _add_month_options(extract_parser)
    _add_execution_options(extract_parser)

    validate_parser = subparsers.add_parser(
        "validate",
        help="Valide les données mensuelles extraites.",
    )
    _add_month_options(validate_parser)

    process_parser = subparsers.add_parser(
        "process",
        help="Prépare les fichiers NetCDF traités.",
    )
    _add_month_options(process_parser)
    _add_execution_options(process_parser)

    return parser


def _configure_logging(args: argparse.Namespace) -> None:
    """Configure le logging une seule fois par invocation."""

    if args.command == "status":
        # La commande status ne doit écrire aucun fichier.
        logging.basicConfig(
            level=args.log_level or "INFO",
            format="%(levelname)s - %(message)s",
        )
        return

    setup_logging(level=args.log_level)


def _resolve_months(
    args: argparse.Namespace,
    config: dict,
) -> list[tuple[int, int]]:
    """Détermine les mois à traiter depuis les options ou la config."""

    if args.year is not None or args.month is not None:

        if args.year is None or args.month is None:
            raise ValueError(
                "--year et --month doivent être fournis ensemble."
            )

        if not 1 <= args.month <= 12:
            raise ValueError("--month doit être compris entre 1 et 12.")

        return [(args.year, args.month)]

    start = args.start or _month_type(config["data"]["start_date"][:7])
    end = args.end or _month_type(config["data"]["end_date"][:7])

    return list(
        iter_months(
            date(start[0], start[1], 1),
            date(end[0], end[1], 1),
        )
    )


def _handle_status(
    args: argparse.Namespace,
    config: dict,
    months: list[tuple[int, int]],
) -> int:
    """Affiche l'état des fichiers sans rien écrire."""

    for month in months:

        paths = resolve_month_paths(config, month)

        print(
            f"{month_label(month)}: "
            f"zip={'oui' if paths['raw_archive'].is_file() else 'non'} "
            f"extrait={'oui' if paths['interim_dir'].is_dir() else 'non'} "
            f"traité={'oui' if paths['processed_file'].is_file() else 'non'}"
        )

    return EXIT_SUCCESS


def _handle_run(
    args: argparse.Namespace,
    config: dict,
    months: list[tuple[int, int]],
) -> int:
    """Exécute le pipeline complet."""

    client = None if args.dry_run else create_cds_client(config)

    result = run_pipeline(
        client,
        config,
        months,
        force=args.force,
        dry_run=args.dry_run,
        fail_fast=args.fail_fast,
    )

    return EXIT_SUCCESS if result["failed_count"] == 0 else EXIT_FAILURE


def _handle_download(
    args: argparse.Namespace,
    config: dict,
    months: list[tuple[int, int]],
) -> int:
    """Télécharge une seule archive par mois."""

    if args.dry_run:

        for month in months:
            logger.info("[dry-run] Téléchargement simulé : %s", month_label(month))

        return EXIT_SUCCESS

    client = create_cds_client(config)
    failures = 0

    for month in months:

        year, month_number = month

        try:
            download_month(
                client,
                config,
                year,
                month_number,
                days_for_month(config, month),
                force=args.force,
            )
        except Exception:

            logger.exception("Échec du téléchargement : %s", month_label(month))
            failures += 1

    return EXIT_SUCCESS if failures == 0 else EXIT_FAILURE


def _handle_extract(
    args: argparse.Namespace,
    config: dict,
    months: list[tuple[int, int]],
) -> int:
    """Extrait les archives mensuelles."""

    failures = 0

    for month in months:

        paths = resolve_month_paths(config, month)

        if args.dry_run:
            logger.info("[dry-run] Extraction simulée : %s", month_label(month))
            continue

        if not paths["raw_archive"].is_file():

            logger.error("Archive absente : %s", paths["raw_archive"])
            failures += 1
            continue

        try:
            extract_month(
                paths["raw_archive"],
                paths["interim_dir"],
                config,
                force=args.force,
            )
        except Exception:

            logger.exception("Échec de l'extraction : %s", month_label(month))
            failures += 1

    return EXIT_SUCCESS if failures == 0 else EXIT_FAILURE


def _handle_validate(
    args: argparse.Namespace,
    config: dict,
    months: list[tuple[int, int]],
) -> int:
    """Valide les mois demandés."""

    failures = 0

    for month in months:

        paths = resolve_month_paths(config, month)

        if not validate_month(paths["interim_dir"], config):
            failures += 1

    return EXIT_SUCCESS if failures == 0 else EXIT_FAILURE


def _process_month(
    config: dict,
    month: tuple[int, int],
    *,
    force: bool,
) -> None:
    """Prépare et écrit le fichier traité d'un mois."""

    paths = resolve_month_paths(config, month)

    if not validate_month(paths["interim_dir"], config):
        raise ValueError(f"Validation échouée pour le mois {month_label(month)}.")

    dataset = preprocess_month(paths["interim_dir"], config)

    try:
        dataset = apply_transformations(dataset)
        write_netcdf(
            dataset,
            paths["processed_file"],
            overwrite=force,
        )
    finally:
        dataset.close()


def _handle_process(
    args: argparse.Namespace,
    config: dict,
    months: list[tuple[int, int]],
) -> int:
    """Prépare les fichiers traités depuis les données extraites."""

    failures = 0

    for month in months:

        paths = resolve_month_paths(config, month)

        if not args.force and paths["processed_file"].exists():
            logger.info("Déjà traité, ignoré : %s", paths["processed_file"].name)
            continue

        if args.dry_run:
            logger.info("[dry-run] Traitement simulé : %s", month_label(month))
            continue

        try:
            _process_month(config, month, force=args.force)
        except Exception:

            logger.exception("Échec du traitement : %s", month_label(month))
            failures += 1

    return EXIT_SUCCESS if failures == 0 else EXIT_FAILURE


HANDLERS = {
    "run": _handle_run,
    "status": _handle_status,
    "download": _handle_download,
    "extract": _handle_extract,
    "validate": _handle_validate,
    "process": _handle_process,
}


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée de la CLI. Retourne un code de sortie."""

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as error:
        print(f"Erreur de configuration : {error}", file=sys.stderr)
        return EXIT_USAGE

    _configure_logging(args)

    try:
        months = _resolve_months(args, config)
    except ValueError as error:
        logger.error("Erreur d'usage : %s", error)
        return EXIT_USAGE

    return HANDLERS[args.command](args, config, months)


if __name__ == "__main__":
    sys.exit(main())
