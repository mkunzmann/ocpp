#!/usr/bin/env python3
"""
Minimal OCPP charger test for debugging GetConfiguration handler.
"""

import asyncio
import logging
import websockets
from datetime import datetime, UTC

from ocpp.routing import on
from ocpp.v16 import ChargePoint, call, call_result
from ocpp.v16.enums import Action

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test configuration
CHARGER_ID = "MINIMAL_CHARGER_001"
CENTRAL_SYSTEM_URL = "ws://localhost:9000"


class MinimalChargePoint(ChargePoint):
    """Minimal charge point for debugging GetConfiguration handling."""

    def __init__(self, id: str, connection, response_timeout=30):
        super().__init__(id, connection)
        logger.info(f"MinimalChargePoint initialized with ID: {id}")

    @on(Action.get_configuration)
    def on_get_configuration(self, key, **kwargs):
        """Handle configuration requests."""
        logger.info(f"🎯 GetConfiguration handler called with key: {key}")
        logger.info(f"🎯 Key type: {type(key)}")
        logger.info(f"🎯 Key[0]: {key[0] if key else 'None'}")

        # Always respond with a basic configuration
        response = call_result.GetConfiguration(
            configuration_key=[
                {
                    "key": key[0] if key else "Unknown",
                    "readonly": False,
                    "value": "Core,FirmwareManagement,LocalAuthListManagement,Reservation,SmartCharging,RemoteTrigger",
                }
            ]
        )
        logger.info(f"🎯 Returning response: {response}")
        return response

    @on(Action.boot_notification)
    def on_boot_notification(self, **kwargs):
        """Handle boot notification."""
        logger.info("🎯 BootNotification handler called")
        return call_result.BootNotification(
            current_time=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            interval=3600,
            status="Accepted",
        )

    @on(Action.heartbeat)
    def on_heartbeat(self, **kwargs):
        """Handle heartbeat."""
        logger.info("🎯 Heartbeat handler called")
        return call_result.Heartbeat()

    @on(Action.authorize)
    def on_authorize(self, id_tag, **kwargs):
        """Handle authorize."""
        logger.info(f"🎯 Authorize handler called with id_tag: {id_tag}")
        return call_result.Authorize(id_tag_info={"status": "Accepted"})

    async def send_boot_notification(self):
        """Send boot notification."""
        logger.info("🚀 Sending BootNotification")
        request = call.BootNotification(
            charge_point_model="Minimal Test Charger",
            charge_point_vendor="Test Vendor",
            charge_point_serial_number="MINIMAL123456",
            charge_box_serial_number="MINIMAL123456",
            firmware_version="1.0.0",
            iccid="",
            imsi="",
            meter_type="",
            meter_serial_number="",
        )

        try:
            response = await asyncio.wait_for(self.call(request), timeout=60)
            logger.info(f"✅ BootNotification response: {response}")
            return True
        except asyncio.TimeoutError:
            logger.warning("⚠️ BootNotification response timeout")
            return False

    async def test_connection(self):
        """Test the connection."""
        logger.info("=== Testing Minimal Charger Connection ===")

        # Start the charge point (this runs the message loop)
        logger.info("🚀 Starting charge point...")
        start_task = asyncio.create_task(self.start())

        # Wait a bit for the message loop to start
        await asyncio.sleep(1)

        # Send boot notification
        boot_success = await self.send_boot_notification()
        logger.info(f"Boot notification result: {boot_success}")

        # Wait for any GetConfiguration requests
        logger.info("Waiting for GetConfiguration requests...")
        await asyncio.sleep(10)

        # Stop the charge point
        logger.info("🛑 Stopping charge point...")
        await self.stop()

        logger.info("✅ Minimal charger test completed!")
        return True


async def main():
    """Main function to run the minimal charger test."""
    logger.info("Starting Minimal OCPP 1.6 Charger Test")
    logger.info(f"Connecting to: {CENTRAL_SYSTEM_URL}")
    logger.info(f"Charger ID: {CHARGER_ID}")

    try:
        # Connect to the central system
        async with websockets.connect(
            CENTRAL_SYSTEM_URL, subprotocols=["ocpp1.6"]
        ) as websocket:
            logger.info("✅ Connected to central system")

            # Create charge point
            cp = MinimalChargePoint(CHARGER_ID, websocket)

            # Test the connection
            success = await cp.test_connection()

            if success:
                logger.info("🎉 Minimal charger test completed successfully!")
                logger.info("Keeping connection alive for 30 seconds...")
                await asyncio.sleep(30)
            else:
                logger.error("❌ Minimal charger test failed!")

    except ConnectionRefusedError:
        logger.error(f"❌ Connection refused to {CENTRAL_SYSTEM_URL}")
        logger.error(
            "Make sure Home Assistant OCPP integration is running on port 9000"
        )
    except Exception as e:
        logger.error(f"❌ Error during test: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
