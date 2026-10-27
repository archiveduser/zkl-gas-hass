"""Gas account and meter sensors."""

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfVolume

from .api import number, timestamp
from .entity import GasEntity, meter_identifier


@dataclass(frozen=True, kw_only=True)
class GasSensorDescription(SensorEntityDescription):
    field: str
    is_text: bool = False


METER_SENSORS = (
    GasSensorDescription(
        key="balance",
        translation_key="balance",
        field="f_balance_amount",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="CNY",
    ),
    GasSensorDescription(
        key="remaining_gas",
        translation_key="remaining_gas",
        field="f_balance_gas",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
    ),
    GasSensorDescription(
        key="meter_reading",
        translation_key="meter_reading",
        field="f_meter_base",
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    GasSensorDescription(
        key="meter_status",
        translation_key="meter_status",
        field="f_table_state",
        is_text=True,
    ),
)
USAGE_SENSORS = (
    GasSensorDescription(
        key="last_usage",
        translation_key="last_usage",
        field="f_oughtamount",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
    ),
    GasSensorDescription(
        key="last_fee",
        translation_key="last_fee",
        field="f_oughtfee",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="CNY",
    ),
    GasSensorDescription(
        key="last_reading_time",
        translation_key="last_reading_time",
        field="f_input_date",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
)
PAYMENT_SENSORS = (
    GasSensorDescription(
        key="last_payment",
        translation_key="last_payment",
        field="f_collection",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="CNY",
    ),
    GasSensorDescription(
        key="last_payment_time",
        translation_key="last_payment_time",
        field="f_delivery_date",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    async_add_entities(
        [
            *(
                GasSensor(runtime.usage, entry, description)
                for description in USAGE_SENSORS
            ),
            *(
                GasSensor(runtime.payments, entry, description)
                for description in PAYMENT_SENSORS
            ),
        ]
    )
    known = set()

    def add_meters():
        entities = []
        for meter in runtime.meters.data or []:
            identity = meter_identifier(meter)
            if identity and identity not in known:
                known.add(identity)
                entities.extend(
                    GasSensor(runtime.meters, entry, description, meter)
                    for description in METER_SENSORS
                )
        if entities:
            async_add_entities(entities)

    add_meters()
    entry.async_on_unload(runtime.meters.async_add_listener(add_meters))


class GasSensor(GasEntity, SensorEntity):
    def __init__(self, coordinator, entry, description, meter=None):
        super().__init__(coordinator, entry, description.key, meter)
        self.entity_description = description

    @property
    def native_value(self):
        row = self.row
        if row is None:
            return None
        value = row.get(self.entity_description.field)
        if self.entity_description.device_class == SensorDeviceClass.TIMESTAMP:
            return timestamp(value)
        if self.entity_description.is_text:
            return str(value) if value is not None else None
        return number(value)

    @property
    def extra_state_attributes(self):
        if not self.row:
            return None
        if self.entity_description.key == "last_usage":
            return {
                "record_time": self.row.get("f_input_date"),
                "previous_reading": self.row.get("f_last_tablebase"),
                "reading": self.row.get("f_tablebase"),
            }
        if self.entity_description.key == "last_payment":
            return {
                "payment_method": self.row.get("f_payment"),
                "payment_time": self.row.get("f_delivery_date"),
            }
        return None
