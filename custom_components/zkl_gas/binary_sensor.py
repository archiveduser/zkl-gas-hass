"""Low balance indicator for each meter."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from .api import number
from .const import CONF_THRESHOLD, DEFAULT_THRESHOLD
from .entity import GasEntity, meter_identifier


async def async_setup_entry(hass, entry, async_add_entities):
    known = set()
    coordinator = entry.runtime_data.meters

    def add_meters():
        entities = []
        for meter in coordinator.data or []:
            identity = meter_identifier(meter)
            if identity and identity not in known:
                known.add(identity)
                entities.append(LowBalance(coordinator, entry, meter))
        if entities:
            async_add_entities(entities)

    add_meters()
    entry.async_on_unload(coordinator.async_add_listener(add_meters))


class LowBalance(GasEntity, BinarySensorEntity):
    _attr_translation_key = "low_balance"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, entry, meter):
        super().__init__(coordinator, entry, "low_balance", meter)

    @property
    def is_on(self):
        value = number(self.row.get("f_balance_amount")) if self.row else None
        if value is None:
            return None
        return value < number(self.entry.options.get(CONF_THRESHOLD, DEFAULT_THRESHOLD))

    @property
    def extra_state_attributes(self):
        return {
            "threshold": self.entry.options.get(CONF_THRESHOLD, DEFAULT_THRESHOLD),
            "threshold_currency": "CNY",
        }
