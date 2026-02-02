#!/usr/bin/env python3
"""Fetch Salus devices and print humidity-related fields."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any


def _normalize_humidity(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.endswith("%"):
            stripped = stripped[:-1].strip()
        try:
            value = float(stripped)
        except ValueError:
            return None
    if isinstance(value, (int, float)):
        if value > 100:
            return float(value) / 100.0
        return float(value)
    return None


def _extract_humidity_from_shadow(shadow_props: dict[str, Any]) -> float | None:
    if not isinstance(shadow_props, dict) or not shadow_props:
        return None

    candidates = [
        "ep9:sIT600TH:LocalHumidity",
        "ep9:sIT600TH:LocalHumidity_x100",
        "ep9:sIT600TH:Humidity",
        "ep9:sIT600TH:Humidity_x100",
    ]
    for key in candidates:
        if key in shadow_props:
            return _normalize_humidity(shadow_props.get(key))

    for key, value in shadow_props.items():
        if "humidity" in key.lower():
            return _normalize_humidity(value)

    return None


def _decode_bcd_pair(b1: int, b2: int) -> int | None:
    """Decode two bytes of BCD into an integer (e.g., 0x21 0x40 -> 2140)."""
    def nibble_to_digit(n: int) -> int | None:
        return n if 0 <= n <= 9 else None

    hi1, lo1 = (b1 >> 4) & 0xF, b1 & 0xF
    hi2, lo2 = (b2 >> 4) & 0xF, b2 & 0xF
    d1 = nibble_to_digit(hi1)
    d2 = nibble_to_digit(lo1)
    d3 = nibble_to_digit(hi2)
    d4 = nibble_to_digit(lo2)
    if None in (d1, d2, d3, d4):
        return None
    return d1 * 1000 + d2 * 100 + d3 * 10 + d4


def _status_d_candidates(status_d: str) -> list[tuple[int, float]]:
    """Return candidate values from Status_d as (offset, value) in percent."""
    try:
        raw = bytes.fromhex(status_d)
    except ValueError:
        return []

    candidates: list[tuple[int, float]] = []
    for i in range(0, len(raw) - 1):
        decoded = _decode_bcd_pair(raw[i], raw[i + 1])
        if decoded is None:
            continue
        value = decoded / 100.0
        if 10.0 <= value <= 90.0:
            candidates.append((i, value))
    return candidates


def _status_d_single_byte_candidates(status_d: str) -> list[tuple[int, int]]:
    """Return candidate single-byte values in 0..100 as (offset, value)."""
    try:
        raw = bytes.fromhex(status_d)
    except ValueError:
        return []
    candidates: list[tuple[int, int]] = []
    for i, b in enumerate(raw):
        if 0 <= b <= 100:
            candidates.append((i, b))
    return candidates


def _status_d_bcd_single_byte_candidates(status_d: str) -> list[tuple[int, int]]:
    """Return candidate single-byte BCD values in 0..99 as (offset, value)."""
    try:
        raw = bytes.fromhex(status_d)
    except ValueError:
        return []
    candidates: list[tuple[int, int]] = []
    for i, b in enumerate(raw):
        hi, lo = (b >> 4) & 0xF, b & 0xF
        if hi <= 9 and lo <= 9:
            value = hi * 10 + lo
            candidates.append((i, value))
    return candidates


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print Salus device humidity data.")
    parser.add_argument(
        "--device",
        help="Filter by device name/id/code (substring match).",
    )
    parser.add_argument(
        "--target-humidity",
        type=float,
        help="Target humidity to locate in Status_d.",
    )
    parser.add_argument(
        "--target-temp",
        type=float,
        help="Target temperature to locate in Status_d.",
    )
    parser.add_argument(
        "--dump-shadow",
        action="store_true",
        help="Dump full shadow properties to stdout for matched devices.",
    )
    parser.add_argument(
        "--dump-shadow-file",
        help="Write full shadow properties JSON to a file for matched devices.",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    email = os.getenv("SALUS_EMAIL")
    password = os.getenv("SALUS_PASSWORD")
    if not email or not password:
        print("Missing SALUS_EMAIL or SALUS_PASSWORD in environment.", file=sys.stderr)
        return 1

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    # Import gateway module directly to avoid Home Assistant deps in __init__.py
    import importlib.util
    import types

    custom_components_path = os.path.join(repo_root, "custom_components")
    salus_path = os.path.join(custom_components_path, "salus_it600_cloud")

    # Create minimal package modules so relative imports in gateway.py work.
    if "custom_components" not in sys.modules:
        pkg = types.ModuleType("custom_components")
        pkg.__path__ = [custom_components_path]
        sys.modules["custom_components"] = pkg
    if "custom_components.salus_it600_cloud" not in sys.modules:
        subpkg = types.ModuleType("custom_components.salus_it600_cloud")
        subpkg.__path__ = [salus_path]
        sys.modules["custom_components.salus_it600_cloud"] = subpkg

    gateway_path = os.path.join(salus_path, "gateway.py")
    spec = importlib.util.spec_from_file_location(
        "custom_components.salus_it600_cloud.gateway", gateway_path
    )
    if spec is None or spec.loader is None:
        print("Failed to load gateway module.", file=sys.stderr)
        return 1
    gateway_module = importlib.util.module_from_spec(spec)
    sys.modules["custom_components.salus_it600_cloud.gateway"] = gateway_module
    spec.loader.exec_module(gateway_module)
    SalusCloudGateway = gateway_module.SalusCloudGateway

    gateway = SalusCloudGateway(email=email, password=password)
    print("Authenticating...")
    try:
        await asyncio.wait_for(gateway.authenticate(), timeout=30)
    except asyncio.TimeoutError:
        print("Authentication timed out after 30s.", file=sys.stderr)
        return 1

    try:
        print("Fetching devices...")
        devices = await asyncio.wait_for(gateway.get_all_devices(), timeout=30)
    except asyncio.TimeoutError:
        print("Device fetch timed out after 30s.", file=sys.stderr)
        return 1
    finally:
        await gateway.close()

    print(f"Found {len(devices)} device(s)\n")

    matched_devices = []
    for device in devices:
        device_id = device.get("id") or device.get("device_id")
        device_code = device.get("device_code")
        name = device.get("name") or device_id
        model = device.get("model")
        device_type = device.get("type")
        haystack = " ".join(str(part) for part in [name, device_id, device_code] if part)
        if args.device and args.device.lower() not in haystack.lower():
            continue
        matched_devices.append(device)

        print("=" * 72)
        print(f"Name: {name}")
        print(f"ID: {device_id}  Code: {device_code}  Model: {model}  Type: {device_type}")

        status = device.get("status") if isinstance(device.get("status"), dict) else {}
        shadow_props = device.get("_shadow_properties") if isinstance(device.get("_shadow_properties"), dict) else {}
        status_d = shadow_props.get("ep9:sIT600TH:Status_d") if isinstance(shadow_props, dict) else None

        direct_humidity = None
        for field in ("humidity", "current_humidity"):
            if field in device:
                direct_humidity = _normalize_humidity(device.get(field))
                break
        status_humidity = _normalize_humidity(status.get("humidity")) if status else None
        shadow_humidity = _extract_humidity_from_shadow(shadow_props)

        print(f"humidity (direct): {direct_humidity}")
        print(f"humidity (status): {status_humidity}")
        print(f"humidity (shadow): {shadow_humidity}")

        if shadow_props:
            humidity_keys = [k for k in shadow_props.keys() if "humidity" in k.lower()]
            if humidity_keys:
                print(f"shadow humidity keys: {humidity_keys}")
                for key in humidity_keys:
                    print(f"  {key}: {shadow_props.get(key)}")
            else:
                print(f"shadow key count: {len(shadow_props.keys())}")
        else:
            print("shadow: none")

        if status_d:
            candidates = _status_d_candidates(status_d)
            print(f"status_d length: {len(status_d)} hex chars")
            if candidates:
                print("status_d humidity candidates (offset -> %):")
                for offset, value in candidates:
                    print(f"  {offset}: {value:.2f}")
            else:
                print("status_d humidity candidates: none")

            if args.target_humidity is not None or args.target_temp is not None:
                single = _status_d_single_byte_candidates(status_d)
                bcd_single = _status_d_bcd_single_byte_candidates(status_d)
                if args.target_humidity is not None:
                    target = args.target_humidity
                    print(f"status_d target humidity: {target}")
                    near = [(o, v) for o, v in single if abs(v - target) <= 2]
                    near_bcd = [(o, v) for o, v in bcd_single if abs(v - target) <= 2]
                    if near:
                        print("  single-byte near matches:")
                        for o, v in near:
                            print(f"    {o}: {v}")
                    if near_bcd:
                        print("  BCD single-byte near matches:")
                        for o, v in near_bcd:
                            print(f"    {o}: {v}")
                if args.target_temp is not None:
                    target = args.target_temp
                    print(f"status_d target temp: {target}")
                    near_bcd = [(o, v) for o, v in candidates if abs(v - target) <= 0.5]
                    if near_bcd:
                        print("  BCD-pair near matches:")
                        for o, v in near_bcd:
                            print(f"    {o}: {v:.2f}")

        if args.dump_shadow and shadow_props:
            print("shadow properties:")
            print(json.dumps(shadow_props, indent=2, sort_keys=True))

    if args.dump_shadow_file and matched_devices:
        output = {}
        for device in matched_devices:
            device_id = device.get("id") or device.get("device_id")
            device_code = device.get("device_code")
            name = device.get("name") or device_id
            shadow_props = device.get("_shadow_properties") if isinstance(device.get("_shadow_properties"), dict) else {}
            output_key = f"{name} ({device_code or device_id})"
            output[output_key] = shadow_props
        with open(args.dump_shadow_file, "w", encoding="utf-8") as handle:
            json.dump(output, handle, indent=2, sort_keys=True)
        print(f"Wrote shadow properties to {args.dump_shadow_file}")

    print("\nDone.")
    return 0


def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
