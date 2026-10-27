"""Allowlisted diagnostics; never export account identifiers or raw records."""


async def async_get_config_entry_diagnostics(hass, entry):
    runtime = entry.runtime_data
    return {
        "options": dict(entry.options),
        "endpoints": {
            kind: {
                "last_update_success": coordinator.last_update_success,
                "record_count": len(coordinator.data or []),
            }
            for kind, coordinator in (
                ("meters", runtime.meters),
                ("usage", runtime.usage),
                ("payments", runtime.payments),
            )
        },
    }
