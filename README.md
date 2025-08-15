# OD‑11 (WebSocket) — Home Assistant Custom Integration

A minimal, clean Home Assistant integration to control **Teenage Engineering OD‑11** speakers over the **native WebSocket API**.

**Scope**: _Input_ and _Volume_ only.  
**Not** a `media_player` (use Music Assistant or other integrations for playback).

---

## Features

- Local WebSocket connection (`ws://<od11-ip>/ws`) with the device’s native handshake:
  - `global_join` → `group_join`
- Full state snapshot & live updates:
  - `sid`, `volume`, `input source`, `sources[]`
  - device info (wifi quality, firmware revision, MAC, SSID)
- Entities:
  - `number`: volume (0–100)
  - `select`: input (AirPlay/Spotify/Playlist/Line in/Optical/Bluetooth)
- Services:
  - `od11.volume_set` (`volume: 0..100`)
  - `od11.volume_nudge` (`amount: +int/-int`)
  - `od11.set_input` (`source: id/name/alias`, e.g. `optical`, `b`)
  - Convenience services:
    - `od11.set_input_airplay`
    - `od11.set_input_spotify`
    - `od11.set_input_playlist`
    - `od11.set_input_linein`
    - `od11.set_input_optical`
    - `od11.set_input_bluetooth`
- Lightweight app‑level keepalive pings.

---

## Installation

### Option A: HACS (custom repository)

1. In HACS → **Integrations** → ⋮ → **Custom repositories**  
   Add this repository URL, Category: **Integration**.
2. Install **OD‑11 (WebSocket, Input & Volume only)**.
3. Restart Home Assistant.

### Option B: Manual

1. Copy the `custom_components/od11` folder into your `<config>/custom_components/` directory.
2. Restart Home Assistant.

---

## Configuration

1. **Settings → Devices & Services → Add Integration → “OD‑11 (WebSocket)”**
2. Enter:
   - **Host**: `10.13.12.212` (your OD‑11 IP/hostname)
   - **WebSocket path**: `/ws` (default)
   - **Origin**: (optional; defaults to `http://<host>`)
   - **Cookie**: (optional; e.g. `orthoplay=...` if your device enforces it)

> The integration uses **local push** via WebSocket; no cloud, no polling for normal state.

---

## Entities

- **`number.<device>_volume`** — 0..100
- **`select.<device>_input`** — one of the device’s sources

Attributes (visible in Dev Tools):
- `sid`, `source_id`, `sources` (id→name map), `wifi_quality`, `revision`, `mac`, `ssid`

---

## Services

### Volume

```yaml
service: od11.volume_set
target:
  entity_id: number.od11_living_room_volume
data:
  volume: 10
```
