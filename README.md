
# Album Artwork Lighting

Automatically match a room's lights to the dominant color of the album artwork playing on Soloist.

## 1. Install ColorExtractor

Home Assistant → Settings → Devices & services → Add integration → **ColorExtractor**.

## 2. Allow Spotify artwork URLs

Add to `configuration.yaml` (merge with any existing `homeassistant:` section):

```yaml
homeassistant:
  allowlist_external_urls:
    - "https://i.scdn.co/image/"
```

Restart Home Assistant.

## 3. Create an automation

Settings → Automations & scenes → Create automation → Edit in YAML:

```yaml
alias: Soloist — Album Artwork Lighting
triggers:
  - trigger: state
    entity_id: media_player.ROOM_DEVICE_soloist
    attribute: entity_picture
  - trigger: state
    entity_id: media_player.ROOM_DEVICE_soloist
    to: playing
conditions:
  - condition: state
    entity_id: media_player.ROOM_DEVICE_soloist
    state: playing
  - condition: template
    value_template: >
      {{ (state_attr('media_player.ROOM_DEVICE_soloist',
      'entity_picture') or '').startswith('https://i.scdn.co/image/') }}
actions:
  - action: color_extractor.turn_on
    target:
      area_id: AREA_ID
    data:
      color_extract_url: >
        {{ state_attr('media_player.ROOM_DEVICE_soloist',
        'entity_picture') }}
      transition: 3
mode: restart
```

Replace `entity_id` with your Soloist player and `area_id` with your room's ID (or use `entity_id: light.your_light`).

**Note:** Lights must support RGB. The automation turns on targeted lights, including those previously off. It runs when artwork changes or playback starts.


# mDNS Discovery

Soloist is automatically discovered through Spotify Connect mDNS (`_spotify-connect._tcp.local.`).

Discovery requires:
- **UDP 5353:** mDNS advertisements.
- **Dynamic TCP port:** Spotify Connect HTTP `getInfo` (changes after restart).
- **TCP 9090:** Soloist WebSocket (or your configured port).

## Linux / UFW

On the **Soloist host**, allow connections from Home Assistant:

```bash
sudo ufw allow from <HA_IP> to any proto tcp
```

This permits access to both the dynamic HTTP port and WebSocket. **Note:** It also grants HA access to other TCP services on the host.

Ensure Soloist listens on the network, not just localhost:

```bash
--ws 0.0.0.0:9090
```

Keep your firewall enabled. Do not expose Soloist's **unauthenticated** WebSocket to the Internet.

If mDNS works but Soloist isn't discovered, verify that Home Assistant can reach the HTTP `getInfo` port advertised in its **Zeroconf Browser**.

**You can also just skip all of this add your device manually with Home Assistant → Settings → Devices & services → Add integration → Soloist.**
