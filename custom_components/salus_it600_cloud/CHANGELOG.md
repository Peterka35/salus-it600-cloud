# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2025-10-31

### Fixed
- 🐛 **MQTT WebSocket connection to AWS IoT**
  - Fixed "WebSocket handshake error, connection not upgraded"
  - Added proper connection synchronization using `asyncio.Event`
  - Improved connection timeout handling (10 seconds)
  - Added connection result verification (rc code check)
  - Better TLS/SSL configuration with cert verification
- 🔧 **Device index detection**
  - Fixed hardcoded device index "11" issue
  - Device index now automatically detected from shadow data
  - Stored as `_shadow_device_index` during device initialization
  - Fallback to "11" if detection fails
- 📝 **Debug logging improvements**
  - Extensive MQTT operation logging
  - Device index information in logs
  - WebSocket URL details (first 100 chars)
  - Error tracebacks for better debugging
  - Proper log level mapping for paho-mqtt

### Changed
- Gateway functions now accept optional `device_index` parameter:
  - `set_temperature(device_code, temperature, device_index=None)`
  - `set_hold_mode(device_code, mode, device_index=None)`
  - `set_switch_state(device_code, state, device_index=None)`
- MQTT connection now waits for actual connection before proceeding
- Better error messages with more context

### Technical Details
- Added `_mqtt_connect_event` and `_mqtt_connect_rc` for connection tracking
- Improved `_ensure_mqtt_connected()` with proper async/sync coordination
- Enhanced `update_device_shadow()` with automatic device index discovery
- Better exception handling with full tracebacks

## [1.0.0] - 2025-01-XX

### Added
- ✨ **Full device control** via AWS IoT MQTT
  - Set thermostat target temperature
  - Change thermostat preset modes (Schedule/Manual/Away)
  - Control switches and relays (turn on/off)
  - Trigger OneTouch automation rules
- 🌡️ **Climate entities** with full functionality
  - Current and target temperature display
  - Three preset modes: Schedule, Manual, Away/Frost
  - HVAC action display (heating/idle/off)
  - Extra state attributes (hold_type, system_mode, battery_voltage, running_state)
- 🔌 **Switch entities** with full control
  - RS600, SPE600, SR600 models
  - Turn on/off functionality
  - State feedback
- 📊 **Sensor entities**
  - Temperature sensors
  - Humidity sensors
  - Battery voltage sensors
- 🚪 **Binary sensor entities**
  - Door/window sensors (WLS models)
  - Motion and occupancy sensors
- 🎯 **Button entities** for OneTouch rules
  - Trigger predefined automation rules
  - Auto-filter system rules
  - Show only user-created rules
- 🔐 **AWS Cognito authentication**
  - SRP (Secure Remote Password) authentication
  - Automatic token refresh
  - Session management
- 📡 **AWS IoT MQTT** communication
  - Real-time device shadow updates
  - WebSocket connection over TLS
  - Automatic reconnection
- 🏷️ **Gateway-specific entity naming**
  - Entity IDs include gateway name
  - Prevents conflicts with multiple gateways
  - Format: `{gateway_slug}_{device_slug}`
- ⚙️ **Configuration flow**
  - User-friendly setup via UI
  - Email/password authentication
  - Automatic device discovery
- 🔄 **Data coordinator**
  - 30-second polling interval
  - Efficient state updates
  - Error handling and retry logic
- 📝 **Comprehensive logging**
  - Debug mode support
  - MQTT connection logging
  - API request/response logging

### Technical Details
- **Authentication**: AWS Cognito with pycognito library
- **MQTT Client**: paho-mqtt for AWS IoT
- **API Base**: service-api.eu.premium.salusconnect.io
- **Region**: EU (eu-central-1)
- **Polling**: 30 seconds
- **Device Shadow**: AWS IoT standard pattern

### Known Limitations
- Only EU region supported (eu-central-1)
- Requires internet connection (cloud-only)
- No local API support
- 30-second polling delay for non-MQTT updates

### Requirements
- Home Assistant 2023.1+
- Python 3.11+
- Active Salus Smart Home account
- Internet connection

## [0.1.0] - 2024-XX-XX (Development)

### Added
- Initial development version
- Read-only implementation
- Basic authentication
- Device discovery
- Entity creation (read-only)

---

## Planned Features

### Future Releases

#### v1.1.0
- [ ] WebSocket support for real-time updates
- [ ] Reduce polling interval when WebSocket active
- [ ] Add diagnostic sensors (signal strength, last seen)
- [ ] Improve error messages and recovery

#### v1.2.0
- [ ] Schedule/program viewing
- [ ] Schedule editing support
- [ ] Manual schedule override
- [ ] Vacation mode support

#### v1.3.0
- [ ] US region support
- [ ] Multi-region account support
- [ ] Automatic region detection

#### v2.0.0
- [ ] Local API support (if available)
- [ ] Hybrid local/cloud mode
- [ ] Offline operation support

---

## Migration Guides

### Upgrading from pre-1.0 (read-only) versions

**Entity ID Changes**:
Old versions used simple entity IDs like `climate.termostat_pokoj`.
Version 1.0+ uses gateway-specific IDs like `climate.apartman_245_5_termostat_pokoj`.

**Steps**:
1. Note down your current entity IDs
2. Update the integration
3. Remove and re-add the integration
4. Update automations and scripts with new entity IDs

**Unique ID Format**:
- Old: `salus_it600_cloud_{device_id}`
- New: `salus_it600_cloud_{gateway_id}_{device_id}`

This allows multiple gateways without conflicts.
