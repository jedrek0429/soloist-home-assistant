# Soloist for Home Assistant

Copy `custom_components/soloist` into `<HA_CONFIG>/custom_components/soloist`, restart Home Assistant, then add **Soloist** under **Settings → Devices & services**. Automatic Spotify Connect mDNS discovery is supported; manual host/port setup is also available.

## Album artwork lighting

The integration extracts a perceptual accent colour from Spotify album artwork using the OKLab/OKLCH algorithm from [Soloist Display](https://github.com/jedrek0429/soloist-display/blob/alpha/v1.1.0/src/backdrop-colour.js). It exposes an **Album colour** sensor with a hex state (`#rrggbb`) and `rgb_color` attribute.

Create an automation (**Settings → Automations & scenes → Create automation → Edit in YAML**):

```yaml
alias: Soloist — Album Artwork Lighting
triggers:
  - trigger: state
    entity_id: sensor.YOUR_SOLOIST_ALBUM_COLOUR
  - trigger: state
    entity_id: media_player.YOUR_SOLOIST
    to: playing
conditions:
  - condition: state
    entity_id: media_player.YOUR_SOLOIST
    state: playing
  - condition: template
    value_template: >
      {{ (state_attr('sensor.YOUR_SOLOIST_ALBUM_COLOUR', 'rgb_color') or []) | count == 3 }}
actions:
  - action: light.turn_on
    target:
      area_id: YOUR_AREA_ID
    data:
      rgb_color: "{{ state_attr('sensor.YOUR_SOLOIST_ALBUM_COLOUR', 'rgb_color') }}"
      transition: 3
mode: restart
```

Replace the sensor/player IDs with the entities created for your Soloist, and `YOUR_AREA_ID` with your room or target individual RGB-capable light entities. **The automation turns on lights that were off.** To change only lights already on, target those lights in your own automation.

Colours are calculated only when the artwork URL changes, cached (64 covers), and cleared when the player disconnects. Only HTTPS artwork from `i.scdn.co/image/` is downloaded, with redirects, transfer size and decoded size restricted. Image decoding runs outside Home Assistant's event loop.

## mDNS discovery and firewall

Discovery uses `_spotify-connect._tcp.local.` (UDP 5353). Home Assistant then requests Spotify Connect HTTP `getInfo` on the **dynamically advertised TCP port**, and uses Soloist WebSocket TCP 9090 (or your configured port) for playback.

On the **Soloist host**, a UFW rule permitting all TCP ports **only from the Home Assistant IP** allows discovery despite the dynamic HTTP port:

```bash
sudo ufw allow from <HA_IP> to any proto tcp
```

This also grants HA access to other TCP services on that host; use a narrower rule if the ZeroConf HTTP port is fixed. Soloist's WebSocket must listen on a network interface, e.g. `--ws 0.0.0.0:9090` rather than `127.0.0.1:9090`. Keep UFW enabled and never expose the unauthenticated WebSocket to the Internet.

Use manual configuration for less hustle.
