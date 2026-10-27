"""Shared household and meter device identities."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_FILIALE, CONF_USER_ID, DOMAIN


def account_identifier(entry):
    return f"{entry.data[CONF_FILIALE]}_{entry.data[CONF_USER_ID]}"


def meter_identifier(row):
    """Do not use id/f_meteread_maxid, which identify changing readings."""
    value = row.get("f_meternumber")
    return str(value) if value else None


def account_device(entry):
    return DeviceInfo(
        identifiers={(DOMAIN, account_identifier(entry))},
        name=entry.title,
        manufacturer=entry.data.get("company", "中昆仑燃气"),
        model="燃气账户",
    )


class GasEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key, meter=None):
        super().__init__(coordinator)
        self.entry = entry
        self.meter_id = meter_identifier(meter) if meter else None
        suffix = f"_meter_{self.meter_id}" if self.meter_id else ""
        self._attr_unique_id = f"{account_identifier(entry)}{suffix}_{key}"
        self._attr_device_info = account_device(entry)
        if self.meter_id:
            self._attr_device_info = DeviceInfo(
                identifiers={
                    (DOMAIN, f"{account_identifier(entry)}_meter_{self.meter_id}")
                },
                name=f"燃气表 {self.meter_id}",
                manufacturer=meter.get("f_meter_brand") or "中昆仑燃气",
                model=meter.get("f_meter_classify"),
                serial_number=self.meter_id,
                via_device=(DOMAIN, account_identifier(entry)),
            )

    @property
    def row(self):
        if self.meter_id:
            return next(
                (
                    row
                    for row in (self.coordinator.data or [])
                    if meter_identifier(row) == self.meter_id
                ),
                None,
            )
        rows = self.coordinator.data or []
        return rows[0] if rows else None

    @property
    def available(self):
        return super().available and (self.meter_id is None or self.row is not None)
