import hashlib
import logging
import re
import shutil
import tempfile
import uuid
import zipfile

from pathlib import Path, PurePosixPath

from era5_tunisia.config import PROJECT_ROOT, load_config


logger = logging.getLogger(__name__)

# Fichier qui contient l'empreinte SHA-256 de l'archive extraite.
CHECKSUM_FILE = ".extraction_complete"


def calculate_sha256(file_path: Path) -> str:
    """
    Calcule l'empreinte SHA-256 d'un fichier.
    """

    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(8192), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def get_archive_info(
    archive_path: Path,
    archive_template: str
) -> tuple[str, str]:
    """
    Récupère l'année et le mois à partir du nom de l'archive.
    """

    pattern = re.escape(archive_template)

    pattern = pattern.replace(
        re.escape("{year}"),
        r"(?P<year>\d{4})"
    )

    pattern = pattern.replace(
        re.escape("{month}"),
        r"(?P<month>\d{2})"
    )

    match = re.fullmatch(pattern, archive_path.name)

    if not match:
        raise ValueError(
            f"Nom d'archive invalide : {archive_path.name}"
        )

    year = match.group("year")
    month = match.group("month")

    if not 1 <= int(month) <= 12:
        raise ValueError(f"Mois invalide : {month}")

    return year, month


def is_already_extracted(
    extracted_dir: Path,
    archive_hash: str
) -> bool:
    """
    Vérifie si l'archive a déjà été extraite
    et si son empreinte correspond à celle enregistrée.
    """

    marker_file = extracted_dir / CHECKSUM_FILE

    if not marker_file.is_file():
        return False

    saved_hash = marker_file.read_text(
        encoding="utf-8"
    ).strip()

    return saved_hash == archive_hash


def validate_archive(archive_path: Path) -> None:
    """
    Vérifie l'intégrité de l'archive ZIP.
    """

    with zipfile.ZipFile(archive_path, "r") as archive:

        corrupted_file = archive.testzip()

        if corrupted_file is not None:
            raise zipfile.BadZipFile(
                f"Fichier corrompu : {corrupted_file}"
            )


def validate_zip_paths(archive: zipfile.ZipFile) -> None:
    """
    Empêche l'extraction de fichiers en dehors
    du dossier de destination (protection ZIP Slip).
    """

    for member in archive.infolist():

        member_name = member.filename.replace("\\", "/")
        member_path = PurePosixPath(member_name)

        if (
            member_path.is_absolute()
            or ".." in member_path.parts
            or (member_path.parts and ":" in member_path.parts[0])
        ):
            raise ValueError(
                f"Chemin dangereux dans le ZIP : {member.filename}"
            )


def save_checksum(
    extracted_dir: Path,
    archive_hash: str
) -> None:
    """
    Enregistre l'empreinte SHA-256 dans le dossier extrait.
    """

    marker_file = extracted_dir / CHECKSUM_FILE

    marker_file.write_text(
        archive_hash,
        encoding="utf-8"
    )


def extract_archive(
    archive_path: Path,
    extracted_dir: Path,
    archive_hash: str
) -> None:
    """
    Extrait une archive ZIP dans un dossier temporaire,
    puis remplace le dossier de destination.
    """

    extracted_dir.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temporary_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{extracted_dir.name}.tmp-",
            dir=extracted_dir.parent
        )
    )

    backup_dir = (
        extracted_dir.parent
        / f".{extracted_dir.name}.backup-{uuid.uuid4().hex}"
    )

    backup_created = False

    try:

        # Vérification de l'intégrité du ZIP.
        validate_archive(archive_path)

        # Extraction dans le dossier temporaire.
        with zipfile.ZipFile(archive_path, "r") as archive:

            validate_zip_paths(archive)

            archive.extractall(temporary_dir)

        # Enregistrement de l'empreinte SHA-256.
        save_checksum(
            temporary_dir,
            archive_hash
        )

        # Sauvegarde de l'ancien dossier, s'il existe.
        if extracted_dir.exists() or extracted_dir.is_symlink():

            extracted_dir.rename(backup_dir)
            backup_created = True

        try:

            # Installation du nouveau dossier extrait.
            temporary_dir.rename(extracted_dir)

        except Exception:

            # Restauration de l'ancien dossier en cas d'échec.
            if backup_created:
                backup_dir.rename(extracted_dir)
                backup_created = False

            raise

        # Suppression de l'ancien dossier après succès.
        if backup_created:
            shutil.rmtree(backup_dir)
            backup_created = False

        logger.info(
            "Extraction terminée : %s",
            archive_path.name
        )

    finally:

        # Nettoyage du dossier temporaire.
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir, ignore_errors=True)


def extract_all() -> None:
    """
    Parcourt toutes les archives ZIP présentes dans raw/
    et extrait celles qui nécessitent une extraction.
    """

    # Chargement de la configuration centrale.
    config = load_config()

    # Lecture des chemins depuis config.yaml.
    raw_dir = PROJECT_ROOT / config["paths"]["raw"]

    interim_dir = PROJECT_ROOT / config["paths"]["interim"]

    # Lecture des conventions de nommage.
    archive_template = config["naming"]["raw_archive"]

    extracted_template = config["naming"]["extracted_dir"]

    # Vérification du dossier source.
    if not raw_dir.is_dir():
        raise FileNotFoundError(
            f"Dossier raw introuvable : {raw_dir}"
        )

    # Création du dossier de destination.
    interim_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    # Récupération des archives ZIP.
    archives = sorted(raw_dir.glob("*.zip"))

    if not archives:
        logger.warning("Aucune archive ZIP trouvée dans raw/.")
        return

    logger.info(
        "%s archive(s) trouvée(s).",
        len(archives)
    )

    extracted_count = 0
    skipped_count = 0
    failed_count = 0

    for archive_path in archives:

        try:

            # Identification de l'année et du mois.
            year, month = get_archive_info(
                archive_path,
                archive_template
            )

            # Construction du nom du dossier extrait.
            extracted_name = extracted_template.format(
                year=year,
                month=month
            )

            extracted_dir = interim_dir / extracted_name

            # Calcul de l'empreinte du ZIP.
            archive_hash = calculate_sha256(archive_path)

            # Vérification d'une extraction précédente.
            if is_already_extracted(
                extracted_dir,
                archive_hash
            ):

                logger.info(
                    "Déjà extrait, ignoré : %s",
                    archive_path.name
                )

                skipped_count += 1
                continue

            # Extraction de l'archive.
            extract_archive(
                archive_path,
                extracted_dir,
                archive_hash
            )

            extracted_count += 1

        except (
            OSError,
            ValueError,
            zipfile.BadZipFile,
            KeyError
        ) as error:

            logger.error(
                "Échec de traitement de %s : %s",
                archive_path.name,
                error
            )

            failed_count += 1

    logger.info("========== Résultat de l'extraction ==========")
    logger.info("Archives extraites : %s", extracted_count)
    logger.info("Archives ignorées : %s", skipped_count)
    logger.info("Archives en échec : %s", failed_count)


if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    extract_all()