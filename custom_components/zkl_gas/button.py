"""Manual refresh of all account endpoints."""

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import account_device, account_identifier


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([RefreshButton(entry)])


class RefreshButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "refresh"
    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry):
        self.runtime = entry.runtime_data
        self._attr_unique_id = f"{account_identifier(entry)}_refresh"
        self._attr_device_info = account_device(entry)

    async def async_press(self):
        await self.runtime.refresh()
