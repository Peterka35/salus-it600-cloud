# Salus iT600 Cloud Integration

This repository contains a full-featured Home Assistant integration for Salus iT600 smart home devices via the Salus Cloud API.

## Quick Links

- 📖 [Full Documentation](custom_components/salus_it600_cloud/README.md)
- 🐛 [Report Issues](../../issues)
- 💬 [Discussions](../../discussions)
- 📦 [Installation Guide](custom_components/salus_it600_cloud/INSTALLATION.md)

## Features

✅ **Full device control** - Set temperature, change modes, control switches
✅ **Real-time updates** - AWS IoT MQTT for instant state changes
✅ **Three preset modes** - Schedule, Manual, Away/Frost protection
✅ **OneTouch rules** - Trigger predefined automation rules
✅ **Multiple gateways** - Support for multiple Salus gateways
✅ **Battery monitoring** - Track battery levels on wireless devices

## Supported Devices

- 🌡️ Thermostats: HTRP-RF, TS600, VS10/VS20, SQ610, FC600, IT800TX
- 🔌 Switches: RS600, SPE600, SR600 (relays, plugs, boiler control)
- 📊 Sensors: Temperature, humidity, battery voltage
- 🚪 Binary Sensors: WLS door/window sensors, motion sensors
- 🎯 Buttons: OneTouch automation rules

## Quick Start

### Installation via HACS

1. Add custom repository: `https://github.com/Peterka35/salus-it600-cloud`
2. Install "Salus iT600 Cloud" integration
3. Restart Home Assistant
4. Add integration via UI with your Salus credentials

### Manual Installation

```bash
cd /config/custom_components
git clone https://github.com/Peterka35/salus-it600-cloud.git
# Restart Home Assistant
```

## Contributing

Contributions welcome! See [README](custom_components/salus_it600_cloud/README.md) for details.

## License

MIT License - See [LICENSE](custom_components/salus_it600_cloud/LICENSE)

**Co je MIT Licence?** Otevřená licence, která umožňuje komukoliv volně používat, upravovat a šířit tento kód, i v komerčních projektech. Jediná podmínka je zachovat copyright poznámku.

## Support

- 🐛 [Report a Bug](../../issues/new?template=bug_report.md)
- 💡 [Request a Feature](../../issues/new?template=feature_request.md)
- 💬 [Join Discussion](../../discussions)
