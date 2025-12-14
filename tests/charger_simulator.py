"""Reusable OCPP 1.6 charger simulator for integration tests."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

from ocpp.routing import on
from ocpp.v16 import ChargePoint as cpclass, call, call_result
from ocpp.v16.enums import (
    Action,
    ChargePointErrorCode,
    ChargePointStatus,
    DataTransferStatus,
    RegistrationStatus,
    RemoteStartStopStatus,
    TriggerMessageStatus,
)


class ChargerSimulator(cpclass):
    """Simple OCPP 1.6 charge point simulator."""

    def __init__(self, identity: str, connection) -> None:
        super().__init__(identity, connection)
        self._transaction_id: int | None = None
        self._id_tag: str | None = None

    async def boot(self) -> None:
        """Send a boot notification to the CSMS."""

        await self.call(
            call.BootNotification(
                charge_point_model="simulator",
                charge_point_vendor="test",
            )
        )

    async def authorize(self, id_tag: str) -> None:
        """Authorize a tag before starting a transaction."""

        self._id_tag = id_tag
        await self.call(call.Authorize(id_tag=id_tag))

    async def begin_session(self, meter_start_kwh: float = 0) -> int:
        """Start a new transaction."""

        result = await self.call(
            call.StartTransaction(
                connector_id=1,
                id_tag=self._id_tag or "sim-tag",
                meter_start=int(meter_start_kwh * 1000),
                timestamp=datetime.now(tz=UTC).isoformat(),
            )
        )
        self._transaction_id = result.transaction_id
        return self._transaction_id

    async def report_meter_value(self, meter_value_kwh: float) -> None:
        """Send a meter value update for the running transaction."""

        if self._transaction_id is None:
            raise RuntimeError("Transaction not started")

        await self.call(
            call.MeterValues(
                connector_id=1,
                transaction_id=self._transaction_id,
                meter_value=[
                    {
                        "timestamp": datetime.now(tz=UTC).isoformat(),
                        "sampledValue": [
                            {
                                "value": str(meter_value_kwh),
                                "measurand": "Energy.Active.Import.Register",
                                "unit": "kWh",
                            }
                        ],
                    }
                ],
            )
        )

    async def end_session(self, meter_stop_kwh: float) -> None:
        """Stop the current transaction."""

        if self._transaction_id is None:
            raise RuntimeError("Transaction not started")

        await self.call(
            call.StopTransaction(
                transaction_id=self._transaction_id,
                meter_stop=int(meter_stop_kwh * 1000),
                id_tag=self._id_tag or "sim-tag",
                timestamp=datetime.now(tz=UTC).isoformat(),
            )
        )

    async def close(self):
        """End simulator tasks and wait briefly for cleanup."""

        await asyncio.sleep(0)

    @on(Action.remote_start_transaction)
    def on_remote_start_transaction(self, **kwargs):
        """Accept remote start requests."""

        return call_result.RemoteStartTransaction(status=RemoteStartStopStatus.accepted)

    @on(Action.remote_stop_transaction)
    def on_remote_stop_transaction(self, **kwargs):
        """Accept remote stop requests."""

        self._transaction_id = None
        return call_result.RemoteStopTransaction(status=RemoteStartStopStatus.accepted)

    @on(Action.trigger_message)
    def on_trigger_message(self, **kwargs):
        """Respond to trigger message calls."""

        return call_result.TriggerMessage(status=TriggerMessageStatus.accepted)

    @on(Action.data_transfer)
    def on_data_transfer(self, **kwargs):
        """Respond to data transfer calls."""

        return call_result.DataTransfer(status=DataTransferStatus.accepted)

    @on(Action.status_notification)
    def on_status_notification(self, **kwargs):
        """Return a default status notification response."""

        return call_result.StatusNotification(
            connector_id=kwargs.get("connector_id", 1),
            error_code=ChargePointErrorCode.no_error,
            status=ChargePointStatus.available,
            timestamp=datetime.now(tz=UTC).isoformat(),
        )

    @on(Action.boot_notification)
    def on_boot_notification(self, **kwargs):
        """Handle boot notifications initiated by the CSMS."""

        return call_result.BootNotification(
            current_time=datetime.now(tz=UTC).isoformat(),
            interval=300,
            status=RegistrationStatus.accepted,
        )

    @on(Action.heartbeat)
    def on_heartbeat(self):
        """Respond to heartbeat requests."""

        return call_result.Heartbeat(current_time=datetime.now(tz=UTC).isoformat())

    @on(Action.change_configuration)
    def on_change_configuration(self, **kwargs):
        """Accept configuration changes."""

        return call_result.ChangeConfiguration(status="Accepted")

    @on(Action.get_configuration)
    def on_get_configuration(self, **kwargs):
        """Return minimal configuration set."""

        return call_result.GetConfiguration(configuration_key=[])

    @on(Action.get_diagnostics)
    def on_get_diagnostics(self, **kwargs):
        """Respond to diagnostics request."""

        return call_result.GetDiagnostics(file_name="/tmp/diagnostics.log")

    @on(Action.meter_values)
    def on_meter_values(self, **kwargs):
        """Acknowledge meter values push from CSMS if triggered."""

        return call_result.MeterValues()


async def run_simulated_session(
    port: int,
    identity: str,
    id_tag: str,
    meter_start_kwh: float,
    meter_stop_kwh: float,
) -> None:
    """Connect a simulator and complete a full transaction."""

    from websockets import connect

    async with connect(
        f"ws://127.0.0.1:{port}/{identity}", subprotocols=["ocpp1.6"]
    ) as ws:
        cp = ChargerSimulator(identity, ws)
        worker = asyncio.create_task(cp.start())
        try:
            await cp.boot()
            await cp.authorize(id_tag)
            await cp.begin_session(meter_start_kwh)
            await cp.report_meter_value(meter_stop_kwh)
            await cp.end_session(meter_stop_kwh)
            # Allow time for the CSMS to deliver any follow-up calls (e.g.,
            # ChangeConfiguration) so the simulator can answer before closing.
            await asyncio.sleep(1)
        finally:
            await cp.close()
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker
