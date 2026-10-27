"""Home Assistant integration for Zhongkunlun Gas."""

from __future__ import annotations

import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GasApi
from .const import CONF_FILIALE, CONF_OPENID, DEFAULT_FILIALE
from .coordinator import GasCoordinator, GasRuntime
from .entity import account_device

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = GasApi(
        async_get_clientsession(hass),
        entry.data[CONF_OPENID],
        entry.data.get(CONF_FILIALE, DEFAULT_FILIALE),
    )
    meters = GasCoordinator(hass, entry, api, "meters")
    usage = GasCoordinator(hass, entry, api, "usage")
    payments = GasCoordinator(hass, entry, api, "payments", meters)
    entry.runtime_data = GasRuntime(api, meters, usage, payments)
    await meters.async_config_entry_first_refresh()
    # Optional endpoints may be temporarily unavailable at setup.
    await asyncio.gather(usage.async_refresh(), payments.async_refresh())
    device_registry.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **account_device(entry)
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
