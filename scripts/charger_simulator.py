#!/usr/bin/env python3
"""
Persistent OCPP 1.6 Charger Simulator

This simulator runs continuously and maintains a stable connection to the Home Assistant
OCPP integration, simulating a real charger that:
- Connects and sends BootNotification
- Sends periodic Heartbeat messages
- Responds to configuration requests
- Can be triggered to start/stop charging sessions
- Sends MeterValues during charging

Usage:
    python charger_simulator.py [charger_id] [host] [port]

Example:
    python charger_simulator.py TEST_CHARGER_001 localhost 9000

Commands (while running):
    start [id_tag] - Start a charging session
    stop [reason]  - Stop the current charging session
    status         - Show current status
    quit           - Exit the simulator
"""

import asyncio
import json
import logging
import signal
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

import websockets
from ocpp.v16 import call, call_result
from ocpp.v16.enums import (
    Action,
    AuthorizationStatus,
    ChargePointStatus,
    Measurand,
    UnitOfMeasure,
    TriggerMessageStatus,
)
from ocpp.v16.datatypes import KeyValue, IdTagInfo, MeterValue, SampledValue


class ChargerSimulator:
    def __init__(self, charger_id: str, host: str = "localhost", port: int = 9000):
        self.charger_id = charger_id
        self.host = host
        self.port = port
        self.websocket = None
        self.connected = False
        self.transaction_id = None
        self.meter_start = 12345
        self.current_meter = self.meter_start
        self.charging = False
        self.heartbeat_task = None
        self.meter_values_task = None
        self.command_task = None
        self.should_exit = False
        self.pending_responses = {}

        # Setup logging
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger(f"ChargerSimulator-{charger_id}")

        # Signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.should_exit = True
        asyncio.create_task(self.shutdown())

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
        elif hasattr(obj, "__dict__"):
            # Handle OCPP datatypes by converting to dict first
            # Handle mappingproxy objects by converting to regular dict
            if hasattr(obj.__dict__, "copy"):
                return self._convert_to_camel_case(dict(obj.__dict__))
            else:
                return self._convert_to_camel_case(obj.__dict__)
        else:
            return obj

    async def connect(self):
        """Connect to the OCPP central system."""
        uri = f"ws://{self.host}:{self.port}/{self.charger_id}"
        self.logger.info(f"Connecting to {uri}")

        try:
            self.websocket = await websockets.connect(uri, subprotocols=["ocpp1.6"])
            self.connected = True
            self.logger.info("Connected successfully")

            # Send BootNotification
            await self.send_boot_notification()

        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            self.connected = False

    async def command_interface(self):
        """Simple command interface for controlling the simulator."""
        self.logger.info("Command interface ready. Type 'help' for commands.")

        while self.connected:
            try:
                # Use asyncio to get input without blocking
                command = await asyncio.get_event_loop().run_in_executor(
                    None, input, "charger> "
                )

                await self.handle_command(command.strip())

            except EOFError:
                break
            except Exception as e:
                self.logger.error(f"Command error: {e}")

    async def handle_command(self, command: str):
        """Handle user commands."""
        parts = command.split()
        if not parts:
            return

        cmd = parts[0].lower()

        if cmd == "help":
            print("Available commands:")
            print("  start [id_tag] - Start a charging session")
            print("  stop [reason]  - Stop the current charging session")
            print("  status         - Show current status")
            print("  quit           - Exit the simulator")

        elif cmd == "start":
            id_tag = parts[1] if len(parts) > 1 else "pulsar"
            await self.start_charging_session(id_tag)

        elif cmd == "stop":
            reason = parts[1] if len(parts) > 1 else "Remote"
            await self.stop_charging_session(reason)

        elif cmd == "status":
            self.show_status()

        elif cmd == "quit":
            self.logger.info("Quitting...")
            await self.shutdown()
            sys.exit(0)

        else:
            print(f"Unknown command: {cmd}. Type 'help' for available commands.")

    def show_status(self):
        """Show current simulator status."""
        print(f"\nCharger Simulator Status:")
        print(f"  Connected: {self.connected}")
        print(f"  Charging: {self.charging}")
        if self.charging:
            print(f"  Transaction ID: {self.transaction_id}")
            print(f"  Current Meter: {self.current_meter} Wh")
        print()

    async def send_boot_notification(self):
        """Send BootNotification message."""
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

        # Send without waiting for response
        await self.send_call(boot_notification)
        self.logger.info("BootNotification sent")

    async def heartbeat_loop(self):
        """Send periodic heartbeat messages."""
        while self.connected:
            try:
                heartbeat = call.Heartbeat()
                await self.send_call(heartbeat)
                self.logger.debug("Heartbeat sent")
                await asyncio.sleep(30)  # Heartbeat every 30 seconds
            except Exception as e:
                self.logger.error(f"Heartbeat failed: {e}")
                break

    async def meter_values_loop(self):
        """Send periodic meter values during charging."""
        while self.charging and self.connected:
            try:
                await self.send_meter_values()
                await asyncio.sleep(60)  # Meter values every minute
            except Exception as e:
                self.logger.error(f"Meter values failed: {e}")
                break

    async def send_meter_values(self):
        """Send MeterValues message."""
        if not self.charging:
            return

        # Increment meter value
        self.current_meter += 184  # Simulate 11.04 kWh per hour (184 Wh per minute)

        meter_values = {
            "connectorId": 1,
            "transactionId": self.transaction_id,
            "meterValue": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sampledValue": [
                        {
                            "value": str(self.current_meter),
                            "measurand": "Energy.Active.Import.Register",
                            "unit": "Wh",
                            "context": "Sample.Periodic",
                            "location": "Outlet",
                        },
                        {
                            "value": "16",
                            "measurand": "Current.Offered",
                            "unit": "A",
                            "context": "Sample.Periodic",
                            "location": "Outlet",
                        },
                        {
                            "value": "11040",
                            "measurand": "Power.Offered",
                            "unit": "W",
                            "context": "Sample.Periodic",
                            "location": "Outlet",
                        },
                        {
                            "value": "234",
                            "measurand": "Voltage",
                            "unit": "V",
                            "phase": "L1",
                            "context": "Sample.Periodic",
                            "location": "Outlet",
                        },
                    ],
                },
            ],
        }

        await self.send_meter_values_call(meter_values)
        self.logger.info(f"MeterValues sent: {self.current_meter} Wh")

    async def start_charging_session(self, id_tag: str = "pulsar"):
        """Start a charging session."""
        if self.charging:
            self.logger.warning("Already charging")
            return

        self.logger.info(f"Starting charging session for {id_tag}")

        # Authorize
        authorize = {"idTag": id_tag}
        await self.send_authorize(authorize)
        await asyncio.sleep(1)

        # Status: Preparing
        await self.send_status_notification(ChargePointStatus.preparing)
        await asyncio.sleep(2)

        # Start Transaction
        start_transaction = {
            "connectorId": 1,
            "idTag": id_tag,
            "meterStart": self.current_meter,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Send StartTransaction and wait for response
        response = await self.call_start_transaction(start_transaction)
        if response and "transactionId" in response:
            self.transaction_id = response["transactionId"]
            self.logger.info(f"Received transaction ID: {self.transaction_id}")
        else:
            self.logger.error(
                "No transaction ID received from StartTransaction response"
            )
            return

        # Status: Charging
        await self.send_status_notification(ChargePointStatus.charging)

        self.charging = True
        self.meter_values_task = asyncio.create_task(self.meter_values_loop())

        self.logger.info(f"Charging session started: transaction {self.transaction_id}")

    async def stop_charging_session(self, reason: str = "Remote"):
        """Stop the current charging session."""
        if not self.charging:
            self.logger.warning("Not charging")
            return

        self.logger.info("Stopping charging session")

        # Status: Finishing
        await self.send_status_notification(ChargePointStatus.finishing)
        await asyncio.sleep(2)

        # Stop Transaction
        stop_transaction = {
            "meterStop": self.current_meter,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "transactionId": self.transaction_id,
            "reason": reason,
            "idTag": "pulsar",
            "transactionData": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sampledValue": [
                        {
                            "value": str(self.current_meter),
                            "measurand": "Energy.Active.Import.Register",
                            "unit": "Wh",
                        }
                    ],
                },
            ],
        }

        await self.send_stop_transaction(stop_transaction)

        # Status: Available
        await self.send_status_notification(ChargePointStatus.available)

        # Stop meter values
        if self.meter_values_task:
            self.meter_values_task.cancel()
            self.meter_values_task = None

        self.charging = False
        self.transaction_id = None

        self.logger.info("Charging session stopped")

    async def send_status_notification(self, status: ChargePointStatus):
        """Send StatusNotification message."""
        status_notification = {
            "connectorId": 1,
            "errorCode": "NoError",
            "status": status.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "info": "",
            "vendorId": "",
            "vendorErrorCode": "",
        }

        await self.send_status_notification_call(status_notification)
        self.logger.info(f"StatusNotification sent: {status}")

    async def call(self, payload):
        """Send a call without waiting for response."""
        if not self.connected or not self.websocket:
            raise Exception("Not connected")

        message_id = str(uuid.uuid4())
        # Get action name from the class name
        action = payload.__class__.__name__
        # Convert payload to dict and then to camelCase for JSON serialization
        payload_dict = payload.__dict__
        payload_camel = self._convert_to_camel_case(payload_dict)
        message = [2, message_id, action, payload_camel]

        self.logger.debug(f"Sending: {message}")
        await self.websocket.send(json.dumps(message))

        # Wait for response with timeout
        try:
            # Create a future to wait for the response
            response_future = asyncio.Future()
            self.pending_responses[message_id] = response_future

            # Wait for response with 10 second timeout
            response = await asyncio.wait_for(response_future, timeout=10.0)
            return response
        except asyncio.TimeoutError:
            self.logger.error(f"Timeout waiting for response to {message_id}")
            if message_id in self.pending_responses:
                del self.pending_responses[message_id]
            raise
        except Exception as e:
            if message_id in self.pending_responses:
                del self.pending_responses[message_id]
            raise

    async def send_call(self, payload):
        """Send a call without waiting for response."""
        if not self.connected or not self.websocket:
            raise Exception("Not connected")

        message_id = str(uuid.uuid4())
        # Get action name from the class name
        action = payload.__class__.__name__
        # Convert payload to dict and then to camelCase for JSON serialization
        payload_dict = payload.__dict__
        payload_camel = self._convert_to_camel_case(payload_dict)
        message = [2, message_id, action, payload_camel]

        self.logger.debug(f"Sending (no response): {message}")
        await self.websocket.send(json.dumps(message))

    async def send_authorize(self, payload):
        """Send Authorize call."""
        if not self.connected or not self.websocket:
            raise Exception("Not connected")

        message_id = str(uuid.uuid4())
        message = [2, message_id, "Authorize", payload]

        self.logger.debug(f"Sending Authorize: {message}")
        await self.websocket.send(json.dumps(message))

    async def send_start_transaction(self, payload):
        """Send StartTransaction call."""
        if not self.connected or not self.websocket:
            raise Exception("Not connected")

        message_id = str(uuid.uuid4())
        message = [2, message_id, "StartTransaction", payload]

        self.logger.debug(f"Sending StartTransaction: {message}")
        await self.websocket.send(json.dumps(message))

    async def call_start_transaction(self, payload):
        """Send StartTransaction call and wait for response."""
        if not self.connected or not self.websocket:
            raise Exception("Not connected")

        message_id = str(uuid.uuid4())
        message = [2, message_id, "StartTransaction", payload]

        self.logger.debug(f"Sending StartTransaction (with response): {message}")
        await self.websocket.send(json.dumps(message))

        # Wait for response with timeout
        try:
            # Create a future to wait for the response
            response_future = asyncio.Future()
            self.pending_responses[message_id] = response_future

            # Wait for response with timeout
            response = await asyncio.wait_for(response_future, timeout=10.0)
            return response
        except asyncio.TimeoutError:
            self.logger.error(f"Timeout waiting for response to {message_id}")
            if message_id in self.pending_responses:
                del self.pending_responses[message_id]
            raise
        except Exception as e:
            self.logger.error(f"Error waiting for response: {e}")
            if message_id in self.pending_responses:
                del self.pending_responses[message_id]
            raise

    async def send_meter_values_call(self, payload):
        """Send MeterValues call."""
        if not self.connected or not self.websocket:
            raise Exception("Not connected")

        message_id = str(uuid.uuid4())
        message = [2, message_id, "MeterValues", payload]

        self.logger.debug(f"Sending MeterValues: {message}")
        await self.websocket.send(json.dumps(message))

    async def send_status_notification_call(self, payload):
        """Send StatusNotification call."""
        if not self.connected or not self.websocket:
            raise Exception("Not connected")

        message_id = str(uuid.uuid4())
        message = [2, message_id, "StatusNotification", payload]

        self.logger.debug(f"Sending StatusNotification: {message}")
        await self.websocket.send(json.dumps(message))

    async def send_stop_transaction(self, payload):
        """Send StopTransaction call."""
        if not self.connected or not self.websocket:
            raise Exception("Not connected")

        message_id = str(uuid.uuid4())
        message = [2, message_id, "StopTransaction", payload]

        self.logger.debug(f"Sending StopTransaction: {message}")
        await self.websocket.send(json.dumps(message))

    async def message_loop(self):
        """Main message handling loop."""
        try:
            while self.connected:
                message = await self.websocket.recv()
                data = json.loads(message)

                if data[0] == 2:  # Call
                    await self.handle_call(data)
                elif data[0] == 3:  # CallResult
                    message_id = data[1]
                    payload = data[2]
                    self.logger.debug(f"CallResult received: {data}")

                    # Resolve pending response if waiting for this message_id
                    if message_id in self.pending_responses:
                        self.pending_responses[message_id].set_result(payload)
                        del self.pending_responses[message_id]
                else:
                    self.logger.warning(f"Unknown message type: {data[0]}")

        except websockets.exceptions.ConnectionClosed:
            self.logger.info("Connection closed")
            self.connected = False
        except Exception as e:
            self.logger.error(f"Message loop error: {e}")
            self.connected = False

    async def handle_call(self, data):
        """Handle incoming calls from the central system."""
        message_id = data[1]
        action = data[2]
        payload = data[3]

        self.logger.info(f"Received call: {action}")

        try:
            if action == Action.get_configuration:
                # Define all available configuration keys
                all_config_keys = {
                    "SupportedFeatureProfiles": {
                        "readonly": True,
                        "value": "Core,FirmwareManagement,LocalAuthListManagement,Reservation,SmartCharging,RemoteTrigger",
                    },
                    "NumberOfConnectors": {
                        "readonly": False,
                        "value": "1",
                    },
                    "MeterValuesSampledData": {
                        "readonly": False,
                        "value": "Energy.Active.Import.Register,Current.Offered,Power.Offered,Voltage",
                    },
                    "MeterValueSampleInterval": {
                        "readonly": False,
                        "value": "60",
                    },
                    "ClockAlignedDataInterval": {
                        "readonly": False,
                        "value": "900",
                    },
                }

                # Check if specific keys were requested
                requested_keys = payload.get("key", [])

                if requested_keys:
                    # Return only the requested keys
                    configuration_key = []
                    for key in requested_keys:
                        if key in all_config_keys:
                            config = all_config_keys[key].copy()
                            config["key"] = key
                            configuration_key.append(config)
                        else:
                            # Return unknown key
                            self.logger.warning(
                                f"Unknown configuration key requested: {key}"
                            )

                    response = {"configurationKey": configuration_key}
                else:
                    # Return all keys if no specific keys were requested
                    configuration_key = []
                    for key, config in all_config_keys.items():
                        config_copy = config.copy()
                        config_copy["key"] = key
                        configuration_key.append(config_copy)

                    response = {"configurationKey": configuration_key}

            elif action == Action.change_configuration:
                response = {"status": "Accepted"}

            elif action == Action.change_availability:
                response = {"status": "Accepted"}

            elif action == Action.trigger_message:
                response = {"status": "Accepted"}

            elif action == Action.authorize:
                response = {"idTagInfo": {"status": "Accepted"}}

            elif action == Action.start_transaction:
                # Let Home Assistant handle the transaction ID
                response = {"idTagInfo": {"status": "Accepted"}}

            elif action == Action.stop_transaction:
                response = {"idTagInfo": {"status": "Accepted"}}

            elif action == Action.meter_values:
                response = {}

            elif action == Action.heartbeat:
                response = {"currentTime": datetime.now(timezone.utc).isoformat()}

            else:
                self.logger.warning(f"Unknown action: {action}")
                return

            # Send response
            response_message = [3, message_id, response]
            await self.websocket.send(json.dumps(response_message))
            self.logger.debug(f"Response sent: {response_message}")

        except Exception as e:
            self.logger.error(f"Error handling call {action}: {e}")

    async def shutdown(self):
        """Gracefully shutdown the simulator."""
        self.logger.info("Shutting down...")
        self.should_exit = True

        if self.charging:
            await self.stop_charging_session()

        if self.heartbeat_task:
            self.heartbeat_task.cancel()

        if self.meter_values_task:
            self.meter_values_task.cancel()

        if self.command_task:
            self.command_task.cancel()

        if self.websocket:
            await self.websocket.close()

        self.connected = False

    async def run(self):
        """Main run loop with automatic reconnection."""
        while not self.should_exit:
            try:
                if not self.connected:
                    await self.connect()

                if self.connected:
                    # Start all the background tasks if not already running
                    if not self.heartbeat_task or self.heartbeat_task.done():
                        self.heartbeat_task = asyncio.create_task(self.heartbeat_loop())

                    if not self.command_task or self.command_task.done():
                        self.command_task = asyncio.create_task(
                            self.command_interface()
                        )

                    # Start the message loop (this will handle incoming messages)
                    await self.message_loop()

                # If we get here, connection was lost
                self.connected = False
                if not self.should_exit:
                    await asyncio.sleep(5)  # Wait before reconnecting

            except Exception as e:
                self.logger.error(f"Connection error: {e}")
                self.connected = False
                if not self.should_exit:
                    await asyncio.sleep(5)  # Wait before reconnecting


async def main():
    """Main entry point."""
    charger_id = sys.argv[1] if len(sys.argv) > 1 else "TEST_CHARGER_001"
    host = sys.argv[2] if len(sys.argv) > 2 else "localhost"
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 9000

    simulator = ChargerSimulator(charger_id, host, port)

    # Start the simulator
    await simulator.run()


if __name__ == "__main__":
    asyncio.run(main())
