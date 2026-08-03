#!/usr/bin/env python3
"""Hold a deterministic PUA glyph test on screen for GUI verification."""

import time


patterns = (0x00, 0x01, 0x08, 0x09, 0x03, 0x18, 0x81, 0xFF)
glyphs = " ".join(chr(0xE000 + value) for value in patterns)
print("PUA Square Braille terminal probe")
print("Masks: 00 01 08 09 03 18 81 FF")
for _ in range(5):
    print(glyphs)
print("This window closes automatically after 20 seconds.")
time.sleep(20)
