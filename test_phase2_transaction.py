#!/usr/bin/env python3
"""
Phase 2: Charging Transaction OCPP 1.6 Charger

This script performs only the transaction phase of the OCPP charger simulation.
Assumes the charger is already connected and registered (Phase 1 completed).
"""

import asyncio
import logging
import websockets
from datetime import datetime, UTC

from ocpp.routing import on
from ocpp.v16 import ChargePoint, call, call_result
from ocpp.v16.enums import (
    Action,
    AuthorizationStatus,
    ChargePointStatus,
    ChargePointErrorCode,
    Measurand,
    UnitOfMeasure,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test configuration
CHARGER_ID = "TEST_CHARGER_001"
CENTRAL_SYSTEM_URL = "ws://localhost:9000"  # Default HA OCPP port
ID_TAG = "pulsar"  # From your configuration.yaml
TRANSACTION_ID = 1
METER_START = 12345  # kWh * 1000 (12.345 kWh)
METER_END = 15678  # kWh * 1000 (15.678 kWh) - 3.333 kWh charged


class TestChargePoint(ChargePoint):
    """Test charge point for Phase 2: Transaction."""

    def __init__(self, id: str, connection, response_timeout=30):
        super().__init__(id, connection)
        self.transaction_id = TRANSACTION_ID
        self.meter_start = METER_START
        self.meter_end = METER_END
        self.charging = False
        self.connector_status = ChargePointStatus.available

    @on(Action.get_configuration)
    def on_get_configuration(self, key, **kwargs):
        """Handle configuration requests."""
        logger.info(f"Received GetConfiguration request for key: {key}")

        # Return basic configuration
        return call_result.GetConfiguration(
            configuration_key=[
                {"key": "HeartbeatInterval", "readonly": False, "value": "300"},
                {"key": "NumberOfConnectors", "readonly": False, "value": "1"},
                {
                    "key": "MeterValuesSampledData",
                    "readonly": False,
                    "value": "Energy.Active.Import.Register",
                },
                {"key": "MeterValueSampleInterval", "readonly": False, "value": "60"},
            ]
        )

    @on(Action.change_availability)
    def on_change_availability(self, **kwargs):
        """Handle availability change requests."""
        logger.info("Received ChangeAvailability request")
        return call_result.ChangeAvailability(status="Accepted")

    @on(Action.remote_start_transaction)
    def on_remote_start_transaction(self, **kwargs):
        """Handle remote start transaction requests."""
        logger.info("Received RemoteStartTransaction request")
        return call_result.RemoteStartTransaction(status="Accepted")

    @on(Action.remote_stop_transaction)
    def on_remote_stop_transaction(self, **kwargs):
        """Handle remote stop transaction requests."""
        logger.info("Received RemoteStopTransaction request")
        return call_result.RemoteStopTransaction(status="Accepted")

    @on(Action.reset)
    def on_reset(self, **kwargs):
        """Handle reset requests."""
        logger.info("Received Reset request")
        return call_result.Reset(status="Accepted")

    async def send_status_notification(
        self,
        connector_id: int = 1,
        status: ChargePointStatus = ChargePointStatus.available,
    ):
        """Send status notification."""
        logger.info(
            f"Sending StatusNotification: connector={connector_id}, status={status}"
        )
        request = call.StatusNotification(
            connector_id=connector_id,
            error_code=ChargePointErrorCode.no_error,
            status=status,
            timestamp=datetime.now(UTC).isoformat(),
            info="",
            vendor_id="",
            vendor_error_code="",
        )
        response = await self.call(request)
        logger.info(f"StatusNotification response: {response}")

    async def send_start_transaction(self, id_tag: str, meter_start: int):
        """Send start transaction."""
        logger.info(
            f"Sending StartTransaction: tag={id_tag}, meter_start={meter_start}"
        )
        request = call.StartTransaction(
            connector_id=1,
            id_tag=id_tag,
            meter_start=meter_start,
            reservation_id=None,
            timestamp=datetime.now(UTC).isoformat(),
        )
        response = await self.call(request)
        logger.info(f"StartTransaction response: {response}")
        return response

    async def send_meter_values(
        self, transaction_id: int, meter_value: int, energy_import: float
    ):
        """Send meter values with energy data."""
        logger.info(
            f"Sending MeterValues: transaction={transaction_id}, meter={meter_value}, energy={energy_import}"
        )
        request = call.MeterValues(
            connector_id=1,
            transaction_id=transaction_id,
            meter_value=[
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "sampled_value": [
                        {
                            "value": str(meter_value),
                            "measurand": Measurand.energy_active_import_register,
                            "unit": UnitOfMeasure.wh,
                        },
                        {
                            "value": str(
                                int(energy_import * 1000)
                            ),  # Convert kWh to Wh
                            "measurand": Measurand.energy_active_import_register,
                            "unit": UnitOfMeasure.kwh,
                        },
                    ],
                }
            ],
        )
        response = await self.call(request)
        logger.info(f"MeterValues response: {response}")

    async def send_stop_transaction(
        self, transaction_id: int, meter_stop: int, id_tag: str
    ):
        """Send stop transaction."""
        logger.info(
            f"Sending StopTransaction: transaction={transaction_id}, meter_stop={meter_stop}"
        )
        request = call.StopTransaction(
            transaction_id=transaction_id,
            id_tag=id_tag,
            meter_stop=meter_stop,
            timestamp=datetime.now(UTC).isoformat(),
            transaction_data=[
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "sampled_value": [
                        {
                            "value": str(meter_stop),
                            "measurand": Measurand.energy_active_import_register,
                            "unit": UnitOfMeasure.wh,
                        }
                    ],
                }
            ],
            reason="Remote",
        )
        response = await self.call(request)
        logger.info(f"StopTransaction response: {response}")

    async def phase2_transaction(self):
        """Phase 2: Perform a complete charging transaction."""
        logger.info("=== PHASE 2: Charging Transaction ===")

        # 1. Change status to preparing
        await self.send_status_notification(
            connector_id=1, status=ChargePointStatus.preparing
        )
        await asyncio.sleep(2)

        # 2. Change status to charging
        await self.send_status_notification(
            connector_id=1, status=ChargePointStatus.charging
        )
        await asyncio.sleep(1)

        # 3. Start transaction
        start_response = await self.send_start_transaction(ID_TAG, self.meter_start)
        if start_response.id_tag_info.status != AuthorizationStatus.accepted:
            logger.error(
                f"Start transaction failed: {start_response.id_tag_info.status}"
            )
            return False

        self.transaction_id = start_response.transaction_id
        logger.info(f"Transaction started with ID: {self.transaction_id}")
        await asyncio.sleep(1)

        # 4. Simulate charging with periodic meter values
        logger.info("=== Simulating Charging Process ===")
        current_meter = self.meter_start
        energy_charged = 0.0

        # Simulate 10 meter value updates over 30 seconds
        for i in range(10):
            # Simulate energy consumption (0.333 kWh per update)
            energy_increment = 0.333
            energy_charged += energy_increment
            current_meter += int(energy_increment * 1000)  # Convert to Wh

            logger.info(
                f"Charging update {i + 1}/10: Energy={energy_charged:.3f} kWh, Meter={current_meter}"
            )

            await self.send_meter_values(
                transaction_id=self.transaction_id,
                meter_value=current_meter,
                energy_import=energy_charged,
            )
            await asyncio.sleep(3)  # 3 seconds between updates

        # 5. Stop charging
        logger.info("=== Stopping Charging Session ===")
        await self.send_status_notification(
            connector_id=1, status=ChargePointStatus.finishing
        )
        await asyncio.sleep(2)

        # 6. Stop transaction
        await self.send_stop_transaction(
            transaction_id=self.transaction_id, meter_stop=self.meter_end, id_tag=ID_TAG
        )
        await asyncio.sleep(1)

        # 7. Return to available status
        await self.send_status_notification(
            connector_id=1, status=ChargePointStatus.available
        )

        logger.info("=== Charging Session Complete ===")
        logger.info(f"Total energy charged: {energy_charged:.3f} kWh")
        logger.info(f"Final meter reading: {self.meter_end}")
        logger.info(f"Transaction ID: {self.transaction_id}")
        logger.info("✅ Phase 2 Complete: Transaction finished!")

        return True


async def main():
    """Main function to run Phase 2: Transaction."""
    logger.info("Starting OCPP 1.6 Charger Simulator - Phase 2")
    logger.info(f"Connecting to: {CENTRAL_SYSTEM_URL}")
    logger.info(f"Charger ID: {CHARGER_ID}")
    logger.info(f"ID Tag: {ID_TAG}")
    logger.info("Note: This assumes Phase 1 (connect/register) has been completed.")

    try:
        # Connect to the central system
        async with websockets.connect(
            CENTRAL_SYSTEM_URL, subprotocols=["ocpp1.6"]
        ) as websocket:
            logger.info("Connected to central system")

            # Create charge point
            cp = TestChargePoint(CHARGER_ID, websocket)

            # Phase 2: Transaction
            success = await cp.phase2_transaction()

            if success:
                logger.info("Phase 2 completed successfully!")
                logger.info("Transaction finished with energy tracking.")
            else:
                logger.error("Phase 2 failed!")

            # Keep connection alive for a bit to see final states
            logger.info("Keeping connection alive for 10 seconds...")
            await asyncio.sleep(10)

    except ConnectionRefusedError:
        logger.error(f"Connection refused to {CENTRAL_SYSTEM_URL}")
        logger.error(
            "Make sure Home Assistant OCPP integration is running on port 9000"
        )
    except Exception as e:
        logger.error(f"Error during Phase 2: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
