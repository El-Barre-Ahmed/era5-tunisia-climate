
import logging

from era5_tunisia.logging_config import setup_logging


def test_setup_logging():

    # Initialiser le logging
    setup_logging()

    # Créer un logger
    logger = logging.getLogger("test")

    # Envoyer un message
    logger.info("Hello")

    # Vérifier que le logger existe
    assert logger is not None
