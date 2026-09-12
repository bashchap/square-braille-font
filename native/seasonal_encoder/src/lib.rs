//! Dependency-free cell analysis for the seasonal terminal renderer.
//!
//! Python retains scene ownership and ANSI generation. Rust performs the hot
//! per-cell priority, colour-average and reconstruction-error scan in one
//! bounds-checked batch call.

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
    if colours.is_null() || priorities.is_null() || bits.is_null() || output.is_null()
        || cell_width == 0 || cell_height == 0 || cell_width * cell_height > 16
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
                let start = (cell_y * cell_height + local_y) * surface_width
                    + cell_x * cell_width;
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
                let start = (cell_y * cell_height + local_y) * surface_width
                    + cell_x * cell_width;
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
                            fr += r; fg += g; fb += b; fc += 1;
                        } else {
                            rr += r; rg += g; rb += b; rc += 1;
                        }
                    }
                    sample += 1;
                }
            }
            let rounded = |sum: u32, count: u32| -> u8 {
                ((sum + count / 2) / count) as u8
            };
            let front = (rounded(fr, fc), rounded(fg, fc), rounded(fb, fc));
            let mut rear = (0u8, 0u8, 0u8);
            let mut rear_valid = false;
            if rc > 0 && fc < sample_count as u32 {
                rear = (rounded(rr, rc), rounded(rg, rc), rounded(rb, rc));
                let (mut without, mut with) = (0i64, 0i64);
                for local_y in 0..cell_height {
                    let start = (cell_y * cell_height + local_y) * surface_width
                        + cell_x * cell_width;
                    for local_x in 0..cell_width {
                        let index = start + local_x;
                        let priority = *priorities.add(index);
                        let colour = *colours.add(index);
                        let expected = if priority == 0 { (0, 0, 0) } else {
                            (((colour >> 16) & 255) as i32,
                             ((colour >> 8) & 255) as i32,
                             (colour & 255) as i32)
                        };
                        let no = if priority == front_priority {
                            (front.0 as i32, front.1 as i32, front.2 as i32)
                        } else { (0, 0, 0) };
                        let yes = if priority == front_priority { no } else {
                            (rear.0 as i32, rear.1 as i32, rear.2 as i32)
                        };
                        for (actual_no, actual_yes, wanted) in
                            [(no.0, yes.0, expected.0), (no.1, yes.1, expected.1),
                             (no.2, yes.2, expected.2)]
                        {
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
    use super::analyse_cells;

    #[test]
    fn finds_front_mask_and_rear_colour() {
        let colours = [0x00ff0000u32, 0x000000ff, 0, 0];
        let priorities = [8u8, 3, 0, 0];
        let bits = [0u8, 1, 2, 3];
        let mut output = [0u8; 10];
        let count = unsafe { analyse_cells(
            colours.as_ptr(), priorities.as_ptr(), 2, 1, 1, 2, 2,
            bits.as_ptr(), output.as_mut_ptr()) };
        assert_eq!(count, 1);
        assert_eq!(output[0], 1);
        assert_eq!(&output[2..5], &[252, 0, 0]);
    }
}
