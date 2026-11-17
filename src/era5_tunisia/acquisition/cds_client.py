
import cdsapi

from era5_tunisia.config import load_config


def create_cds_client(config: dict | None = None):
    """Créer et retourner un client CDS.

    Args:
        config: Configuration déjà chargée. Si ``None``, la configuration
            par défaut (``config/config.yaml``) est chargée.
    """

    if config is None:
        config = load_config()

    timeout = config["acquisition"]["timeout_seconds"]

    client = cdsapi.Client(timeout=timeout)

    return client
