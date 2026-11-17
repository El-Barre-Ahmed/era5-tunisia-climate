import pytest

import era5_tunisia.acquisition.cds_client as cds_client_module
from era5_tunisia.acquisition.cds_client import create_cds_client


def test_create_cds_client_uses_provided_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received_options: dict = {}
    client_sentinel = object()

    def _fake_client(**options):
        received_options.update(options)
        return client_sentinel

    def _unexpected_load_config(*args, **kwargs):
        raise AssertionError(
            "load_config ne doit pas être appelé quand une config est fournie."
        )

    monkeypatch.setattr(cds_client_module.cdsapi, "Client", _fake_client)
    monkeypatch.setattr(
        cds_client_module,
        "load_config",
        _unexpected_load_config,
    )

    client = create_cds_client(
        {"acquisition": {"timeout_seconds": 42}}
    )

    assert client is client_sentinel
    assert received_options == {"timeout": 42}


def test_create_cds_client_loads_default_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received_options: dict = {}

    monkeypatch.setattr(
        cds_client_module,
        "load_config",
        lambda: {"acquisition": {"timeout_seconds": 7}},
    )
    monkeypatch.setattr(
        cds_client_module.cdsapi,
        "Client",
        lambda **options: received_options.update(options),
    )

    assert create_cds_client() is None
    assert received_options == {"timeout": 7}
