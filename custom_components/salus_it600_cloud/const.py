"""Constants for Salus iT600 Cloud integration."""

DOMAIN = "salus_it600_cloud"

# Config flow
CONF_EMAIL = "email"
CONF_PASSWORD = "password"

# AWS Cognito configuration
AWS_REGION = "eu-central-1"
AWS_USER_POOL_ID = "eu-central-1_XGRz3CgoY"
AWS_CLIENT_ID = "4pk5efh3v84g5dav43imsv4fbj"
AWS_IDENTITY_POOL_ID = "eu-central-1:60912c00-287d-413b-a2c9-ece3ccef9230"
AWS_IOT_ENDPOINT = "a24u3z7zzwrtdl-ats.iot.eu-central-1.amazonaws.com"

# Service API
SERVICE_API_BASE_URL = "https://service-api.eu.premium.salusconnect.io/api/v1"
COMPANY_CODE = "salus-eu"

# Polling interval
SCAN_INTERVAL_SECONDS = 30

# Device types
DEVICE_TYPE_CLIMATE = "climate"
DEVICE_TYPE_SENSOR = "sensor"
DEVICE_TYPE_SWITCH = "switch"
DEVICE_TYPE_BINARY_SENSOR = "binary_sensor"

# Attributes
ATTR_DEVICE_ID = "device_id"
ATTR_GATEWAY_ID = "gateway_id"
ATTR_MODEL = "model"
ATTR_DEVICE_CODE = "device_code"
