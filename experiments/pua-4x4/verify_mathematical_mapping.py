#!/usr/bin/env python3
"""Independent exhaustive proof of the agreed PUA 4x4 mathematics.

This verifier intentionally defines its own oracle formulas.  It then compares
the project implementation with that oracle.  It does not inspect or generate
font outlines, select a runtime font, or claim that terminal raster output is
correct.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


P0_BASE = 0xF0000
P1_BASE = 0x100000
PART_SIZE = 0x8000
MASK_LIMIT = 0x10000
GRID = 4


def oracle_address(vx: int, vy: int) -> dict[str, int]:
    """Translate a zero-based virtual pixel to terminal and bit coordinates."""
    if vx < 0 or vy < 0:
        raise ValueError("virtual coordinates must be non-negative")
    terminal_column, local_x = divmod(vx, GRID)
    terminal_row, local_y = divmod(vy, GRID)
    bit_position = GRID * local_y + (GRID - 1 - local_x)
    return {
        "virtual_x": vx,
        "virtual_y": vy,
        "terminal_column_zero_based": terminal_column,
        "terminal_row_zero_based": terminal_row,
        "ansi_column_one_based": terminal_column + 1,
        "ansi_row_one_based": terminal_row + 1,
        "local_x": local_x,
        "local_y": local_y,
        "bit_position": bit_position,
        "bit_value": 1 << bit_position,
    }


def oracle_local_from_bit(bit_position: int) -> tuple[int, int]:
    """Reverse one bit number to (local_x, local_y)."""
    if not 0 <= bit_position < 16:
        raise ValueError("bit position must be in the range 0..15")
    local_y, numeric_column = divmod(bit_position, GRID)
    local_x = GRID - 1 - numeric_column
    return local_x, local_y


def oracle_virtual_from_bit(
    terminal_column: int, terminal_row: int, bit_position: int
) -> tuple[int, int]:
    """Reverse a terminal cell and bit number to a virtual coordinate."""
    if terminal_column < 0 or terminal_row < 0:
        raise ValueError("terminal coordinates must be non-negative")
    local_x, local_y = oracle_local_from_bit(bit_position)
    return (
        GRID * terminal_column + local_x,
        GRID * terminal_row + local_y,
    )


def oracle_codepoint(mask: int) -> int:
    """Map an unsigned 16-bit mask into the agreed P0/P1 ranges."""
    if not 0 <= mask < MASK_LIMIT:
        raise ValueError("mask must be in the range 0x0000..0xFFFF")
    if mask < PART_SIZE:
        return P0_BASE + mask
    return P1_BASE + (mask - PART_SIZE)


def oracle_mask(codepoint: int) -> int:
    """Reverse either agreed PUA range into its complete 16-bit mask."""
    if P0_BASE <= codepoint < P0_BASE + PART_SIZE:
        return codepoint - P0_BASE
    if P1_BASE <= codepoint < P1_BASE + PART_SIZE:
        return PART_SIZE + (codepoint - P1_BASE)
    raise ValueError("codepoint is outside the agreed PUA 4x4 ranges")


def oracle_mask_from_local_pixels(pixels: set[tuple[int, int]]) -> int:
    mask = 0
    for local_x, local_y in pixels:
        if not (0 <= local_x < GRID and 0 <= local_y < GRID):
            raise ValueError("local coordinates must be in the range 0..3")
        mask |= 1 << (GRID * local_y + (GRID - 1 - local_x))
    return mask


def oracle_local_pixels_from_mask(mask: int) -> set[tuple[int, int]]:
    if not 0 <= mask < MASK_LIMIT:
        raise ValueError("mask must be in the range 0x0000..0xFFFF")
    return {
        oracle_local_from_bit(bit)
        for bit in range(16)
        if mask & (1 << bit)
    }


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bitmap(mask: int) -> list[str]:
    pixels = oracle_local_pixels_from_mask(mask)
    return [
        "".join("#" if (x, y) in pixels else "." for x in range(4))
        for y in range(4)
    ]


def one_bit_records() -> list[dict[str, object]]:
    records = []
    for local_y in range(4):
        for local_x in range(4):
            bit = 4 * local_y + (3 - local_x)
            mask = 1 << bit
            codepoint = oracle_codepoint(mask)
            reverse_x, reverse_y = oracle_local_from_bit(bit)
            assert (reverse_x, reverse_y) == (local_x, local_y)
            assert oracle_mask(codepoint) == mask
            records.append(
                {
                    "local_x": local_x,
                    "local_y": local_y,
                    "bit_position": bit,
                    "bit_value_decimal": mask,
                    "mask_hex": f"0x{mask:04X}",
                    "part": 0 if mask < PART_SIZE else 1,
                    "codepoint_hex": f"U+{codepoint:06X}",
                    "reverse_local_x": reverse_x,
                    "reverse_local_y": reverse_y,
                }
            )
    return records


def boundary_records() -> list[dict[str, object]]:
    records = []
    for mask in (0x0000, 0x0001, 0x0008, 0x0400, 0x7FFE, 0x7FFF,
                 0x8000, 0x8001, 0x9669, 0xFFFE, 0xFFFF):
        codepoint = oracle_codepoint(mask)
        reverse = oracle_mask(codepoint)
        assert reverse == mask
        records.append(
            {
                "mask_decimal": mask,
                "mask_hex": f"0x{mask:04X}",
                "binary_msb_to_lsb": f"{mask:016b}",
                "part": 0 if mask < PART_SIZE else 1,
                "codepoint_hex": f"U+{codepoint:06X}",
                "reverse_mask_hex": f"0x{reverse:04X}",
                "bitmap": bitmap(mask),
            }
        )
    return records


def verify_virtual_round_trips(columns: int, rows: int) -> int:
    count = 0
    for vy in range(rows * GRID):
        for vx in range(columns * GRID):
            address = oracle_address(vx, vy)
            reverse = oracle_virtual_from_bit(
                address["terminal_column_zero_based"],
                address["terminal_row_zero_based"],
                address["bit_position"],
            )
            assert reverse == (vx, vy), (vx, vy, address, reverse)
            count += 1
    return count


def verify_all_masks() -> tuple[int, int, int]:
    codepoints = set()
    boolean_cases = 0
    for mask in range(MASK_LIMIT):
        codepoint = oracle_codepoint(mask)
        assert oracle_mask(codepoint) == mask
        codepoints.add(codepoint)

        pixels = oracle_local_pixels_from_mask(mask)
        assert oracle_mask_from_local_pixels(pixels) == mask

        for bit in range(16):
            value = 1 << bit
            set_mask = mask | value
            clear_mask = mask & ~value & 0xFFFF
            toggle_mask = mask ^ value
            assert set_mask & value
            assert not (clear_mask & value)
            assert bool(toggle_mask & value) != bool(mask & value)
            assert (set_mask & ~value) == (mask & ~value)
            assert (clear_mask & ~value) == (mask & ~value)
            assert (toggle_mask & ~value) == (mask & ~value)
            boolean_cases += 3
    assert len(codepoints) == MASK_LIMIT
    p0 = sum(P0_BASE <= cp < P0_BASE + PART_SIZE for cp in codepoints)
    p1 = sum(P1_BASE <= cp < P1_BASE + PART_SIZE for cp in codepoints)
    assert (p0, p1) == (PART_SIZE, PART_SIZE)
    return len(codepoints), p0, boolean_cases


def verify_project_implementation(root: Path) -> dict[str, int]:
    authoritative = load_module(root / "pua4x4.py", "project_pua4x4")
    backend = load_module(
        root / "demos4x4" / "pua4x4_backend.py", "project_pua4x4_backend"
    )

    local_cases = 0
    for local_y in range(4):
        for local_x in range(4):
            expected = 4 * local_y + (3 - local_x)
            assert authoritative.bit_for_cell(local_y, local_x) == expected
            assert backend.DOT_BIT[local_y][local_x] == expected
            assert backend.DOT_WEIGHTS[local_y][local_x] == 1 << expected
            local_cases += 1

    mask_cases = 0
    for mask in range(MASK_LIMIT):
        expected_cp = oracle_codepoint(mask)
        assert authoritative.mask_to_codepoint(mask) == expected_cp
        assert backend.mask_to_codepoint(mask) == expected_cp
        assert authoritative.codepoint_to_mask(expected_cp) == mask
        assert backend.codepoint_to_mask(expected_cp) == mask
        mask_cases += 1

    return {
        "local_position_cases": local_cases,
        "complete_mask_cases": mask_cases,
        "functions_compared_per_mask": 4,
    }


def verify_triangle_mapping(root: Path) -> dict[str, int]:
    demo_dir = root / "demos4x4"
    sys.path.insert(0, str(demo_dir))
    try:
        triangle = load_module(demo_dir / "triangle.py", "project_triangle")
    finally:
        sys.path.pop(0)

    width, height = 320, 160
    points = triangle.triangle_pixels(width, height)
    expected_pixels = {coordinate for coordinate, _ in points}
    masks: dict[tuple[int, int], int] = {}
    for vx, vy in expected_pixels:
        address = oracle_address(vx, vy)
        cell = (
            address["terminal_column_zero_based"],
            address["terminal_row_zero_based"],
        )
        masks[cell] = masks.get(cell, 0) | address["bit_value"]

    decoded_pixels = set()
    for (terminal_column, terminal_row), mask in masks.items():
        for bit in range(16):
            if mask & (1 << bit):
                decoded_pixels.add(
                    oracle_virtual_from_bit(terminal_column, terminal_row, bit)
                )

    missing = expected_pixels - decoded_pixels
    unexpected = decoded_pixels - expected_pixels
    assert not missing and not unexpected
    return {
        "triangle_virtual_pixels": len(expected_pixels),
        "nonempty_terminal_cells": len(masks),
        "missing_after_decode": len(missing),
        "unexpected_after_decode": len(unexpected),
    }


def write_one_bit_csv(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--columns", type=int, default=80)
    parser.add_argument("--rows", type=int, default=24)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=root / "output" / "audit" / "pua4x4-mathematics-proof-v1.0.json",
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        default=root / "output" / "audit" / "pua4x4-one-bit-table-v1.0.csv",
    )
    args = parser.parse_args()
    if args.columns <= 0 or args.rows <= 0:
        parser.error("columns and rows must be positive")

    one_bits = one_bit_records()
    boundaries = boundary_records()
    virtual_cases = verify_virtual_round_trips(args.columns, args.rows)
    unique_codepoints, per_part, boolean_cases = verify_all_masks()
    implementation = verify_project_implementation(root)
    triangle = verify_triangle_mapping(root)

    worked = oracle_address(13, 10)
    worked_mask = worked["bit_value"]
    worked_codepoint = oracle_codepoint(worked_mask)
    assert worked["terminal_column_zero_based"] == 3
    assert worked["terminal_row_zero_based"] == 2
    assert worked["ansi_column_one_based"] == 4
    assert worked["ansi_row_one_based"] == 3
    assert worked["local_x"] == 1 and worked["local_y"] == 2
    assert worked["bit_position"] == 10
    assert worked_mask == 0x0400
    assert worked_codepoint == 0xF0400

    corners_and_center = {
        (0, 0), (3, 0), (1, 1), (2, 1),
        (1, 2), (2, 2), (0, 3), (3, 3),
    }
    example_mask = oracle_mask_from_local_pixels(corners_and_center)
    assert example_mask == 0x9669
    assert oracle_codepoint(example_mask) == 0x101669

    report = {
        "document_scope": "mathematics and source-code mapping only; no font claim",
        "status": "PASS_MATHEMATICS_ONLY",
        "authoritative_layout": [
            [3, 2, 1, 0],
            [7, 6, 5, 4],
            [11, 10, 9, 8],
            [15, 14, 13, 12],
        ],
        "bit_label_order_msb_to_lsb": "fedcba9876543210",
        "formulas": {
            "terminal_cell_zero_based": "cx = vx // 4; cy = vy // 4",
            "ansi_cursor_one_based": "column = cx + 1; row = cy + 1",
            "local_coordinate": "lx = vx % 4; ly = vy % 4",
            "bit_position": "b = 4 * ly + (3 - lx)",
            "bit_value": "v = 1 << b",
            "aggregate_mask": "M = bitwise OR of all v in one terminal cell",
            "P0": "M < 0x8000: cp = 0xF0000 + M",
            "P1": "M >= 0x8000: cp = 0x100000 + (M - 0x8000)",
            "reverse_P0": "M = cp - 0xF0000",
            "reverse_P1": "M = 0x8000 + (cp - 0x100000)",
            "reverse_local": "ly = b // 4; lx = 3 - (b % 4)",
            "reverse_virtual": "vx = 4 * cx + lx; vy = 4 * cy + ly",
        },
        "worked_example_v13_v10": {
            **worked,
            "mask_hex": f"0x{worked_mask:04X}",
            "codepoint_hex": f"U+{worked_codepoint:06X}",
            "reverse_mask_hex": f"0x{oracle_mask(worked_codepoint):04X}",
            "reverse_virtual": list(
                oracle_virtual_from_bit(
                    worked["terminal_column_zero_based"],
                    worked["terminal_row_zero_based"],
                    worked["bit_position"],
                )
            ),
        },
        "worked_example_corners_and_center": {
            "local_pixels": sorted([list(value) for value in corners_and_center]),
            "mask_hex": f"0x{example_mask:04X}",
            "binary_msb_to_lsb": f"{example_mask:016b}",
            "codepoint_hex": f"U+{oracle_codepoint(example_mask):06X}",
            "bitmap": bitmap(example_mask),
        },
        "one_bit_records": one_bits,
        "boundary_records": boundaries,
        "test_counts": {
            "local_one_bit_round_trips": len(one_bits),
            "virtual_round_trips": virtual_cases,
            "terminal_dimensions": [args.columns, args.rows],
            "virtual_dimensions": [args.columns * 4, args.rows * 4],
            "all_masks_round_tripped": MASK_LIMIT,
            "unique_codepoints": unique_codepoints,
            "codepoints_per_part": per_part,
            "boolean_operation_assertions": boolean_cases,
            "project_implementation": implementation,
            "triangle_mapping": triangle,
        },
        "observed_runtime_status": {
            "result": "FAIL_NOT_EXPLAINED_BY_MATHEMATICS_GATE",
            "observation": (
                "The supplied Linux triangle screenshots show periodic detached "
                "or discontinuous marks on the left edge and visible terminal-cell seams."
            ),
            "conclusion": (
                "The current visual output is not accepted. Font-outline, runtime "
                "selection, shaping, fixed-cell placement and raster repaint remain "
                "separate unpassed gates."
            ),
        },
    }

    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_one_bit_csv(args.csv_output, one_bits)

    print("PASS: authoritative 16-position MSB-left table")
    print(f"PASS: {virtual_cases:,} virtual-coordinate round trips")
    print(f"PASS: {MASK_LIMIT:,} mask/codepoint/mask round trips")
    print(f"PASS: {unique_codepoints:,} unique codepoints ({per_part:,} per part)")
    print(f"PASS: {boolean_cases:,} OR/AND-NOT/XOR assertions")
    print(
        "PASS: project mapping functions match the independent oracle for "
        f"{implementation['complete_mask_cases']:,} masks"
    )
    print(
        "PASS: triangle masks decode to the same "
        f"{triangle['triangle_virtual_pixels']:,} virtual pixels"
    )
    print("FAIL (recorded, not waived): observed terminal triangle output")
    print(args.json_output)
    print(args.csv_output)
    print("evidence_sha256", sha256(args.json_output))


if __name__ == "__main__":
    main()
