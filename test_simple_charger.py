#!/usr/bin/env python3
"""
Simple OCPP charger test focusing on GetConfiguration handling.
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
CHARGER_ID = "SIMPLE_CHARGER_001"
CENTRAL_SYSTEM_URL = "ws://localhost:9000"
ID_TAG = "pulsar"


class SimpleChargePoint(ChargePoint):
    """Simple charge point for testing GetConfiguration handling."""

    def __init__(self, id: str, connection, response_timeout=30):
        super().__init__(id, connection)
        logger.info(f"SimpleChargePoint initialized with ID: {id}")

    @on(Action.get_configuration)
    def on_get_configuration(self, key, **kwargs):
        """Handle configuration requests."""
        logger.info(f"🔧 Received GetConfiguration request for key: {key}")

        # Handle different configuration keys
        if key[0] == "SupportedFeatureProfiles":
            logger.info("📋 Responding to SupportedFeatureProfiles")
            return call_result.GetConfiguration(
                configuration_key=[
                    {
                        "key": key[0],
                        "readonly": False,
                        "value": "Core,FirmwareManagement,LocalAuthListManagement,Reservation,SmartCharging,RemoteTrigger",
                    }
                ]
            )
        elif key[0] == "NumberOfConnectors":
            logger.info("📋 Responding to NumberOfConnectors")
            return call_result.GetConfiguration(
                configuration_key=[{"key": key[0], "readonly": False, "value": "1"}]
            )
        elif key[0] == "MeterValuesSampledData":
            logger.info("📋 Responding to MeterValuesSampledData")
            return call_result.GetConfiguration(
                configuration_key=[
                    {
                        "key": key[0],
                        "readonly": False,
                        "value": "Energy.Active.Import.Register",
                    }
                ]
            )
        elif key[0] == "MeterValueSampleInterval":
            logger.info("📋 Responding to MeterValueSampleInterval")
            return call_result.GetConfiguration(
                configuration_key=[{"key": key[0], "readonly": False, "value": "60"}]
            )
        elif key[0] == "WebSocketPingInterval":
            logger.info("📋 Responding to WebSocketPingInterval")
            return call_result.GetConfiguration(
                configuration_key=[{"key": key[0], "readonly": False, "value": "60"}]
            )
        elif key[0] == "ChargingScheduleAllowedChargingRateUnit":
            logger.info("📋 Responding to ChargingScheduleAllowedChargingRateUnit")
            return call_result.GetConfiguration(
                configuration_key=[
                    {"key": key[0], "readonly": False, "value": "Current"}
                ]
            )
        elif key[0] == "AuthorizeRemoteTxRequests":
            logger.info("📋 Responding to AuthorizeRemoteTxRequests")
            return call_result.GetConfiguration(
                configuration_key=[{"key": key[0], "readonly": False, "value": "false"}]
            )
        elif key[0] == "ChargeProfileMaxStackLevel":
            logger.info("📋 Responding to ChargeProfileMaxStackLevel")
            return call_result.GetConfiguration(
                configuration_key=[{"key": key[0], "readonly": False, "value": "3"}]
            )
        else:
            logger.warning(f"⚠️ Unknown configuration key: {key[0]}")
            # Default response for unknown keys
            return call_result.GetConfiguration(
                configuration_key=[{"key": key[0], "readonly": False, "value": ""}]
            )

    @on(Action.change_availability)
    def on_change_availability(self, **kwargs):
        """Handle availability change requests."""
        logger.info("🔄 Received ChangeAvailability request")
        return call_result.ChangeAvailability(status="Accepted")

    @on(Action.reset)
    def on_reset(self, **kwargs):
        """Handle reset requests."""
        logger.info("🔄 Received Reset request")
        return call_result.Reset(status="Accepted")

    @on(Action.authorize)
    def on_authorize(self, id_tag, **kwargs):
        """Handle authorize requests."""
        logger.info(f"🔐 Received Authorize request for tag: {id_tag}")
        return call_result.Authorize(id_tag_info={"status": "Accepted"})

    async def send_boot_notification(self):
        """Send boot notification."""
        logger.info("🚀 Sending BootNotification")
        request = call.BootNotification(
            charge_point_model="Simple Test Charger",
            charge_point_vendor="Test Vendor",
            charge_point_serial_number="SIMPLE123456",
            charge_box_serial_number="SIMPLE123456",
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
            logger.warning(
                "⚠️ BootNotification response timeout - this might be normal with HA's non-standard flow"
            )
            return False

    async def send_heartbeat(self):
        """Send heartbeat."""
        logger.info("💓 Sending Heartbeat")
        request = call.Heartbeat()
        try:
            response = await asyncio.wait_for(self.call(request), timeout=30)
            logger.info(f"✅ Heartbeat response: {response}")
            return True
        except asyncio.TimeoutError:
            logger.error("❌ Heartbeat timeout")
            return False

    async def send_authorize(self, id_tag: str):
        """Send authorize request."""
        logger.info(f"🔐 Sending Authorize for tag: {id_tag}")
        request = call.Authorize(id_tag=id_tag)
        try:
            response = await asyncio.wait_for(self.call(request), timeout=30)
            logger.info(f"✅ Authorize response: {response}")
            return response
        except asyncio.TimeoutError:
            logger.error("❌ Authorize timeout")
            return None

    async def test_connection(self):
        """Test the connection and basic functionality."""
        logger.info("=== Testing Simple Charger Connection ===")

        # 1. Send boot notification
        boot_success = await self.send_boot_notification()
        if not boot_success:
            logger.warning("⚠️ Boot notification failed, but continuing...")

        await asyncio.sleep(2)

        # 2. Send heartbeat
        heartbeat_success = await self.send_heartbeat()
        if not heartbeat_success:
            logger.error("❌ Heartbeat failed")
            return False

        await asyncio.sleep(1)

        # 3. Send authorize
        auth_response = await self.send_authorize(ID_TAG)
        if auth_response is None:
            logger.error("❌ Authorize failed")
            return False

        if auth_response.id_tag_info.status != AuthorizationStatus.accepted:
            logger.error(f"❌ Authorization failed: {auth_response.id_tag_info.status}")
            return False

        logger.info("✅ Authorization successful!")
        logger.info("✅ Simple charger test completed successfully!")
        return True


async def main():
    """Main function to run the simple charger test."""
    logger.info("Starting Simple OCPP 1.6 Charger Test")
    logger.info(f"Connecting to: {CENTRAL_SYSTEM_URL}")
    logger.info(f"Charger ID: {CHARGER_ID}")
    logger.info(f"ID Tag: {ID_TAG}")

    try:
        # Connect to the central system
        async with websockets.connect(
            CENTRAL_SYSTEM_URL, subprotocols=["ocpp1.6"]
        ) as websocket:
            logger.info("✅ Connected to central system")

            # Create charge point
            cp = SimpleChargePoint(CHARGER_ID, websocket)

            # Test the connection
            success = await cp.test_connection()

            if success:
                logger.info("🎉 Simple charger test completed successfully!")
                logger.info("Keeping connection alive for 30 seconds...")
                await asyncio.sleep(30)
            else:
                logger.error("❌ Simple charger test failed!")

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
