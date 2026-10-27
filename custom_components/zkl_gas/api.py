"""Read-only client for the WeChat gas service."""

from __future__ import annotations

import base64
import binascii
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import aiohttp
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .const import AES_KEY, BASE_URL, DEFAULT_FILIALE, PAGE_SIZE

SHANGHAI = ZoneInfo("Asia/Shanghai")
OPENID_PATTERN = re.compile(r"[A-Za-z0-9_-]{10,128}\Z")


class GasApiError(Exception):
    """The remote service could not provide usable data."""


class InvalidOpenId(ValueError):
    """An OpenID is not a valid identifier."""


def validate_openid(value: str) -> str:
    """Validate before including an identifier in the service's condition syntax."""
    value = value.strip()
    if not OPENID_PATTERN.fullmatch(value):
        raise InvalidOpenId("Invalid OpenID format")
    return value


def numeric_id(value: Any) -> str:
    """Only allow numeric IDs in server-side conditions."""
    result = str(value)
    if not re.fullmatch(r"[0-9]+", result):
        raise GasApiError("Missing or invalid user identifier")
    return result


def encrypt(payload: Any) -> str:
    """Encode the service's AES-128-ECB/PKCS7 envelope."""
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    padder = padding.PKCS7(128).padder()
    padded = padder.update(raw) + padder.finalize()
    cipher = Cipher(algorithms.AES(AES_KEY), modes.ECB()).encryptor()
    return base64.b64encode(cipher.update(padded) + cipher.finalize()).decode()


def decrypt(value: str) -> Any:
    """Decode and strictly validate the service response."""
    cipher = Cipher(algorithms.AES(AES_KEY), modes.ECB()).decryptor()
    raw = cipher.update(base64.b64decode(value, validate=True)) + cipher.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    raw = unpadder.update(raw) + unpadder.finalize()
    return json.loads(raw.decode("utf-8"))


def decode_rows(text: str) -> list[dict[str, Any]]:
    """Accept encrypted envelopes, encrypted text and plain JSON lists."""
    try:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = decrypt(text.strip())
        if isinstance(data, dict) and data.get("aoteEncrypt") == "AES":
            data = decrypt(data["data"])
        if isinstance(data, str):
            data = decrypt(data)
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            data = data["data"]
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise GasApiError("Unexpected response structure")
        return data
    except (ValueError, TypeError, KeyError, binascii.Error) as err:
        raise GasApiError("Invalid encrypted response") from err


def number(value: Any) -> Decimal | None:
    """Keep decimal precision and reject non-finite values."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def timestamp(value: Any) -> datetime | None:
    """The server returns local Chinese time without a timezone."""
    if not isinstance(value, str) or not value:
        return None
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        return None
    return result.replace(tzinfo=SHANGHAI) if result.tzinfo is None else result


def history_start() -> str:
    """Use a one-year window, including the whole first day."""
    now = datetime.now(SHANGHAI)
    try:
        start = now.replace(year=now.year - 1)
    except ValueError:
        start = now.replace(year=now.year - 1, day=28)
    return start.strftime("%Y-%m-%d 00:00:00")


def sort_records(rows: list[dict], date_key: str) -> list[dict]:
    """Sort valid dated records newest first; discard duplicate snapshots."""
    seen: set[str] = set()
    result = []
    for row in rows:
        if timestamp(row.get(date_key)) is None:
            continue
        key = (
            str(row["f_hand_id"])
            if row.get("f_hand_id") is not None
            else json.dumps(row, sort_keys=True, ensure_ascii=False)
        )
        if key not in seen:
            seen.add(key)
            result.append(row)
    return sorted(result, key=lambda row: timestamp(row[date_key]), reverse=True)


class GasApi:
    """Share HA's aiohttp session; never make blocking network calls."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        openid: str,
        filiale: str = DEFAULT_FILIALE,
    ) -> None:
        self.session = session
        self.openid = validate_openid(openid)
        self.filiale = filiale

    async def request(
        self, path: str, payload: dict, *, paginated: bool = False
    ) -> list[dict]:
        query = f"?pageNo=1&pageSize={PAGE_SIZE}" if paginated else ""
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "http://rqjf.shanting.gov.cn",
            "Referer": f"{BASE_URL}/index11.html?{urlencode({'openid': self.openid, 'filiale': self.filiale})}",
            "User-Agent": "Mozilla/5.0 HomeAssistant ZhongkunlunGas/0.1",
            "Cache-Control": "no-cache",
        }
        try:
            async with self.session.post(
                f"{BASE_URL}/rs/{path}{query}",
                json={"aoteEncrypt": "AES", "data": encrypt(payload)},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as response:
                response.raise_for_status()
                return decode_rows(await response.text())
        except (TimeoutError, aiohttp.ClientError) as err:
            # Avoid including response bodies, OpenID or private details in logs.
            raise GasApiError("Gas service request failed") from err

    async def bindings(self) -> list[dict]:
        return await self.request(
            "logic/searchBandList",
            {
                "condition": f"f_open_id = '{self.openid}'",
                "f_open_id": self.openid,
            },
        )

    async def meters(self, user_id: str) -> list[dict]:
        return await self.request(
            "logic/searchUserMeter",
            {"condition": f"f_userinfo_id = {numeric_id(user_id)}"},
        )

    async def usage(self, user_id: str) -> list[dict]:
        rows = await self.request(
            "sql/searchUserHandPlanDetailToNew",
            {
                "data": {
                    "f_user_id": numeric_id(user_id),
                    "startDate": history_start(),
                },
            },
            paginated=True,
        )
        return sort_records(rows, "f_input_date")

    async def payments(self, user_id: str, files_id: str) -> list[dict]:
        rows = await self.request(
            "sql/searchUserSellDetailToNew",
            {
                "data": {
                    "f_user_id": numeric_id(user_id),
                    "f_userfiles_id": numeric_id(files_id),
                    "startDate": history_start(),
                },
            },
            paginated=True,
        )
        return sort_records(rows, "f_delivery_date")
