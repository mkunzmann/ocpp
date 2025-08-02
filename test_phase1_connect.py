#!/usr/bin/env python3
"""
Phase 1: Connect and Register OCPP 1.6 Charger

This script performs only the connection and registration phase
of the OCPP charger simulation.
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
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test configuration
CHARGER_ID = "TEST_CHARGER_001"
CENTRAL_SYSTEM_URL = "ws://localhost:9000"  # Default HA OCPP port
ID_TAG = "pulsar"  # From your configuration.yaml


class TestChargePoint(ChargePoint):
    """Test charge point for Phase 1: Connect and Register."""

    def __init__(self, id: str, connection, response_timeout=30):
        super().__init__(id, connection)
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
        logger.info("Charger is now ready for transactions.")
        return True


async def main():
    """Main function to run Phase 1: Connect and Register."""
    logger.info("Starting OCPP 1.6 Charger Simulator - Phase 1")
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
            success = await cp.phase1_connect_and_register()

            if success:
                logger.info("Phase 1 completed successfully!")
                logger.info(
                    "You can now run Phase 2 (transaction) or keep this connection alive."
                )
                logger.info("Keeping connection alive for 60 seconds...")
                await asyncio.sleep(60)
            else:
                logger.error("Phase 1 failed!")

    except ConnectionRefusedError:
        logger.error(f"Connection refused to {CENTRAL_SYSTEM_URL}")
        logger.error(
            "Make sure Home Assistant OCPP integration is running on port 9000"
        )
    except Exception as e:
        logger.error(f"Error during Phase 1: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
