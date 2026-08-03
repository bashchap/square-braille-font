#!/usr/bin/env python3
"""Display corresponding Unicode Braille and compatibility PUA glyphs."""

print("Offset   Unicode Braille        PUA alias")
for row in range(16):
    offset = row * 16
    unicode_run = "".join(chr(0x2800 + offset + column) for column in range(16))
    pua_run = "".join(chr(0xE000 + offset + column) for column in range(16))
    print(f"{offset:02X}       {unicode_run}    {pua_run}")
