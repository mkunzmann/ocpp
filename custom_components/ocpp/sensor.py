"""Sensor platform for ocpp."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import homeassistant
from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import CONF_MONITORED_VARIABLES
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

_LOGGER = logging.getLogger(__name__)

from .api import CentralSystem
from .const import (
    CONF_AUTH_LIST,
    CONF_CPID,
    CONF_CPIDS,
    DATA_UPDATED,
    DEFAULT_CLASS_UNITS_HA,
    DOMAIN,
    ICON,
    Measurand,
)
from .enums import HAChargerDetails, HAChargerSession, HAChargerStatuses


@dataclass
class OcppSensorDescription(SensorEntityDescription):
    """Class to describe a Sensor entity."""

    metric: str | None = None
    key: str | None = None
    name: str | None = None
    entity_category: EntityCategory | None = None


@dataclass
class ChargingSession:
    """Represents a charging session for an ID tag."""

    id_tag: str
    transaction_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    energy_kwh: float = 0.0
    duration_minutes: int = 0


class TagEnergySensor(RestoreSensor, SensorEntity):
    """Sensor for tracking energy charged per ID tag."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        central_system: CentralSystem,
        tag_id: str,
    ):
        """Initialize the tag energy sensor."""
        self.central_system = central_system
        self.tag_id = tag_id
        self._hass = hass
        self.hass = hass  # Set the base class attribute
        self._sessions: List[ChargingSession] = []
        self._total_energy = 0.0
        self._last_session: Optional[ChargingSession] = None

        self._attr_unique_id = f"{DOMAIN}.tag_energy.{tag_id}"
        self._attr_name = f"Energy Charged - {tag_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"tag_{tag_id}")},
            name=f"Tag {tag_id}",
            model="OCPP ID Tag",
        )
        self._attr_icon = "mdi:account-lightning-bolt"
        self._attr_native_unit_of_measurement = "kWh"
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

        _LOGGER.info(
            f"Initialized TagEnergySensor for tag {tag_id} with unique_id: {self._attr_unique_id}"
        )

    @property
    def available(self) -> bool:
        """Return if sensor is available."""
        return True

    @property
    def should_poll(self):
        """Return True if entity has to be polled for state."""
        return False

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = {
            "total_sessions": len(self._sessions),
            "last_session_start": None,
            "last_session_end": None,
            "last_session_energy": None,
            "last_session_duration": None,
        }

        if self._last_session:
            attrs.update(
                {
                    "last_session_start": self._last_session.start_time.isoformat(),
                    "last_session_end": self._last_session.end_time.isoformat()
                    if self._last_session.end_time
                    else None,
                    "last_session_energy": self._last_session.energy_kwh,
                    "last_session_duration": self._last_session.duration_minutes,
                }
            )

        # Add recent sessions (last 10)
        recent_sessions = []
        for session in self._sessions[-10:]:
            recent_sessions.append(
                {
                    "transaction_id": session.transaction_id,
                    "start_time": session.start_time.isoformat(),
                    "end_time": session.end_time.isoformat()
                    if session.end_time
                    else None,
                    "energy_kwh": session.energy_kwh,
                    "duration_minutes": session.duration_minutes,
                }
            )
        attrs["recent_sessions"] = recent_sessions

        return attrs

    @property
    def native_value(self):
        """Return the total energy charged for this tag."""
        return self._total_energy

    def add_session(self, session: ChargingSession):
        """Add a new charging session."""
        self._sessions.append(session)
        if session.end_time and session.energy_kwh > 0:
            self._total_energy += session.energy_kwh
        self._last_session = session
        # Only schedule update if we're in a real Home Assistant context
        if (
            hasattr(self, "_hass")
            and self._hass is not None
            and hasattr(self._hass, "async_create_task")
        ):
            self.async_schedule_update_ha_state(True)

    def update_session(
        self, transaction_id: str, energy_kwh: float, duration_minutes: int
    ):
        """Update an existing session with final values."""
        for session in self._sessions:
            if session.transaction_id == transaction_id and session.end_time is None:
                session.energy_kwh = energy_kwh
                session.duration_minutes = duration_minutes
                session.end_time = datetime.now()
                if energy_kwh > 0:
                    self._total_energy += energy_kwh
                self._last_session = session
                # Only schedule update if we're in a real Home Assistant context
                if (
                    hasattr(self, "_hass")
                    and self._hass is not None
                    and hasattr(self._hass, "async_create_task")
                ):
                    self.async_schedule_update_ha_state(True)
                break

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        _LOGGER.info(
            f"TagEnergySensor {self._attr_unique_id} being added to Home Assistant"
        )
        await super().async_added_to_hass()
        if restored := await self.async_get_last_sensor_data():
            self._attr_native_value = restored.native_value
            self._attr_native_unit_of_measurement = restored.native_unit_of_measurement
            _LOGGER.info(
                f"Restored sensor data for {self._attr_unique_id}: {self._attr_native_value}"
            )

        async_dispatcher_connect(
            self._hass, DATA_UPDATED, self._schedule_immediate_update
        )
        _LOGGER.info(
            f"TagEnergySensor {self._attr_unique_id} successfully added to Home Assistant"
        )

    @callback
    def _schedule_immediate_update(self):
        self.async_schedule_update_ha_state(True)


async def async_setup_entry(hass, entry, async_add_entities):
    """Configure the sensor platform."""
    central_system = hass.data[DOMAIN][entry.entry_id]
    entities = []

    # Create tag energy sensors for each authorized ID tag
    # Check if we have a converted auth_list from hass.data
    converted_auth_list = hass.data.get(DOMAIN, {}).get("converted_auth_list")
    if converted_auth_list is not None:
        auth_list = converted_auth_list
        _LOGGER.info("Using converted auth list from hass.data")
    else:
        auth_list = entry.data.get(CONF_AUTH_LIST, {})
        _LOGGER.info(f"Setting up sensors. Auth list: {auth_list}")
        _LOGGER.info(f"Auth list type: {type(auth_list)}")
        _LOGGER.info(f"Entry data keys: {list(entry.data.keys())}")

        # Handle both list and dict formats for authorization_list
        if isinstance(auth_list, list):
            _LOGGER.info("Auth list is a list, converting to dict format")
            auth_dict = {}
            for item in auth_list:
                if isinstance(item, dict) and "id_tag" in item:
                    tag_id = item["id_tag"]
                    auth_dict[tag_id] = item
            auth_list = auth_dict
            _LOGGER.info(f"Converted auth list to dict: {auth_list}")

    _LOGGER.info(f"Auth list keys: {list(auth_list.keys())}")

    tag_sensors = {}
    for tag_id in auth_list.keys():
        _LOGGER.info(f"Creating tag energy sensor for tag: {tag_id}")
        tag_sensor = TagEnergySensor(hass, central_system, tag_id)
        tag_sensors[tag_id] = tag_sensor
        entities.append(tag_sensor)
        _LOGGER.info(f"Created sensor with unique_id: {tag_sensor._attr_unique_id}")

    _LOGGER.info(f"Created {len(tag_sensors)} tag energy sensors")
    _LOGGER.info(f"Total entities to add: {len(entities)}")

    # Store tag sensors in central system for access by charge points
    central_system.tag_sensors = tag_sensors
    central_system.set_tag_sensors_for_all_charge_points(tag_sensors)
    _LOGGER.info(f"Stored tag sensors in central system: {list(tag_sensors.keys())}")
    _LOGGER.info(f"Central system ID: {id(central_system)}")
    _LOGGER.info(f"Central system type: {type(central_system)}")

    # setup all chargers added to config
    for charger in entry.data[CONF_CPIDS]:
        cp_id_settings = list(charger.values())[0]
        cpid = cp_id_settings[CONF_CPID]
        SENSORS = []
        for metric in list(
            set(
                cp_id_settings[CONF_MONITORED_VARIABLES].split(",")
                + list(HAChargerSession)
            )
        ):
            SENSORS.append(
                OcppSensorDescription(
                    key=metric.lower(),
                    name=metric.replace(".", " "),
                    metric=metric,
                )
            )
        for metric in list(HAChargerStatuses) + list(HAChargerDetails):
            SENSORS.append(
                OcppSensorDescription(
                    key=metric.lower(),
                    name=metric.replace(".", " "),
                    metric=metric,
                    entity_category=EntityCategory.DIAGNOSTIC,
                )
            )

        for ent in SENSORS:
            cpx = ChargePointMetric(
                hass,
                central_system,
                cpid,
                ent,
            )
            entities.append(cpx)

    _LOGGER.info(f"Calling async_add_entities with {len(entities)} entities")
    async_add_entities(entities, False)
    _LOGGER.info("async_add_entities call completed")


class ChargePointMetric(RestoreSensor, SensorEntity):
    """Individual sensor for charge point metrics."""

    _attr_has_entity_name = True
    entity_description: OcppSensorDescription

    def __init__(
        self,
        hass: HomeAssistant,
        central_system: CentralSystem,
        cpid: str,
        description: OcppSensorDescription,
    ):
        """Instantiate instance of a ChargePointMetrics."""
        self.central_system = central_system
        self.cpid = cpid
        self.entity_description = description
        self.metric = self.entity_description.metric
        self._hass = hass
        self._extra_attr = {}
        self._last_reset = homeassistant.util.dt.utc_from_timestamp(0)
        self._attr_unique_id = ".".join(
            [DOMAIN, self.cpid, self.entity_description.key, SENSOR_DOMAIN]
        )
        self._attr_name = self.entity_description.name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.cpid)},
        )
        self._attr_icon = ICON
        self._attr_native_unit_of_measurement = None

    @property
    def available(self) -> bool:
        """Return if sensor is available."""
        return self.central_system.get_available(self.cpid)

    @property
    def should_poll(self):
        """Return True if entity has to be polled for state.

        False if entity pushes its state to HA.
        """
        return True

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self.central_system.get_extra_attr(self.cpid, self.metric)

    @property
    def state_class(self):
        """Return the state class of the sensor."""
        state_class = None
        if self.device_class is SensorDeviceClass.ENERGY:
            state_class = SensorStateClass.TOTAL_INCREASING
        elif self.device_class in [
            SensorDeviceClass.CURRENT,
            SensorDeviceClass.VOLTAGE,
            SensorDeviceClass.POWER,
            SensorDeviceClass.REACTIVE_POWER,
            SensorDeviceClass.TEMPERATURE,
            SensorDeviceClass.BATTERY,
            SensorDeviceClass.FREQUENCY,
        ] or self.metric in [
            HAChargerStatuses.latency_ping.value,
            HAChargerStatuses.latency_pong.value,
        ]:
            state_class = SensorStateClass.MEASUREMENT

        return state_class

    @property
    def device_class(self):
        """Return the device class of the sensor."""
        device_class = None
        if self.metric.lower().startswith("current."):
            device_class = SensorDeviceClass.CURRENT
        elif self.metric.lower().startswith("voltage"):
            device_class = SensorDeviceClass.VOLTAGE
        elif self.metric.lower().startswith("energy.r"):
            device_class = None
        elif self.metric.lower().startswith("energy"):
            device_class = SensorDeviceClass.ENERGY
        elif self.metric in [
            Measurand.frequency,
            Measurand.rpm,
        ] or self.metric.lower().startswith("frequency"):
            device_class = SensorDeviceClass.FREQUENCY
        elif self.metric.lower().startswith(("power.a", "power.o")):
            device_class = SensorDeviceClass.POWER
        elif self.metric.lower().startswith("power.r"):
            device_class = SensorDeviceClass.REACTIVE_POWER
        elif self.metric.lower().startswith("temperature"):
            device_class = SensorDeviceClass.TEMPERATURE
        elif self.metric.lower().startswith("timestamp") or self.metric in [
            HAChargerDetails.config_response.value,
            HAChargerDetails.data_response.value,
            HAChargerStatuses.heartbeat.value,
        ]:
            device_class = SensorDeviceClass.TIMESTAMP
        elif self.metric.lower().startswith("soc"):
            device_class = SensorDeviceClass.BATTERY
        return device_class

    @property
    def native_value(self):
        """Return the state of the sensor, rounding if a number."""
        value = self.central_system.get_metric(self.cpid, self.metric)
        if value is not None:
            self._attr_native_value = value
        return self._attr_native_value

    @property
    def native_unit_of_measurement(self):
        """Return the native unit of measurement."""
        value = self.central_system.get_ha_unit(self.cpid, self.metric)
        if value is not None:
            self._attr_native_unit_of_measurement = value
        else:
            self._attr_native_unit_of_measurement = DEFAULT_CLASS_UNITS_HA.get(
                self.device_class
            )
        return self._attr_native_unit_of_measurement

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        if restored := await self.async_get_last_sensor_data():
            self._attr_native_value = restored.native_value
            self._attr_native_unit_of_measurement = restored.native_unit_of_measurement

        async_dispatcher_connect(
            self._hass, DATA_UPDATED, self._schedule_immediate_update
        )

    @callback
    def _schedule_immediate_update(self):
        self.async_schedule_update_ha_state(True)
