# 🚀 Jak nahrát integraci na GitHub

Tento návod ti ukáže, jak publikovat Salus iT600 Cloud integraci na GitHub.

## 📋 Příprava

### 1. Struktura souborů

Ujisti se, že máš tuto strukturu:

```
salus-it600-cloud/          (root GitHub repositáře)
├── custom_components/
│   └── salus_it600_cloud/  (složka integrace)
│       ├── __init__.py
│       ├── manifest.json
│       ├── config_flow.py
│       ├── coordinator.py
│       ├── gateway.py
│       ├── climate.py
│       ├── sensor.py
│       ├── switch.py
│       ├── binary_sensor.py
│       ├── button.py
│       ├── const.py
│       ├── strings.json
│       ├── hacs.json
│       ├── README.md
│       ├── INSTALLATION.md
│       ├── CHANGELOG.md
│       └── LICENSE
├── .gitignore
├── .gitattributes
├── INFO.md              (hlavní README pro GitHub)
└── README.md           (symlink na INFO.md)
```

### 2. Vyčisti složku

```bash
cd "C:\Users\peter\OneDrive\Home Assistant\Salus IT600"

# Smaž __pycache__ a .pyc soubory
Remove-Item -Recurse -Force salus_it600_cloud\__pycache__
Get-ChildItem -Recurse -Filter "*.pyc" | Remove-Item -Force

# Smaž testovací skripty (volitelné)
Remove-Item test_*.py
Remove-Item toggle_boiler.py
Remove-Item check_modes_after_rule.py
Remove-Item clean_salus_storage.py
Remove-Item cleanup_storage.py
```

## 🌐 Vytvoření GitHub repositáře

### Krok 1: Vytvoř nový repositář na GitHubu

1. Jdi na https://github.com/new
2. Zadej:
   - **Repository name**: `salus-it600-cloud`
   - **Description**: `Full-featured Home Assistant integration for Salus iT600 devices via Cloud API`
   - **Visibility**: Public
   - ❌ NEVYTVÁŘEJ README, .gitignore nebo LICENSE (už máme)
3. Klikni **Create repository**

### Krok 2: Inicializuj Git lokálně

```powershell
cd "C:\Users\peter\OneDrive\Home Assistant\Salus IT600"

# Inicializuj Git
git init

# Přejmenuj složku pro GitHub strukturu
mkdir custom_components
Move-Item salus_it600_cloud custom_components\

# Přesuň soubory do rootu
Move-Item INFO.md README.md
Move-Item custom_components\salus_it600_cloud\.gitignore .
Move-Item .gitattributes .

# Přidej všechny soubory
git add .

# První commit
git commit -m "Initial commit - Salus iT600 Cloud Integration v1.0.0

Features:
- Full device control (thermostats, switches)
- AWS IoT MQTT communication
- Three preset modes (Schedule, Manual, Away)
- OneTouch rules support
- Multiple gateway support
- Real-time updates"

# Nastav main větev
git branch -M main

# Přidej remote (nahraď YOUR_USERNAME svým GitHub uživatelským jménem)
git remote add origin https://github.com/YOUR_USERNAME/salus-it600-cloud.git

# Push na GitHub
git push -u origin main
```

## 🏷️ Vytvoření první release

### Krok 3: Vytvoř release na GitHubu

1. Jdi na `https://github.com/YOUR_USERNAME/salus-it600-cloud`
2. Klikni na **Releases** → **Create a new release**
3. Klikni **Choose a tag** → zadej `v1.0.0` → **Create new tag**
4. **Release title**: `v1.0.0 - Initial Release`
5. **Description**:

```markdown
# 🎉 First Release - Full Control Support

This is the first public release of the Salus iT600 Cloud integration for Home Assistant.

## ✨ Features

- ✅ Full thermostat control (temperature + preset modes)
- ✅ Switch/relay control (boiler, plugs)
- ✅ OneTouch automation rules
- ✅ Real-time MQTT updates via AWS IoT
- ✅ Multiple gateway support
- ✅ Battery monitoring
- ✅ Temperature, humidity, and binary sensors

## 📦 Installation

Via HACS:
1. Add custom repository: `https://github.com/YOUR_USERNAME/salus-it600-cloud`
2. Install "Salus iT600 Cloud"
3. Restart Home Assistant
4. Add integration via UI

## 📋 Requirements

- Home Assistant 2023.1+
- Salus Smart Home account
- Internet connection

## 🐛 Known Issues

None reported yet!

## 📖 Documentation

See [README](https://github.com/YOUR_USERNAME/salus-it600-cloud/blob/main/custom_components/salus_it600_cloud/README.md) for full documentation.
```

6. Klikni **Publish release**

## 📦 HACS Instalace

### Krok 4: Přidej do HACS

**Pro uživatele:**

1. Otevři HACS v Home Assistantu
2. Jdi na **Integrations**
3. Klikni **⋮** → **Custom repositories**
4. Přidej URL: `https://github.com/YOUR_USERNAME/salus-it600-cloud`
5. Kategorie: **Integration**
6. Klikni **Add**
7. Vyhledej "Salus iT600 Cloud"
8. Klikni **Download**

## 📝 Po publikaci

### Aktualizuj odkazy v souborech

1. **manifest.json** - aktualizuj `documentation` URL:
   ```json
   "documentation": "https://github.com/YOUR_USERNAME/salus-it600-cloud"
   ```

2. **README.md** - nahraď `YOUR_USERNAME` skutečným jménem:
   ```bash
   cd custom_components/salus_it600_cloud
   # Windows PowerShell
   (Get-Content README.md) -replace 'YOUR_USERNAME', 'your_actual_username' | Set-Content README.md
   ```

3. **INFO.md** - stejně

4. Commit změn:
   ```bash
   git add .
   git commit -m "Update repository URLs"
   git push
   ```

## 🎯 Propagace

### Kam sdílet

1. **Home Assistant Community Forum**
   - https://community.home-assistant.io/
   - Kategorie: Third party integrations
   - Nadpis: "[Custom Integration] Salus iT600 Cloud - Full Control"

2. **Reddit**
   - r/homeassistant
   - Nadpis: "New Integration: Salus iT600 Cloud with Full Control"

3. **Home Assistant Discord**
   - #custom-integrations channel

## 📊 Statistiky

Po publikaci můžeš sledovat:
- ⭐ Stars na GitHubu
- 👀 Views repositáře
- 📥 Downloads přes HACS
- 🐛 Nahlášené issues
- 💬 Diskuse

## 🔄 Budoucí aktualizace

Pro release nové verze:

```bash
# Aktualizuj manifest.json version
# Přidej změny do CHANGELOG.md

git add .
git commit -m "Release v1.1.0 - Add feature XYZ"
git tag v1.1.0
git push origin main --tags

# Vytvoř nový release na GitHubu
```

## 🎉 Hotovo!

Gratulace! Tvoje integrace je nyní veřejně dostupná na GitHubu a připravená pro instalaci přes HACS! 🚀
