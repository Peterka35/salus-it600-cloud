"""Constants for Salus iT600 Cloud integration."""

DOMAIN = "salus_it600_cloud"

# Config flow
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
# Option: mode change of one thermostat is applied to all thermostats of its gateway
CONF_SYNC_MODES = "sync_thermostat_modes"

# AWS Cognito configuration
AWS_REGION = "eu-central-1"
AWS_USER_POOL_ID = "eu-central-1_XGRz3CgoY"
AWS_CLIENT_ID = "4pk5efh3v84g5dav43imsv4fbj"
AWS_IDENTITY_POOL_ID = "eu-central-1:60912c00-287d-413b-a2c9-ece3ccef9230"
AWS_IOT_ENDPOINT = "a24u3z7zzwrtdl-ats.iot.eu-central-1.amazonaws.com"

# Service API
SERVICE_API_BASE_URL = "https://service-api.eu.premium.salusconnect.io/api/v1"
COMPANY_CODE = "salus-eu"

# Polling of device states (seconds)
SCAN_INTERVAL_SECONDS = 30
# While device state changes are pushed over MQTT, polling is only a safety net
PUSH_SCAN_INTERVAL_SECONDS = 300
# Gateways, devices and OneTouch rules change rarely and are re-read less often
METADATA_REFRESH_SECONDS = 900
# Entities of a device without state data for this long become unavailable
STALE_AFTER_SECONDS = 600
# Commanded state is shown until the device reports it, at most this long
PENDING_TIMEOUT_SECONDS = 60
# Without pushed state changes a command is confirmed by polling after this delay
CONFIRM_REFRESH_DELAY_SECONDS = 10

# Shadow device index of the gateway itself and default index of other devices
GATEWAY_SHADOW_INDEX = "000000000001"
DEFAULT_SHADOW_INDEX = "11"

# Thermostat hold types
HOLD_TYPE_SCHEDULE = 0
HOLD_TYPE_MANUAL = 2
HOLD_TYPE_STANDBY = 7
