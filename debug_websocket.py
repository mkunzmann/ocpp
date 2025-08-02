#!/usr/bin/env python3
"""
Simple WebSocket debug script to test communication with Home Assistant OCPP integration.
"""

import asyncio
import json
import logging
import websockets
from datetime import datetime, UTC

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test configuration
CHARGER_ID = "TEST_CHARGER_001"
CENTRAL_SYSTEM_URL = "ws://localhost:9000"


async def debug_websocket():
    """Debug WebSocket communication."""
    logger.info("Starting WebSocket debug")
    logger.info(f"Connecting to: {CENTRAL_SYSTEM_URL}")

    try:
        async with websockets.connect(
            CENTRAL_SYSTEM_URL, subprotocols=["ocpp1.6"]
        ) as websocket:
            logger.info("Connected to central system")

            # Send a simple BootNotification
            boot_message = {
                "chargePointModel": "Test Charger Model",
                "chargePointVendor": "Test Vendor",
                "chargeBoxSerialNumber": "TEST123456",
                "chargePointSerialNumber": "TEST123456",
                "firmwareVersion": "1.0.0",
                "iccid": "",
                "imsi": "",
                "meterSerialNumber": "",
                "meterType": "",
            }

            # Create OCPP message format
            message_id = "debug-boot-001"
            ocpp_message = [2, message_id, "BootNotification", boot_message]

            logger.info(f"Sending: {json.dumps(ocpp_message)}")
            await websocket.send(json.dumps(ocpp_message))

            # Wait for response
            logger.info("Waiting for response...")
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                logger.info(f"Received: {response}")

                # Parse response
                response_data = json.loads(response)
                logger.info(f"Parsed response: {json.dumps(response_data, indent=2)}")

                if response_data[0] == 2:  # Request message
                    request_id = response_data[1]
                    action = response_data[2]
                    payload = response_data[3]

                    logger.info(f"Received request: {action}")

                    if action == "GetConfiguration":
                        # Respond to GetConfiguration
                        config_response = {
                            "configurationKey": [
                                {
                                    "key": "SupportedFeatureProfiles",
                                    "readonly": False,
                                    "value": "Core,FirmwareManagement,LocalAuthListManagement,Reservation,SmartCharging,RemoteTrigger",
                                }
                            ]
                        }

                        response_message = [3, request_id, config_response]
                        logger.info(f"Sending response: {json.dumps(response_message)}")
                        await websocket.send(json.dumps(response_message))

                        # Wait for more messages
                        logger.info("Waiting for additional messages...")
                        try:
                            while True:
                                additional_msg = await asyncio.wait_for(
                                    websocket.recv(), timeout=5.0
                                )
                                logger.info(f"Additional message: {additional_msg}")
                        except asyncio.TimeoutError:
                            logger.info("No additional messages received")

                elif response_data[0] == 3:  # Response message
                    logger.info("✅ Received BootNotificationResponse")

                    # Wait for any additional messages
                    logger.info("Waiting for additional messages...")
                    try:
                        while True:
                            additional_msg = await asyncio.wait_for(
                                websocket.recv(), timeout=5.0
                            )
                            logger.info(f"Additional message: {additional_msg}")
                    except asyncio.TimeoutError:
                        logger.info("No additional messages received")

            except asyncio.TimeoutError:
                logger.error("❌ No response received within 10 seconds")

    except Exception as e:
        logger.error(f"Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(debug_websocket())
