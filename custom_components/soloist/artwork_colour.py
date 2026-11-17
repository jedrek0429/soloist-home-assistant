"""Perceptual artwork accent colour, ported from Soloist Display's OKLab algorithm.

Source: soloist-display/src/backdrop-colour.js (alpha/v1.1.0).
Keep the weighting, hue buckets and sRGB gamut mapping in sync with it.
"""

from __future__ import annotations

from math import atan2, cbrt, cos, floor, hypot, pi, sin
from typing import Sequence

BUCKET_COUNT = 24
FALLBACK_COLOUR = "#555963"


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _linear(value: int) -> float:
    channel = value / 255
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _srgb(value: float) -> float:
    return 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055


def _to_oklab(red: int, green: int, blue: int) -> tuple[float, float, float]:
    r, g, b = _linear(red), _linear(green), _linear(blue)
    l = cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m = cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s = cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return (
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    )


def _from_oklch(lightness: float, chroma: float, hue: float) -> str:
    """Reduce chroma until the colour fits sRGB, preserving hue."""
    for _ in range(24):
        a, b = chroma * cos(hue), chroma * sin(hue)
        l = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
        m = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
        s = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
        rgb = (
            4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
        )
        if all(0 <= channel <= 1 for channel in rgb):
            return "#" + "".join(
                f"{floor(_clamp(_srgb(channel), 0, 1) * 255 + 0.5):02x}"
                for channel in rgb
            )
        chroma *= 0.9
    return FALLBACK_COLOUR


def dominant_colour_from_pixels(
    data: bytes | bytearray | memoryview | Sequence[int],
    width: int,
    height: int,
) -> str | None:
    """Extract a prominent chromatic region from RGBA pixels.

    The caller should normally downsample the artwork to 64×64 first.
    White typography, black borders and isolated neon pixels are deweighted.
    """
    if width <= 0 or height <= 0 or len(data) < width * height * 4:
        return None

    # Each bin stores [weight, pixels, weighted a, weighted b, weighted L,
    # weighted chroma]. Neighbouring hue bins compete as one circular group.
    bins = [[0.0] * 6 for _ in range(BUCKET_COUNT)]
    visible = neutral_lightness = neutral_weight = 0.0
    stride = max(1, max(width, height) // 64)

    for y in range(0, height, stride):
        for x in range(0, width, stride):
            offset = (y * width + x) * 4
            alpha = data[offset + 3] / 255
            if alpha < 0.5:
                continue

            l, a, b = _to_oklab(
                data[offset], data[offset + 1], data[offset + 2]
            )
            chroma = hypot(a, b)
            visible += alpha

            if 0.12 < l < 0.94:
                neutral_lightness += l * alpha
                neutral_weight += alpha

            if l < 0.14 or l > 0.93 or chroma < 0.027:
                continue

            hue = atan2(b, a)
            index = floor((hue + pi) / (2 * pi) * BUCKET_COUNT) % BUCKET_COUNT
            weight = alpha * (0.8 + 0.65 * min(chroma / 0.12, 1.5))
            bucket = bins[index]
            bucket[0] += weight
            bucket[1] += alpha
            bucket[2] += a * weight
            bucket[3] += b * weight
            bucket[4] += l * weight
            bucket[5] += chroma * weight

    if not visible:
        return None

    winner: list[float] | None = None
    winner_score = -1.0
    for index in range(BUCKET_COUNT):
        group = [
            sum(bins[(index + neighbour) % BUCKET_COUNT][field] for neighbour in (-1, 0, 1))
            for field in range(6)
        ]
        weight, pixels, _, _, _, chroma_total = group
        if pixels < visible * 0.012 or weight == 0:
            continue
        average_chroma = chroma_total / weight
        score = weight * (0.8 + 0.2 * min(average_chroma / 0.12, 1.5))
        if score > winner_score:
            winner, winner_score = group, score

    if winner is None:
        average = neutral_lightness / neutral_weight if neutral_weight else 0.48
        return _from_oklch(_clamp(0.54 + (average - 0.5) * 0.08, 0.5, 0.58), 0.022, 4.35)

    weight, _, a, b, lightness_total, chroma_total = winner
    hue = atan2(b, a)
    lightness = _clamp(0.58 + (lightness_total / weight - 0.5) * 0.12, 0.54, 0.63)
    chroma = _clamp(chroma_total / weight * 1.3, 0.095, 0.19)
    return _from_oklch(lightness, chroma, hue)


def rgb_from_hex(colour: str) -> tuple[int, int, int]:
    """Convert an extracted #rrggbb colour to Home Assistant RGB values."""
    return (int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16))


def average_colour_from_pixels(
    data: bytes | bytearray | memoryview | Sequence[int],
    width: int,
    height: int,
) -> str | None:
    """Alpha-weighted arithmetic mean in sRGB, without aesthetic correction."""
    if width <= 0 or height <= 0 or len(data) < width * height * 4:
        return None
    totals = [0.0, 0.0, 0.0]
    weight = 0.0
    for i in range(0, width * height * 4, 4):
        alpha = data[i + 3] / 255
        weight += alpha
        for channel in range(3):
            totals[channel] += data[i + channel] * alpha
    if not weight:
        return None
    return "#" + "".join(f"{floor(value / weight + 0.5):02x}" for value in totals)


def lighting_colour_from_display(colour: str) -> str:
    """Make the display accent richer for lighting, retaining its OKLCH hue.

    Operates on the *final display colour*, never on independently selected
    artwork pixels. Near-neutral colours remain neutral.
    """
    red, green, blue = rgb_from_hex(colour)
    lightness, a, b = _to_oklab(red, green, blue)
    chroma = hypot(a, b)
    if chroma < 0.035:
        return colour.lower()
    hue = atan2(b, a)
    # Stronger chroma for muted colours, with a smooth saturation ceiling.
    # Darken moderately to reduce the washed-out appearance of RGB lighting.
    target_chroma = _clamp(chroma * (1.0 + 0.75 * (1.0 - min(chroma / 0.25, 1.0))), chroma, 0.24)
    target_lightness = _clamp(lightness - 0.075, 0.32, 0.78)
    return _from_oklch(target_lightness, target_chroma, hue)
