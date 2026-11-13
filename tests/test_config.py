from era5_tunisia.config import load_config


def test_load_config():

    config = load_config()

    assert config is not None
    assert isinstance(config, dict)