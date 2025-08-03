#!/usr/bin/env python3
"""
Test script to send commands to the running charger simulator.

This script connects to the charger simulator and sends commands to trigger
charging sessions, stop charging, etc.

Usage:
    python test_charger_commands.py [command] [args...]

Commands:
    start [id_tag] - Start a charging session
    stop [reason]  - Stop the current charging session
    status         - Show current status
    help           - Show this help
"""

import asyncio
import json
import logging
import sys
import uuid
from datetime import datetime, timezone

import websockets
from ocpp.v16 import call
from ocpp.v16.enums import (
    AuthorizationStatus,
    ChargePointStatus,
    Measurand,
    UnitOfMeasure,
)


class ChargerCommandClient:
    def __init__(self, charger_id: str, host: str = "localhost", port: int = 9000):
        self.charger_id = charger_id
        self.host = host
        self.port = port
        self.websocket = None
        self.connected = False

        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger(f"ChargerCommandClient-{charger_id}")

    async def connect(self):
        """Connect to the charger simulator."""
        uri = f"ws://{self.host}:{self.port}/{self.charger_id}"
        self.logger.info(f"Connecting to {uri}")

        try:
            self.websocket = await websockets.connect(uri, subprotocols=["ocpp1.6"])
            self.connected = True
            self.logger.info("Connected successfully")
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            self.connected = False

    def _convert_to_camel_case(self, obj):
        """Convert snake_case field names to camelCase for OCPP compatibility."""
        if isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                # Convert snake_case to camelCase
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

    async def call(self, payload):
        """Send a call and wait for the response."""
        if not self.connected or not self.websocket:
            raise Exception("Not connected")

        message_id = str(uuid.uuid4())
        action = payload.__class__.__name__
        # Convert payload to dict and then to camelCase for JSON serialization
        payload_dict = payload.__dict__
        payload_camel = self._convert_to_camel_case(payload_dict)
        message = [2, message_id, action, payload_camel]

        self.logger.debug(f"Sending: {message}")
        await self.websocket.send(json.dumps(message))

        response = await self.websocket.recv()
        self.logger.debug(f"Received: {response}")

        return json.loads(response)

    async def start_charging_session(self, id_tag: str = "pulsar"):
        """Start a charging session."""
        if not self.connected:
            await self.connect()

        self.logger.info(f"Starting charging session for {id_tag}")

        # Authorize
        authorize = call.Authorize(id_tag=id_tag)
        response = await self.call(authorize)

        # Debug: print the response
        self.logger.info(f"Authorization response: {response}")

        # Parse the response - CallResult format is [3, message_id, payload]
        response_data = response[2]  # Payload is at index 2 for CallResult
        self.logger.info(f"Response data: {response_data}")

        if response_data.get("idTagInfo", {}).get("status") == "Accepted":
            # Status: Preparing
            status_notification = call.StatusNotification(
                connector_id=1,
                error_code="NoError",
                status=ChargePointStatus.preparing,
                timestamp=datetime.now(timezone.utc).isoformat(),
                info="",
                vendor_id="",
                vendor_error_code="",
            )
            await self.call(status_notification)
            await asyncio.sleep(2)

            # Start Transaction
            start_transaction = call.StartTransaction(
                connector_id=1,
                id_tag=id_tag,
                meter_start=12345,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            response = await self.call(start_transaction)
            transaction_id = response[2]["transactionId"]  # Payload at index 2

            # Status: Charging
            status_notification = call.StatusNotification(
                connector_id=1,
                error_code="NoError",
                status=ChargePointStatus.charging,
                timestamp=datetime.now(timezone.utc).isoformat(),
                info="",
                vendor_id="",
                vendor_error_code="",
            )
            await self.call(status_notification)

            self.logger.info(f"Charging session started: transaction {transaction_id}")
        else:
            self.logger.error(f"Authorization failed for {id_tag}")

    async def stop_charging_session(self, reason: str = "Remote"):
        """Stop the current charging session."""
        if not self.connected:
            await self.connect()

        self.logger.info("Stopping charging session")

        # Status: Finishing
        status_notification = call.StatusNotification(
            connector_id=1,
            error_code="NoError",
            status=ChargePointStatus.finishing,
            timestamp=datetime.now(timezone.utc).isoformat(),
            info="",
            vendor_id="",
            vendor_error_code="",
        )
        await self.call(status_notification)
        await asyncio.sleep(2)

        # Stop Transaction
        stop_transaction = call.StopTransaction(
            meter_stop=15678,
            timestamp=datetime.now(timezone.utc).isoformat(),
            transaction_id=1754174206,
            reason=reason,
            id_tag="pulsar",
            transaction_data=[
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sampledValue": [
                        {
                            "value": "15678",
                            "measurand": Measurand.energy_active_import_register,
                            "unit": UnitOfMeasure.wh,
                        }
                    ],
                }
            ],
        )

        await self.call(stop_transaction)

        # Status: Available
        status_notification = call.StatusNotification(
            connector_id=1,
            error_code="NoError",
            status=ChargePointStatus.available,
            timestamp=datetime.now(timezone.utc).isoformat(),
            info="",
            vendor_id="",
            vendor_error_code="",
        )
        await self.call(status_notification)

        self.logger.info("Charging session stopped")

    async def send_meter_values(self, energy_wh: int = 15000):
        """Send meter values."""
        if not self.connected:
            await self.connect()

        meter_values = call.MeterValues(
            connector_id=1,
            transaction_id=1754174206,
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

        await self.call(meter_values)
        self.logger.info(f"MeterValues sent: {energy_wh} Wh")

    async def close(self):
        """Close the connection."""
        if self.websocket:
            await self.websocket.close()
        self.connected = False


async def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python test_charger_commands.py [command] [args...]")
        print("Commands: start [id_tag], stop [reason], meter [energy_wh], help")
        return

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    client = ChargerCommandClient("TEST_CHARGER_001", "localhost", 9000)

    try:
        if command == "start":
            id_tag = args[0] if args else "pulsar"
            await client.start_charging_session(id_tag)
        elif command == "stop":
            reason = args[0] if args else "Remote"
            await client.stop_charging_session(reason)
        elif command == "meter":
            energy_wh = int(args[0]) if args else 15000
            await client.send_meter_values(energy_wh)
        elif command == "help":
            print("Available commands:")
            print("  start [id_tag] - Start a charging session")
            print("  stop [reason]  - Stop the current charging session")
            print("  meter [energy_wh] - Send meter values")
            print("  help           - Show this help")
        else:
            print(f"Unknown command: {command}")
            print("Use 'help' for available commands")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
