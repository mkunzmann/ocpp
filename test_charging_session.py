#!/usr/bin/env python3
"""
Standalone OCPP 1.6 Charger Simulator for Testing Energy Tracking

This script simulates a complete charging session with energy tracking
to test the tag energy sensors in the Home Assistant OCPP integration.
"""

import asyncio
import json
import logging
import websockets
from datetime import datetime, UTC
from typing import Optional

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
    """Test charge point that simulates a complete charging session."""

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

    async def send_boot_notification(self):
        """Send boot notification."""
        logger.info("Sending BootNotification")
        request = call.BootNotification(
            charge_point_model="Test Charger Model",
            charge_point_vendor="Test Vendor",
            charge_point_serial_number="TEST123456",
            charge_box_serial_number="TEST123456",
            firmware_version="1.0.0",
            iccid="",
            imsi="",
            meter_type="",
            meter_serial_number="",
        )
        response = await self.call(request)
        logger.info(f"BootNotification response: {response}")

    async def send_heartbeat(self):
        """Send heartbeat."""
        logger.info("Sending Heartbeat")
        request = call.Heartbeat()
        response = await self.call(request)
        logger.info(f"Heartbeat response: {response}")

    async def send_authorize(self, id_tag: str):
        """Send authorize request."""
        logger.info(f"Sending Authorize for tag: {id_tag}")
        request = call.Authorize(id_tag=id_tag)
        response = await self.call(request)
        logger.info(f"Authorize response: {response}")
        return response

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

    async def phase1_connect_and_register(self):
        """Phase 1: Connect and register the charger."""
        logger.info("=== PHASE 1: Connect and Register ===")

        # 1. Send boot notification
        await self.send_boot_notification()
        await asyncio.sleep(1)

        # 2. Send heartbeat
        await self.send_heartbeat()
        await asyncio.sleep(1)

        # 3. Send status notification (available)
        await self.send_status_notification(
            connector_id=1, status=ChargePointStatus.available
        )
        await asyncio.sleep(1)

        # 4. Authorize the ID tag
        auth_response = await self.send_authorize(ID_TAG)
        if auth_response.id_tag_info.status != AuthorizationStatus.accepted:
            logger.error(f"Authorization failed: {auth_response.id_tag_info.status}")
            return False
        logger.info("Authorization successful!")
        await asyncio.sleep(1)

        logger.info("✅ Phase 1 Complete: Charger connected and registered!")
        return True

    async def phase2_transaction(self):
        """Phase 2: Perform a complete charging transaction."""
        logger.info("=== PHASE 2: Charging Transaction ===")

        # 5. Change status to preparing
        await self.send_status_notification(
            connector_id=1, status=ChargePointStatus.preparing
        )
        await asyncio.sleep(2)

        # 6. Change status to charging
        await self.send_status_notification(
            connector_id=1, status=ChargePointStatus.charging
        )
        await asyncio.sleep(1)

        # 7. Start transaction
        start_response = await self.send_start_transaction(ID_TAG, self.meter_start)
        if start_response.id_tag_info.status != AuthorizationStatus.accepted:
            logger.error(
                f"Start transaction failed: {start_response.id_tag_info.status}"
            )
            return False

        self.transaction_id = start_response.transaction_id
        logger.info(f"Transaction started with ID: {self.transaction_id}")
        await asyncio.sleep(1)

        # 8. Simulate charging with periodic meter values
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

        # 9. Stop charging
        logger.info("=== Stopping Charging Session ===")
        await self.send_status_notification(
            connector_id=1, status=ChargePointStatus.finishing
        )
        await asyncio.sleep(2)

        # 10. Stop transaction
        await self.send_stop_transaction(
            transaction_id=self.transaction_id, meter_stop=self.meter_end, id_tag=ID_TAG
        )
        await asyncio.sleep(1)

        # 11. Return to available status
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
    """Main function to run the charging session simulation."""
    logger.info("Starting OCPP 1.6 Charger Simulator")
    logger.info(f"Connecting to: {CENTRAL_SYSTEM_URL}")
    logger.info(f"Charger ID: {CHARGER_ID}")
    logger.info(f"ID Tag: {ID_TAG}")

    try:
        # Connect to the central system
        async with websockets.connect(
            CENTRAL_SYSTEM_URL, subprotocols=["ocpp1.6"]
        ) as websocket:
            logger.info("Connected to central system")

            # Create charge point
            cp = TestChargePoint(CHARGER_ID, websocket)

            # Phase 1: Connect and register
            if await cp.phase1_connect_and_register():
                logger.info("Phase 1 successful, proceeding to Phase 2...")

                # Keep connection alive between phases
                await asyncio.sleep(5)

                # Phase 2: Transaction
                await cp.phase2_transaction()
            else:
                logger.error("Phase 1 failed, cannot proceed to Phase 2")

            # Keep connection alive for a bit to see final states
            logger.info("Keeping connection alive for 10 seconds...")
            await asyncio.sleep(10)

    except ConnectionRefusedError:
        logger.error(f"Connection refused to {CENTRAL_SYSTEM_URL}")
        logger.error(
            "Make sure Home Assistant OCPP integration is running on port 9000"
        )
    except Exception as e:
        logger.error(f"Error during simulation: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
