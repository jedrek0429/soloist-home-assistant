"""Standalone tests for the Soloist Display colour port (no HA import needed)."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "soloist"
    / "artwork_colour.py"
)
spec = importlib.util.spec_from_file_location("artwork_colour", SOURCE)
assert spec is not None and spec.loader is not None
colours = importlib.util.module_from_spec(spec)
spec.loader.exec_module(colours)


def solid(red: int, green: int, blue: int, *, alpha: int = 255) -> bytes:
    return bytes((red, green, blue, alpha)) * (64 * 64)


class ArtworkColourTests(unittest.TestCase):
    def test_missing_pixels(self) -> None:
        self.assertIsNone(colours.dominant_colour_from_pixels(b"", 64, 64))

    def test_transparent_artwork(self) -> None:
        self.assertIsNone(
            colours.dominant_colour_from_pixels(
                solid(255, 0, 0, alpha=0), 64, 64
            )
        )

    def test_saturated_red_is_red(self) -> None:
        colour = colours.dominant_colour_from_pixels(solid(255, 0, 0), 64, 64)
        self.assertIsNotNone(colour)
        red, green, blue = colours.rgb_from_hex(colour)
        self.assertGreater(red, green + 40)
        self.assertGreater(red, blue + 40)

    def test_saturated_blue_is_blue(self) -> None:
        colour = colours.dominant_colour_from_pixels(solid(0, 0, 255), 64, 64)
        self.assertIsNotNone(colour)
        red, green, blue = colours.rgb_from_hex(colour)
        self.assertGreater(blue, red + 40)
        self.assertGreater(blue, green + 40)

    def test_monochrome_artwork_yields_restrained_neutral(self) -> None:
        colour = colours.dominant_colour_from_pixels(solid(128, 128, 128), 64, 64)
        self.assertIsNotNone(colour)
        rgb = colours.rgb_from_hex(colour)
        self.assertLess(max(rgb) - min(rgb), 30)

    def test_alpha_and_output_are_deterministic(self) -> None:
        pixels = solid(25, 180, 150)
        result = colours.dominant_colour_from_pixels(pixels, 64, 64)
        self.assertEqual(result, colours.dominant_colour_from_pixels(pixels, 64, 64))
        self.assertRegex(result, r"^#[0-9a-f]{6}$")

    def test_rgb_parser(self) -> None:
        self.assertEqual(colours.rgb_from_hex("#a105ff"), (161, 5, 255))


if __name__ == "__main__":
    unittest.main()
