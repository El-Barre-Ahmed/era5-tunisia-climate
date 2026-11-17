"""Gestion de l'écriture des fichiers NetCDF."""

import logging
import os
import tempfile
from contextlib import suppress
from pathlib import Path

import xarray as xr


logger = logging.getLogger(__name__)


# --------------------------------------------------
# 1. Écriture d'un Dataset au format NetCDF
# --------------------------------------------------

def write_netcdf(
    dataset: xr.Dataset,
    output_file: Path,
    overwrite: bool = False,
) -> Path:
    """
    Enregistre un Dataset dans un fichier NetCDF.

    L'écriture est d'abord effectuée dans un fichier temporaire.
    Le fichier final est remplacé uniquement après réussite.
    """

    output_file = Path(output_file)

    # Créer le dossier de destination si nécessaire.
    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Vérifier si le fichier existe déjà.
    if output_file.exists() and not overwrite:

        raise FileExistsError(
            f"Le fichier existe déjà : {output_file}"
        )

    temporary_file = None

    try:

        # Créer un fichier temporaire unique dans le même dossier.
        with tempfile.NamedTemporaryFile(
            prefix=f".{output_file.stem}_",
            suffix=".tmp.nc",
            dir=output_file.parent,
            delete=False,
        ) as temporary:

            temporary_file = Path(temporary.name)

        logger.info(
            "Écriture du fichier NetCDF : %s",
            output_file,
        )

        # Écrire les données dans le fichier temporaire.
        dataset.to_netcdf(temporary_file)

        # Remplacer le fichier final après réussite.
        os.replace(
            temporary_file,
            output_file,
        )

        logger.info(
            "Fichier NetCDF enregistré avec succès : %s",
            output_file,
        )

        return output_file

    except Exception:

        logger.exception(
            "Erreur pendant l'écriture du fichier : %s",
            output_file,
        )

        raise

    finally:

        # Nettoyer le fichier temporaire en cas d'échec.
        if temporary_file is not None:

            with suppress(FileNotFoundError):
                temporary_file.unlink()