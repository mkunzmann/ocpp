"""Tests for tracking energy usage per RFID tag."""

import pytest

pytest_homeassistant_custom_component = pytest.importorskip(
    "pytest_homeassistant_custom_component"
)
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_socket import enable_socket, socket_allow_hosts

from custom_components.ocpp.const import (
    CONF_CPID,
    CONF_CPIDS,
    CONF_PORT,
    DOMAIN as OCPP_DOMAIN,
)

from .charge_point_test import create_configuration, remove_configuration
from .charger_simulator import run_simulated_session
from .const import MOCK_CONFIG_CP_APPEND, MOCK_CONFIG_DATA


@pytest.mark.enable_socket
@pytest.mark.asyncio
async def test_energy_is_aggregated_per_rfid_tag(hass):
    """Verify that session energy is stored per RFID tag across chargers."""

    pytest.importorskip("websockets")

    config = {**MOCK_CONFIG_DATA}
    config[CONF_CPIDS] = [
        {"CP_SIM_1": {**MOCK_CONFIG_CP_APPEND, CONF_CPID: "sim1"}},
        {"CP_SIM_2": {**MOCK_CONFIG_CP_APPEND, CONF_CPID: "sim2"}},
    ]

    enable_socket()
    socket_allow_hosts(["127.0.0.1"])

    config_entry = MockConfigEntry(
        domain=OCPP_DOMAIN, data=config, version=2, minor_version=0
    )
    cs = await create_configuration(hass, config_entry)
    cpids = config_entry.data[CONF_CPIDS]
    port = config_entry.data[CONF_PORT]

    await run_simulated_session(port, list(cpids[0].keys())[0], "TAG-1", 0, 1.5)
    await run_simulated_session(port, list(cpids[1].keys())[0], "TAG-1", 1.5, 2.0)
    await run_simulated_session(port, list(cpids[0].keys())[0], "TAG-2", 2.0, 2.6)

    assert cs.get_tag_energy("TAG-1") == pytest.approx(2.0)
    assert cs.get_tag_energy("TAG-2") == pytest.approx(0.6)

    await remove_configuration(hass, config_entry)
