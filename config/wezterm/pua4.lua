local wezterm = require 'wezterm'
local config = wezterm.config_builder()

local function number_from_environment(name, fallback)
  local value = tonumber(os.getenv(name) or '')
  if value == nil then
    return fallback
  end
  return value
end

-- Normal shell text comes from Square Braille.  The two disjoint supplementary
-- PUA ranges then fall through to Part 0 and Part 1 in an explicit order.
config.font = wezterm.font_with_fallback {
  'Square Braille Unicode Text Seamless',
  'PUA 4x4 Part 0 v0.6 Candidate 6',
  'PUA 4x4 Part 1 v0.6 Candidate 6',
}
config.font_size = number_from_environment('FONT_DEMO_SIZE', 12.0)
config.color_scheme = 'Builtin Dark'
config.initial_cols = number_from_environment('FONT_DEMO_COLUMNS', 120)
config.initial_rows = number_from_environment('FONT_DEMO_ROWS', 36)
config.enable_tab_bar = false
config.adjust_window_size_when_changing_font_size = false
config.warn_about_missing_glyphs = true

return config
