"""Independent polling for meters, usage and payments."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GasApi, GasApiError, numeric_id, sort_records
from .const import CONF_INTERVAL, CONF_USER_ID, DEFAULT_INTERVAL, DOMAIN

LOGGER = logging.getLogger(__name__)


class GasCoordinator(DataUpdateCoordinator[list[dict]]):
    """One failure only affects entities reading this endpoint."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: GasApi,
        kind: str,
        meters: GasCoordinator | None = None,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_{kind}",
            config_entry=entry,
            update_interval=timedelta(
                minutes=360
                if kind == "payments"
                else entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL)
            ),
        )
        self.api = api
        self.kind = kind
        self.user_id = entry.data[CONF_USER_ID]
        self.meters = meters

    async def _async_update_data(self) -> list[dict]:
        try:
            if self.kind == "meters":
                rows = await self.api.meters(self.user_id)
                if not rows:
                    raise GasApiError("No meters found")
                return rows
            if self.kind == "usage":
                return await self.api.usage(self.user_id)
            if not self.meters or not self.meters.data:
                raise GasApiError("Meter information unavailable")
            files_ids = {
                numeric_id(row["f_userfiles_id"])
                for row in self.meters.data
                if row.get("f_userfiles_id") is not None
            }
            if not files_ids:
                raise GasApiError("User file identifier unavailable")
            batches = await asyncio.gather(
                *(
                    self.api.payments(self.user_id, files_id)
                    for files_id in sorted(files_ids)
                )
            )
            return sort_records(
                [row for batch in batches for row in batch], "f_delivery_date"
            )
        except GasApiError as err:
            raise UpdateFailed(str(err)) from err


@dataclass
class GasRuntime:
    """Resources for one configured household."""

    api: GasApi
    meters: GasCoordinator
    usage: GasCoordinator
    payments: GasCoordinator

    async def refresh(self) -> None:
        """Refresh meters first because payments depend on file identifiers."""
        await self.meters.async_request_refresh()
        await asyncio.gather(
            self.usage.async_request_refresh(), self.payments.async_request_refresh()
        )
