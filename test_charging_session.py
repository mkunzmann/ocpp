#!/usr/bin/env python3
"""
Simple test script to trigger a charging session.

This script sends the necessary OCPP messages to simulate a complete charging session.
"""

import asyncio
import json
import logging
import sys
import uuid
from datetime import datetime, timezone

import websockets
from ocpp.v16 import call
from ocpp.v16.enums import ChargePointStatus, Measurand, UnitOfMeasure


class ChargingSessionTest:
    def __init__(
        self,
        charger_id: str = "TEST_CHARGER_001",
        host: str = "localhost",
        port: int = 9000,
    ):
        self.charger_id = charger_id
        self.host = host
        self.port = port
        self.websocket = None
        self.connected = False

        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger("ChargingSessionTest")

    def _convert_to_camel_case(self, obj):
        """Convert snake_case field names to camelCase for OCPP compatibility."""
        if isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                camel_key = "".join(
                    word.capitalize() if i > 0 else word
                    for i, word in enumerate(key.split("_"))
                )
                result[camel_key] = self._convert_to_camel_case(value)
            return result
        elif isinstance(obj, list):
            return [self._convert_to_camel_case(item) for item in obj]
        else:
            return obj

    async def connect(self):
        """Connect to Home Assistant OCPP server."""
        uri = f"ws://{self.host}:{self.port}/{self.charger_id}"
        self.logger.info(f"Connecting to {uri}")

        try:
            self.websocket = await websockets.connect(uri, subprotocols=["ocpp1.6"])
            self.connected = True
            self.logger.info("Connected successfully")
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            self.connected = False

    async def send_message(self, payload):
        """Send a message to Home Assistant."""
        if not self.connected or not self.websocket:
            raise Exception("Not connected")

        message_id = str(uuid.uuid4())
        action = payload.__class__.__name__
        payload_dict = payload.__dict__
        payload_camel = self._convert_to_camel_case(payload_dict)
        message = [2, message_id, action, payload_camel]

        self.logger.info(f"Sending: {action}")
        await self.websocket.send(json.dumps(message))

        # Wait for response
        response = await self.websocket.recv()
        response_data = json.loads(response)
        self.logger.info(f"Received: {response_data[2]}")  # Action name from response
        return response_data

    async def simulate_charging_session(self, id_tag: str = "pulsar"):
        """Simulate a complete charging session."""
        if not self.connected:
            await self.connect()

        self.logger.info(f"Starting charging session simulation for {id_tag}")

        # 1. Send BootNotification
        boot_notification = call.BootNotification(
            charge_point_model="Test Charger Model",
            charge_point_vendor="Test Vendor",
            charge_box_serial_number="TEST123456",
            charge_point_serial_number="TEST123456",
            firmware_version="1.0.0",
            iccid="",
            imsi="",
            meter_serial_number="",
            meter_type="",
        )
        await self.send_message(boot_notification)
        await asyncio.sleep(1)

        # 2. Send StatusNotification - Available
        status_available = call.StatusNotification(
            connector_id=1,
            error_code="NoError",
            status=ChargePointStatus.available,
            timestamp=datetime.now(timezone.utc).isoformat(),
            info="",
            vendor_id="",
            vendor_error_code="",
        )
        await self.send_message(status_available)
        await asyncio.sleep(1)

        # 3. Send Authorize
        authorize = call.Authorize(id_tag=id_tag)
        await self.send_message(authorize)
        await asyncio.sleep(1)

        # 4. Send StatusNotification - Preparing
        status_preparing = call.StatusNotification(
            connector_id=1,
            error_code="NoError",
            status=ChargePointStatus.preparing,
            timestamp=datetime.now(timezone.utc).isoformat(),
            info="",
            vendor_id="",
            vendor_error_code="",
        )
        await self.send_message(status_preparing)
        await asyncio.sleep(2)

        # 5. Send StartTransaction
        start_transaction = call.StartTransaction(
            connector_id=1,
            id_tag=id_tag,
            meter_start=12345,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        response = await self.send_message(start_transaction)
        transaction_id = response[2]["transactionId"]
        self.logger.info(f"Transaction started: {transaction_id}")
        await asyncio.sleep(1)

        # 6. Send StatusNotification - Charging
        status_charging = call.StatusNotification(
            connector_id=1,
            error_code="NoError",
            status=ChargePointStatus.charging,
            timestamp=datetime.now(timezone.utc).isoformat(),
            info="",
            vendor_id="",
            vendor_error_code="",
        )
        await self.send_message(status_charging)
        await asyncio.sleep(1)

        # 7. Send MeterValues during charging
        for i in range(3):
            energy_wh = 12345 + (i + 1) * 150  # Simulate energy consumption
            meter_values = call.MeterValues(
                connector_id=1,
                transaction_id=transaction_id,
                meter_value=[
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "sampledValue": [
                            {
                                "value": str(energy_wh),
                                "measurand": Measurand.energy_active_import_register,
                                "unit": UnitOfMeasure.wh,
                            }
                        ],
                    }
                ],
            )
            await self.send_message(meter_values)
            await asyncio.sleep(2)

        # 8. Send StatusNotification - Finishing
        status_finishing = call.StatusNotification(
            connector_id=1,
            error_code="NoError",
            status=ChargePointStatus.finishing,
            timestamp=datetime.now(timezone.utc).isoformat(),
            info="",
            vendor_id="",
            vendor_error_code="",
        )
        await self.send_message(status_finishing)
        await asyncio.sleep(2)

        # 9. Send StopTransaction
        stop_transaction = call.StopTransaction(
            meter_stop=12945,  # Final meter reading
            timestamp=datetime.now(timezone.utc).isoformat(),
            transaction_id=transaction_id,
            reason="Remote",
            id_tag=id_tag,
            transaction_data=[
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sampledValue": [
                        {
                            "value": "12945",
                            "measurand": Measurand.energy_active_import_register,
                            "unit": UnitOfMeasure.wh,
                        }
                    ],
                }
            ],
        )
        await self.send_message(stop_transaction)
        await asyncio.sleep(1)

        # 10. Send StatusNotification - Available
        status_available_final = call.StatusNotification(
            connector_id=1,
            error_code="NoError",
            status=ChargePointStatus.available,
            timestamp=datetime.now(timezone.utc).isoformat(),
            info="",
            vendor_id="",
            vendor_error_code="",
        )
        await self.send_message(status_available_final)

        self.logger.info("Charging session simulation completed!")

    async def close(self):
        """Close the connection."""
        if self.websocket:
            await self.websocket.close()
        self.connected = False


async def main():
    """Main entry point."""
    test = ChargingSessionTest()

    try:
        await test.simulate_charging_session("pulsar")
    finally:
        await test.close()


if __name__ == "__main__":
    asyncio.run(main())
