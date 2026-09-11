"""Tests for Salus Cloud REST API client."""

import base64
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import aiohttp
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from custom_components.salus_it600_cloud.api import (
    GatewayInfo,
    IotCredentials,
    SalusCloudApi,
    SalusCloudAuthenticationError,
    SalusCloudConnectionError,
    jwt_expiry,
)

from . import fixtures


class _Response:
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise aiohttp.ClientResponseError(MagicMock(real_url="https://api"), (), status=self.status)

    async def json(self, content_type: str | None = "application/json") -> Any:
        return self._payload


class _RequestContext:
    def __init__(self, result: _Response | BaseException) -> None:
        self._result = result

    async def __aenter__(self) -> _Response:
        if isinstance(self._result, BaseException):
            raise self._result
        return self._result

    async def __aexit__(self, *args: object) -> None:
        return None


Route = Callable[[], _Response | BaseException]


class _Session:
    """Minimal aiohttp session answering Salus API calls by path and Cognito calls by X-Amz-Target."""

    closed = False

    def __init__(self, routes: dict[str, Route]) -> None:
        self._routes = routes
        self.requests: list[tuple[str, str]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> _RequestContext:
        path = url.split("/api/v1", 1)[1].split("?", 1)[0]
        self.requests.append((method, path))
        return _RequestContext(self._routes[path]())

    def post(self, url: str, **kwargs: Any) -> _RequestContext:
        target = kwargs.get("headers", {}).get("X-Amz-Target")
        if target:
            self.requests.append(("POST", target))
            return _RequestContext(self._routes[target]())
        return self.request("POST", url, **kwargs)


def _token(exp: int) -> str:
    def encode(part: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(part).encode()).decode().rstrip("=")

    return f"{encode({'alg': 'RS256'})}.{encode({'exp': exp, 'email': fixtures.GUEST_EMAIL})}.signature"


def _api(routes: dict[str, Route]) -> tuple[SalusCloudApi, _Session, MagicMock]:
    session = _Session(routes)
    api = SalusCloudApi("owner@example.com", "password", session=session)
    login = MagicMock()

    def _authenticate() -> None:
        login()
        api._access_token = "access"
        api._id_token = _token(4102444800)
        api._refresh_token = "refresh"

    api._sync_authenticate = _authenticate
    return api, session, login


def test_jwt_expiry_reads_exp_claim() -> None:
    """Token validity comes from the token itself instead of an assumed lifetime."""

    assert jwt_expiry(_token(1789143790)) == datetime(2026, 9, 11, 16, 23, 10, tzinfo=UTC)


def test_jwt_expiry_of_malformed_token() -> None:
    """Malformed token has no known expiry."""

    assert jwt_expiry("not-a-jwt") is None
    assert jwt_expiry(None) is None


async def test_rejected_credentials_raise_authentication_error() -> None:
    """Wrong password is reported as authentication error so Home Assistant asks for new credentials."""

    api, _, _ = _api({})

    def _reject() -> None:
        raise ClientError(
            {"Error": {"Code": "NotAuthorizedException", "Message": "Incorrect username or password."}},
            "InitiateAuth",
        )

    api._sync_authenticate = _reject

    with pytest.raises(SalusCloudAuthenticationError):
        await api.authenticate()


async def test_unreachable_login_service_raises_connection_error() -> None:
    """Network failure during login is a connection error, not a reason to ask for new credentials."""

    api, _, _ = _api({})

    def _unreachable() -> None:
        raise EndpointConnectionError(endpoint_url="https://cognito-idp.eu-central-1.amazonaws.com/")

    api._sync_authenticate = _unreachable

    with pytest.raises(SalusCloudConnectionError):
        await api.authenticate()


async def test_request_timeout_raises_connection_error() -> None:
    """A timed out API call is reported as connection error, not as an unexpected exception."""

    api, _, _ = _api({"/occupants/slider_list": lambda: TimeoutError()})
    await api.authenticate()

    with pytest.raises(SalusCloudConnectionError):
        await api.get_gateways()


async def test_unauthorized_request_logs_in_again_and_retries() -> None:
    """Rejected token leads to a new login and one retry of the request."""

    responses = iter([_Response(401, {}), _Response(200, fixtures.slider_list())])
    api, _, login = _api({"/occupants/slider_list": lambda: next(responses)})
    await api.authenticate()

    gateways = await api.get_gateways()

    assert [gateway["id"] for gateway in gateways] == [fixtures.GATEWAY_ID]
    assert login.call_count == 2


async def test_api_responses_are_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    """Personal data from API responses never reaches the log, not even at debug level."""

    caplog.set_level(logging.DEBUG)
    api, _, _ = _api({"/occupants/slider_list": lambda: _Response(200, fixtures.slider_list())})
    await api.authenticate()

    await api.get_gateways()

    assert fixtures.GUEST_EMAIL not in caplog.text
    assert "+420600000000" not in caplog.text


async def test_fetch_metadata_splits_gateways_devices_and_rules() -> None:
    """Gateway details items are split into devices and OneTouch rules, each linked to its gateway."""

    api, _, _ = _api(
        {
            "/occupants/slider_list": lambda: _Response(200, fixtures.slider_list()),
            "/occupants/slider_details": lambda: _Response(200, fixtures.slider_details()),
        }
    )
    await api.authenticate()

    metadata = await api.fetch_metadata()

    assert metadata.gateways == [
        GatewayInfo(id=fixtures.GATEWAY_ID, name=fixtures.GATEWAY_NAME, device_code=fixtures.GATEWAY_CODE)
    ]
    assert [device["id"] for device in metadata.devices] == [
        fixtures.THERMOSTAT_ID,
        fixtures.THERMOSTAT_2_ID,
        fixtures.RELAY_ID,
        fixtures.GATEWAY_ID,
    ]
    assert {device["_gateway_id"] for device in metadata.devices} == {fixtures.GATEWAY_ID}
    assert [rule["id"] for rule in metadata.rules] == [fixtures.RULE_ID, fixtures.AUTO_RULE_ID]
    assert {rule["_gateway_id"] for rule in metadata.rules} == {fixtures.GATEWAY_ID}


async def test_fetch_metadata_fails_when_gateway_details_fail() -> None:
    """Metadata is never returned incomplete when details of a gateway cannot be fetched."""

    api, _, _ = _api(
        {
            "/occupants/slider_list": lambda: _Response(200, fixtures.slider_list()),
            "/occupants/slider_details": lambda: aiohttp.ClientConnectionError("reset"),
        }
    )
    await api.authenticate()

    with pytest.raises(SalusCloudConnectionError):
        await api.fetch_metadata()


async def test_device_shadows_skips_unparsable_payload() -> None:
    """One malformed shadow payload does not drop shadows of other devices."""

    response = fixtures.device_shadows({fixtures.RELAY_CODE: fixtures.relay_shadow(1)})
    response["data"]["success_list"].append({"device_code": fixtures.THERMOSTAT_CODE, "payload": "{broken"})
    api, session, _ = _api({"/devices/device_shadows": lambda: _Response(200, response)})
    await api.authenticate()

    shadows = await api.get_device_shadows([fixtures.RELAY_CODE, fixtures.THERMOSTAT_CODE])

    assert shadows == {fixtures.RELAY_CODE: fixtures.relay_shadow(1)}
    assert session.requests == [("POST", "/devices/device_shadows")]


async def test_iot_credentials_from_cognito_identity_pool() -> None:
    """AWS IoT credentials and their expiry are taken from the Cognito identity pool response."""

    api, _, _ = _api(
        {
            "AWSCognitoIdentityService.GetId": lambda: _Response(200, {"IdentityId": "eu-central-1:1111"}),
            "AWSCognitoIdentityService.GetCredentialsForIdentity": lambda: _Response(
                200,
                {
                    "IdentityId": "eu-central-1:1111",
                    "Credentials": {
                        "AccessKeyId": "ASIAEXAMPLE",
                        "SecretKey": "secret",
                        "SessionToken": "session-token",
                        "Expiration": 1789143790,
                    },
                },
            ),
        }
    )
    await api.authenticate()

    credentials = await api.get_iot_credentials()

    assert credentials == IotCredentials(
        access_key="ASIAEXAMPLE",
        secret_key="secret",
        session_token="session-token",
        expiry=datetime(2026, 9, 11, 16, 23, 10, tzinfo=UTC),
    )


async def test_close_keeps_shared_session_open() -> None:
    """Closing the client does not close the Home Assistant shared HTTP session."""

    api, session, _ = _api({})
    session.close = MagicMock()

    await api.close()

    session.close.assert_not_called()
