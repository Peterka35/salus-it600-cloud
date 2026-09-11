"""AWS IoT MQTT connection for Salus device shadows: sends commands and receives state changes."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import ssl
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlencode, urlparse

import paho.mqtt.client as mqtt

from .api import IotCredentials, SalusCloudConnectionError
from .const import AWS_IOT_ENDPOINT, AWS_REGION

_LOGGER = logging.getLogger(__name__)

# AWS IoT accepts at most 8 topic filters in one SUBSCRIBE request
SUBSCRIBE_BATCH_SIZE = 8
CONNECT_TIMEOUT = 15
KEEPALIVE = 60
MAX_RECONNECT_DELAY = 300


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def create_signed_websocket_url(host: str, region: str, credentials: IotCredentials, now: datetime) -> str:
    """Return AWS SigV4 presigned WebSocket URL for AWS IoT.

    The session token is appended after the signature because AWS IoT does not expect it in the signed query.
    """
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    credential_scope = f"{date_stamp}/{region}/iotdevicegateway/aws4_request"
    query = urlencode(
        sorted(
            {
                "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
                "X-Amz-Credential": f"{credentials.access_key}/{credential_scope}",
                "X-Amz-Date": amz_date,
                "X-Amz-SignedHeaders": "host",
            }.items()
        ),
        quote_via=lambda value, *_: quote(str(value), safe=""),
    )
    canonical_request = f"GET\n/mqtt\n{query}\nhost:{host}\n\nhost\n{hashlib.sha256(b'').hexdigest()}"
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )
    signing_key = _sign(
        _sign(_sign(_sign(f"AWS4{credentials.secret_key}".encode(), date_stamp), region), "iotdevicegateway"),
        "aws4_request",
    )
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return (
        f"wss://{host}/mqtt?{query}&X-Amz-Signature={signature}"
        f"&X-Amz-Security-Token={quote(credentials.session_token, safe='')}"
    )


def _create_client(client_id: str) -> mqtt.Client:
    return mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
        transport="websockets",
        protocol=mqtt.MQTTv311,
    )


class SalusMqttConnection:
    """Keeps an AWS IoT MQTT connection alive, publishes shadow updates and delivers shadow documents."""

    def __init__(
        self,
        *,
        credentials_provider: Callable[[], Awaitable[IotCredentials]],
        client_id_prefix: str,
        on_shadow_document: Callable[[str, dict[str, Any]], None],
        on_push_available: Callable[[bool], None],
        client_factory: Callable[[str], Any] = _create_client,
        reconnect_delay: float = 5,
        renew_margin: timedelta = timedelta(minutes=5),
        publish_timeout: float = 10,
    ) -> None:
        """Initialize the connection.

        client_id_prefix: gateway device code, AWS IoT policy requires client ids to start with it
        on_shadow_document: called in the event loop with device code and current shadow document
        on_push_available: called in the event loop when receiving shadow documents becomes (un)available
        """
        self._credentials_provider = credentials_provider
        self._client_id_prefix = client_id_prefix
        self._on_shadow_document = on_shadow_document
        self._on_push_available = on_push_available
        self._client_factory = client_factory
        self._reconnect_delay = reconnect_delay
        self._renew_margin = renew_margin
        self._publish_timeout = publish_timeout
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None
        self._client: Any = None
        self._device_codes: list[str] = []
        self._connected = asyncio.Event()
        self._lost = asyncio.Event()
        self._connack: asyncio.Future[str | None] | None = None
        self._push_available: bool | None = None
        self._push_denied = False
        self._subscribing = False
        self._subscriptions_sent = False
        self._expected_mids: set[int] = set()
        self._subacks: dict[int, bool] = {}

    @property
    def push_available(self) -> bool | None:
        """Return whether shadow documents are received, None while unknown."""
        return self._push_available

    def set_device_codes(self, device_codes: list[str]) -> None:
        """Set devices whose shadow documents are subscribed on the next connection."""
        self._device_codes = list(device_codes)

    async def async_start(self, device_codes: list[str]) -> None:
        """Start keeping the connection in the background."""
        self._loop = asyncio.get_running_loop()
        self._device_codes = list(device_codes)
        self._task = self._loop.create_task(self._run(), name="salus_it600_cloud_mqtt")

    async def async_stop(self) -> None:
        """Stop the connection."""
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._async_stop_client()

    async def async_publish_shadow(self, device_code: str, device_index: str, properties: dict[str, Any]) -> None:
        """Set desired properties of a device shadow."""
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                await self._connected.wait()
        except TimeoutError as err:
            raise SalusCloudConnectionError("Not connected to AWS IoT") from err
        client = self._client
        if client is None:
            raise SalusCloudConnectionError("Not connected to AWS IoT")
        payload = json.dumps({"state": {"desired": {device_index: {"properties": properties}}}})
        _LOGGER.debug("Publishing %s to %s", properties, device_code)
        await asyncio.to_thread(self._publish_sync, client, f"$aws/things/{device_code}/shadow/update", payload)

    def _publish_sync(self, client: Any, topic: str, payload: str) -> None:
        info = client.publish(topic, payload, qos=1)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise SalusCloudConnectionError(f"Publishing to AWS IoT failed: {mqtt.error_string(info.rc)}")
        try:
            info.wait_for_publish(timeout=self._publish_timeout)
        except (RuntimeError, ValueError) as err:
            raise SalusCloudConnectionError(f"Publishing to AWS IoT failed: {err}") from err
        if not info.is_published():
            raise SalusCloudConnectionError("AWS IoT did not confirm the command in time")

    async def _run(self) -> None:
        delay = self._reconnect_delay
        while True:
            try:
                expiry = await self._async_connect()
            except Exception as err:
                _LOGGER.warning("AWS IoT connection failed, retrying in %.0f s: %s", delay, err)
                await self._async_stop_client()
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_RECONNECT_DELAY)
                continue
            delay = self._reconnect_delay
            renew_in = (expiry - self._renew_margin - datetime.now(UTC)).total_seconds()
            try:
                async with asyncio.timeout(max(renew_in, 0)):
                    await self._lost.wait()
            except TimeoutError:
                _LOGGER.debug("Reconnecting to AWS IoT with renewed credentials")
                await self._async_stop_client()
            else:
                _LOGGER.warning("AWS IoT connection lost, reconnecting")
                await self._async_stop_client()
                await asyncio.sleep(self._reconnect_delay)

    async def _async_connect(self) -> datetime:
        credentials = await self._credentials_provider()
        url = urlparse(create_signed_websocket_url(AWS_IOT_ENDPOINT, AWS_REGION, credentials, datetime.now(UTC)))
        client = self._client_factory(f"{self._client_id_prefix}-{uuid.uuid4()}")
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_subscribe = self._on_subscribe
        client.on_message = self._on_message
        self._lost.clear()
        self._connack = self._loop.create_future()
        self._client = client
        await asyncio.to_thread(self._connect_sync, client, url.hostname, f"{url.path}?{url.query}")
        async with asyncio.timeout(CONNECT_TIMEOUT):
            failure = await self._connack
        if failure:
            raise SalusCloudConnectionError(f"AWS IoT refused the connection: {failure}")
        self._connected.set()
        _LOGGER.debug("Connected to AWS IoT")
        if not self._push_denied and self._device_codes:
            await self._async_subscribe(client)
        return credentials.expiry

    @staticmethod
    def _connect_sync(client: Any, host: str, path: str) -> None:
        client.tls_set_context(ssl.create_default_context())
        client.ws_set_options(path=path, headers={"Sec-WebSocket-Protocol": "mqtt"})
        client.connect(host, 443, keepalive=KEEPALIVE)
        client.loop_start()

    async def _async_subscribe(self, client: Any) -> None:
        topics = [f"$aws/things/{code}/shadow/update/documents" for code in self._device_codes]
        self._subscribing = True
        self._subscriptions_sent = False
        self._expected_mids = set()
        self._subacks = {}
        for start in range(0, len(topics), SUBSCRIBE_BATCH_SIZE):
            batch = [(topic, 1) for topic in topics[start : start + SUBSCRIBE_BATCH_SIZE]]
            result, mid = await asyncio.to_thread(client.subscribe, batch)
            if result != mqtt.MQTT_ERR_SUCCESS:
                raise SalusCloudConnectionError(f"Subscribing to shadow documents failed: {mqtt.error_string(result)}")
            self._expected_mids.add(mid)
        self._subscriptions_sent = True
        self._evaluate_subscriptions()

    async def _async_stop_client(self) -> None:
        client, self._client = self._client, None
        self._connected.clear()
        if client is not None:
            await asyncio.to_thread(self._stop_sync, client)

    @staticmethod
    def _stop_sync(client: Any) -> None:
        try:
            client.disconnect()
        finally:
            client.loop_stop()

    # Callbacks below are called by paho in its network thread

    def _on_connect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        failure = str(reason_code) if reason_code.is_failure else None
        self._loop.call_soon_threadsafe(self._handle_connect, client, failure)

    def _on_disconnect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        self._loop.call_soon_threadsafe(self._handle_disconnect, client)

    def _on_subscribe(self, client: Any, userdata: Any, mid: int, reason_codes: list[Any], properties: Any) -> None:
        failed = any(code.is_failure for code in reason_codes)
        self._loop.call_soon_threadsafe(self._handle_subscribe, client, mid, failed)

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        self._loop.call_soon_threadsafe(self._handle_message, client, message.topic, message.payload)

    # Handlers below run in the event loop

    def _handle_connect(self, client: Any, failure: str | None) -> None:
        if client is self._client and self._connack is not None and not self._connack.done():
            self._connack.set_result(failure)

    def _handle_disconnect(self, client: Any) -> None:
        if client is not self._client:
            return
        self._connected.clear()
        if self._subscribing:
            # AWS IoT closes the connection when the policy does not allow the subscription
            self._subscribing = False
            self._set_push_available(False)
        self._lost.set()

    def _handle_subscribe(self, client: Any, mid: int, failed: bool) -> None:
        if client is self._client:
            self._subacks[mid] = failed
            self._evaluate_subscriptions()

    def _evaluate_subscriptions(self) -> None:
        if not self._subscribing or not self._subscriptions_sent or not self._expected_mids <= self._subacks.keys():
            return
        self._subscribing = False
        self._set_push_available(not any(self._subacks[mid] for mid in self._expected_mids))

    def _set_push_available(self, available: bool) -> None:
        if not available:
            self._push_denied = True
        if self._push_available is available:
            return
        self._push_available = available
        if available:
            _LOGGER.info("Receiving device state changes from AWS IoT")
        else:
            _LOGGER.warning("AWS IoT does not allow receiving device state changes, polling device states instead")
        self._on_push_available(available)

    def _handle_message(self, client: Any, topic: str, payload: bytes) -> None:
        if client is not self._client:
            return
        parts = topic.split("/")
        if len(parts) != 6 or parts[3:] != ["shadow", "update", "documents"]:
            return
        try:
            document = json.loads(payload)["current"]
        except (KeyError, TypeError, ValueError):
            _LOGGER.debug("Ignoring unparsable shadow document of %s", parts[2])
            return
        self._on_shadow_document(parts[2], document)
