"""Tests for RFID tag energy aggregation and exposure."""

import asyncio
import contextlib
from datetime import UTC, datetime

import pytest
from ocpp.v16 import ChargePoint as cpclass, call, call_result
from ocpp.v16.enums import (
    Action,
    AvailabilityStatus,
    ConfigurationStatus,
    TriggerMessageStatus,
)
from ocpp.routing import on
import websockets
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ocpp.api import CentralSystem
from custom_components.ocpp.const import CONF_CPID, CONF_CPIDS, CONF_PORT, DOMAIN as OCPP_DOMAIN
from tests.charge_point_test import create_configuration, remove_configuration, wait_ready
from tests.const import MOCK_CONFIG_CP_APPEND, MOCK_CONFIG_DATA


class ResponsiveChargePoint(cpclass):
    """Minimal client-side handlers to satisfy CSMS requests during tests."""

    @on(Action.get_configuration)
    def on_get_configuration(self, key, **kwargs):
        config = [
            {"key": k, "readonly": False, "value": ""}
            for k in (key or [])
        ]
        return call_result.GetConfiguration(configuration_key=config)

    @on(Action.change_configuration)
    def on_change_configuration(self, key, value, **kwargs):
        return call_result.ChangeConfiguration(status=ConfigurationStatus.accepted)

    @on(Action.change_availability)
    def on_change_availability(self, connector_id, type, **kwargs):
        return call_result.ChangeAvailability(status=AvailabilityStatus.accepted)

    @on(Action.trigger_message)
    def on_trigger_message(self, requested_message, **kwargs):
        return call_result.TriggerMessage(status=TriggerMessageStatus.accepted)


@pytest.mark.timeout(10)
async def test_rfid_tag_energy_totals(hass, socket_enabled):
    """Accumulate charged energy totals per RFID tag and expose them via sensor."""

    cp_id = "CP_tag_energy"
    cpid = "test_cpid_tag_energy"

    data = MOCK_CONFIG_DATA.copy()
    cp_data = MOCK_CONFIG_CP_APPEND.copy()
    cp_data[CONF_CPID] = cpid
    data[CONF_CPIDS].append({cp_id: cp_data})
    data[CONF_PORT] = 9110

    config_entry = MockConfigEntry(
        domain=OCPP_DOMAIN,
        data=data,
        entry_id="test_cms_tag_energy",
        title="test_cms_tag_energy",
        version=2,
        minor_version=0,
    )

    cs: CentralSystem = await create_configuration(hass, config_entry)

    async with websockets.connect(
        f"ws://127.0.0.1:{data[CONF_PORT]}/{cp_id}",
        subprotocols=["ocpp1.6"],
    ) as ws:
        cp = ResponsiveChargePoint(f"{cp_id}_client", ws)
        task = asyncio.create_task(cp.start())
        try:
            await cp.call(
                call.BootNotification(
                    charge_point_model="SingleSocketCharger",
                    charge_point_vendor="ocpp",  # strings do not matter for test
                )
            )

            await wait_ready(cs.charge_points[cp_id])

            start_resp = await cp.call(
                call.StartTransaction(
                    connector_id=1,
                    id_tag="TAG-123",
                    meter_start=1000,
                    timestamp=datetime.now(tz=UTC).isoformat(),
                )
            )

            await cp.call(
                call.StopTransaction(
                    transaction_id=start_resp.transaction_id,
                    meter_stop=1500,
                    timestamp=datetime.now(tz=UTC).isoformat(),
                )
            )

            await hass.async_block_till_done()

            totals = cs.get_tag_energy_totals()
            assert totals["TAG-123"] == pytest.approx(0.5)

            tag_sensor = hass.states.get("sensor.test_csid_rfid_energy")
            assert tag_sensor is not None
            assert float(tag_sensor.state) == pytest.approx(0.5)
            assert tag_sensor.attributes["tag_energy_kwh"]["TAG-123"] == pytest.approx(0.5)
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await ws.close()

    await remove_configuration(hass, config_entry)
