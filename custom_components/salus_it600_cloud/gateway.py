"""Salus iT600 Cloud Gateway API client."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode

import aiohttp
import paho.mqtt.client as mqtt
from pycognito import Cognito
from pycognito.exceptions import SoftwareTokenMFAChallengeException

from .const import (
    AWS_CLIENT_ID,
    AWS_IDENTITY_POOL_ID,
    AWS_IOT_ENDPOINT,
    AWS_REGION,
    AWS_USER_POOL_ID,
    COMPANY_CODE,
    SERVICE_API_BASE_URL,
)

_LOGGER = logging.getLogger(__name__)


def _sign(key: bytes, msg: str) -> bytes:
    """Sign message with key."""
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signature_key(key: str, date_stamp: str, region: str, service: str) -> bytes:
    """Generate AWS SigV4 signing key."""
    k_date = _sign(("AWS4" + key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    k_signing = _sign(k_service, "aws4_request")
    return k_signing


def _create_signed_websocket_url(
    host: str,
    region: str,
    access_key: str,
    secret_key: str,
    session_token: str | None = None,
) -> str:
    """Create AWS SigV4 signed WebSocket URL for AWS IoT."""
    # Create timestamp
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    # Create canonical request
    method = "GET"
    canonical_uri = "/mqtt"
    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{region}/iotdevicegateway/aws4_request"

    # Query parameters for signing (EXCLUDING session token!)
    # Session token is added AFTER signature, not before!
    canonical_querystring = {
        "X-Amz-Algorithm": algorithm,
        "X-Amz-Credential": f"{access_key}/{credential_scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-SignedHeaders": "host",
    }

    # Custom quote function for AWS SigV4 - must encode ALL special chars including /
    def aws_quote(s, safe='', encoding=None, errors=None):
        # Ignore encoding and errors parameters, use default quote behavior but with safe=''
        return quote(str(s), safe=safe)

    # Sort and encode query string (without session token yet!)
    sorted_params = sorted(canonical_querystring.items())
    encoded_params = urlencode(sorted_params, quote_via=aws_quote)

    # Create canonical request
    canonical_headers = f"host:{host}\n"
    signed_headers = "host"
    payload_hash = hashlib.sha256(b"").hexdigest()

    canonical_request = (
        f"{method}\n{canonical_uri}\n{encoded_params}\n"
        f"{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )

    # Create string to sign
    string_to_sign = (
        f"{algorithm}\n{amz_date}\n{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )

    # Calculate signature
    signing_key = _get_signature_key(secret_key, date_stamp, region, "iotdevicegateway")
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    # Build URL with signature first
    final_params = encoded_params + "&X-Amz-Signature=" + signature

    # NOW add session token AFTER signature (this is critical!)
    if session_token:
        final_params += "&X-Amz-Security-Token=" + aws_quote(session_token)

    websocket_url = f"wss://{host}{canonical_uri}?{final_params}"

    return websocket_url


class SalusCloudAuthenticationError(Exception):
    """Exception raised for authentication errors."""


class SalusCloudConnectionError(Exception):
    """Exception raised for connection errors."""


class SalusCloudGateway:
    """Salus iT600 Cloud Gateway client."""

    def __init__(self, email: str, password: str) -> None:
        """Initialize the gateway."""
        self.email = email
        self._password = password
        self._cognito: Cognito | None = None
        self._access_token: str | None = None
        self._id_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expiry: datetime | None = None
        self._session: aiohttp.ClientSession | None = None

        # AWS IoT credentials
        self._aws_access_key: str | None = None
        self._aws_secret_key: str | None = None
        self._aws_session_token: str | None = None
        self._aws_identity_id: str | None = None

        # MQTT client
        self._mqtt_client: mqtt.Client | None = None
        self._mqtt_connected: bool = False
        self._mqtt_connect_event: asyncio.Event | None = None
        self._mqtt_connect_rc: int | None = None

    def _sync_authenticate(self) -> None:
        """Synchronous authentication (to be run in thread)."""
        # Create Cognito client
        self._cognito = Cognito(
            user_pool_id=AWS_USER_POOL_ID,
            client_id=AWS_CLIENT_ID,
            user_pool_region=AWS_REGION,
            username=self.email,
        )

        # Authenticate using SRP
        self._cognito.authenticate(password=self._password)

        # Get tokens
        self._access_token = self._cognito.access_token
        self._id_token = self._cognito.id_token
        self._refresh_token = self._cognito.refresh_token

    async def authenticate(self) -> None:
        """Authenticate with AWS Cognito using SRP."""
        try:
            _LOGGER.debug("Authenticating with AWS Cognito for user %s", self.email)

            # Run synchronous authentication in a thread to avoid blocking
            await asyncio.to_thread(self._sync_authenticate)

            # Calculate token expiry (tokens are valid for 3 hours = 10800 seconds)
            self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=10800)

            _LOGGER.debug("Successfully authenticated with AWS Cognito")

        except SoftwareTokenMFAChallengeException as err:
            _LOGGER.error("MFA is required but not supported: %s", err)
            raise SalusCloudAuthenticationError("MFA is not supported") from err
        except Exception as err:
            _LOGGER.error("Authentication failed: %s", err)
            raise SalusCloudAuthenticationError(f"Authentication failed: {err}") from err

    def _sync_refresh_tokens(self) -> None:
        """Synchronous token refresh (to be run in thread)."""
        if self._cognito and self._refresh_token:
            self._cognito.renew_access_token()
            self._access_token = self._cognito.access_token
            self._id_token = self._cognito.id_token

    async def refresh_tokens(self) -> None:
        """Refresh access tokens if needed."""
        if self._token_expiry and datetime.now(timezone.utc) < self._token_expiry - timedelta(minutes=5):
            # Tokens are still valid for more than 5 minutes
            return

        try:
            _LOGGER.debug("Refreshing access tokens")

            if self._cognito and self._refresh_token:
                # Run synchronous refresh in a thread to avoid blocking
                await asyncio.to_thread(self._sync_refresh_tokens)
                self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=10800)
                _LOGGER.debug("Successfully refreshed access tokens")
            else:
                # Re-authenticate if we don't have refresh token
                await self.authenticate()

        except Exception as err:
            _LOGGER.error("Token refresh failed, re-authenticating: %s", err)
            await self.authenticate()

    async def _get_aws_iot_credentials(self) -> None:
        """Get AWS IoT credentials from Cognito Identity Pool."""
        try:
            _LOGGER.debug("Getting AWS IoT credentials")

            # Ensure we have tokens
            if not self._id_token:
                await self.authenticate()

            await self._ensure_session()

            # Step 1: Get Identity ID
            get_id_url = f"https://cognito-identity.{AWS_REGION}.amazonaws.com/"
            get_id_payload = {
                "IdentityPoolId": AWS_IDENTITY_POOL_ID,
                "Logins": {
                    f"cognito-idp.{AWS_REGION}.amazonaws.com/{AWS_USER_POOL_ID}": self._id_token
                },
            }

            async with self._session.post(
                get_id_url,
                json=get_id_payload,
                headers={
                    "Content-Type": "application/x-amz-json-1.1",
                    "X-Amz-Target": "AWSCognitoIdentityService.GetId",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                response.raise_for_status()
                # AWS returns application/x-amz-json-1.1, need to ignore content type
                get_id_result = await response.json(content_type=None)
                self._aws_identity_id = get_id_result["IdentityId"]
                _LOGGER.debug("Got identity ID: %s", self._aws_identity_id)

            # Step 2: Get Credentials for Identity
            get_creds_url = f"https://cognito-identity.{AWS_REGION}.amazonaws.com/"
            get_creds_payload = {
                "IdentityId": self._aws_identity_id,
                "Logins": {
                    f"cognito-idp.{AWS_REGION}.amazonaws.com/{AWS_USER_POOL_ID}": self._id_token
                },
            }

            async with self._session.post(
                get_creds_url,
                json=get_creds_payload,
                headers={
                    "Content-Type": "application/x-amz-json-1.1",
                    "X-Amz-Target": "AWSCognitoIdentityService.GetCredentialsForIdentity",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                response.raise_for_status()
                # AWS returns application/x-amz-json-1.1, need to ignore content type
                creds_result = await response.json(content_type=None)
                credentials = creds_result["Credentials"]

                self._aws_access_key = credentials["AccessKeyId"]
                self._aws_secret_key = credentials["SecretKey"]
                self._aws_session_token = credentials["SessionToken"]

                _LOGGER.debug("Successfully obtained AWS IoT credentials")

        except Exception as err:
            _LOGGER.error("Failed to get AWS IoT credentials: %s", err)
            raise SalusCloudAuthenticationError(f"Failed to get AWS IoT credentials: {err}") from err

    def _get_headers(self) -> dict[str, str]:
        """Get headers for API requests."""
        return {
            "Content-Type": "application/json",
            "x-access-token": self._access_token or "",
            "x-auth-token": self._id_token or "",
            "x-company-code": COMPANY_CODE,
        }

    async def _ensure_session(self) -> None:
        """Ensure aiohttp session exists."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def _request(
        self, method: str, endpoint: str, **kwargs: Any
    ) -> dict[str, Any] | list[Any]:
        """Make an API request."""
        await self.refresh_tokens()
        await self._ensure_session()

        url = f"{SERVICE_API_BASE_URL}{endpoint}"
        headers = self._get_headers()

        # Log request details for debugging
        _LOGGER.debug("Making %s request to %s", method, url)
        if "json" in kwargs:
            _LOGGER.debug("Request JSON: %s", kwargs["json"])

        try:
            async with self._session.request(
                method, url, headers=headers, timeout=aiohttp.ClientTimeout(total=10), **kwargs
            ) as response:
                response.raise_for_status()
                result = await response.json()
                _LOGGER.debug("Response: %s", result)
                return result

        except aiohttp.ClientResponseError as err:
            if err.status == 401:
                _LOGGER.warning("Unauthorized, re-authenticating")
                await self.authenticate()
                # Retry once after re-authentication
                headers = self._get_headers()
                async with self._session.request(
                    method, url, headers=headers, timeout=aiohttp.ClientTimeout(total=10), **kwargs
                ) as response:
                    response.raise_for_status()
                    return await response.json()
            raise SalusCloudConnectionError(f"API request failed: {err}") from err

        except aiohttp.ClientError as err:
            raise SalusCloudConnectionError(f"Connection error: {err}") from err

    async def get_gateways(self) -> list[dict[str, Any]]:
        """Get list of gateways."""
        _LOGGER.debug("Fetching gateways")
        response = await self._request("GET", "/occupants/slider_list")

        if isinstance(response, dict) and "data" in response:
            gateways = [item for item in response["data"] if item.get("type") == "gateway"]
            _LOGGER.debug("Found %d gateway(s)", len(gateways))
            return gateways

        return []

    async def get_gateway_details(self, gateway_id: str) -> dict[str, Any]:
        """Get gateway details including all devices."""
        _LOGGER.debug("Fetching details for gateway %s", gateway_id)
        response = await self._request(
            "GET", f"/occupants/slider_details?id={gateway_id}&type=gateway"
        )

        if isinstance(response, dict) and "data" in response:
            return response["data"]

        return {}

    async def get_device_shadows(self, device_codes: list[str]) -> dict[str, Any]:
        """Get device shadows (states) for multiple devices."""
        _LOGGER.debug("Fetching device shadows for %d devices", len(device_codes))

        payload = {
            "request_id": "home-assistant-request",
            "device_codes": device_codes
        }

        response = await self._request("POST", "/devices/device_shadows", json=payload)

        # Parse shadows from response
        shadows = {}
        if isinstance(response, dict) and "data" in response:
            success_list = response["data"].get("success_list", [])
            for item in success_list:
                device_code = item.get("device_code")
                payload_str = item.get("payload", "{}")

                if device_code:
                    try:
                        # Parse the stringified JSON payload
                        import json
                        shadow = json.loads(payload_str)
                        shadows[device_code] = shadow
                    except Exception as err:
                        _LOGGER.error("Failed to parse shadow for %s: %s", device_code, err)

        return shadows

    async def get_all_devices(self) -> list[dict[str, Any]]:
        """Get all devices from all gateways with their current states."""
        devices = []
        device_codes = []

        gateways = await self.get_gateways()

        for gateway in gateways:
            gateway_id = gateway.get("id")
            if not gateway_id:
                continue

            try:
                details = await self.get_gateway_details(gateway_id)

                # The API returns devices in the "items" array
                if "items" in details:
                    _LOGGER.debug("Found %d items for gateway %s", len(details["items"]), gateway_id)
                    for item in details["items"]:
                        # Skip rules and one_touch_rules, only process actual devices
                        item_type = item.get("dashboard_attributes", {}).get("type")
                        if item_type in ["one_touch_rule", None]:
                            # Check if it has rule_trigger_key (indicates it's a rule)
                            if "rule_trigger_key" in item:
                                continue

                        # Add gateway ID to each device
                        item["_gateway_id"] = gateway_id
                        devices.append(item)

                        # Collect device codes for shadow fetch
                        device_code = item.get("device_code")
                        if device_code:
                            device_codes.append(device_code)

            except Exception as err:
                _LOGGER.error("Failed to get details for gateway %s: %s", gateway_id, err)
                continue

        # Fetch device shadows (states) for all devices
        if device_codes:
            try:
                shadows = await self.get_device_shadows(device_codes)

                # Merge shadow data into device data
                for device in devices:
                    device_code = device.get("device_code")
                    if device_code and device_code in shadows:
                        shadow = shadows[device_code]
                        # Extract reported state properties
                        reported = shadow.get("state", {}).get("reported", {})

                        # Find the device properties in shadow
                        # Properties are nested under a key like "11" (device index)
                        for key, value in reported.items():
                            if isinstance(value, dict) and "properties" in value:
                                device["_shadow_properties"] = value["properties"]
                                device["_shadow_model"] = value.get("model")
                                device["_shadow_device_index"] = key  # Store device index for updates!
                                _LOGGER.debug("Device %s uses shadow index: %s", device_code, key)
                                break

                        # Store full shadow for reference
                        device["_shadow"] = shadow

            except Exception as err:
                _LOGGER.error("Failed to fetch device shadows: %s", err)

        _LOGGER.debug("Found total of %d device(s)", len(devices))
        return devices

    async def get_onetouch_rules(self) -> list[dict[str, Any]]:
        """Get all OneTouch rules from all gateways."""
        rules = []

        gateways = await self.get_gateways()

        for gateway in gateways:
            gateway_id = gateway.get("id")
            if not gateway_id:
                continue

            try:
                details = await self.get_gateway_details(gateway_id)

                # The API returns rules in the "items" array along with devices
                if "items" in details:
                    for item in details["items"]:
                        # Only include OneTouch rules
                        item_type = item.get("dashboard_attributes", {}).get("type")
                        has_rule_trigger = "rule_trigger_key" in item and "rule" in item

                        if item_type == "one_touch_rule" or has_rule_trigger:
                            # Add gateway ID to each rule
                            item["_gateway_id"] = gateway_id
                            rules.append(item)
                            _LOGGER.debug(
                                "Found OneTouch rule: %s",
                                item.get("rule", {}).get("name", "Unknown")
                            )

            except Exception as err:
                _LOGGER.error("Failed to get rules for gateway %s: %s", gateway_id, err)
                continue

        _LOGGER.debug("Found total of %d OneTouch rule(s)", len(rules))
        return rules

    async def _ensure_mqtt_connected(self) -> None:
        """Ensure MQTT client is connected to AWS IoT."""
        if self._mqtt_connected and self._mqtt_client:
            _LOGGER.debug("MQTT already connected, skipping")
            return

        try:
            _LOGGER.debug("Starting MQTT connection to AWS IoT")

            # Get AWS IoT credentials if we don't have them
            if not self._aws_access_key:
                _LOGGER.debug("Getting AWS IoT credentials first")
                await self._get_aws_iot_credentials()

            _LOGGER.debug("Creating signed WebSocket URL...")
            # Create signed WebSocket URL
            websocket_url = _create_signed_websocket_url(
                host=AWS_IOT_ENDPOINT,
                region=AWS_REGION,
                access_key=self._aws_access_key,
                secret_key=self._aws_secret_key,
                session_token=self._aws_session_token,
            )

            _LOGGER.debug("Created signed WebSocket URL for AWS IoT")
            _LOGGER.debug("WebSocket URL (first 100 chars): %s...", websocket_url[:100])

            # Get gateway info for client ID (required for AWS IoT policy)
            # AWS IoT policy expects client ID format: {GATEWAY_DEVICE_CODE}-{UUID}
            if not hasattr(self, '_gateway_device_code'):
                gateways = await self.get_gateways()
                if not gateways:
                    raise SalusCloudConnectionError("No gateways found for MQTT client ID")

                gateway = gateways[0]
                gateway_data = gateway.get("gateway", {})
                self._gateway_device_code = gateway_data.get("device_code", "")

                if not self._gateway_device_code:
                    raise SalusCloudConnectionError("Gateway device_code not found")

                _LOGGER.debug("Using gateway device_code for MQTT: %s", self._gateway_device_code)

            # Create event for waiting on connection
            self._mqtt_connect_event = asyncio.Event()
            self._mqtt_connect_rc = None

            # Create MQTT client with WebSocket
            # Client ID format: {GATEWAY_DEVICE_CODE}-{RANDOM_UUID}
            # Example: SAU2AG1_GW-001E5E044354-a1b2c3d4-e5f6-4789-a0b1-c2d3e4f5g6h7
            import uuid
            connection_uuid = str(uuid.uuid4())
            client_id = f"{self._gateway_device_code}-{connection_uuid}"
            _LOGGER.debug("Creating MQTT client with ID: %s", client_id)
            self._mqtt_client = mqtt.Client(
                client_id=client_id,
                transport="websockets",
                protocol=mqtt.MQTTv311,  # AWS IoT requires MQTT 3.1.1
            )

            # Add MQTT callbacks for debugging
            def on_connect(client, userdata, flags, rc):
                self._mqtt_connect_rc = rc
                if rc == 0:
                    _LOGGER.debug("MQTT connected successfully (rc=0)")
                    self._mqtt_connected = True
                else:
                    _LOGGER.error("MQTT connection failed (rc=%s): %s", rc, mqtt.connack_string(rc))
                    self._mqtt_connected = False
                # Signal that connection attempt is complete
                if self._mqtt_connect_event:
                    import asyncio
                    loop = asyncio.get_event_loop()
                    loop.call_soon_threadsafe(self._mqtt_connect_event.set)

            def on_disconnect(client, userdata, rc):
                _LOGGER.warning("MQTT disconnected (rc=%s): %s", rc, mqtt.connack_string(rc) if rc > 0 else "Clean disconnect")
                self._mqtt_connected = False

            def on_log(client, userdata, level, buf):
                # Map paho-mqtt log levels to Python logging levels
                if level == mqtt.MQTT_LOG_ERR:
                    _LOGGER.error("MQTT: %s", buf)
                elif level == mqtt.MQTT_LOG_WARNING:
                    _LOGGER.warning("MQTT: %s", buf)
                elif level == mqtt.MQTT_LOG_NOTICE:
                    _LOGGER.debug("MQTT: %s", buf)
                else:
                    _LOGGER.debug("MQTT: %s", buf)

            def on_socket_open(client, userdata, sock):
                _LOGGER.debug("MQTT WebSocket opened")

            def on_socket_close(client, userdata, sock):
                _LOGGER.debug("MQTT WebSocket closed")

            self._mqtt_client.on_connect = on_connect
            self._mqtt_client.on_disconnect = on_disconnect
            self._mqtt_client.on_log = on_log
            self._mqtt_client.on_socket_open = on_socket_open
            self._mqtt_client.on_socket_close = on_socket_close

            # Enable debug logging for MQTT
            self._mqtt_client.enable_logger(_LOGGER)

            # Connect in a thread (paho-mqtt is synchronous)
            def connect_sync():
                try:
                    # Set TLS (required for wss://) - must be in thread to avoid blocking
                    _LOGGER.debug("Setting up TLS for WebSocket connection")
                    import ssl
                    # Use default SSL context with proper cert verification
                    self._mqtt_client.tls_set(
                        cert_reqs=ssl.CERT_REQUIRED,
                        tls_version=ssl.PROTOCOL_TLSv1_2
                    )

                    # Parse URL to get host and path with query params
                    import urllib.parse
                    parsed = urllib.parse.urlparse(websocket_url)

                    _LOGGER.debug("Setting WebSocket options - host: %s, path: %s", parsed.hostname, parsed.path)
                    _LOGGER.debug("Query params length: %d chars", len(parsed.query))

                    # Set the full path with query parameters
                    # NOTE: AWS IoT requires the WebSocket subprotocol to be "mqtt"
                    self._mqtt_client.ws_set_options(
                        path=f"{parsed.path}?{parsed.query}",
                        headers={
                            "Sec-WebSocket-Protocol": "mqtt"
                        }
                    )

                    # Connect (default port 443 for wss)
                    _LOGGER.debug("Connecting to MQTT broker at %s:443", parsed.hostname)
                    self._mqtt_client.connect(parsed.hostname, 443, keepalive=60)
                    _LOGGER.debug("MQTT connect() call completed, starting network loop")
                    self._mqtt_client.loop_start()
                    _LOGGER.debug("MQTT loop_start() completed")

                except Exception as e:
                    _LOGGER.error("Exception in MQTT connect_sync: %s", e, exc_info=True)
                    # Signal event even on error so we don't hang
                    if self._mqtt_connect_event:
                        import asyncio
                        loop = asyncio.get_event_loop()
                        loop.call_soon_threadsafe(self._mqtt_connect_event.set)
                    raise

            _LOGGER.debug("Starting MQTT connection in background thread")
            await asyncio.to_thread(connect_sync)

            # Wait for connection callback (with timeout)
            _LOGGER.debug("Waiting for MQTT connection callback...")
            try:
                await asyncio.wait_for(self._mqtt_connect_event.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                _LOGGER.error("MQTT connection timeout - no callback received within 10 seconds")
                raise SalusCloudConnectionError("MQTT connection timeout")

            # Check connection result
            if self._mqtt_connect_rc != 0:
                error_msg = f"MQTT connection failed with code {self._mqtt_connect_rc}"
                if self._mqtt_connect_rc:
                    error_msg += f": {mqtt.connack_string(self._mqtt_connect_rc)}"
                _LOGGER.error(error_msg)
                raise SalusCloudConnectionError(error_msg)

            _LOGGER.debug("MQTT connection established successfully")

        except Exception as err:
            _LOGGER.error("Failed to connect to AWS IoT MQTT: %s", err, exc_info=True)
            self._mqtt_connected = False
            if self._mqtt_client:
                try:
                    self._mqtt_client.loop_stop()
                except:
                    pass
            raise SalusCloudConnectionError(f"Failed to connect to AWS IoT MQTT: {err}") from err

    async def update_device_shadow(
        self, device_code: str, properties: dict[str, Any], device_index: str | None = None
    ) -> None:
        """Update device shadow via AWS IoT MQTT.

        Args:
            device_code: Device code (thing name in AWS IoT)
            properties: Properties to update
            device_index: Device index in shadow (if None, will try to fetch it)
        """
        try:
            _LOGGER.debug("Updating device shadow for %s", device_code)

            # Ensure MQTT is connected
            await self._ensure_mqtt_connected()

            # If device_index not provided, try to get current shadow to find it
            if device_index is None:
                _LOGGER.debug("Device index not provided, fetching current shadow")
                try:
                    shadows = await self.get_device_shadows([device_code])
                    if device_code in shadows:
                        shadow = shadows[device_code]
                        reported = shadow.get("state", {}).get("reported", {})
                        # Find device index from reported state
                        for key, value in reported.items():
                            if isinstance(value, dict) and "properties" in value:
                                device_index = key
                                _LOGGER.debug("Found device index from shadow: %s", device_index)
                                break
                except Exception as e:
                    _LOGGER.debug("Could not fetch device index from shadow: %s", e)

                # Fallback to default if still not found
                if device_index is None:
                    device_index = "11"
                    _LOGGER.debug("Using default device index '11' - this may not work for all devices")

            # Create shadow update payload
            shadow_update = {
                "state": {
                    "desired": {
                        device_index: {
                            "properties": properties
                        }
                    }
                }
            }

            # Publish to shadow update topic
            topic = f"$aws/things/{device_code}/shadow/update"
            payload = json.dumps(shadow_update)

            _LOGGER.debug("Publishing to topic %s with device_index %s: %s", topic, device_index, payload)

            # Publish in a thread (paho-mqtt is synchronous)
            def publish_sync():
                if not self._mqtt_client:
                    raise SalusCloudConnectionError("MQTT client not initialized")
                result = self._mqtt_client.publish(topic, payload, qos=1)
                result.wait_for_publish()
                if result.rc != mqtt.MQTT_ERR_SUCCESS:
                    raise SalusCloudConnectionError(f"MQTT publish failed with code {result.rc}: {mqtt.error_string(result.rc)}")

            await asyncio.to_thread(publish_sync)

            _LOGGER.debug("Successfully published shadow update for %s (index: %s)", device_code, device_index)

        except Exception as err:
            _LOGGER.error("Failed to update device shadow: %s", err, exc_info=True)
            # Reset MQTT connection on error
            self._mqtt_connected = False
            raise SalusCloudConnectionError(f"Failed to update device shadow: {err}") from err

    async def set_temperature(
        self, device_code: str, temperature: float, device_index: str | None = None
    ) -> None:
        """Set target temperature for a thermostat."""
        _LOGGER.debug("Setting temperature for %s to %.1f°C", device_code, temperature)

        # Convert temperature to x100 format
        temp_x100 = int(temperature * 100)

        properties = {
            "ep9:sIT600TH:SetHeatingSetpoint_x100": temp_x100,
            "ep9:sIT600TH:SetHoldType": 2,  # Hold temperature
            "ep9:sIT600TH:SetSystemMode": 4,  # Heat mode
        }

        await self.update_device_shadow(device_code, properties, device_index)

    async def set_hold_mode(
        self, device_code: str, mode: int, device_index: str | None = None
    ) -> None:
        """Set thermostat hold mode.

        Args:
            device_code: Device code of the thermostat
            mode: Hold mode value
                0 = Auto/Schedule mode (follow schedule)
                2 = Manual Hold mode (maintain set temperature)
                7 = Standby/Frost mode (frost protection)
            device_index: Device index in shadow (optional)
        """
        _LOGGER.debug("Setting hold mode for %s to %d", device_code, mode)

        properties = {
            "ep9:sIT600TH:SetHoldType": mode,
        }

        await self.update_device_shadow(device_code, properties, device_index)

    async def set_switch_state(
        self, device_code: str, state: bool, device_index: str | None = None
    ) -> None:
        """Turn switch/relay on or off."""
        _LOGGER.debug("Setting switch %s to %s", device_code, "ON" if state else "OFF")

        properties = {
            "ep9:sOnOffS:SetOnOff": 1 if state else 0
        }

        await self.update_device_shadow(device_code, properties, device_index)

    async def update_gateway_shadow(
        self, gateway_code: str, properties: dict[str, Any]
    ) -> None:
        """Update gateway shadow via AWS IoT MQTT.

        Gateway shadow uses special device ID "000000000001".
        """
        try:
            _LOGGER.debug("Updating gateway shadow for %s", gateway_code)

            # Ensure MQTT is connected
            await self._ensure_mqtt_connected()

            # Create shadow update payload for gateway
            shadow_update = {
                "state": {
                    "desired": {
                        # Gateway always uses device ID "000000000001"
                        "000000000001": {
                            "properties": properties
                        }
                    }
                }
            }

            # Publish to shadow update topic
            topic = f"$aws/things/{gateway_code}/shadow/update"
            payload = json.dumps(shadow_update)

            _LOGGER.debug("Publishing to gateway topic %s: %s", topic, payload)

            # Publish in a thread (paho-mqtt is synchronous)
            def publish_sync():
                result = self._mqtt_client.publish(topic, payload, qos=1)
                result.wait_for_publish()
                if result.rc != mqtt.MQTT_ERR_SUCCESS:
                    raise SalusCloudConnectionError(f"MQTT publish failed with code {result.rc}")

            await asyncio.to_thread(publish_sync)

            _LOGGER.debug("Successfully published gateway shadow update for %s", gateway_code)

        except Exception as err:
            _LOGGER.error("Failed to update gateway shadow: %s", err)
            # Reset MQTT connection on error
            self._mqtt_connected = False
            raise SalusCloudConnectionError(f"Failed to update gateway shadow: {err}") from err

    async def trigger_onetouch_rule(
        self, gateway_code: str, rule_trigger_key: str
    ) -> None:
        """Trigger a OneTouch rule.

        Args:
            gateway_code: Gateway device code (not gateway ID)
            rule_trigger_key: Rule trigger key from the rule data
        """
        _LOGGER.debug("Triggering OneTouch rule with key: %s", rule_trigger_key)

        # OneTouch rules are triggered via gateway shadow update
        properties = {
            "ep0:sRule:SetTriggerRule": rule_trigger_key
        }

        await self.update_gateway_shadow(gateway_code, properties)

    async def close(self) -> None:
        """Close the session."""
        # Close MQTT connection
        if self._mqtt_client:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except Exception as err:
                _LOGGER.debug("Error closing MQTT client: %s", err)
            self._mqtt_client = None
            self._mqtt_connected = False

        # Close HTTP session
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
