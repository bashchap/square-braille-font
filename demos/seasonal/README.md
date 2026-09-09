# Christmas snow demo

`christmas_snow.py` is a layered seasonal animation for both graphics-font
systems:

- Square Braille: 2×4 virtual pixels per terminal cell;
- PUA 4x4: 4×4 virtual pixels per terminal cell.

It combines differently sized geometric snowflakes, true-colour snow palettes,
wind and gusts, uneven accumulation, broad threshold-driven fall-away events,
aged local tower collapses with bounded chain reactions, layered
pine trees, coloured lights, optional cabin and reindeer scenery, swaying
treetops, airborne leaves, and rolling tumbleweed.

```text
CLI settings
    │
    ├── deterministic scenery ── trees / cabin / reindeer
    ├── snow particles ───────── size / rate / speed / wind / gust / drift
    └── snow bank ────────────── settle / accumulate / broad shed / local slump
                                      │
                                      ▼
                         virtual-pixel layer ownership
                                      │
                         2×4 Square or 4×4 PUA packing
                                      │
                                      ▼
             foreground RGB + glyph + optional reconstructed background RGB
```

The cell compositor uses the proven layered two-colour rule from the Voyager
renderer. The nearest visible depth becomes the glyph foreground. A dense
visible layer immediately behind it may become the ANSI cell background, but
only when that lowers measured reconstruction error for the whole cell. This
preserves a pale flake in front of a green tree instead of deleting the tree or
turning the whole cell white. Sparse rear content stays black rather than
flooding unused pixels. Full masks remain ordinary foreground glyphs and the
demo never emits reverse video.

## Launch it

### macOS

From the repository root:

```sh
./scripts/macos/run-demo.sh pua4 christmas-snow --scenery all
./scripts/macos/run-demo.sh square christmas-snow --scenery trees,cabin
```

The launcher opens an isolated WezTerm window with the correct repository font
stack. Its window controls may precede the mode or follow the demo name:

```sh
./scripts/macos/run-demo.sh \
  --terminal-columns 160 --terminal-rows 48 --font-size 10 \
  pua4 christmas-snow --scenery all

./scripts/macos/run-demo.sh pua4 christmas-snow \
  --terminal-columns 300 --terminal-rows 90 --font-size 7 \
  --scenery all --ambient all --fps 4
```

### Linux with MATE Terminal

```sh
# Square Braille 2×4
./scripts/linux/launch-mate-terminal.sh christmas-snow --scenery all

# PUA 4×4 Candidate 6
./experiments/pua-4x4/demos4x4/run-demo.sh christmas-snow --scenery all

# An explicitly sized, high-capacity window
./experiments/pua-4x4/demos4x4/run-demo.sh christmas-snow \
  --terminal-columns 300 --terminal-rows 90 --font-size 7 \
  --scenery all --ambient all --fps 4
```

Both launchers perform their established user-font/profile setup first.

### Windows or an already configured terminal

Open the repository's Square or PUA4 WezTerm configuration, then run:

```powershell
python demos\seasonal\christmas_snow.py --mode pua4 --scenery all
```

For Square Braille use `--mode square`. Direct Python execution never selects a
font itself; the active terminal must already use the matching font or fallback
stack.

## Scenery

`--scenery` accepts `none`, `trees`, `cabin`, `reindeer`, `all`, or a comma
list. These are equivalent ways to request the complete scene:

```sh
--scenery all
--scenery trees,cabin,reindeer
--scenery trees --cabin --reindeer
```

`--no-trees` removes trees from any selection. `--tree-density` changes the
number of background trees, `--max-trees` places a performance ceiling on very
wide scenes, `--tree-sway` controls wind-driven crown movement, and `--lights`
changes the density of coloured lights on foreground trees.

### Procedural tree families and formula controls

`--tree-types all` rotates six visibly different families: `pine`, `fir`,
`spruce`, `oak`, `maple`, and `birch`. Pass one name or a comma list to compose a
particular forest. Conifers retain filled, snow-bearing silhouettes at any
terminal resolution; oak, maple, and birch expose recursive branch structure,
with distinct bark colours, crown angles and proportions.

The geometry is a bounded two-dimensional adaptation of published parametric
tree work, not a claim of botanical simulation. Honda's 1971 tree model showed
that branch angle and child/parent length ratio strongly affect the whole tree
form. Each branch endpoint here follows the auditable polar relation
`x1 = x0 + L sin(theta)`, `y1 = y0 - L cos(theta)`. Recursive child thickness
uses `r_child = r_parent / 2^(1/a)`, derived from
`r_parent^a = r_child1^a + r_child2^a`. At the default `a = 2`, this preserves
the summed circular cross-sectional area described by Leonardo's rule. These
references also make clear that real trees can deviate from that ideal, so the
exponent is exposed rather than hard-coded:

- Hisao Honda, *Description of the form of trees by the parameters of the
  tree-like body* (1971), DOI
  [10.1016/0022-5193(71)90191-3](https://doi.org/10.1016/0022-5193(71)90191-3)
- Minamino and Tateno, *Tree Branching: Leonardo da Vinci's Rule versus
  Biomechanical Models* (2014),
  [PLOS ONE](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0093535)

| Control | Range | Effect |
|---|---:|---|
| `--tree-branches` | 1–16 | Conifer whorls or broadleaf primary crown limbs |
| `--tree-branch-levels` | 1–7 | Recursive oak/maple/birch daughter generations; cost can roughly double per extra level |
| `--tree-branch-angle` | 1–75° | Upright to spreading daughter limbs |
| `--tree-length-ratio` | 0.35–0.90 | Child length divided by parent length |
| `--tree-trunk-thickness` | 0.5–12 VPX | Base procedural stroke weight |
| `--tree-thickness-exponent` | 1.2–4 | Taper law; 2 is area-preserving for equal bifurcation |
| `--tree-segment-budget` | 0–100,000 | Frame-wide safety ceiling for formula-generated segments |

For example, a sparse forest of broad, heavily branched winter trees is:

```sh
--tree-types oak,maple,birch --tree-density 0.42 --tree-branches 7 \
  --tree-branch-levels 4 --tree-branch-angle 36 \
  --tree-length-ratio 0.64 --tree-trunk-thickness 3.2 \
  --tree-thickness-exponent 2 --tree-segment-budget 10000
```

The segment budget is intentionally independent of `--max-trees`: when it is
spent, complete conifer silhouettes and trunks continue to render, but further
recursive limb detail stops. This makes extreme settings degrade gracefully
instead of allowing recursive growth to dominate CPU time.

Cabins retain a fixed aspect ratio based on scene height. Widening the terminal
therefore redistributes or adds complete cabins instead of stretching one
building horizontally. `--cabin-count auto` selects the number from available
width, bounded by `--max-cabins`; specify an exact whole number when composing a
particular scene. `--cabin-scale` changes their size without changing their
proportions.

`--cabin-types` accepts `cottage`, `lodge`, `a-frame`, `all`, or a comma list.
When more than one cabin is requested, the selected designs are distributed in
order and then repeated. `--cabin-size-variation` adds deterministic size
variation around `--cabin-scale`; the seed makes the same scene reproducible.
Every design retains its own fixed proportions, so neither a live terminal
resize nor a deeper snow bank stretches the building.

`--ambient auto` adds animated leaves and, once the viewport is at least 720
virtual pixels wide, tumbleweed. Use `--ambient all` to force both at any size,
or `--ambient none`, `leaves`, or `tumbleweed`. `--leaf-count`,
`--tumbleweed-count`, and `--ambient-speed` provide explicit control.
Tumbleweed follow the uneven snow surface, accelerate through gust cycles,
bounce without an artificial contact shadow, and rotate stable asymmetrical branches according
to distance actually travelled. A rise higher than `--tumbleweed-climb` times
the weed radius now blocks horizontal progress; the weed presses against that
snow face and multiplies its tower age by
`--tumbleweed-collapse-pressure`. The wall can consequently slump, after which
the weed continues. Downhill motion is gravity-limited rather than snapping the
weed to an arbitrary lower surface. This makes translation, rolling, collision,
falling, and terrain response separately visible through the graphics font.

## Wildlife, flybys, and snow clearing

The foreground is not limited to falling snow:

- `--rabbit-count`, `--rabbit-interval`, and `--rabbit-speed` control rabbits
  that follow the current snow surface. They hop, pause to eat, and continue in
  either direction. A nearby tumbleweed or plough startles a rabbit, which
  turns away and accelerates.
- `--sky-events auto` rotates aeroplane, UFO, and Santa-with-reindeer flybys.
  Use `none`, one name, or a comma list with `--flyby-interval` and
  `--flyby-speed` for a particular demonstration. All flights occupy a distant
  compositing layer and are occluded by trees, cabins, animals and snow.
  `--santa-scale 0.50` is the half-size default. `--santa-arc-height` controls
  his mid-flight rise, and `--santa-trail-seconds` controls the fading
  gold-and-ice particle trail left behind the sleigh.
- The snow plough is enabled by default. `--plough-interval` controls how often
  it enters, `--plough-speed` controls traversal speed, and
  `--plough-clear-to` is the shallow bank left by a completed pass. Use
  `--no-snow-plough` for a scene that never receives a full-width clearing.

To isolate the half-scale arcing Santa and his fading trail:

```sh
./scripts/macos/run-demo.sh pua4 christmas-snow \
  --sky-events santa --flyby-interval 1 --flyby-speed 32 \
  --santa-scale 0.50 --santa-arc-height 0.16 --santa-trail-seconds 2.8
```

For a busy, reproducible test scene:

```sh
--scenery all --ambient all --rabbit-count 3 --rabbit-interval 8 \
  --sky-events aeroplane,ufo,santa --flyby-interval 12 \
  --plough-interval 24 --cabin-count 3 \
  --cabin-types cottage,lodge,a-frame --cabin-size-variation 0.32
```

## Illustrated command help

Open the complete colour guide through the same launcher and font used by the
demo:

```sh
# macOS
./scripts/macos/run-demo.sh pua4 christmas-snow --help

# Linux
./experiments/pua-4x4/demos4x4/run-demo.sh christmas-snow --help
```

The help is generated directly from the active option parser and therefore
lists every program control and its default. It also documents the three
launcher-only window controls, provides task-oriented recipes, and renders
panels containing exactly 8 and 24 live `Flake` objects through the selected
Square or PUA4 production encoder. Set the conventional `NO_COLOR=1`
environment variable when plain, capture-friendly output is required.

## Live keyboard control

The controller is deliberately a separate terminal program: one window remains
an unobstructed graphics viewport while the other becomes an operational
console. Both processes share a small versioned JSON file. Updates replace that
file atomically, so the renderer sees either a complete old revision or a
complete new revision—never half of an edit.

On macOS, open two shells at the repository root:

```sh
# Terminal 1: graphics viewport
./scripts/macos/run-demo.sh pua4 christmas-snow --listen

# Terminal 2: keyboard controller
./scripts/macos/run-demo.sh pua4 christmas-snow-control
```

Use `square` in both commands for Square Braille. On Linux PUA4:

```sh
./experiments/pua-4x4/demos4x4/run-demo.sh christmas-snow --listen
./experiments/pua-4x4/demos4x4/run-demo.sh christmas-snow-control
```

For Linux Square Braille:

```sh
./scripts/linux/launch-mate-terminal.sh christmas-snow --listen
./scripts/linux/launch-mate-terminal.sh christmas-snow-control
```

The default shared file is the platform temporary directory's
`font-demo-christmas-snow-control.json`. To isolate two simultaneous sessions,
give both sides the same explicit path:

```sh
./scripts/macos/run-demo.sh pua4 christmas-snow \
  --listen /tmp/north-pole-control.json
./scripts/macos/run-demo.sh pua4 christmas-snow-control \
  --control-file /tmp/north-pole-control.json \
  --save-file presets/north-pole.json
```

The controller also accepts any Christmas Snow option as an initial value. For
example, start it first with the reported blizzard settings, then start the
viewer with only `--listen`:

```sh
./scripts/macos/run-demo.sh pua4 christmas-snow-control \
  --snow-rate 180 --max-flakes 900 --fall-speed 26 \
  --wind 8 --gust-strength 10 --gust-period 4 --drift 3 --wobble 2 \
  --flake-sizes tiny,small,medium --size-weights 7,3,1

./scripts/macos/run-demo.sh pua4 christmas-snow --listen
```

The viewer performs a forced read of the shared control JSON before its first
animated frame whenever `--listen` is present. It therefore starts with the
last state published to that exact control path. Without `--listen`, it uses
CLI/default values and deliberately does **not** search for
`christmas-snow-preset.json`; this avoids a hidden file silently changing a
reproducible command. Pressing `S` creates a separate durable preset, which is
used by launching its `.command.txt` file or explicitly loading the JSON into
the controller as described below.

An explicit `--preset FILE` takes precedence over these initial values; without
either, the controller reconnects to the current control file when one exists,
or starts from defaults.

Every option row carries an activity symbol—for example `❄` for snowfall,
`⌂` for cabins, `♙` for rabbits, `✈` for flybys, and `▰` for the plough. The
right-hand inspector explains the selected option, its slider range and step or
allowed values, its predicted visual effect, and whether large values have
low, moderate, or high performance sensitivity. Direct input remains available
when a value outside the convenient slider range is valid.

Controller keys:

| Key | Operation |
|---|---|
| Up / Down, Page Up / Page Down, Home / End | Navigate every option |
| Left / Right | Move a numeric slider or cycle a choice |
| Space | Toggle an on/off option |
| Enter | Type an exact value; type `AUTO` for auto-sized controls |
| `S` | Save a JSON preset and adjacent standalone `.command.txt` launch command |
| `P` | Display a complete standalone command; it is also printed on exit |
| `R` | Restore defaults for the selected font mode |
| `Q` | Quit the controller; the viewer keeps its last accepted values |

`LIVE` options take effect on the next control poll (default 0.20 seconds).
`RESTART` options affect raster construction or process lifetime; the TUI saves
them, but clearly identifies that the graphics viewer must be restarted. The
viewer dashboard shows `LIVE WAIT`, `LIVE R<n>`, `LIVE ERROR`, or
`LIVE RESTART:MODE`, making the control state observable.
The printed command uses the detected macOS, Linux PUA4, Linux Square, or
direct Windows launch form. It contains the effective options but deliberately
omits `--listen`, so it reproduces the scene later without needing the
controller.

### Launching a saved preset

Pressing `S` creates two adjacent files with different purposes:

- `christmas-snow-preset.json` is structured controller state. Reload it with
  `christmas-snow-control --preset christmas-snow-preset.json` when you want to
  continue editing the values.
- `christmas-snow-preset.command.txt` is a complete executable shell script.
  It includes a shebang, safe shell settings, and literal trailing backslashes
  on every continued command line.

From the repository root on macOS or Linux, run the saved scene directly:

```sh
./christmas-snow-preset.command.txt
```

The equivalent explicit-shell form is:

```sh
bash christmas-snow-preset.command.txt
```

If the file was saved by an older controller and is not executable, the
explicit `bash` form still works; pressing `S` in the current controller
rewrites it with executable permissions. The saved script already contains the
correct platform launcher and font mode, so do not pass it as an argument to
`christmas-snow`.

`--snapshot` has exact one-frame semantics. If it is ON when the preset is
saved, the generated script prints one frame and exits; on macOS the launcher
holds that successful frame open for inspection. Turn `--snapshot` OFF in the
controller and press `S` again when the intended result is a continuous
animation. The generated script includes an explicit warning comment whenever
snapshot mode is saved.

## Detailed font-usage dashboard

Add `--detailed-dashboard` when the compact one-line status is not enough:

```sh
./scripts/macos/run-demo.sh pua4 christmas-snow \
  --detailed-dashboard --scenery all
```

The five extra rows are now a tabbed dashboard. Press `Tab` to rotate through
`FONT`, `SNOW`, `TREES`, `ANIMALS`, `FLIGHTS`, and `PROCESS`; the highlighted
name in the Unicode tab strip is the active page. Press `q` or `Esc` to leave
the animation. The terminal input mode is temporary and restored on exit.

- `FONT` separates the static repertoire, runtime-created count, distinct
  glyphs in the current frame, cumulative distinct glyphs seen since launch,
  active/blank cells, deduplication, and colour combinations.
- `SNOW` covers airborne particles, ground-bank mass, repose relaxation,
  broad/local shedding, and sparse object-snow catches and releases.
- `TREES` shows species, density, branch formula controls, the segment budget,
  sway and object-snow state.
- `ANIMALS` shows rabbit states/reactions and foreground-reindeer state.
- `FLIGHTS` identifies the current distant event, schedule, speed, occlusion
  rule, Santa scale/arc/trail state, and snow-plough activity.
- `PROCESS` shows CPU sampled over quarter-second windows, raster-and-encode
  time against the frame budget implied by `--fps`, peak resident memory
  (`PEAK RSS`), and the main configured cost sources. Peak RSS is a high-water
  mark, so it does not fall after temporary allocations are released.

`RUNTIME REDEFINED` and `DYNAMICALLY CREATED FOR THIS ANIMATION` are deliberately
reported as zero in this demo. Christmas Snow uses
the repository's already-built static Square or PUA4 repertoire; it chooses
codepoints but does not modify a font while running. This distinguishes the
metric from FontColour's dynamic image-font compiler, where generated glyphs
really are added to a new font. `UNIQUE GLYPHS CURRENT FRAME` is the exact
distinct mask/codepoint count visible now. `SEEN SINCE START` is the union over
all frames rendered so far and therefore answers how many glyph definitions a
trimmed bespoke font would have required up to that point. `STATIC AVAILABLE`
is the complete 256-glyph Square or 65,536-glyph PUA4 repertoire on disk.

The event artwork is virtual-pixel geometry rather than embedded images. The
aeroplane includes a tapered shaded fuselage, swept wings, tail, engine,
windows, cockpit, and contrails. The UFO has a layered saucer, glass dome,
occupant, alternating lamps, and scan beam. Both flybys, plus the static
foreground reindeer, are now one third of their former linear scale so they
read as scene accents rather than dominating the landscape. Santa is half its
former linear size. It now separates sack and presents, Santa's
face, beard, hat, belt and mitten, the sleigh side panel and curled runners,
reins, and four reindeer with eyes, muzzles, ears, tails and four jointed legs.
The far and near leg pairs use different shades and gait phases for depth and a
more natural suspended gallop. The foreground seasonal reindeer remains a
separate design with the same anatomical and seasonal cues at its reduced size.

## Snow controls

| Control | Meaning |
|---|---|
| `--snow-rate` | Newly generated flakes per second |
| `--max-flakes` | Safety ceiling for simultaneously active flakes |
| `--flake-sizes` | Comma list drawn from `tiny,small,medium,large` |
| `--size-weights` | Relative frequency of each selected size |
| `--fall-speed` | Mean downward speed in virtual pixels per second |
| `--speed-variation` | Random variation around the mean fall speed |
| `--wind` | Constant horizontal velocity; negative values blow left |
| `--gust-strength` | Additional sinusoidal wind strength |
| `--gust-period` | Seconds between gust-cycle repetitions |
| `--drift` | Random horizontal bias unique to each flake |
| `--wobble` | Side-to-side flutter while falling |
| `--palette` | `winter`, `christmas`, `aurora`, or `monochrome` |

The deterministic `--seed` makes the same dimensions and settings reproduce
the same initial scene and snow population.

`--flake-sizes` may be changed on its own. When `--size-weights` is omitted,
the selected names inherit the built-in `tiny=55, small=28, medium=13,
large=4` profile. In live-control mode, changing either the selected sizes or
their weights immediately redistributes the shapes of existing airborne
flakes; it does not wait for the current particles to land. The SNOW dashboard
tab prints the effective `MIX`, making the applied names and weights visible.

## Accumulation and fall-away controls

| Control | Meaning |
|---|---|
| `--initial-snow` | Initial maximum bank depth as a fraction of scene height |
| `--bank-drift` | Amount of unevenness in the initial snow line |
| `--accumulation` / `--accumulation-rate` | Deposit added when a flake settles |
| `--snow-repose-slope` | Maximum stable adjacent height difference before snow moves sideways |
| `--snow-relaxation` | Maximum excess depth moved per second while smoothing steep slopes |
| `--no-accumulation` | Keep the initial bank fixed |
| `--shed-threshold` | Bank fraction that starts a fall-away; default `0.50` |
| `--shed-to` | Local target after the bank breaks; default `0.36` |
| `--shed-width` | Fraction of screen width affected by the break |
| `--shed-rate` | How quickly the selected bank section drops |
| `--tower-collapse` / `--no-tower-collapse` | Enable or disable narrow-peak ageing and collapse |
| `--tower-age` | Minimum time a prominent local tower must persist |
| `--tower-age-jitter` | Seeded random lifetime added per tower position |
| `--tower-prominence` | Required height above neighbouring shoulders |
| `--tower-collapse-rate` | Speed of a local slump |
| `--tower-cascade-chance` | Probability that one collapse destabilises a neighbour |
| `--tower-cascade-radius` | Width searched for a chain-reaction candidate |
| `--object-snow` / `--no-object-snow` | Enable sparse temporary snow on scenery surfaces |
| `--object-snow-capture` | Per-impact retention chance; default 8% |
| `--object-snow-max` | Hard ceiling for separate retained patches |
| `--object-snow-hold` | Mean lifetime before creep releases a patch |
| `--object-snow-hold-jitter` | Seeded lifetime variation that prevents uniform release |
| `--object-snow-adhesion` | Flake-equivalent mass supported before gravity wins |

The dashboard reports both maximum and average snow depth. The maximum depth
triggers shedding because a tall local drift should collapse without requiring
the whole screen to become half full. The affected section falls toward
`--shed-to`, emits visible chunks, waits briefly, and then resumes normal
accumulation.

Broad shedding and local tower collapse solve different problems. A broad shed
limits the overall high-water mark once any bank crosses `--shed-threshold`.
The local mechanism watches each narrow peak relative to snow on both sides.
Only a peak that remains prominent for `--tower-age` plus deterministic random
`--tower-age-jitter` is failed; it slumps toward its shoulders, emits falling
snow chunks, and may trigger one nearby peak. Cascades are capped at three
generations and simultaneous failures are spatially separated. Consequently a
brief fresh spike can exist, but the persistent vertical towers created by an
extreme accumulation rate cannot remain indefinitely. The dashboard's
`TOWERS` count is the number of local failures begun, while `SHEDS` counts the
broad events.

The terrain baseline is captured independently when the scene is created.
Trees, cabins, and reindeer remain attached to that baseline while the snow
surface rises and falls around them; accumulated snow can realistically bury
their lowest pixels but cannot move the scenery vertically. `GROUND=FIXED` in
the dashboard identifies this path. A genuine window-height resize scales the
terrain and scenery together.

### Purpose-built seasonal physics

`SeasonalPhysics` is a small deterministic virtual-pixel engine, not a general
rigid-body dependency. Ground deposits are distributed through a Gaussian-like
kernel instead of adding a narrow vertical needle. Each frame then transfers
depth from any neighbouring pair steeper than `--snow-repose-slope`, bounded by
`--snow-relaxation`. This conserves the transferred snow mass while rounding
the implausible spikes seen in earlier builds.

Scenery records occupied vertical runs while it is drawn. The resulting bitset
index exposes object top edges without a second full-raster collision scan. A flake
crossing one of those edges has only `--object-snow-capture` probability of
sticking, so roofs, branches and figures receive sparse, non-uniform patches
rather than a second ground-sized bank. Use `--object-snow-max` as the hard
patch ceiling, `--object-snow-hold` and `--object-snow-hold-jitter` for creep,
and `--object-snow-adhesion` for supported flake-equivalent mass. Each impact
adds mass; when `mass × 9.81` exceeds that patch's seeded adhesion—or its hold
time expires—the patch becomes one or more falling chunks. `--no-object-snow`
disables this collision path without changing ground accumulation.

`--physics` makes the cost and behaviour explicit and supports repeatable A/B
comparison:

| Mode | Ground slumping and terrain bodies | Object-surface snow |
|---|---:|---:|
| `none` | No | No |
| `ground` | Yes | No |
| `full` (default) | Yes | Yes |

`none` retains the smooth deposit shape, broad threshold shedding and the same
renderer, but bypasses the newer repose, terrain-body and object-snow systems.
`ground` keeps realistic bank and tumbleweed behaviour while avoiding scenery
collision indexing. `full` adds sparse snow capture, mass and gravity on scenery.
The setting is live: the companion console can switch it while the demo runs.

Procedural trees are rasterized once for each deterministic size, species and
formula setting. Frames reuse that immutable geometry and apply a cheap
height-weighted sway while compositing it. The cache is bounded, invalidates
naturally when a relevant tree option changes, and is reported on the PROCESS
dashboard tab as hits and misses.

This engine also owns stateful tumbleweed contact, vertical velocity, gravity,
terrain climb limits, pressure-assisted bank collapse, and Santa's fading
trail lifetime. The compositor remains separate: physics decides positions and
state, while the Square/PUA4 renderer decides glyphs, colours and depth.

## Window size, font size, and live resizing

`--terminal-columns`, `--terminal-rows`, and `--font-size` belong to the macOS
and Linux launchers. They choose the initial terminal window and font without
hard-coding the animation raster. Dragging the live terminal window then
changes the renderer's cell grid immediately: existing flakes, falling chunks,
and the accumulated bank are proportionally preserved, while deterministic
scenery is regenerated for the new area.

The Python-only `--columns` and `--rows` controls are different. They fix the
internal raster and are intended for snapshots, reproducible tests, and output
capture; specifying either dimension deliberately prevents live tracking for
that axis.

At hundreds of columns, use a smaller terminal font and a realistic frame rate.
The exact rate depends on the machine and scene density; `--fps 4` is a useful
starting point for a 300×90 PUA4 scene. The dashboard displays `GRID`, which is
the currently observed terminal cell size, and `2CLR=ON`, which confirms the
two-colour depth compositor is active.

## Useful presets

Gentle fine snow:

```sh
--snow-rate 20 --flake-sizes tiny,small --size-weights 4,1 \
--fall-speed 10 --wind 0.2 --gust-strength 0.4 --drift 0.5
```

Christmas-card scene:

```sh
--scenery all --palette christmas --snow-rate 70 \
--tree-density 0.85 --lights 0.55
```

Blizzard:

```sh
--snow-rate 180 --max-flakes 900 --fall-speed 26 \
--wind 8 --gust-strength 10 --gust-period 4 --drift 3 --wobble 2 \
--flake-sizes tiny,small,medium --size-weights 7,3,1
```

Blizzard with faster, more contagious tower failure:

```sh
--snow-rate 180 --max-flakes 900 --accumulation 3.5 \
--tower-age 2 --tower-age-jitter 2 --tower-prominence 0.06 \
--tower-collapse-rate 0.8 --tower-cascade-chance 0.65
```

Wide animated winter landscape:

```sh
--scenery all --ambient all --tree-sway 3.5 --tree-density 0.65 \
--max-trees 96 --leaf-count 45 --tumbleweed-count 3 \
--wind 6 --gust-strength 9 --accumulation-rate 1.4 --fps 4
```

Quick accumulation/fall-away demonstration:

```sh
--initial-snow 0.46 --accumulation 5 \
--shed-threshold 0.50 --shed-to 0.30 --shed-width 0.36 --shed-rate 0.40
```

See every option without opening a graphics window:

```sh
python3 demos/seasonal/christmas_snow.py --help
```

Print one deterministic frame for diagnostics or capture:

```sh
python3 demos/seasonal/christmas_snow.py \
  --mode pua4 --snapshot --columns 100 --rows 30 --scenery all
```

Press `Control-C` to leave the continuous animation.

## Verification

```sh
python3 demos/seasonal/verify_christmas_snow.py
```

For a repeatable phase-by-phase comparison of all three physics levels:

```sh
python3 demos/seasonal/benchmark_christmas_snow.py
python3 demos/seasonal/benchmark_christmas_snow.py --viewport 168x60 --runs 5
python3 demos/seasonal/benchmark_christmas_snow.py --viewport 279x43 --json
```

The report separates simulation, scenery, collision-index extraction, moving
object rasterization and glyph encoding. Timings are medians after two warm-up
frames; compare results only on the same host and terminal-independent workload.

The verifier checks both full-mask mappings, the PUA4 MSB-left top-left bit,
two-colour depth ownership, scenery generation, the 50% shedding trigger, live
resize preservation, animated tree movement, frame dimensions, and the absence
of reverse-video output. It also forces an aged local tower and neighbour
cascade, applies a live JSON revision, and round-trips the TUI's effective
options back through the production parser. Additional checks cover varied
cabin types, tumbleweed-aware rabbits, all three sky events, complete plough
clearing, detailed reindeer and flyby pixel complexity, dashboard dimensions
and CPU/memory labels, per-option TUI icons and guidance, snapshot-window hold
behaviour, and an executable saved command containing literal shell
continuation backslashes. It also cross-checks draw-time exposed-surface indexing
and confirms that `none`, `ground` and `full` isolate their intended subsystems.
