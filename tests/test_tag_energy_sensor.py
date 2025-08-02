"""Test tag energy sensor for ocpp integration."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy

from custom_components.ocpp.sensor import TagEnergySensor, ChargingSession


@pytest.fixture
def mock_central_system():
    """Create a mock central system."""
    central = MagicMock()
    central.get_available.return_value = True
    return central


@pytest.fixture
def mock_hass():
    """Create a mock hass instance."""
    hass = MagicMock()
    hass.async_create_task = MagicMock()
    return hass


def test_charging_session_creation():
    """Test creating a charging session."""
    start_time = datetime.now()
    session = ChargingSession(
        id_tag="TEST_TAG", transaction_id="12345", start_time=start_time
    )

    assert session.id_tag == "TEST_TAG"
    assert session.transaction_id == "12345"
    assert session.start_time == start_time
    assert session.end_time is None
    assert session.energy_kwh == 0.0
    assert session.duration_minutes == 0


def test_tag_energy_sensor_initialization(mock_central_system, mock_hass):
    """Test tag energy sensor initialization."""
    sensor = TagEnergySensor(mock_hass, mock_central_system, "TEST_TAG")

    assert sensor.tag_id == "TEST_TAG"
    assert sensor._attr_unique_id == "ocpp.tag_energy.TEST_TAG"
    assert sensor._attr_name == "Energy Charged - TEST_TAG"
    assert sensor._attr_native_unit_of_measurement == "kWh"
    assert sensor._attr_device_class == SensorDeviceClass.ENERGY
    assert sensor._attr_state_class == SensorStateClass.TOTAL_INCREASING
    assert sensor._total_energy == 0.0
    assert len(sensor._sessions) == 0


def test_tag_energy_sensor_add_session(mock_central_system, mock_hass):
    """Test adding a session to the sensor."""
    sensor = TagEnergySensor(mock_hass, mock_central_system, "TEST_TAG")

    # Create a session
    session = ChargingSession(
        id_tag="TEST_TAG",
        transaction_id="12345",
        start_time=datetime.now(),
        end_time=datetime.now(),
        energy_kwh=10.5,
        duration_minutes=30,
    )

    # Add the session
    sensor.add_session(session)

    assert len(sensor._sessions) == 1
    assert sensor._total_energy == 10.5
    assert sensor._last_session == session
    assert sensor.native_value == 10.5


def test_tag_energy_sensor_update_session(mock_central_system, mock_hass):
    """Test updating a session in the sensor."""
    sensor = TagEnergySensor(mock_hass, mock_central_system, "TEST_TAG")

    # Create an initial session without end time
    session = ChargingSession(
        id_tag="TEST_TAG", transaction_id="12345", start_time=datetime.now()
    )

    # Add the session
    sensor.add_session(session)
    initial_total = sensor._total_energy

    # Update the session with final values
    sensor.update_session("12345", 15.5, 45)

    assert len(sensor._sessions) == 1
    assert sensor._total_energy == initial_total + 15.5
    assert sensor._sessions[0].energy_kwh == 15.5
    assert sensor._sessions[0].duration_minutes == 45
    assert sensor._sessions[0].end_time is not None


def test_tag_energy_sensor_extra_state_attributes(mock_central_system, mock_hass):
    """Test the extra state attributes of the sensor."""
    sensor = TagEnergySensor(mock_hass, mock_central_system, "TEST_TAG")

    # Add a session
    session = ChargingSession(
        id_tag="TEST_TAG",
        transaction_id="12345",
        start_time=datetime(2023, 1, 1, 12, 0, 0),
        end_time=datetime(2023, 1, 1, 12, 30, 0),
        energy_kwh=10.5,
        duration_minutes=30,
    )
    sensor.add_session(session)

    attrs = sensor.extra_state_attributes

    assert attrs["total_sessions"] == 1
    assert attrs["last_session_start"] == "2023-01-01T12:00:00"
    assert attrs["last_session_end"] == "2023-01-01T12:30:00"
    assert attrs["last_session_energy"] == 10.5
    assert attrs["last_session_duration"] == 30
    assert len(attrs["recent_sessions"]) == 1
    assert attrs["recent_sessions"][0]["transaction_id"] == "12345"


def test_tag_energy_sensor_multiple_sessions(mock_central_system, mock_hass):
    """Test sensor with multiple sessions."""
    sensor = TagEnergySensor(mock_hass, mock_central_system, "TEST_TAG")

    # Add multiple sessions
    for i in range(3):
        session = ChargingSession(
            id_tag="TEST_TAG",
            transaction_id=f"1234{i}",
            start_time=datetime.now(),
            end_time=datetime.now(),
            energy_kwh=10.0 + i,
            duration_minutes=30 + i,
        )
        sensor.add_session(session)

    assert len(sensor._sessions) == 3
    assert sensor._total_energy == 33.0  # 10 + 11 + 12
    assert sensor.native_value == 33.0
    assert len(sensor.extra_state_attributes["recent_sessions"]) == 3
