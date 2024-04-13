from homeassistant.components.number import PLATFORM_SCHEMA, NumberEntity
from homeassistant.const import PERCENTAGE
import homeassistant.helpers.config_validation as cv
from homeassistant.const import (CONF_HOST, CONF_NAME)

import voluptuous as vol
from functools import cached_property
import logging

from .hoymiles.client import HoymilesModbusTCP
from .hoymiles.datatypes import MicroinverterType


CONF_RW_COILS = "rw_coils"
RW_TYPES = {
    'limit_active_power'
}
DEFAULT_NAME = 'Hoymiles DTU'
CONF_DTU_TYPE = "dtu_type"
_LOGGER = logging.getLogger(__name__)


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_RW_COILS, default=[]):
        vol.All(cv.ensure_list, [vol.In(RW_TYPES)]),
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_DTU_TYPE, default=0): cv.byte,    
})


def setup_platform(hass, config, add_entities, discovery_info=None):
    name = config.get(CONF_NAME)
    host = config.get(CONF_HOST)
    dtu_type = config.get(CONF_DTU_TYPE)
    dev = []
    if 'limit_active_power' in RW_TYPES:
        dev.append(HoymilesInverterInput(name, host, dtu_type))
    add_entities(dev, True)


class HoymilesInverterInput(NumberEntity):
    # TODO 
    # Numbers which restore the state should extend RestoreNumber and call await self.async_get_last_number_data from async_added_to_hass
    def __init__(self, name, client_host, dtu_type):
        self._client_name = name + ' inverters power limit'
        self._value = 100  # Initializes with 100 instead of reading to prevent startup error and update reads
        self._min_value = 2
        self._max_value = 100
        self._step = 1
        self._mode = "box"  # To prevent accidentally setting the value multiple times
        self._unit_of_measurement = PERCENTAGE
        self._name = 'limit_active_power'
        self._client_host = client_host
        self._dtu_type = dtu_type
        self._type = 'limit_active_power'


    @property
    def name(self):
        return '{} {}'.format(self._client_name, self._type)

    @property
    def unique_id(self):
        """Return a unique ID."""
        return f"dtu-pv-{self._name}-{self._type.lower()}" 
    
    @cached_property
    def native_min_value(self):
        return self._min_value

    @cached_property
    def native_max_value(self):
        return self._max_value

    @property
    def native_value(self):
        return self._value

    @cached_property
    def native_unit_of_measurement(self):
        return self._unit_of_measurement
    
    @cached_property
    def native_step(self):
        return self._step

    @cached_property
    def mode(self):
        return self._mode
    
    # def set_native_value(self, value: float):
    #     rounded_value = round(value)
    #     HoymilesModbusTCP(
    #         self._client_host,
    #         microinverter_type=MicroinverterType.HM,
    #         dtu_type=self._dtu_type
    #     ).set_active_power(0xC001, rounded_value)
    #     self._value = value

    async def async_set_native_value(self, value: float):
        rounded_value = round(value)
        HoymilesModbusTCP(
            self._client_host,
            microinverter_type=MicroinverterType.HM,
            dtu_type=self._dtu_type
        ).set_active_power(0xC001, rounded_value)
        self._value = rounded_value
        _LOGGER.warning(f"Set inverter input number value to {self._value}")
