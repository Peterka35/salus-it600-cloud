# Instalační průvodce - Salus iT600 Cloud

## Krok 1: Instalace integrace

### Varianta A: Ruční instalace

1. Zkopírujte celou složku `salus_it600_cloud` do složky `custom_components` ve vaší Home Assistant instalaci:
   ```
   /config/custom_components/salus_it600_cloud/
   ```

2. Struktura by měla vypadat takto:
   ```
   /config/
   └── custom_components/
       └── salus_it600_cloud/
           ├── __init__.py
           ├── manifest.json
           ├── config_flow.py
           ├── const.py
           ├── coordinator.py
           ├── gateway.py
           ├── climate.py
           ├── sensor.py
           ├── switch.py
           ├── binary_sensor.py
           └── strings.json
   ```

### Varianta B: HACS (budoucnost)

V budoucnu bude možné instalovat přes HACS jako custom repository.

## Krok 2: Restart Home Assistant

Po zkopírování souborů restartujte Home Assistant:
- **Nastavení** → **Systém** → **Restartovat**

## Krok 3: Přidání integrace

1. Přejděte do **Nastavení** → **Zařízení a služby**
2. Klikněte na tlačítko **+ Přidat integraci** (vpravo dole)
3. Vyhledejte **Salus iT600 Cloud**
4. Zadejte vaše přihlašovací údaje:
   - **Email**: Váš email do Salus Smart Home aplikace
   - **Password**: Vaše heslo do Salus Smart Home aplikace

## Krok 4: Ověření

Po úspěšném přidání by se měla integrace objevit v seznamu zařízení a služeb.

### Co očekávat:

✅ **Funguje:**
- Zobrazení všech termostátů jako climate entity
- Zobrazení aktuální teploty
- Zobrazení cílové teploty
- Zobrazení sensorů (teplota, vlhkost, baterie)
- Zobrazení spínačů a binárních sensorů
- Automatická aktualizace každých 30 sekund

⚠️ **Nefunguje (zatím):**
- Nastavování teploty
- Zapínání/vypínání spínačů
- Změna režimů termostatu

## Řešení problémů

### Integrace se nenačte

**Příznaky:** Integrace se nezobrazí v seznamu dostupných integrací

**Řešení:**
1. Ověřte, že jste zkopírovali všechny soubory
2. Zkontrolujte log Home Assistant (**Nastavení** → **Systém** → **Protokoly**)
3. Ujistěte se, že Home Assistant má nainstalované závislosti

### Chyba autentizace

**Chyba:** `Invalid email or password`

**Řešení:**
1. Ověřte si přihlašovací údaje v mobilní aplikaci Salus Smart Home
2. Zkuste se odhlásit a znovu přihlásit v mobilní aplikaci
3. Použijte email (ne přihlašovací jméno)

### Žádná zařízení

**Chyba:** `No devices found on your account`

**Řešení:**
1. Ověřte, že máte zařízení spárovaná v mobilní aplikaci
2. Zkontrolujte, že gateway je online
3. Restartujte gateway

### Debugging

Pro zobrazení detailních logů přidejte do `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.salus_it600_cloud: debug
```

Potom restartujte Home Assistant a zkontrolujte logy.

## Co dál?

### Pomoc s implementací ovládání

Pokud chcete pomoci s dokončením funkce ovládání zařízení:

1. Nainstalujte aplikaci pro zachytávání síťového provozu:
   - Na počítači: Charles Proxy, mitmproxy
   - Na Android: Packet Capture
   - V prohlížeči: Developer Tools → Network

2. Použijte mobilní aplikaci Salus Smart Home:
   - Změňte teplotu na termostatu
   - Zapněte/vypněte spínač
   - Změňte režim

3. Zachyťte HTTP požadavky:
   - Hledejte požadavky na `service-api.eu.premium.salusconnect.io`
   - Uložte jako HAR soubor nebo screenshot

4. Sdílejte data:
   - Vytvořte issue na GitHubu
   - Připojte HAR soubor nebo detaily požadavku

### Užitečné odkazy

- Oficiální Salus aplikace: https://eu.premium.salusconnect.io
- Home Assistant dokumentace: https://www.home-assistant.io/docs/
- Problém s autentizací? Kontaktujte Salus support

## Bezpečnost

- Heslo je uloženo v Home Assistant konfiguraci (šifrované)
- Komunikace probíhá přes HTTPS
- Tokeny jsou automaticky obnovované
- Používá se AWS Cognito autentizace (bezpečný standard)

## Časté dotazy

**Q: Mohu používat lokální i cloud integraci zároveň?**
A: Ano, můžete mít obě integrace nainstalované současně. Doporučujeme použít různá jména pro entity.

**Q: Funguje to i mimo domácí síť?**
A: Ano, cloud integrace funguje odkudkoli, kde máte internet.

**Q: Podporuje to scény a automatizace?**
A: Ano, jakmile bude implementováno ovládání, budete moci používat všechny Home Assistant automatizace.

**Q: Je to bezpečné?**
A: Ano, používáme oficiální Salus Cloud API s AWS Cognito autentizací.
