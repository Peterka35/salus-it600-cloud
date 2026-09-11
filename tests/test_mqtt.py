"""Tests for AWS IoT MQTT connection used for device commands and state push."""

import asyncio
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import paho.mqtt.client as mqtt
import pytest
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.reasoncodes import ReasonCode

from custom_components.salus_it600_cloud.api import (
    IotCredentials,
    SalusCloudConnectionError,
)
from custom_components.salus_it600_cloud.mqtt import SalusMqttConnection

from . import fixtures

DEVICE_CODES = [fixtures.THERMOSTAT_CODE, fixtures.THERMOSTAT_2_CODE, fixtures.RELAY_CODE, fixtures.GATEWAY_CODE]


class _MessageInfo:
    def __init__(self, published: bool) -> None:
        self.rc = mqtt.MQTT_ERR_SUCCESS
        self._published = published

    def wait_for_publish(self, timeout: float | None = None) -> None:
        return None

    def is_published(self) -> bool:
        return self._published


class _Message:
    def __init__(self, topic: str, payload: bytes) -> None:
        self.topic = topic
        self.payload = payload


class _Broker:
    """Fake AWS IoT broker shared by all clients created during a test."""

    def __init__(
        self,
        *,
        deny_subscribe: bool = False,
        disconnect_on_subscribe: bool = False,
        publish_succeeds: bool = True,
    ) -> None:
        self.deny_subscribe = deny_subscribe
        self.disconnect_on_subscribe = disconnect_on_subscribe
        self.publish_succeeds = publish_succeeds
        self.clients: list[_Client] = []

    def create_client(self, client_id: str) -> "_Client":
        client = _Client(self, client_id)
        self.clients.append(client)
        return client


class _Client:
    """Fake paho client calling callbacks with paho 2 (callback API version 2) signatures."""

    def __init__(self, broker: _Broker, client_id: str) -> None:
        self.broker = broker
        self.client_id = client_id
        self.on_connect: Callable[..., None] | None = None
        self.on_disconnect: Callable[..., None] | None = None
        self.on_subscribe: Callable[..., None] | None = None
        self.on_message: Callable[..., None] | None = None
        self.ws_path = ""
        self.host = ""
        self.subscriptions: list[list[str]] = []
        self.published: list[tuple[str, Any, int]] = []
        self.stopped = False
        self._connected = False
        self._mid = 0

    def tls_set_context(self, context: object = None) -> None:
        return None

    def ws_set_options(self, path: str = "/mqtt", headers: dict[str, str] | None = None) -> None:
        self.ws_path = path

    def connect(self, host: str, port: int = 1883, keepalive: int = 60) -> None:
        self.host = host

    def loop_start(self) -> None:
        self._connected = True
        self.on_connect(self, None, None, ReasonCode(PacketTypes.CONNACK, "Success"), None)

    def loop_stop(self) -> None:
        self.stopped = True

    def disconnect(self, *args: object, **kwargs: object) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def subscribe(self, topics: list[tuple[str, int]]) -> tuple[int, int]:
        self._mid += 1
        self.subscriptions.append([topic for topic, _ in topics])
        if self.broker.disconnect_on_subscribe:
            self.drop()
            return mqtt.MQTT_ERR_SUCCESS, self._mid
        code = 0x80 if self.broker.deny_subscribe else 1
        self.on_subscribe(
            self, None, self._mid, [ReasonCode(PacketTypes.SUBACK, identifier=code) for _ in topics], None
        )
        return mqtt.MQTT_ERR_SUCCESS, self._mid

    def publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False) -> _MessageInfo:
        self.published.append((topic, json.loads(payload), qos))
        return _MessageInfo(self.broker.publish_succeeds)

    def drop(self) -> None:
        self._connected = False
        self.on_disconnect(self, None, None, ReasonCode(PacketTypes.DISCONNECT, "Unspecified error"), None)

    def deliver(self, topic: str, document: dict[str, Any]) -> None:
        self.on_message(self, None, _Message(topic, json.dumps(document).encode()))


class _Credentials:
    def __init__(self, lifetime: timedelta = timedelta(hours=1)) -> None:
        self.calls = 0
        self._lifetime = lifetime

    async def __call__(self) -> IotCredentials:
        self.calls += 1
        return IotCredentials(
            access_key=f"ASIAEXAMPLE{self.calls}",
            secret_key="secret",
            session_token="token/with+chars",
            expiry=datetime.now(UTC) + self._lifetime,
        )


def _connection(
    broker: _Broker,
    credentials: _Credentials | None = None,
    documents: list[tuple[str, dict[str, Any]]] | None = None,
    push_states: list[bool] | None = None,
) -> SalusMqttConnection:
    return SalusMqttConnection(
        credentials_provider=credentials or _Credentials(),
        client_id_prefix=fixtures.GATEWAY_CODE,
        on_shadow_document=lambda code, doc: documents.append((code, doc)) if documents is not None else None,
        on_push_available=lambda available: push_states.append(available) if push_states is not None else None,
        client_factory=broker.create_client,
        reconnect_delay=0.01,
        renew_margin=timedelta(minutes=5),
        publish_timeout=1,
    )


async def _until(predicate: Callable[[], object], timeout: float = 3) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


async def test_publish_sends_desired_properties_to_device_shadow() -> None:
    """Command sent right after start waits for the connection and updates desired state of the device."""

    broker = _Broker()
    connection = _connection(broker)
    await connection.async_start(DEVICE_CODES)

    await connection.async_publish_shadow(fixtures.THERMOSTAT_CODE, "11", {"ep9:sIT600TH:SetHoldType": 7})
    await connection.async_stop()

    (client,) = broker.clients
    assert client.published == [
        (
            f"$aws/things/{fixtures.THERMOSTAT_CODE}/shadow/update",
            {"state": {"desired": {"11": {"properties": {"ep9:sIT600TH:SetHoldType": 7}}}}},
            1,
        )
    ]
    assert client.client_id.startswith(f"{fixtures.GATEWAY_CODE}-")
    assert re.search(r"X-Amz-Signature=[0-9a-f]{64}&X-Amz-Security-Token=token%2Fwith%2Bchars$", client.ws_path)
    assert client.stopped is True


async def test_unconfirmed_publish_raises_connection_error() -> None:
    """Command the broker does not confirm in time is reported as failed."""

    broker = _Broker(publish_succeeds=False)
    connection = _connection(broker)
    await connection.async_start(DEVICE_CODES)

    with pytest.raises(SalusCloudConnectionError):
        await connection.async_publish_shadow(fixtures.RELAY_CODE, "11", {"ep9:sOnOffS:SetOnOff": 1})

    await connection.async_stop()


async def test_subscribes_to_shadow_documents_in_batches_of_eight() -> None:
    """Shadow documents of all devices are subscribed with at most 8 topics per request (AWS IoT limit)."""

    codes = [f"{fixtures.GATEWAY_CODE}-SR600-{index:016X}" for index in range(11)]
    broker = _Broker()
    push_states: list[bool] = []
    connection = _connection(broker, push_states=push_states)
    await connection.async_start(codes)

    await _until(lambda: connection.push_available is True)
    await connection.async_stop()

    (client,) = broker.clients
    assert [len(batch) for batch in client.subscriptions] == [8, 3]
    assert client.subscriptions[1] == [f"$aws/things/{code}/shadow/update/documents" for code in codes[8:]]
    assert push_states == [True]


async def test_shadow_document_push_is_delivered() -> None:
    """Current shadow document pushed by the broker is handed over with its device code."""

    documents: list[tuple[str, dict[str, Any]]] = []
    broker = _Broker()
    connection = _connection(broker, documents=documents)
    await connection.async_start(DEVICE_CODES)
    await _until(lambda: connection.push_available is True)
    current = fixtures.thermostat_shadow(hold_type=0)

    broker.clients[0].deliver(
        f"$aws/things/{fixtures.THERMOSTAT_CODE}/shadow/update/documents",
        {"previous": fixtures.thermostat_shadow(hold_type=7), "current": current, "timestamp": 1789140200},
    )
    await _until(lambda: documents)
    await connection.async_stop()

    assert documents == [(fixtures.THERMOSTAT_CODE, current)]


async def test_denied_subscription_keeps_connection_for_commands() -> None:
    """Without permission to subscribe, push is reported unavailable and commands still work."""

    broker = _Broker(deny_subscribe=True)
    push_states: list[bool] = []
    connection = _connection(broker, push_states=push_states)
    await connection.async_start(DEVICE_CODES)
    await _until(lambda: connection.push_available is False)

    await connection.async_publish_shadow(fixtures.RELAY_CODE, "11", {"ep9:sOnOffS:SetOnOff": 1})
    await connection.async_stop()

    assert push_states == [False]
    assert len(broker.clients) == 1
    assert [topic for topic, _, _ in broker.clients[0].published] == [
        f"$aws/things/{fixtures.RELAY_CODE}/shadow/update"
    ]


async def test_disconnect_on_subscribe_disables_push_and_reconnects() -> None:
    """Broker dropping the connection because of the subscription is not repeated on reconnect."""

    broker = _Broker(disconnect_on_subscribe=True)
    push_states: list[bool] = []
    connection = _connection(broker, push_states=push_states)
    await connection.async_start(DEVICE_CODES)
    await _until(lambda: len(broker.clients) == 2 and broker.clients[1].is_connected())

    await connection.async_publish_shadow(fixtures.RELAY_CODE, "11", {"ep9:sOnOffS:SetOnOff": 0})
    await connection.async_stop()

    assert push_states == [False]
    assert broker.clients[0].stopped is True
    assert broker.clients[1].subscriptions == []
    assert len(broker.clients[1].published) == 1


async def test_unexpected_disconnect_reconnects_with_new_client() -> None:
    """Lost connection is replaced by a new client and the old one is stopped."""

    broker = _Broker()
    connection = _connection(broker)
    await connection.async_start(DEVICE_CODES)
    await _until(lambda: connection.push_available is True)

    broker.clients[0].drop()
    await _until(lambda: len(broker.clients) == 2 and broker.clients[1].is_connected())
    await connection.async_stop()

    assert broker.clients[0].stopped is True


async def test_renews_credentials_before_they_expire() -> None:
    """Connection is re-established with new AWS credentials before the current ones expire."""

    credentials = _Credentials(lifetime=timedelta(minutes=5, seconds=0.3))
    broker = _Broker()
    connection = _connection(broker, credentials=credentials)
    await connection.async_start(DEVICE_CODES)

    await _until(lambda: len(broker.clients) == 2 and broker.clients[1].is_connected())
    await connection.async_stop()

    assert credentials.calls == 2
    assert broker.clients[0].stopped is True
