from datetime import timedelta, datetime
import logging

import voluptuous as vol

from homeassistant.util import Throttle
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfElectricCurrent, UnitOfEnergy, UnitOfPower, UnitOfElectricPotential, UnitOfTemperature, UnitOfFrequency
from homeassistant.const import (CONF_HOST, CONF_NAME, CONF_MONITORED_CONDITIONS, CONF_SCAN_INTERVAL)
# TODO unit of PERCENTAGE
from homeassistant.components.number import NumberEntity
from homeassistant.components.switch import SwitchEntity
import homeassistant.helpers.config_validation as cv

from functools import cached_property

from .hoymiles.client import HoymilesModbusTCP
from .hoymiles.datatypes import MicroinverterType

CONF_MONITORED_CONDITIONS_PV = "monitored_conditions_pv"
CONF_RW_COILS = "rw_coils"
CONF_MICROINVERTERS = "microinverters"
CONF_PANELS = "panels"
CONF_DTU_TYPE = "dtu_type"
CONF_INVERTERS = "inverters"

_LOGGER = logging.getLogger(__name__)
DEFAULT_NAME = 'Hoymiles DTU'
DEFAULT_SCAN_INTERVAL = timedelta(minutes=2)

# opis, jednostka, urzadzenie, klasa, reset, mnoznik, utrzymanie wartosci (0-brak, 1-tak, 2-do polnocy)
SENSOR_TYPES = {
    'pv_power': ['Aktualna moc', UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, None, False, 1000, 0],
    'today_production': ['Energia dzisiaj', UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, False, 1000, 2],
    'total_production': ['Energia od początku', UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL, False, 1000, 1],
    'alarm_flag': ['Flaga alarmu', ' ', 'alarm_flag', None, False, 1, 0]
}

PV_TYPES = {
    'pv_voltage': [3, 'Napięcie', UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, None, False, 1, 0],
    'pv_current': [4, 'Prąd', UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, None, False, 1, 0],
    'grid_voltage': [5, 'Napięcie sieci', UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, None, False, 1, 0],
    'grid_frequency': [6, 'Częstotliwość sieci', UnitOfFrequency.HERTZ, None, None, False, 1, 0],
    'pv_power': [7, 'Aktualna moc', UnitOfPower.WATT, SensorDeviceClass.POWER, None, False, 1, 0],
    'today_production': [8, 'Energia dzisiaj', UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, False, 1000, 2],
    'total_production': [9, 'Energia od początku', UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL, False, 1000, 1],
    'temperature': [10, 'Temperatura', UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, None, False, 1, 0],
    'operating_status': [11, 'Status', ' ', 'operating_status', None, False, 1, 0],
    'alarm_code': [12, 'Kod alarmu', ' ', 'alarm_code', None, False, 1, 0],
    'alarm_count': [13, 'Wystąpienia alarmu', ' ', 'alarm_count', None, False, 1, 0],
    'link_status': [14, 'Status połączenia', ' ', 'link_status', None, False, 1, 0]
}

RW_TYPES = {
    'on_off': [0, 'on/off status', ' ', 'limit_active_power', None, False, 1, 0],
    'limit_active_power': [1, 'percentage limit of active power production', PERCENTAGE, 'limit_active_power', None, False, 1, 0]
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_MONITORED_CONDITIONS, default=[]):
        vol.All(cv.ensure_list, [vol.In(SENSOR_TYPES)]),
    vol.Optional(CONF_MONITORED_CONDITIONS_PV, default=[]):
        vol.All(cv.ensure_list, [vol.In(PV_TYPES)]),
    vol.Optional(CONF_RW_COILS, default=[]):
        vol.All(cv.ensure_list, [vol.In(RW_TYPES)]),
    vol.Optional(CONF_PANELS, default=0): cv.byte,
    vol.Optional(CONF_INVERTERS, default=0): cv.byte,
    vol.Optional(CONF_DTU_TYPE, default=0): cv.byte,    
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.time_period
})

def setup_platform(hass, config, add_entities, discovery_info=None):
    name = config.get(CONF_NAME)
    host = config.get(CONF_HOST)
    panels = config.get(CONF_PANELS)
    inverters = config.get(CONF_INVERTERS)
    dtu_type = config.get(CONF_DTU_TYPE)
    scan_interval = config.get(CONF_SCAN_INTERVAL)
    updater = HoymilesDTUUpdater(host, scan_interval, dtu_type)
    updater.update()
    if updater.data is None:
        raise Exception('Invalid configuration for Hoymiles DTU platform')
    dev = []
    for variable in config[CONF_MONITORED_CONDITIONS]:
        dev.append(HoymilesDTUSensor(hass, name, variable, panels, updater))
    for variable in config[CONF_MONITORED_CONDITIONS_PV]:
        i = 1
        while i<=panels:
          dev.append(HoymilesPVSensor(name, updater.data.microinverter_data[i-1].serial_number, i, updater.data.microinverter_data[i-1].port_number, variable, updater))
          i+=1
    for variable in config[CONF_RW_COILS]:
            dev.append()
            dev.append(HoymilesInverterInput(name, i, variable))
    add_entities(dev, True)

class HoymilesDTUSensor(SensorEntity):
    def __init__(self, hass, name, sensor_type, panels, updater):
        self._hass = hass
        self._client_name = name
        self._type = sensor_type
        self._updater = updater
        self._name = SENSOR_TYPES[sensor_type][0]
        self._state = None
        self._unit_of_measurement = SENSOR_TYPES[sensor_type][1]
        self._state_old = 0
        self._panels = panels
        
    @property
    def name(self):
        return '{} {}'.format(self._client_name, self._type)

    @property
    def state(self):
        if self._updater.data is not None and self._updater.data.total_production>0:
            temp = vars(self._updater.data)
            self._state = temp[self._type]/SENSOR_TYPES[self._type][5]
        elif self._updater.data is not None and self._updater.data.total_production==0:
            if SENSOR_TYPES[self._type][6]==0:
                self._state = 0
            elif SENSOR_TYPES[self._type][6]==2 and datetime.now().hour==0:
                self._state = 0
            if self._updater.data is not None and self._type=='total_production':
                i = 1
                licz_total = 0
                while i<=self._panels:
                    temp2 = self._updater.data.microinverter_data[i-1]
                    licz_total = licz_total + temp2[PV_TYPES[self._type][0]]/PV_TYPES[self._type][6]
                    i+=1
                if licz_total>0:
                    self._state = licz_total
            if self._updater.data is not None and self._type=='today_production':
                i = 1
                licz_total = 0
                while i<=self._panels:
                    temp2 = self._updater.data.microinverter_data[i-1]
                    licz_total = licz_total + temp2[PV_TYPES[self._type][0]]/PV_TYPES[self._type][6]
                    i+=1
                if licz_total>0:
                    self._state = licz_total
        if self._state is not None and self._state < self._state_old and self._type=='total_production':
            self._state = self._state_old
        elif self._state is not None and self._state > self._state_old and self._type=='total_production':
            if self._state > self._state_old + self._panels*0.5 and self._state_old > 0:
                self._state = self._state_old
            else:
                self._state_old = self._state

        return self._state

    @property
    def unique_id(self):
        """Return a unique ID."""
        return f"dtu-{self._client_name.lower()}-{self._type.lower()}"  

    @property
    def device_class(self):
        return SENSOR_TYPES[self._type][2]

    @property
    def state_class(self):
        return SENSOR_TYPES[self._type][3]

    @property
    def last_reset(self):
        if SENSOR_TYPES[self._type][4]:
            return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
			
    @property
    def unit_of_measurement(self):
        return self._unit_of_measurement

    def update(self):
        self._updater.update()

class HoymilesPVSensor(SensorEntity):
    def __init__(self, name, serial_number, panel_number, panel, sensor_type, updater):
        self._client_name = name +' '+ serial_number +' PV '+str(panel)
        self._serial_number = serial_number
        self._panel_number = panel_number
        self._panel = panel
        self._type = sensor_type
        self._updater = updater
        self._name = PV_TYPES[sensor_type][1]
        self._state = None
        self._unit_of_measurement = PV_TYPES[sensor_type][2]
        self._unique_id_name = name



    @property
    def name(self):
        return '{} {}'.format(self._client_name, self._type)

    @property
    def state(self):
        if self._updater.data is not None and self._updater.data.total_production>0:
            temp = self._updater.data.microinverter_data[self._panel_number-1]
            self._state = temp[PV_TYPES[self._type][0]]/PV_TYPES[self._type][6]
        elif self._updater.data is not None and self._updater.data.total_production==0:
            if PV_TYPES[self._type][7]==0:
                self._state = 0
            elif PV_TYPES[self._type][7]==2 and datetime.now().hour==0:
                self._state = 0
        return self._state

    @property
    def unique_id(self):
        """Return a unique ID."""
        return f"dtu-pv-{self._unique_id_name}-{self._serial_number}-{str(self._panel)}-{self._type.lower()}"  
        
    @property
    def device_class(self):
        return PV_TYPES[self._type][3]

    @property
    def state_class(self):
        return PV_TYPES[self._type][4]

    @property
    def last_reset(self):
        if PV_TYPES[self._type][5]:
            return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    @property
    def unit_of_measurement(self):
        return self._unit_of_measurement

    def update(self):
        self._updater.update()


class HoymilesInverterInput(NumberEntity):
    def __init__(self, name, index, sensor_type, client_host, dtu_type):
        self._client_name = name + f' inverter {index}'
        self._index = index
        self._value = 100  # Initializes with 100 instead of reading to prevent startup error and update reads
        self._min_value = 2
        self._max_value = 100
        self._step = 1
        self._mode = "box"  # To prevent accidentally setting the value multiple times
        self._unit_of_measurement = PERCENTAGE
        self._name = RW_TYPES[sensor_type][1]
        self._client_host = client_host
        self._dtu_type = dtu_type
        self._type = sensor_type


    @property
    def name(self):
        return '{} {}'.format(self._client_name, self._type)

    @property
    def unique_id(self):
        """Return a unique ID."""
        return f"dtu-pv-{self._name}-{self._index}-{self._type.lower()}" 

    @property
    def value(self):
        return self.value
    
    @cached_property
    def native_min_value(self):
        return self._min_value

    @cached_property
    def native_max_value(self):
        return self._max_value

    @cached_property
    def native_value(self):
        return self._value

    @cached_property
    def native_unit_of_measurement(self):
        return PERCENTAGE
    
    @cached_property
    def native_step(self):
        return self._step

    @cached_property
    def mode(self):
        return self.mode
    
    def set_native_value(self, value: float):
        rounded_value = round(value)
        with HoymilesModbusTCP(
            self._client_host,
            microinverter_type=MicroinverterType.HM,
            dtu_type=self._dtu_type
        ) as client:
            client.set_active_power(self._index * 6 + 0xC007, rounded_value)



class HoymilesInverterBoolean(SwitchEntity):
    def __init__(self, name, index, sensor_type, client_host, dtu_type):
        self._client_name = name + f' inverter {index}'
        self._index = index
        self._name = RW_TYPES[sensor_type][1]
        self._type = sensor_type
        self._client_host = client_host
        self._dtu_type = dtu_type
        self._is_on = True  # Dirty hack to prevent coil reads on update

    @property
    def name(self):
        return '{} {}'.format(self._client_name, self._type)

    @property
    def unique_id(self):
        """Return a unique ID."""
        return f"dtu-pv-{self._name}-{self._index}-{self._type.lower()}" 

    @property
    def is_on(self):
        return self._is_on

    def turn_on(self):
        with HoymilesModbusTCP(
            self._client_host,
            microinverter_type=MicroinverterType.HM,
            dtu_type=self._dtu_type
        ) as client:
            client.set_on_off(self._index * 6 + 0xC006, True)

    def turn_off(self):
        with HoymilesModbusTCP(
            self._client_host,
            microinverter_type=MicroinverterType.HM,
            dtu_type=self._dtu_type
        ) as client:
            client.set_on_off(self._index * 6 + 0xC006, False)


# class HoymilesInverterSensor(SensorEntity):
#     def __init__(self, name, index, sensor_type, updater):
#         self._client_name = name + f' inverter {index}'
#         self._index = index
#         self._inverter_number = -1
#         self._type = sensor_type
#         self._updater = updater
#         self._name = RW_TYPES[sensor_type][1]
#         self._state = None
#         self._unit_of_measurement = RW_TYPES[sensor_type][2]
#         self._unique_id_name = name

#     @property
#     def name(self):
#         return '{} {}'.format(self._client_name, self._type)

#     @property
#     def state(self):
#         if self._updater.data is not None:
#             temp = self._updater.data.microinverter_coils[self._inverter_number-1]
#             self._state = temp[RW_TYPES[self._type][0]]
#         return self._state


#     @property
#     def unique_id(self):
#         """Return a unique ID."""
#         return f"dtu-inverter-{self._unique_id_name}-{self._index}-{self._type.lower()}"  
        
#     @property
#     def device_class(self):
#         return RW_TYPES[self._type][3]

#     @property
#     def state_class(self):
#         return RW_TYPES[self._type][4]

#     @property
#     def unit_of_measurement(self):
#         return self._unit_of_measurement

#     def update(self):
#         self._updater.update()



class HoymilesDTUUpdater:
    def __init__(self, host, scan_interval, dtu_type):
        self.host = host
        self.update = Throttle(scan_interval)(self._update)
        self.data = None
        self.dtu_type = dtu_type
    def _update(self):
        try:
          plant_data = HoymilesModbusTCP(self.host, microinverter_type=MicroinverterType.HM, dtu_type=self.dtu_type).plant_data
          self.data = plant_data
        except:
          self.data = None
