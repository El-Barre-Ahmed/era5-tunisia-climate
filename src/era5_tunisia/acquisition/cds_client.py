
import cdsapi

from era5_tunisia.config import load_config


def create_cds_client():
    """Créer et retourner un client CDS."""

    config = load_config()

    timeout = config["acquisition"]["timeout_seconds"]

    client = cdsapi.Client(timeout=timeout)

    return client
