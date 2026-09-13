//! Dependency-free cell analysis and terminal emission for the demo suite.
//!
//! Python retains scene ownership. Rust performs the hot per-cell priority,
//! colour-average and reconstruction-error scan for the seasonal renderer and
//! complete UTF-8/ANSI emission for the shared legacy framebuffer path.

use std::fmt::Write;

fn mapped_character(mask: u16, mapping: u8) -> Option<char> {
    let codepoint = match mapping {
        0 => 0xE000 + u32::from(mask),
        1 => 0x2800 + u32::from(mask),
        2 if mask < 0x8000 => 0xF0000 + u32::from(mask),
        2 => 0x100000 + u32::from(mask - 0x8000),
        _ => return None,
    };
    char::from_u32(codepoint)
}

/// Encode an already rasterised mask/colour framebuffer to UTF-8 ANSI text.
///
/// Mapping 0 is the U+E000 Square alias, 1 is official Braille U+2800 and 2
/// is the two-font PUA 4x4 split. Colour mode 0 accepts packed 0xRRGGBB,
/// mode 1 accepts an ANSI-256 index and mode 2 suppresses colour control. A
/// non-zero blank_glyph emits the
/// mapping's zero-mask character; otherwise blank cells are spaces.
#[no_mangle]
pub unsafe extern "C" fn encode_terminal_cells(
    masks: *const u16,
    colours: *const u32,
    columns: usize,
    rows: usize,
    mapping: u8,
    colour_mode: u8,
    blank_glyph: u8,
    carriage_return: u8,
    reset_at_end: u8,
    output: *mut u8,
    capacity: usize,
) -> usize {
    if masks.is_null()
        || colours.is_null()
        || columns == 0
        || rows == 0
        || mapping > 2
        || colour_mode > 2
    {
        return 0;
    }
    let count = match columns.checked_mul(rows) {
        Some(value) => value,
        None => return 0,
    };
    let masks = std::slice::from_raw_parts(masks, count);
    let colours = std::slice::from_raw_parts(colours, count);
    let mut text = String::with_capacity(count.saturating_mul(8));
    let mut active: Option<u32> = None;
    for row in 0..rows {
        for column in 0..columns {
            let index = row * columns + column;
            let mask = masks[index];
            if mask != 0 && colour_mode != 2 {
                let colour = colours[index];
                if active != Some(colour) {
                    if colour_mode == 0 {
                        let _ = write!(
                            text,
                            "\x1b[38;2;{};{};{}m",
                            (colour >> 16) & 255,
                            (colour >> 8) & 255,
                            colour & 255
                        );
                    } else if colour_mode == 1 {
                        let _ = write!(text, "\x1b[38;5;{}m", colour & 255);
                    }
                    active = Some(colour);
                }
            } else if (mask == 0 || colour_mode == 2) && active.is_some() {
                text.push_str("\x1b[39m");
                active = None;
            }
            if mask == 0 && blank_glyph == 0 {
                text.push(' ');
            } else if let Some(character) = mapped_character(mask, mapping) {
                text.push(character);
            } else {
                return 0;
            }
        }
        if row + 1 < rows {
            if carriage_return != 0 {
                text.push('\r');
            }
            text.push('\n');
        }
    }
    if reset_at_end != 0 && active.is_some() {
        text.push_str("\x1b[39m");
    }
    let required = text.len();
    if output.is_null() || capacity < required {
        return required;
    }
    std::ptr::copy_nonoverlapping(text.as_ptr(), output, required);
    required
}

/// Encode a two-colour cell framebuffer used by the layered Voyager renderer.
#[no_mangle]
pub unsafe extern "C" fn encode_terminal_cells_v2(
    masks: *const u16,
    foreground: *const u32,
    background: *const u32,
    flags: *const u8,
    columns: usize,
    rows: usize,
    mapping: u8,
    output: *mut u8,
    capacity: usize,
) -> usize {
    if masks.is_null()
        || foreground.is_null()
        || background.is_null()
        || flags.is_null()
        || columns == 0
        || rows == 0
        || mapping > 2
    {
        return 0;
    }
    let count = match columns.checked_mul(rows) {
        Some(value) => value,
        None => return 0,
    };
    let masks = std::slice::from_raw_parts(masks, count);
    let foreground = std::slice::from_raw_parts(foreground, count);
    let background = std::slice::from_raw_parts(background, count);
    let flags = std::slice::from_raw_parts(flags, count);
    let mut text = String::with_capacity(count.saturating_mul(10));
    let mut active_foreground: Option<u32> = None;
    let mut active_background: Option<u32> = None;
    for row in 0..rows {
        for column in 0..columns {
            let index = row * columns + column;
            let mask = masks[index];
            if mask != 0 {
                let colour = foreground[index];
                if active_foreground != Some(colour) {
                    let _ = write!(
                        text,
                        "\x1b[38;2;{};{};{}m",
                        (colour >> 16) & 255,
                        (colour >> 8) & 255,
                        colour & 255
                    );
                    active_foreground = Some(colour);
                }
            } else if active_foreground.is_some() {
                text.push_str("\x1b[39m");
                active_foreground = None;
            }
            let cell_background = if flags[index] & 1 != 0 {
                Some(background[index])
            } else {
                None
            };
            if cell_background != active_background {
                match cell_background {
                    Some(colour) => {
                        let _ = write!(
                            text,
                            "\x1b[48;2;{};{};{}m",
                            (colour >> 16) & 255,
                            (colour >> 8) & 255,
                            colour & 255
                        );
                    }
                    None => text.push_str("\x1b[49m"),
                }
                active_background = cell_background;
            }
            if mask == 0 {
                text.push(' ');
            } else if let Some(character) = mapped_character(mask, mapping) {
                text.push(character);
            } else {
                return 0;
            }
        }
        text.push_str("\x1b[0m");
        active_foreground = None;
        active_background = None;
        if row + 1 < rows {
            text.push('\n');
        }
    }
    let required = text.len();
    if output.is_null() || capacity < required {
        return required;
    }
    std::ptr::copy_nonoverlapping(text.as_ptr(), output, required);
    required
}

#[no_mangle]
pub unsafe extern "C" fn analyse_cells(
    colours: *const u32,
    priorities: *const u8,
    surface_width: usize,
    columns: usize,
    rows: usize,
    cell_width: usize,
    cell_height: usize,
    bits: *const u8,
    output: *mut u8,
) -> usize {
    if colours.is_null()
        || priorities.is_null()
        || bits.is_null()
        || output.is_null()
        || cell_width == 0
        || cell_height == 0
        || cell_width * cell_height > 16
    {
        return 0;
    }
    let sample_count = cell_width * cell_height;
    let bit_map = std::slice::from_raw_parts(bits, sample_count);
    let out = std::slice::from_raw_parts_mut(output, columns * rows * 10);
    for cell_y in 0..rows {
        for cell_x in 0..columns {
            let output_index = (cell_y * columns + cell_x) * 10;
            let mut front_priority = 0u8;
            for local_y in 0..cell_height {
                let start = (cell_y * cell_height + local_y) * surface_width + cell_x * cell_width;
                for local_x in 0..cell_width {
                    front_priority = front_priority.max(*priorities.add(start + local_x));
                }
            }
            if front_priority == 0 {
                out[output_index..output_index + 10].fill(0);
                continue;
            }
            let mut mask = 0u16;
            let (mut fr, mut fg, mut fb, mut fc) = (0u32, 0u32, 0u32, 0u32);
            let (mut rr, mut rg, mut rb, mut rc) = (0u32, 0u32, 0u32, 0u32);
            let mut sample = 0usize;
            for local_y in 0..cell_height {
                let start = (cell_y * cell_height + local_y) * surface_width + cell_x * cell_width;
                for local_x in 0..cell_width {
                    let index = start + local_x;
                    let priority = *priorities.add(index);
                    if priority != 0 {
                        let colour = *colours.add(index);
                        let r = (colour >> 16) & 255;
                        let g = (colour >> 8) & 255;
                        let b = colour & 255;
                        if priority == front_priority {
                            mask |= 1u16 << bit_map[sample];
                            fr += r;
                            fg += g;
                            fb += b;
                            fc += 1;
                        } else {
                            rr += r;
                            rg += g;
                            rb += b;
                            rc += 1;
                        }
                    }
                    sample += 1;
                }
            }
            let rounded = |sum: u32, count: u32| -> u8 { ((sum + count / 2) / count) as u8 };
            let front = (rounded(fr, fc), rounded(fg, fc), rounded(fb, fc));
            let mut rear = (0u8, 0u8, 0u8);
            let mut rear_valid = false;
            if rc > 0 && fc < sample_count as u32 {
                rear = (rounded(rr, rc), rounded(rg, rc), rounded(rb, rc));
                let (mut without, mut with) = (0i64, 0i64);
                for local_y in 0..cell_height {
                    let start =
                        (cell_y * cell_height + local_y) * surface_width + cell_x * cell_width;
                    for local_x in 0..cell_width {
                        let index = start + local_x;
                        let priority = *priorities.add(index);
                        let colour = *colours.add(index);
                        let expected = if priority == 0 {
                            (0, 0, 0)
                        } else {
                            (
                                ((colour >> 16) & 255) as i32,
                                ((colour >> 8) & 255) as i32,
                                (colour & 255) as i32,
                            )
                        };
                        let no = if priority == front_priority {
                            (front.0 as i32, front.1 as i32, front.2 as i32)
                        } else {
                            (0, 0, 0)
                        };
                        let yes = if priority == front_priority {
                            no
                        } else {
                            (rear.0 as i32, rear.1 as i32, rear.2 as i32)
                        };
                        for (actual_no, actual_yes, wanted) in [
                            (no.0, yes.0, expected.0),
                            (no.1, yes.1, expected.1),
                            (no.2, yes.2, expected.2),
                        ] {
                            without += i64::from((wanted - actual_no).pow(2));
                            with += i64::from((wanted - actual_yes).pow(2));
                        }
                    }
                }
                rear_valid = with < without;
            }
            out[output_index] = mask as u8;
            out[output_index + 1] = (mask >> 8) as u8;
            out[output_index + 2] = front.0 & !3;
            out[output_index + 3] = front.1 & !3;
            out[output_index + 4] = front.2 & !3;
            out[output_index + 5] = rear.0 & !3;
            out[output_index + 6] = rear.1 & !3;
            out[output_index + 7] = rear.2 & !3;
            out[output_index + 8] = u8::from(rear_valid);
            out[output_index + 9] = 1;
        }
    }
    columns * rows
}

#[cfg(test)]
mod tests {
    use super::{analyse_cells, encode_terminal_cells, encode_terminal_cells_v2};

    #[test]
    fn finds_front_mask_and_rear_colour() {
        let colours = [0x00ff0000u32, 0x000000ff, 0, 0];
        let priorities = [8u8, 3, 0, 0];
        let bits = [0u8, 1, 2, 3];
        let mut output = [0u8; 10];
        let count = unsafe {
            analyse_cells(
                colours.as_ptr(),
                priorities.as_ptr(),
                2,
                1,
                1,
                2,
                2,
                bits.as_ptr(),
                output.as_mut_ptr(),
            )
        };
        assert_eq!(count, 1);
        assert_eq!(output[0], 1);
        assert_eq!(&output[2..5], &[252, 0, 0]);
    }

    #[test]
    fn emits_square_and_pua4_utf8() {
        let masks = [1u16, 0, 0x8000, 0xffff];
        let colours = [0xff0000u32, 0, 0x00ff00, 0x00ff00];
        for mapping in [0u8, 2] {
            let mut output = [0u8; 256];
            let count = unsafe {
                encode_terminal_cells(
                    masks.as_ptr(),
                    colours.as_ptr(),
                    2,
                    2,
                    mapping,
                    0,
                    1,
                    0,
                    1,
                    output.as_mut_ptr(),
                    output.len(),
                )
            };
            let text = std::str::from_utf8(&output[..count]).unwrap();
            assert!(text.contains("\x1b[38;2;255;0;0m"));
            assert!(text.ends_with("\x1b[39m"));
        }
    }

    #[test]
    fn emits_two_colour_cells() {
        let masks = [1u16, 0];
        let foreground = [0xff0000u32, 0];
        let background = [0x0000ffu32, 0];
        let flags = [1u8, 0];
        let mut output = [0u8; 256];
        let count = unsafe {
            encode_terminal_cells_v2(
                masks.as_ptr(),
                foreground.as_ptr(),
                background.as_ptr(),
                flags.as_ptr(),
                2,
                1,
                1,
                output.as_mut_ptr(),
                output.len(),
            )
        };
        let text = std::str::from_utf8(&output[..count]).unwrap();
        assert!(text.contains("\x1b[48;2;0;0;255m"));
        assert!(text.ends_with("\x1b[0m"));
    }
}
