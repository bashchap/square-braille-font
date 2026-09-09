local wezterm = require 'wezterm'
local config = wezterm.config_builder()

local function number_from_environment(name, fallback)
  local value = tonumber(os.getenv(name) or '')
  if value == nil then
    return fallback
  end
  return value
end

-- Load the repository copy directly.  This avoids depending on when CoreText
-- notices a newly copied user font and prevents an older same-family font from
-- winning macOS font discovery.
local root = os.getenv('FONT_DEMO_ROOT')
if root ~= nil and root ~= '' then
  config.font_dirs = {
    root .. '/fonts/current',
  }
end

config.font = wezterm.font 'Square Braille Unicode Text Seamless'
-- WezTerm normally draws Braille with its own built-in block renderer.  The
-- project deliberately replaces those glyphs, so the configured font must win.
config.custom_block_glyphs = false
config.font_size = number_from_environment('FONT_DEMO_SIZE', 12.0)
config.color_scheme = 'Builtin Dark'
config.initial_cols = number_from_environment('FONT_DEMO_COLUMNS', 120)
config.initial_rows = number_from_environment('FONT_DEMO_ROWS', 36)
config.enable_tab_bar = false
config.adjust_window_size_when_changing_font_size = false
config.warn_about_missing_glyphs = true

local function write_geometry(window, pane)
  local path = os.getenv('FONT_DEMO_GEOMETRY_FILE')
  if path == nil or path == '' then
    return
  end
  local dimensions = pane:get_dimensions()
  local effective = window:effective_config()
  local position = os.getenv('FONT_DEMO_POSITION') or ''
  local temporary = path .. '.tmp'
  local file = io.open(temporary, 'w')
  if file ~= nil then
    file:write(string.format(
      '{"columns":%d,"rows":%d,"font_size":%.3f,"window_position":"%s"}\n',
      dimensions.cols, dimensions.viewport_rows, effective.font_size,
      position:gsub('"', '\\"')))
    file:close()
    os.rename(temporary, path)
  end
end

wezterm.on('window-resized', write_geometry)
wezterm.on('update-status', write_geometry)

return config
