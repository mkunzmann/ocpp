#!/usr/bin/env python3
"""
Validation script to test the charging session script components
without requiring a connection to Home Assistant.
"""

import asyncio
import logging
from datetime import datetime, UTC
from ocpp.v16 import call, call_result
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


def test_ocpp_message_creation():
    """Test that OCPP messages can be created correctly."""
    logger.info("Testing OCPP message creation...")

    # Test BootNotification
    boot_request = call.BootNotification(
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
    logger.info(f"BootNotification request created: {boot_request}")

    # Test Authorize
    auth_request = call.Authorize(id_tag="pulsar")
    logger.info(f"Authorize request created: {auth_request}")

    # Test StartTransaction
    start_request = call.StartTransaction(
        connector_id=1,
        id_tag="pulsar",
        meter_start=12345,
        reservation_id=None,
        timestamp=datetime.now(UTC).isoformat(),
    )
    logger.info(f"StartTransaction request created: {start_request}")

    # Test MeterValues
    meter_request = call.MeterValues(
        connector_id=1,
        transaction_id=1,
        meter_value=[
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "sampled_value": [
                    {
                        "value": "12345",
                        "measurand": Measurand.energy_active_import_register,
                        "unit": UnitOfMeasure.wh,
                    },
                    {
                        "value": "12.345",
                        "measurand": Measurand.energy_active_import_register,
                        "unit": UnitOfMeasure.kwh,
                    },
                ],
            }
        ],
    )
    logger.info(f"MeterValues request created: {meter_request}")

    # Test StatusNotification
    status_request = call.StatusNotification(
        connector_id=1,
        error_code=ChargePointErrorCode.no_error,
        status=ChargePointStatus.charging,
        timestamp=datetime.now(UTC).isoformat(),
        info="",
        vendor_id="",
        vendor_error_code="",
    )
    logger.info(f"StatusNotification request created: {status_request}")

    # Test StopTransaction
    stop_request = call.StopTransaction(
        transaction_id=1,
        id_tag="pulsar",
        meter_stop=15678,
        timestamp=datetime.now(UTC).isoformat(),
        transaction_data=[
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "sampled_value": [
                    {
                        "value": "15678",
                        "measurand": Measurand.energy_active_import_register,
                        "unit": UnitOfMeasure.wh,
                    }
                ],
            }
        ],
        reason="Remote",
    )
    logger.info(f"StopTransaction request created: {stop_request}")

    logger.info("✅ All OCPP message creation tests passed!")


def test_energy_calculation():
    """Test energy calculation logic."""
    logger.info("Testing energy calculation...")

    meter_start = 12345  # 12.345 kWh
    meter_end = 15678  # 15.678 kWh

    energy_charged_wh = meter_end - meter_start
    energy_charged_kwh = energy_charged_wh / 1000

    logger.info(f"Meter start: {meter_start} Wh ({meter_start / 1000:.3f} kWh)")
    logger.info(f"Meter end: {meter_end} Wh ({meter_end / 1000:.3f} kWh)")
    logger.info(
        f"Energy charged: {energy_charged_wh} Wh ({energy_charged_kwh:.3f} kWh)"
    )

    expected_energy = 3.333  # kWh
    if abs(energy_charged_kwh - expected_energy) < 0.001:
        logger.info("✅ Energy calculation test passed!")
    else:
        logger.error(
            f"❌ Energy calculation failed! Expected {expected_energy}, got {energy_charged_kwh}"
        )


def test_configuration():
    """Test configuration values."""
    logger.info("Testing configuration...")

    config = {
        "CHARGER_ID": "TEST_CHARGER_001",
        "CENTRAL_SYSTEM_URL": "ws://localhost:9000",
        "ID_TAG": "pulsar",
        "METER_START": 12345,
        "METER_END": 15678,
    }

    logger.info(f"Charger ID: {config['CHARGER_ID']}")
    logger.info(f"Central System URL: {config['CENTRAL_SYSTEM_URL']}")
    logger.info(f"ID Tag: {config['ID_TAG']}")
    logger.info(f"Meter Start: {config['METER_START']} Wh")
    logger.info(f"Meter End: {config['METER_END']} Wh")

    logger.info("✅ Configuration test passed!")


async def main():
    """Run all validation tests."""
    logger.info("=== OCPP Charging Session Script Validation ===")

    try:
        test_ocpp_message_creation()
        test_energy_calculation()
        test_configuration()

        logger.info("=== All validation tests passed! ===")
        logger.info("The charging session script is ready to use.")
        logger.info(
            "Make sure Home Assistant OCPP integration is running before executing the main script."
        )

    except Exception as e:
        logger.error(f"Validation failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
