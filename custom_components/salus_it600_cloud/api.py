"""Salus iT600 Cloud REST API client: AWS Cognito login, Salus service API and AWS IoT credentials."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp
from botocore.exceptions import ClientError
from pycognito import Cognito
from pycognito.exceptions import SoftwareTokenMFAChallengeException

from .const import (
    AWS_CLIENT_ID,
    AWS_IDENTITY_POOL_ID,
    AWS_REGION,
    AWS_USER_POOL_ID,
    COMPANY_CODE,
    SERVICE_API_BASE_URL,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)
# Token lifetime assumed when the token does not carry its expiry
TOKEN_FALLBACK_LIFETIME = timedelta(hours=1)
TOKEN_REFRESH_MARGIN = timedelta(minutes=5)
COGNITO_IDENTITY_URL = f"https://cognito-identity.{AWS_REGION}.amazonaws.com/"
COGNITO_LOGIN_PROVIDER = f"cognito-idp.{AWS_REGION}.amazonaws.com/{AWS_USER_POOL_ID}"
# Cognito error codes meaning the stored credentials can no longer be used
AUTH_ERROR_CODES = {
    "NotAuthorizedException",
    "UserNotFoundException",
    "PasswordResetRequiredException",
    "UserNotConfirmedException",
}


class SalusCloudAuthenticationError(Exception):
    """Credentials were rejected."""


class SalusCloudConnectionError(Exception):
    """Salus Cloud could not be reached or returned an error."""


@dataclass(frozen=True)
class GatewayInfo:
    """Salus gateway."""

    id: str
    name: str
    device_code: str


@dataclass
class SalusMetadata:
    """Gateways with their devices and OneTouch rules."""

    gateways: list[GatewayInfo]
    devices: list[dict[str, Any]]
    rules: list[dict[str, Any]]


@dataclass(frozen=True)
class IotCredentials:
    """Temporary AWS credentials for AWS IoT."""

    access_key: str
    secret_key: str
    session_token: str
    expiry: datetime


def jwt_expiry(token: str | None) -> datetime | None:
    """Return expiry time from the exp claim of a JWT token."""

    if not token:
        return None
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return datetime.fromtimestamp(claims["exp"], tz=UTC)
    except (IndexError, KeyError, TypeError, ValueError):
        return None


class SalusCloudApi:
    """Client for Salus Cloud REST API."""

    def __init__(self, email: str, password: str, session: aiohttp.ClientSession | None = None) -> None:
        """Initialize the client; a passed HTTP session is shared and never closed by the client."""
        self.email = email
        self._password = password
        self._session = session
        self._owns_session = session is None
        self._cognito: Cognito | None = None
        self._access_token: str | None = None
        self._id_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expiry: datetime | None = None
        self._identity_id: str | None = None

    def _sync_authenticate(self) -> None:
        """Log in using SRP (blocking)."""
        self._cognito = Cognito(
            user_pool_id=AWS_USER_POOL_ID,
            client_id=AWS_CLIENT_ID,
            user_pool_region=AWS_REGION,
            username=self.email,
        )
        self._cognito.authenticate(password=self._password)
        self._access_token = self._cognito.access_token
        self._id_token = self._cognito.id_token
        self._refresh_token = self._cognito.refresh_token

    def _sync_refresh_tokens(self) -> None:
        """Renew tokens using the refresh token (blocking)."""
        self._cognito.renew_access_token()
        self._access_token = self._cognito.access_token
        self._id_token = self._cognito.id_token

    async def authenticate(self) -> None:
        """Log in to AWS Cognito."""
        _LOGGER.debug("Logging in to Salus Cloud")
        await self._login(self._sync_authenticate)

    async def _login(self, func: Callable[[], None]) -> None:
        try:
            await asyncio.to_thread(func)
        except SoftwareTokenMFAChallengeException as err:
            raise SalusCloudAuthenticationError("MFA is not supported") from err
        except ClientError as err:
            code = err.response.get("Error", {}).get("Code")
            if code in AUTH_ERROR_CODES:
                raise SalusCloudAuthenticationError(f"Login rejected: {code}") from err
            raise SalusCloudConnectionError(f"Login failed: {code}") from err
        except Exception as err:
            raise SalusCloudConnectionError(f"Login failed: {err!r}") from err
        self._token_expiry = jwt_expiry(self._id_token) or datetime.now(UTC) + TOKEN_FALLBACK_LIFETIME

    async def _ensure_token(self) -> None:
        """Renew tokens shortly before they expire."""
        if self._token_expiry and datetime.now(UTC) < self._token_expiry - TOKEN_REFRESH_MARGIN:
            return
        if self._cognito and self._refresh_token:
            try:
                await self._login(self._sync_refresh_tokens)
            except SalusCloudAuthenticationError:
                _LOGGER.debug("Refresh token rejected, logging in again")
            else:
                return
        await self.authenticate()

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-access-token": self._access_token or "",
            "x-auth-token": self._id_token or "",
            "x-company-code": COMPANY_CODE,
        }

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def _send(self, method: str, endpoint: str, **kwargs: Any) -> Any:
        async with self._get_session().request(
            method, f"{SERVICE_API_BASE_URL}{endpoint}", headers=self._headers(), timeout=REQUEST_TIMEOUT, **kwargs
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def _request(self, method: str, endpoint: str, **kwargs: Any) -> Any:
        """Call a Salus service API endpoint, logging in again once when the token is rejected."""
        await self._ensure_token()
        path = endpoint.split("?", 1)[0]
        _LOGGER.debug("%s %s", method, path)
        try:
            try:
                return await self._send(method, endpoint, **kwargs)
            except aiohttp.ClientResponseError as err:
                if err.status != 401:
                    raise
                _LOGGER.debug("Token rejected by %s, logging in again", path)
                await self.authenticate()
                return await self._send(method, endpoint, **kwargs)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise SalusCloudConnectionError(f"{method} {path} failed: {err!r}") from err

    async def get_gateways(self) -> list[dict[str, Any]]:
        """Return gateways of the account."""
        response = await self._request("GET", "/occupants/slider_list")
        if not isinstance(response, dict):
            return []
        return [item for item in response.get("data", []) if item.get("type") == "gateway"]

    async def get_gateway_details(self, gateway_id: str) -> dict[str, Any]:
        """Return details of a gateway including its devices and rules."""
        response = await self._request("GET", f"/occupants/slider_details?id={gateway_id}&type=gateway")
        return response.get("data", {}) if isinstance(response, dict) else {}

    async def fetch_metadata(self) -> SalusMetadata:
        """Return gateways with their devices and OneTouch rules, failing when any gateway cannot be read."""
        gateways: list[GatewayInfo] = []
        devices: list[dict[str, Any]] = []
        rules: list[dict[str, Any]] = []
        for item in await self.get_gateways():
            gateway_id = item.get("id")
            if not gateway_id:
                continue
            gateway = item.get("gateway", {})
            gateways.append(
                GatewayInfo(
                    id=gateway_id,
                    name=gateway.get("name") or "Salus Gateway",
                    device_code=gateway.get("device_code", ""),
                )
            )
            details = await self.get_gateway_details(gateway_id)
            for detail in details.get("items", []):
                entry = {**detail, "_gateway_id": gateway_id}
                (rules if "rule_trigger_key" in detail else devices).append(entry)
        return SalusMetadata(gateways=gateways, devices=devices, rules=rules)

    async def get_device_shadows(self, device_codes: list[str]) -> dict[str, dict[str, Any]]:
        """Return shadow documents of the devices keyed by device code."""
        response = await self._request(
            "POST",
            "/devices/device_shadows",
            json={"request_id": "home-assistant-request", "device_codes": device_codes},
        )
        data = response.get("data", {}) if isinstance(response, dict) else {}
        shadows: dict[str, dict[str, Any]] = {}
        for item in data.get("success_list", []):
            code = item.get("device_code")
            if not code:
                continue
            try:
                shadows[code] = json.loads(item.get("payload") or "{}")
            except ValueError:
                _LOGGER.warning("Ignoring unparsable shadow of device %s", code)
        return shadows

    async def _cognito_identity_call(self, target: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._get_session().post(
            COGNITO_IDENTITY_URL,
            json=payload,
            headers={"Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": target},
            timeout=REQUEST_TIMEOUT,
        ) as response:
            response.raise_for_status()
            return await response.json(content_type=None)

    async def get_iot_credentials(self) -> IotCredentials:
        """Return temporary AWS credentials for AWS IoT from the Cognito identity pool."""
        await self._ensure_token()
        logins = {COGNITO_LOGIN_PROVIDER: self._id_token}
        try:
            if self._identity_id is None:
                result = await self._cognito_identity_call(
                    "AWSCognitoIdentityService.GetId", {"IdentityPoolId": AWS_IDENTITY_POOL_ID, "Logins": logins}
                )
                self._identity_id = result["IdentityId"]
            result = await self._cognito_identity_call(
                "AWSCognitoIdentityService.GetCredentialsForIdentity",
                {"IdentityId": self._identity_id, "Logins": logins},
            )
            credentials = result["Credentials"]
        except (aiohttp.ClientError, TimeoutError, KeyError) as err:
            raise SalusCloudConnectionError(f"Failed to get AWS IoT credentials: {err!r}") from err
        expiration = credentials.get("Expiration")
        return IotCredentials(
            access_key=credentials["AccessKeyId"],
            secret_key=credentials["SecretKey"],
            session_token=credentials["SessionToken"],
            expiry=(
                datetime.fromtimestamp(expiration, tz=UTC)
                if expiration
                else datetime.now(UTC) + TOKEN_FALLBACK_LIFETIME
            ),
        )

    async def close(self) -> None:
        """Close the HTTP session if the client created it."""
        if self._owns_session and self._session is not None and not self._session.closed:
            await self._session.close()
