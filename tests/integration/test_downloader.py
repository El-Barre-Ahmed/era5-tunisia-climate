import logging

from era5_tunisia.config import load_config
from era5_tunisia.logging_config import setup_logging
from era5_tunisia.acquisition.cds_client import create_cds_client
from era5_tunisia.acquisition.downloader import (
    generate_months,
    download_month,
)


def test_download_january_2000():
    """Tester le téléchargement des données ERA5 de janvier 2000."""

    # Initialiser le logging
    setup_logging()

    logger = logging.getLogger(__name__)

    # Charger la configuration
    config = load_config()

    # Créer le client CDS
    client = create_cds_client()

    # Générer le premier mois de la période
    year, month, days = next(
        generate_months(
            config["data"]["start_date"],
            config["data"]["end_date"]
        )
    )

    # Vérifier la période
    assert year == 2000
    assert month == 1

    # Télécharger janvier 2000
    file_path = download_month(
        client,
        config,
        year,
        month,
        days
    )

    # Vérifier que le fichier existe
    assert file_path.exists()

    # Afficher le chemin du fichier
    print(f"\nDownloaded file saved at:\n{file_path}")

    logger.info("January 2000 download test completed successfully.")


if __name__ == "__main__":
    test_download_january_2000()