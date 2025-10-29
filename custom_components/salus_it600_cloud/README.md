# Salus iT600 Cloud Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Full-featured Home Assistant integration for controlling Salus iT600 smart home devices via the Salus Cloud API.

## ✨ Features

### Core Functionality
- ✅ **Cloud-based control** - Works from anywhere with internet access
- ✅ **Full device control** - Set temperature, change modes, control switches
- ✅ **Real-time updates** - AWS IoT MQTT for instant device state changes
- ✅ **AWS Cognito authentication** - Secure login with email/password
- ✅ **Automatic token refresh** - Seamless authentication management
- ✅ **30-second polling** - Keep device states up to date

### Supported Entities

#### 🌡️ Climate (Thermostats)
- Read current and target temperature
- **Set target temperature** with 0.5°C precision
- **Three preset modes:**
  - **Schedule** - Follow programmed schedule (HoldType = 0)
  - **Manual** - Hold specific temperature (HoldType = 2)
  - **Away** - Frost protection mode (HoldType = 7)
- View HVAC action (heating/idle/off)
- Extra attributes: hold_type, system_mode, battery_voltage, running_state

#### 🔌 Switches
- **Full control** - Turn switches/relays on and off
- RS600, SPE600, SR600 models supported
- Examples: boiler control, plug switches, relay switches

#### 📊 Sensors
- Temperature sensors
- Humidity sensors
- Battery voltage sensors

#### 🚪 Binary Sensors
- Door/window sensors (WLS models)
- Motion sensors
- Occupancy sensors

#### 🎯 Buttons (OneTouch Rules)
- Trigger predefined automation rules from Home Assistant
- Execute complex multi-device actions with one button press
- Auto-filters system rules, shows only user-created rules

## 📦 Installation

### Method 1: HACS (Recommended)

1. Open **HACS** in Home Assistant
2. Click on **Integrations**
3. Click the **⋮** menu → **Custom repositories**
4. Add repository URL: `https://github.com/Peterka35/salus-it600-cloud`
5. Category: **Integration**
6. Click **Add**
7. Search for "Salus iT600 Cloud"
8. Click **Download**
9. **Restart Home Assistant**

### Method 2: Manual Installation

1. Download the latest release
2. Extract the `salus_it600_cloud` folder
3. Copy it to your `<config>/custom_components/` directory
4. Your structure should look like:
   ```
   <config>/
   └── custom_components/
       └── salus_it600_cloud/
           ├── __init__.py
           ├── manifest.json
           ├── config_flow.py
           ├── coordinator.py
           ├── gateway.py
           ├── climate.py
           ├── sensor.py
           ├── switch.py
           ├── binary_sensor.py
           ├── button.py
           ├── const.py
           └── strings.json
   ```
5. **Restart Home Assistant**

## ⚙️ Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **➕ Add Integration**
3. Search for **Salus iT600 Cloud**
4. Enter your credentials:
   - **Email**: Your Salus Smart Home app email
   - **Password**: Your Salus Smart Home app password
5. Click **Submit**
6. Your devices will be automatically discovered

### Entity Naming

All entities are prefixed with your gateway name for easy identification:
- `climate.apartman_245_5_termostat_pokoj`
- `switch.apartman_245_5_boiler`
- `button.apartman_245_5_vypnout_topeni_15_stupnu`

This allows you to have multiple gateways without naming conflicts.

## 🎮 Usage Examples

### Setting Temperature
```yaml
service: climate.set_temperature
target:
  entity_id: climate.apartman_245_5_termostat_pokoj
data:
  temperature: 21.5
```

### Changing Preset Mode
```yaml
service: climate.set_preset_mode
target:
  entity_id: climate.apartman_245_5_termostat_koupelna
data:
  preset_mode: schedule  # or 'manual' or 'away'
```

### Controlling Switch
```yaml
service: switch.turn_on
target:
  entity_id: switch.apartman_245_5_boiler
```

### Triggering OneTouch Rule
```yaml
service: button.press
target:
  entity_id: button.apartman_245_5_zapnout_topeni_21_stupnu
```

## 🔧 Technical Details

### Cloud API Architecture
- **Authentication**: AWS Cognito SRP (Secure Remote Password)
- **API Base URL**: `https://service-api.eu.premium.salusconnect.io`
- **Control Method**: AWS IoT MQTT over WebSockets
- **Region**: EU (eu-central-1)
- **Polling Interval**: 30 seconds
- **MQTT**: Real-time device shadow updates

### AWS Services Used
- **Cognito User Pool**: Authentication
- **Cognito Identity Pool**: AWS credentials
- **IoT Core**: MQTT device communication
- **Device Shadows**: State synchronization

### Device Control Implementation
Temperature and mode changes are sent via MQTT to AWS IoT device shadows using the standard shadow update pattern:

```json
{
  "state": {
    "desired": {
      "11": {
        "properties": {
          "ep9:sIT600TH:SetHeatingSetpoint_x100": 2100,
          "ep9:sIT600TH:SetHoldType": 2
        }
      }
    }
  }
}
```

## 📋 Requirements

- **Home Assistant**: 2023.1 or newer
- **Python**: 3.11 or newer
- **Salus Account**: Active Salus Smart Home app account
- **Internet**: Required for cloud API access

## 📦 Dependencies

Automatically installed:
- `pycognito==2024.5.1` - AWS Cognito authentication
- `paho-mqtt>=1.6.1` - MQTT client for AWS IoT

## 🔍 Supported Devices

### Thermostats (Climate)
- **HTRP-RF** - Wireless programmable thermostat
- **TS600** - Touchscreen thermostat
- **VS10/VS20** - Wired thermostats
- **SQ610** - Thermostat with humidity sensor
- **FC600** - Fan coil thermostat

### Switches/Relays
- **RS600** - Relay switch
- **SPE600** - Smart plug
- **SR600** - Boiler switch

### Sensors
- **Temperature sensors** - IT600TH models
- **Humidity sensors** - SQ610 models
- **Battery sensors** - All battery-powered devices

### Binary Sensors
- **WLS** - Door/window sensors
- **Motion sensors**
- **Occupancy sensors**

## 🐛 Troubleshooting

### Authentication Failed

**Error**: `Invalid email or password`

**Solutions**:
- Verify credentials in the Salus Smart Home app
- Use email (not username) for login
- Try logging out and back in the mobile app
- Check for special characters in password

### No Devices Found

**Solutions**:
- Ensure devices are set up in the Salus app
- Check gateway is online (green LED)
- Wait 30 seconds for first poll
- Reload the integration

### MQTT Connection Issues

**Symptoms**: Device control doesn't work, but reading works

**Solutions**:
- Check Home Assistant can reach `*.iot.eu-central-1.amazonaws.com`
- Verify port 443 (HTTPS) is not blocked
- Check firewall/proxy settings
- Reload integration to reconnect MQTT

### Entity IDs Changed After Update

This is expected if you upgraded from an older version. The integration now uses gateway-specific entity IDs to support multiple gateways.

**Old**: `climate.termostat_pokoj`
**New**: `climate.apartman_245_5_termostat_pokoj`

Update your automations and scripts to use the new entity IDs.

## 📝 Debug Logging

To enable detailed logging for troubleshooting:

```yaml
# configuration.yaml
logger:
  default: warning
  logs:
    custom_components.salus_it600_cloud: debug
    paho.mqtt: info
```

Then check logs at **Settings** → **System** → **Logs**.

## 🤝 Contributing

Contributions are welcome! To contribute:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Credits

- **Author**: Created with assistance from Claude (Anthropic)
- **Based on**: Reverse engineering of Salus Cloud API
- **Inspired by**: Local `pyit600` library and `salusfy` integration

## ⚠️ Disclaimer

This integration is not officially affiliated with, endorsed by, or supported by Salus Controls. It is a community project that uses publicly accessible APIs.

Use at your own risk. The authors are not responsible for any damage to your devices or heating system.

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/Peterka35/salus-it600-cloud/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Peterka35/salus-it600-cloud/discussions)
- **Home Assistant Community**: [Forum Thread](https://community.home-assistant.io/)

## 🌟 Star History

If you find this integration useful, please consider giving it a star on GitHub!
