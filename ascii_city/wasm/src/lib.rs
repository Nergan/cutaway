//! The same grid walk the TypeScript raycaster uses for each screen column.
//!
//! Painting stays in TypeScript. This only answers which cells a ray hits,
//! because that walk runs once per column per frame. The exports are a plain
//! C ABI so the page can load the wasm without a binding generator.

use std::sync::Mutex;

const SOLID_BUILDING: u8 = 1;
const SOLID_WATER: u8 = 2;
const SOLID_BLOCKED: u8 = 3;
const STRIDE: usize = 8;
const MAX_HITS: usize = 16;

struct Grid {
    cells: Vec<u8>,
    heights: Vec<u8>,
    styles: Vec<u8>,
    width: i32,
    height: i32,
    cell_size: f64,
    floor_step: f64,
    ready: bool,
    out: [f64; MAX_HITS * STRIDE],
}

fn grid() -> std::sync::MutexGuard<'static, Grid> {
    static GRID: Mutex<Grid> = Mutex::new(Grid {
        cells: Vec::new(),
        heights: Vec::new(),
        styles: Vec::new(),
        width: 0,
        height: 0,
        cell_size: 2.0,
        floor_step: 0.25,
        ready: false,
        out: [0.0; MAX_HITS * STRIDE],
    });
    GRID.lock().unwrap_or_else(|poison| poison.into_inner())
}

#[no_mangle]
pub extern "C" fn prepare(count: u32) -> *mut u8 {
    let mut grid = grid();
    let count = count as usize;
    grid.cells.resize(count, 0);
    grid.heights.resize(count, 0);
    grid.styles.resize(count, 0);
    grid.ready = false;
    grid.cells.as_mut_ptr()
}

#[no_mangle]
pub extern "C" fn heights_ptr() -> *mut u8 {
    grid().heights.as_mut_ptr()
}

#[no_mangle]
pub extern "C" fn styles_ptr() -> *mut u8 {
    grid().styles.as_mut_ptr()
}

#[no_mangle]
pub extern "C" fn bind_grid(width: i32, height: i32, cell_size: f64, floor_step: f64) {
    let mut grid = grid();
    grid.width = width;
    grid.height = height;
    grid.cell_size = cell_size;
    grid.floor_step = floor_step;
    grid.ready = true;
}

#[no_mangle]
pub extern "C" fn out_ptr() -> *mut f64 {
    grid().out.as_mut_ptr()
}

/// Writes up to `layers` hits into the buffer from `out_ptr` as groups of eight
/// numbers: distance, height, style, side, cell x, cell y, ledge (1 or 0), along.
#[no_mangle]
pub extern "C" fn cast(
    origin_x: f64,
    origin_y: f64,
    ray_x: f64,
    ray_y: f64,
    max_cells: f64,
    layers: u32,
) -> u32 {
    let mut grid = grid();
    if !grid.ready {
        return 0;
    }
    let pos_x = origin_x / grid.cell_size;
    let pos_y = origin_y / grid.cell_size;
    let mut map_x = pos_x.floor() as i32;
    let mut map_y = pos_y.floor() as i32;

    let delta_x = if ray_x == 0.0 { f64::INFINITY } else { (1.0 / ray_x).abs() };
    let delta_y = if ray_y == 0.0 { f64::INFINITY } else { (1.0 / ray_y).abs() };
    let step_x: i32 = if ray_x < 0.0 { -1 } else { 1 };
    let step_y: i32 = if ray_y < 0.0 { -1 } else { 1 };
    let mut side_x = if ray_x < 0.0 {
        (pos_x - map_x as f64) * delta_x
    } else {
        (map_x as f64 + 1.0 - pos_x) * delta_x
    };
    let mut side_y = if ray_y < 0.0 {
        (pos_y - map_y as f64) * delta_y
    } else {
        (map_y as f64 + 1.0 - pos_y) * delta_y
    };

    let mut found = 0u32;
    let mut ground_along = floor_at(&grid, map_x, map_y);
    let room = (layers as usize).min(MAX_HITS);

    for _ in 0..2048 {
        let side = if side_x < side_y {
            side_x += delta_x;
            map_x += step_x;
            0
        } else {
            side_y += delta_y;
            map_y += step_y;
            1
        };
        let travelled = if side == 0 { side_x - delta_x } else { side_y - delta_y };
        if travelled > max_cells {
            break;
        }
        if map_x < -1 || map_y < -1 || map_x > grid.width || map_y > grid.height {
            break;
        }

        let solid = is_solid(&grid, map_x, map_y);
        let ledge_top = if solid {
            0.0
        } else {
            let floor = floor_at(&grid, map_x, map_y);
            if floor <= ground_along + 0.01 {
                ground_along = floor;
                continue;
            }
            ground_along = floor;
            floor
        };

        let mut distance = travelled * grid.cell_size;
        if distance < 0.01 {
            distance = 0.01;
        }
        let height = if solid {
            f64::from(height_at(&grid, map_x, map_y).max(1))
        } else {
            ledge_top
        };
        let along = if side == 0 {
            origin_y + ray_y * distance
        } else {
            origin_x + ray_x * distance
        };
        let at = found as usize * STRIDE;
        grid.out[at] = distance;
        grid.out[at + 1] = height;
        grid.out[at + 2] = f64::from(style_at(&grid, map_x, map_y));
        grid.out[at + 3] = f64::from(side);
        grid.out[at + 4] = f64::from(map_x);
        grid.out[at + 5] = f64::from(map_y);
        grid.out[at + 6] = if solid { 0.0 } else { 1.0 };
        grid.out[at + 7] = along;
        found += 1;

        if found as usize >= room {
            break;
        }
        if !solid {
            continue;
        }
        if height > 200.0 && distance < 6.0 {
            break;
        }
    }
    found
}

fn index(grid: &Grid, cx: i32, cy: i32) -> Option<usize> {
    if cx < 0 || cy < 0 || cx >= grid.width || cy >= grid.height {
        return None;
    }
    Some((cy as usize) * (grid.width as usize) + (cx as usize))
}

fn code_at(grid: &Grid, cx: i32, cy: i32) -> u8 {
    index(grid, cx, cy).map(|at| grid.cells[at]).unwrap_or(SOLID_BLOCKED)
}

fn is_solid(grid: &Grid, cx: i32, cy: i32) -> bool {
    matches!(code_at(grid, cx, cy), SOLID_BUILDING | SOLID_WATER | SOLID_BLOCKED)
}

fn height_at(grid: &Grid, cx: i32, cy: i32) -> u8 {
    index(grid, cx, cy).map(|at| grid.heights.get(at).copied().unwrap_or(0)).unwrap_or(0)
}

fn style_at(grid: &Grid, cx: i32, cy: i32) -> u8 {
    index(grid, cx, cy).map(|at| grid.styles.get(at).copied().unwrap_or(0)).unwrap_or(0)
}

fn floor_at(grid: &Grid, cx: i32, cy: i32) -> f64 {
    if is_solid(grid, cx, cy) {
        0.0
    } else {
        f64::from(height_at(grid, cx, cy)) * grid.floor_step
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_wall_to_the_east_is_the_first_hit() {
        let count = 16u32;
        let cells = prepare(count);
        unsafe {
            std::ptr::write_bytes(cells, 0, count as usize);
            *cells.add(1) = SOLID_BUILDING;
            std::ptr::write_bytes(heights_ptr(), 12, count as usize);
            std::ptr::write_bytes(styles_ptr(), 4, count as usize);
        }
        bind_grid(4, 4, 2.0, 0.25);
        let found = cast(1.0, 1.0, 1.0, 0.0, 20.0, 2);
        assert!(found >= 1);
        let out = unsafe { std::slice::from_raw_parts(out_ptr(), 8) };
        assert_eq!(out[4] as i32, 1);
        assert_eq!(out[5] as i32, 0);
        assert_eq!(out[1], 12.0);
        assert_eq!(out[2], 4.0);
        assert_eq!(out[6], 0.0);
    }
}
