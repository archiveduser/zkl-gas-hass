"""Configure with an OpenID, discover and select a bound household."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GasApi, GasApiError, InvalidOpenId, numeric_id, validate_openid
from .const import (
    CONF_FILIALE,
    CONF_INTERVAL,
    CONF_OPENID,
    CONF_THRESHOLD,
    CONF_USER_ID,
    DEFAULT_FILIALE,
    DEFAULT_INTERVAL,
    DEFAULT_THRESHOLD,
    DOMAIN,
)


class GasConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._openid = ""
        self._users: dict[str, dict] = {}

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                self._openid = validate_openid(user_input[CONF_OPENID])
                api = GasApi(async_get_clientsession(self.hass), self._openid)
                rows = await api.bindings()
                self._users = {
                    numeric_id(row["f_userinfo_id"]): row
                    for row in rows
                    if row.get("f_userinfo_id") is not None
                }
                if not self._users:
                    errors["base"] = "no_bindings"
                elif len(self._users) == 1:
                    return await self._create(next(iter(self._users)))
                else:
                    return await self.async_step_select_user()
            except InvalidOpenId:
                errors[CONF_OPENID] = "invalid_openid"
            except GasApiError:
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_OPENID): str}),
            errors=errors,
        )

    async def async_step_select_user(self, user_input=None):
        if user_input is not None:
            return await self._create(user_input[CONF_USER_ID])
        choices = {
            user_id: f"{row.get('f_userinfo_code') or user_id} ({row.get('f_identity') or '燃气户号'})"
            for user_id, row in self._users.items()
        }
        return self.async_show_form(
            step_id="select_user",
            data_schema=vol.Schema({vol.Required(CONF_USER_ID): vol.In(choices)}),
        )

    async def _create(self, user_id: str):
        await self.async_set_unique_id(f"{DEFAULT_FILIALE}_{user_id}")
        self._abort_if_unique_id_configured()
        row = self._users[user_id]
        api = GasApi(async_get_clientsession(self.hass), self._openid)
        try:
            meters = await api.meters(user_id)
        except GasApiError:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({vol.Required(CONF_OPENID): str}),
                errors={"base": "cannot_connect"},
            )
        if not meters:
            return self.async_abort(reason="no_meters")
        code = str(row.get("f_userinfo_code") or user_id)
        return self.async_create_entry(
            title=f"中昆仑燃气 {code}",
            data={
                CONF_OPENID: self._openid,
                CONF_USER_ID: user_id,
                CONF_FILIALE: DEFAULT_FILIALE,
                "user_code": code,
                "company": row.get("f_orgname") or "中昆仑燃气",
            },
        )

    async def async_step_reconfigure(self, user_input=None):
        """Allow replacing OpenID without losing entities or history."""
        errors = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            try:
                openid = validate_openid(user_input[CONF_OPENID])
                rows = await GasApi(
                    async_get_clientsession(self.hass), openid
                ).bindings()
                if not any(
                    str(row.get("f_userinfo_id")) == entry.data[CONF_USER_ID]
                    for row in rows
                ):
                    errors["base"] = "user_not_bound"
                else:
                    return self.async_update_reload_and_abort(
                        entry, data_updates={CONF_OPENID: openid}
                    )
            except InvalidOpenId:
                errors[CONF_OPENID] = "invalid_openid"
            except GasApiError:
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({vol.Required(CONF_OPENID): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return GasOptionsFlow()


class GasOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_INTERVAL, DEFAULT_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=15, max=1440)),
                    vol.Required(
                        CONF_THRESHOLD,
                        default=self.config_entry.options.get(
                            CONF_THRESHOLD, DEFAULT_THRESHOLD
                        ),
                    ): vol.All(vol.Coerce(float), vol.Range(min=0, max=100000)),
                }
            ),
        )
