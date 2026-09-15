# Christmas snow demo

`christmas_snow.py` is a layered seasonal animation for both graphics-font
systems:

- Square Braille: 2×4 virtual pixels per terminal cell;
- PUA 4x4: 4×4 virtual pixels per terminal cell.

It combines sparse geometric snowflakes, optional rain, bouncing hail and
branched lightning, true-colour weather palettes,
wind and gusts, uneven accumulation, broad threshold-driven fall-away events,
aged local tower collapses with bounded chain reactions, layered
pine trees, coloured lights, optional cabin and reindeer scenery, swaying
treetops, airborne leaves, rolling tumbleweed, parallax clouds, and varied
distant flybys.

```text
CLI settings
    │
    ├── gradient sky ─────────── 2–8 colours / stops / blend curve
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
  --window-position 80,40 \
  --scenery all --ambient all --fps 4
```

`--window-position X,Y` sets the initial macOS WezTerm pixel position. The
saved control-console command records the live terminal rows/columns and
effective font size. It also asks macOS Accessibility for the front window's
current position; if that access is unavailable, it preserves the explicitly
launched `--window-position` value instead.

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
| `--tree-trunk-thickness` | 0.5–12 VPX | Main trunk weight; default 4.2 VPX |
| `--tree-branch-thickness-ratio` | 0.1–1.0 | Primary branch weight as a fraction of the main trunk; default 0.42 keeps branches visibly slimmer |
| `--conifer-colour-variation` | 0–100 RGB levels | Seeded colour separation among pine/fir/spruce individuals; default 28 |
| `--tree-thickness-exponent` | 1.2–4 | Taper law; 2 is area-preserving for equal bifurcation |
| `--tree-segment-budget` | 0–100,000 | Frame-wide safety ceiling for formula-generated segments |

For example, a sparse forest of broad, heavily branched winter trees is:

```sh
--tree-types oak,maple,birch --tree-density 0.42 --tree-branches 7 \
  --tree-branch-levels 4 --tree-branch-angle 36 \
  --tree-length-ratio 0.64 --tree-trunk-thickness 4.2 \
  --tree-branch-thickness-ratio 0.42 \
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
The A-frame uses a filled outer roof shell and inset wall triangle rather than
a fragile one-pixel outline, keeping both diagonals and the eaves continuous
after the image is reduced into 4×4 PUA cells. Its door geometry is shared by
the cabin renderer and postman target calculation and is inset from the sloped
wall, so it cannot escape the triangular footprint.

`--cabin-depth-share` assigns a repeatable fraction of cabins to the distance;
`--cabin-depth-scale` makes those buildings smaller and raises them toward the
horizon. Their real elevated door coordinates are also used by the postman, so
the walk from the foreground road becomes longer and the figure scales
continuously throughout the trip.
Every door is connected to one shared woodland route: sparse, irregular dark
dirt pixels form a road and a spur to each entrance. The route is deliberately
non-colliding, may be partly covered by snow, and is also the postman's route.

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
  turns away and accelerates. Each rabbit keeps a deterministic depth lane:
  distant rabbits are smaller, travel more slowly through parallax, sit closer
  to the horizon, and can pass behind cabins and trees; near rabbits pass in
  front.
- `--npcs` manages colour-varied roaming people using the postman's cached
  jointed eight-frame gait without using his delivery state machine. NPCs
  move on an `(x, depth)` ground plane: sideways motion crosses the terminal,
  depth motion approaches or recedes from the artificial horizon, and every
  intermediate heading remains perspective-correct. The same depth controls
  terrain contact, figure scale, parallax speed, and whether scenery occludes
  the person. `--npc-count` sets the active slots and
  `--npc-colours` assigns two to eight coat colours. Each person receives a
  speed between `--npc-speed-min` and `--npc-speed-max`, then reconsiders
  its heading between `--npc-decision-min-seconds` and
  `--npc-decision-max-seconds`. `--npc-response-seconds`,
  `--npc-object-awareness`, and `--npc-avoidance-strength` tune smooth
  reactions to cabins, other actors, crates, the plough, and a landed
  helicopter's exclusion zone. The signed crossing-motivation min/max values
  bias travel toward or away from an assigned side;
  `--npc-wander-angle 180` permits a complete 360-degree choice, and
  `--npc-reversal-chance` can swap the intended side. The signed social
  factor disperses or groups NPCs inside the configured social distance.
  `--npc-path-adherence` attracts them to the same live, perspective-tapered
  dirt network used by the postman. Depths above `1` deliberately approach
  through the near viewport and enlarge the figure for a fourth-wall effect.
  Actor terrain samples are clamped at the viewport edges rather than wrapping
  like airborne particles, and are filtered across the figure's footprint, so
  crossing an edge or a one-column snow step cannot teleport a walking NPC.
  Even when a bank rises above the artificial horizon, the projected feet stay
  on the visible ground side of that horizon rather than walking in the sky.
  At `--npc-depth-max`, `--npc-viewport-respawn-chance` chooses whether the
  person disappears into a replacement slot or immediately turns away.
  On leaving any lateral or depth boundary, a slot waits
  `--npc-respawn-seconds` and receives a new generation, colour, speed, and
  motivation. Set `--npc-track-id N` to mark slot `N` in cyan and report
  its generation, state, x position, and depth on the ANIMALS dashboard.
- `--postman` schedules a postman who walks in from either edge, selects an
  actual cabin door, turns smoothly from a side view to show his back, walks
  from the road to the house, posts a visible letter, waits, turns to face the
  viewer, returns to the road, turns sideways and continues off screen.
  During the approach, spaced footsteps compact the bank and release small
  falling crumbs, leaving a local collapsed path rather than walking through
  rigid snow.
  `--postman-interval`, `--postman-speed`, and `--postman-stop-seconds` tune the
  visit. `--postman-delivery-frequency` multiplies visit frequency (zero
  disables deliveries), while a rotating target index ensures every cabin is
  visited before the route repeats. His detailed road-scale figure is 70%
  larger than the earlier design;
  it scales linearly down to fit the selected door during approach and back to
  full size on the return. Cached jointed gait and turning phases use opposing
  arms and legs, front/back colour shading, cap, uniform insignia, buttons,
  footwear, satchel and envelope detail. The motion
  was informed by [Eadweard Muybridge's 1887 public-domain walking sequence](https://commons.wikimedia.org/wiki/File:Muybridge_human_male_walking_animated.gif)
  and the [Library of Congress record for *Animal locomotion*](https://www.loc.gov/item/92502807/);
  the demo does not copy or bundle their photographic pixels.
  When a helicopter has left a supply crate, the next postman stops on the
  road, opens it, collects mail, breaks the empty box into fading fragments,
  and then continues to the scheduled cabin. The crate is never an obstacle.
- `--sky-events auto` rotates commuter/airliner aeroplanes, AH-64 and
  Airwolf-style helicopters, a
  lost kite whose segmented tail bends and flutters under the live wind/gust
  field, UFO, Santa-with-reindeer, and Superman flybys. Superman now has a
  roughly doubled horizontal silhouette with face, hair, eye, extended fist,
  chest emblem, belt, shaded suit and boots; his reduced cape still flutters.
  `--superman-path straight|curve|arc`,
  `--superman-frequency`, and `--superman-speed` control his route and timing.
  Use `none`, one name, or a comma list with `--flyby-interval` and
  `--flyby-speed` for a particular demonstration. All flights occupy a distant
  compositing layer and are occluded by trees, cabins, animals and snow.
  `--aeroplane-types` selects a compact rounded commuter aircraft or long
  red-striped airliner; both are half the preceding release's scale.
  `--pilot-ejection` permits a deterministic occasional ejection: the pilot
  starts in freefall, opens a larger billowing canopy, then visibly swings and
  drifts down at
  `--parachute-fall-speed` in the furthest flight layer. Set
  `--ejection-chance 0` to disable it or `1` to demonstrate every pass.
  A failed probability roll leaves the original aeroplane visible for its
  complete crossing; only a successful ejection transfers it to the crash
  state machine.
  With `--aircraft-crash` (the default), the abandoned aircraft then rolls
  continuously into a steep gravity-driven arc with a fire-and-smoke wake.
  `--aircraft-crash-depth auto|away|toward` chooses whether it shrinks toward
  the horizon or grows toward the viewer; descent, arc, spin and smoke each
  have independent controls. Impact creates a persistent `fiery` or `nuclear`
  animated explosion selected by `--explosion-types`, with configurable scale
  and lifetime. The enlarged red/yellow fireball and nuclear mushroom cloud
  retain a hot core, ground front and embers before fading smoothly near the
  end of their lifetime. A `toward` crash that reaches the foreground melts a
  tapered cavity in both bank and retained object snow for as long as the
  explosion remains hot; a distant `away` impact cannot alter foreground
  terrain. `all` alternates both forms; `--no-aircraft-crash` restores a
  non-destructive ejection flyby.
  `--santa-scale-min 0.02` and `--santa-scale-max 0.50` make the formation grow
  smoothly from an almost single-dot distance to its nearest midpoint size,
  then recede symmetrically. Legacy `--santa-scale` remains an alias for the
  maximum. `--santa-arc-height` controls his mid-flight rise,
  `--santa-trail-length` controls its spatial extent, and
  `--santa-trail-seconds` controls the fading red, blue, yellow, orange and
  green particle trail left behind the sleigh. The defaults are now `3.0`
  times the original spatial length and `5.6` seconds—twice the original
  lifetime. Santa releases `--santa-presents-min` through
  `--santa-presents-max` parcels on the same frame over every crossed cottage
  or lodge chimney. Each has an independent initial fall speed. Disable
  deliveries with `--no-santa-presents` or tune the baseline with
  `--present-fall-speed`.
- The doubled-size AH-64-inspired helicopter and independently selectable
  black/red `airwolf` type approach nose-on from a point,
  grows into a detailed hover at a repeatably varied horizontal position,
  descends into the foreground, waits between `--helicopter-wait-min` and
  `--helicopter-wait-max`, leaves a supply crate, rises vertically until its
  complete lower silhouette clears the highest cabin roof/chimney, passes
  through thirteen stationary orientation frames, then shows its rear and
  recedes lower toward the artificial horizon. Its live depth moves from the
  landing lane back to the distant layer, allowing trees, cabins and the snow
  bank to progressively occlude it. A scale-aware clearance plane
  prevents the shrinking craft from crossing back over cabin roofs. Its
  canopy, paired engines, stub wings, weapon pods,
  chin sensor, landing gear and flashing warning lamps remain procedural. The
  Airwolf variant has a longer pointed nose, dark streamlined body, silver
  canopy treatment and continuous red lower stripe, while using the same
  flight, cargo and downwash simulation.
  Thirteen axial/profile orientations and four thin projected rotor blades remove
  the former turn snap and make rotor phase visible.
  `--helicopter-hover-seconds` controls transition pauses.
  `--helicopter-downwash` ranges from 0 (off) to 4 (extreme), displacing nearby
  precipitation and loose chunks, adding a short-lived volumetric wake and
  scouring loose snow. `--helicopter-downwash-width` independently expands the
  affected radius from 0.25 to 4 times the normal rotor field.
  The wake is emitted outside and below the fuselage, moves outward, and is
  composited behind the aircraft so it cannot paint through the cockpit.
  A landing target is rejected while a visible rabbit or postman is underneath;
  throughout hover, descent, landing and takeoff, the active rotor radius forms a hard
  exclusion zone which turns rabbits and tumbleweed away and stops the postman
  at its boundary. Nose-on panes, canopy frames, twin intakes and the central
  sensor are redrawn at high priority so front detail survives PUA4 quantizing.
  Generate an exact PUA4/ANSI-quantized contact sheet of all thirteen yaw
  frames with:

  ```sh
  python3 demos/seasonal/render_helicopter_mockup.py
  python3 demos/seasonal/render_helicopter_mockup.py --style airwolf
  ```
- `--ufo-abduction` makes a UFO pause and activate a moving cyan, blue, violet,
  gold and white transporter column. The UFO selects one already-visible
  rabbit, swoops from a distant point toward that rabbit, and freezes directly
  above it before the beam appears. If no rabbit is visible, the flyby proceeds
  without manufacturing a hidden stand-in, but it continues checking during
  approach so a naturally emerging existing rabbit can still be selected. The selected rabbit
  then rises vertically in front of the sparse beam and shrinks to 10% of the
  UFO's width. Both rabbit and beam retain the rabbit's original depth lane:
  a rabbit that began in front of a cabin remains in front throughout capture,
  while a distant rabbit and its beam remain occluded. `--ufo-types` rotates
  saucer, orb and delta vehicles, while
  `--ufo-beam-style spiral|rings|lattice|stargate` selects four moving,
  deliberately sparse transporter treatments, and
  `--ufo-trail-length` and `--ufo-trail-seconds` tune their plasma wakes. After
  capture the craft accelerates away while shrinking back toward a point.
- The snow plough is enabled by default. `--plough-interval` controls how often
  it enters, `--plough-speed` controls traversal speed, and
  `--plough-clear-to` is the shallow bank left by a completed pass. Its wheels
  remain on one horizontal road datum while the blade removes changing snow;
  it does not climb the bank it is clearing. There is no end-of-pass global
  cleanup: snow that falls behind the blade remains, as it is newer than the
  cleared path. Use `--no-snow-plough` for a scene
  that never receives a full-width clearing.

To isolate the half-scale arcing Santa and his fading trail:

```sh
./scripts/macos/run-demo.sh pua4 christmas-snow \
  --sky-events santa --flyby-interval 1 --flyby-speed 32 \
  --santa-scale-min 0.02 --santa-scale-max 0.50 --santa-arc-height 0.16 \
  --santa-trail-length 3 --santa-trail-seconds 5.6
```

## Gradient sky

The sky is the farthest raster layer, beneath flybys and every scenery or snow
pixel. It is enabled by default. Choose two to eight hexadecimal RGB colours,
give each a matching top-to-bottom stop between `0` and `1`, and select the
interpolation curve:

```sh
./scripts/macos/run-demo.sh pua4 christmas-snow \
  --sky-colours 07152F,315A82,B9D8E8 \
  --sky-stops 0,0.58,1 --sky-blend smooth
```

`linear` changes colour at a constant rate, `smooth` eases into and out of each
stop, and `cosine` gives an even gentler merge. Use `--no-sky` for the old
terminal-black background. Colours, stops, blend, and the on/off state are live
controls. When changing the number of colours in the console, evenly spaced
stops are generated automatically and can then be edited precisely.

The sky can make small flybys look coarser even though their depth order is
correct. A PUA4 terminal cell has one 4x4 binary foreground mask plus, at most,
one representative ANSI background colour. With a solid gradient behind a
small multicolour object, its edge colours and the already-coloured rear pixels
must share those two cell-level colour roles. The encoder preserves the nearest
mask and minimizes reconstruction error, but cannot retain every source colour
inside the same cell. Against terminal black, empty samples need no background
colour, so more of a small silhouette survives crisply. This is a two-colour
per-cell and 4x4 sampling limit, not missing depth compositing; foreground trees
and cabins still occlude the distant flights correctly.

### Parallax clouds

`--clouds` enables procedural, continuously wrapping cloud bodies. No bitmap
assets are loaded. `--cloud-depths` supplies one to eight perspective lanes;
near lanes are larger and, through `--cloud-parallax`, move faster than distant
lanes. Depths below `0.62` pass behind flights and depths at or above it may
cross in front of them, while all clouds remain behind scenery. `--cloud-count`,
`--cloud-speed`, and `--cloud-colours` control population, base movement and a
cycled RRGGBB palette. For example:

```sh
--clouds --cloud-count 9 --cloud-speed 5 \
  --cloud-depths 0.18,0.42,0.72,0.9 --cloud-parallax 1.4 \
  --cloud-colours 91A9BA,C7DBE7,F4F1E8
```

The companion console exposes these together on its dedicated `CLOUDS` tab.

## Rain, hail and lightning

`--weather` selects `none`, `snow`, `rain`, `hail`, `mixed`, or `storm`.
`none` disables precipitation and lightning without removing the gradient sky,
scenery, ambient motion, rabbits, or scheduled flights. Rain uses
wind-slanted streaks and does not add to the snow bank. Hail uses round stones,
can bounce up to twice, and also does not become snow. Mixed mode uses
`--rain-share` and `--hail-share`; the remaining share is snow. Storm mode is a
rain/hail combination.

```sh
# Rain with occasional branched lightning
./scripts/macos/run-demo.sh pua4 christmas-snow \
  --weather rain --rain-speed 2.8 --rain-length 7 \
  --lightning --lightning-interval 12 --lightning-branches 5

# Snow, rain and hail together
./scripts/macos/run-demo.sh pua4 christmas-snow \
  --weather mixed --rain-share 0.35 --hail-share 0.10 \
  --hail-size 1.4 --hail-bounce 0.55
```

Rain and hail colours accept six hexadecimal RGB digits through
`--rain-colour` and `--hail-colour`. Lightning brightens the distant sky and
draws a white core, cyan glow and strong blue edge behind trees, cabins and
other foreground scenery. Its interval, flash
lifetime and branch count are live controls.

Every newly created snowflake, raindrop, and hailstone is assigned permanently
to either the foreground or background precipitation layer.
`--weather-foreground-share 0.45` means approximately 45% are painted after
the cabins, trees, and animals while the other 55% can be occluded by them.
Use `0` for entirely distant weather or `1` for weather entirely in front.
The WEATHER dashboard reports the current population in each layer.

```sh
# Sky, scenery and animals with no weather at all
./scripts/macos/run-demo.sh pua4 christmas-snow --weather none

# Put 70% of a windy rain shower in front of the scenery
./scripts/macos/run-demo.sh pua4 christmas-snow \
  --weather rain --weather-foreground-share 0.70 \
  --wind 8 --gust-strength 10
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

The console is divided into related pages instead of one oversized list:
`DISPLAY`, `WINDOW`, `LIVE`, `SNOW`, `SKY`, `CLOUDS`, `WEATHER`, `GROUND`,
`SCENE`, `TREES`, `ANIMALS`, and `FLIGHTS`. The active page is bracketed in the coloured
Unicode tab strip; narrow windows scroll the strip so the active page remains
visible. Each tab symbol has its own colour. The right-hand inspector uses
separate coloured sections for the current value, purpose, valid range,
predicted effect, and performance sensitivity.

Controller keys:

| Key | Operation |
|---|---|
| Tab / Shift-Tab | Move to the next / previous related option page |
| Up / Down, Page Up / Page Down, Home / End | Navigate every option |
| Left / Right | Move a numeric slider or cycle a choice |
| Space | Toggle an on/off option |
| Enter | Type an exact value; type `AUTO` for auto-sized controls |
| `V` | Launch a second window containing only the active tab's visual elements; WEATHER retains wind/gust behavior |
| `X` | Rebuild the listening viewer with the current configuration inside its existing terminal window, preserving OS position and size |
| `S` | Capture window geometry/font size, then save a JSON preset and adjacent standalone `.command.txt` launch command |
| `P` | Display a complete standalone command; it is also printed on exit |
| `R` | Restore defaults for the selected font mode |
| `Q` | Quit the controller; the viewer keeps its last accepted values |

`LIVE` options take effect on the next control poll (default 0.20 seconds).
The isolated visual previews use a black canvas so unrelated sky/scenery does
not mask the selected element. ANIMALS retains only a shallow flat baseline
needed by terrain-following animals. The CLOUDS preview retains only its sky
and configured depth lanes. DISPLAY, WINDOW, and LIVE contain no
drawable scene object, so their preview is the complete scene under those
meta-settings.
`RESTART` options affect raster construction or process lifetime; the TUI saves
them, but clearly identifies that the graphics viewer must be restarted. Press
`X` to publish a restart token: the listening viewer recreates its engine and
background in place, so the terminal window, font, position and current size do
not move. The
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
`FONT`, `SNOW`, `SKY`, `WEATHER`, `TREES`, `ANIMALS`, `FLIGHTS`, and `PROCESS`; the highlighted
name in the Unicode tab strip is the active page. Press `q` or `Esc` to leave
the animation. The terminal input mode is temporary and restored on exit.

- `FONT` separates the static repertoire, runtime-created count, distinct
  glyphs in the current frame, cumulative distinct glyphs seen since launch,
  active/blank cells, deduplication, and colour combinations.
- `SNOW` covers airborne particles, ground-bank mass, repose relaxation,
  broad/local shedding, and sparse object-snow catches and releases.
- `SKY` shows the current colour sequence, stop positions, blend curve, and
  layer order.
- `WEATHER` separates live snow/rain/hail counts, foreground/background
  populations, hail bounce settings, lightning timing and completed strikes.
- `TREES` shows species, density, branch formula controls, the segment budget,
  sway and object-snow state.
- `ANIMALS` shows NPC population/spawn/exit counts, steering and avoidance
  totals, the selected tracked identity, crossing/wander/social settings,
  rabbit states and depth lanes, postman state/deliveries, and terrain-blocked
  tumbleweed counts.
- `FLIGHTS` identifies the current distant event and aircraft type, schedule,
  Superman path/frequency/speed, Santa depth-scale range,
  ejected-pilot count, Santa scale/arc/trail state, and UFO vehicle,
  abduction/beam and plasma-trail state.
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
commuter aeroplane follows the supplied compact reference's rounded cream
fuselage, red tail, shaded belly, swept wings, windows and underslung engine;
the long airliner and olive helicopter have separate silhouettes. The kite is
a wind-wandering diamond with spars, a segmented line and coloured tail bows.
The UFO can be a layered saucer, orb or delta craft. Its tractor beam is
normally absent. With
`--ufo-abduction`, the UFO stops at mid-flight, the beam appears only while a
rabbit rises, and the rabbit steadily shrinks until its width is 10% of the
saucer. `--ufo-hover-seconds` controls the duration. Both flybys, plus the static
foreground reindeer, are now one third of their former linear scale so they
read as scene accents rather than dominating the landscape. Santa is half its
former linear size. It now separates sack and presents, Santa's
face, beard, hat, belt and mitten, the sleigh side panel and curled runners,
reins, and four reindeer with eyes, muzzles, ears, tails and four jointed legs.
The far and near leg pairs use different shades and gait phases for depth and a
more natural suspended gallop. The foreground seasonal reindeer remains a
separate design with the same anatomical and seasonal cues at its reduced size.

## What is prebuilt, generated, and cached

The PUA4 font is a static, prebuilt lookup repertoire containing all 65,536
possible 4×4 binary masks. Christmas Snow does not create or redefine a font
while it runs and it does not load cabin, tree, rabbit, aircraft, UFO, Santa,
or weather bitmap assets. Python constructs those objects as coloured
virtual-pixel geometry. The encoder examines each final 4×4 cell, converts its
16 occupied/unoccupied samples into a 16-bit mask, selects the corresponding
existing PUA4 codepoint, and emits ANSI foreground/background colours.

Caching already happens at two useful levels:

- expensive procedural tree geometry is held in a bounded in-memory cache,
  then wind-dependent sway is applied while it is composited. Sway displacement
  is calculated once per tree scanline and reused by all pixels on that row,
  avoiding repeated clamp/multiply/round work in the inner pixel loop.
- the postman's direction-, gait-, turn- and scale-specific procedural frames
  are held in a separate bounded cache. The process dashboard reports hit/miss
  totals for both tree geometry and postman frames.

The composed scenery surface itself is currently rebuilt each frame because
tree sway depends on live wind and time. Dirt and distant huts are deterministic
within that rebuild, not retained as a separate bitmap; splitting immutable
and swaying scenery into two cached layers is therefore a worthwhile next
optimization.

An optional dependency-free Rust terminal encoder now lives under
`native/seasonal_encoder`. Build it with:

```sh
cargo build --release --manifest-path native/seasonal_encoder/Cargo.toml
```

`--native-encoder auto` uses it when present and safely falls back to Python;
`off` forces the reference path and `on` requires Rust. It accelerates the
per-cell priority/mask/colour/error scan. Its shared ABI also performs complete
RGB, ANSI-256 and no-colour terminal emission for the older basic, vector, 3D,
PUA4 motion, Voyager and layered Voyager framebuffer demos.
Local repeated encoding was approximately twice as fast at both 120x36 and
168x60 cells, including marshaling. The verifier demands byte-for-byte ANSI and
telemetry parity whenever the release library is present.

The shared migration covers geometry, snow, starfield, trail, vector tunnel
(and its Elite/Defender users), Doom, Enterprise flyby/wireframe (and the
Spaceship importer), PUA4 Vortex/motion, Voyager recordings/model viewer, and
the two-colour layered Grand Tour. Triangle and vertical seam probes, font
catalogues/probes and the interactive editor intentionally retain their direct
terminal writers: they diagnose cursor placement or font behaviour rather
than encode a framebuffer, so routing them through the cell encoder would
change what they test. The animation/simulation logic remains Python; Rust owns
the repeated cell-to-terminal hot path, which preserves one behavioural
reference instead of duplicating every demo in two languages.

Further caching is viable, but whole pre-encoded frames would be a poor fit:
movement, arbitrary terminal sizes, cell alignment, foreground/background
occlusion, live colours, and snow depth change the final cells continuously.
A 303x46 full-physics comparison against the previous per-pixel sway algorithm
measured scenery at 44.465 -> 33.139 ms (25.5% lower) and the complete frame at
120.966 -> 110.645 ms (8.5% lower). The benchmark now uses the native encoder
when `--native-encoder auto` successfully loads it, matching the viewer.

Fresh full-engine profiling is recorded in
[`PERFORMANCE-2026-09-15.md`](PERFORMANCE-2026-09-15.md). At 303×46/full physics,
the Rust path measured 132.90 ms/frame: 62.4% scenery plus raster/compositing,
30.0% encoding (still including Python tuple packing), and 7.4% simulation plus
collision. The current Rust encoder reduced total time by 16.3% relative to the
Python encoder on that workload.

The next optimization boundary is therefore the tuple-based virtual-pixel
`Surface`, not a rewrite of the behavioural engine. A packed priority/RGB
buffer shared with Rust removes per-frame tuple marshalling and provides a
native target for batched rectangles, lines, polygons, accumulation and cached
tree compositing. Keep event/NPC/postman/rabbit logic and procedural art
definitions in Python. Fine-grained per-pixel FFI calls are explicitly avoided;
the native side must consume buffers or command batches. A sprite atlas remains
a possible later optimization for discrete poses, but profiling shows the
shared raster/store path is the broader target.

## Snow controls

| Control | Meaning |
|---|---|
| `--snow-rate` | Newly generated flakes per second |
| `--max-flakes` | Safety ceiling for simultaneously active flakes |
| `--flake-sizes` | Comma list drawn from `tiny,small,medium,large`; every size is sparse crystal/branch geometry, never a solid square block |
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
| `--snow-fallaway-threshold` | Sustained local bank-height fraction that starts a separate countdown |
| `--snow-fallaway-min-seconds` / `--snow-fallaway-max-seconds` | Seeded countdown range before that loaded area releases |
| `--snow-fallaway-width` | Width of each local mass release |
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
accumulation. Broad sheds and mass-triggered releases now preserve their
outside shoulder heights and use a smooth taper across both sides. They do not
wrap around viewport edges, so a release cannot leave ruler-straight vertical
walls or mirror part of itself onto the opposite side. The SNOW dashboard
reports mass fallaways separately from broad sheds and ordinary tower slumps,
including the largest active countdown and both configured trigger heights.
While a footprint is actively collapsing, it rejects new deposits and the
general angle-of-repose solver cannot refill it from the sides; snowfall still
accumulates everywhere outside that footprint. This guarantees the event can
finish and release the broad-shed slot for a later bank.

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

For the current full-engine workload and an explicit Python/Rust comparison:

```sh
cargo build --release --manifest-path native/seasonal_encoder/Cargo.toml
python3 demos/seasonal/benchmark_christmas_snow.py \
  --workload full --physics full --encoder both \
  --sky-event helicopter --start-seconds 15 \
  --viewport 120x36 --viewport 168x60 --viewport 303x46
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
cabin types and depth lanes, tumbleweed-aware rabbits, all seven sky events,
parallax clouds, complete plough clearing, rabbit perspective/occlusion,
360-degree NPC steering, scale/parallax, scenery occlusion, avoidance,
social response, replacement spawning and tracked-identity highlighting,
non-wrapping NPC terrain continuity and horizon-safe foot projection,
depth-stable existing-rabbit-only UFO capture, Santa depth zoom,
helicopter/kite/Superman rotation, enlarged moving pilot parachute, cached
all-cabin postman delivery, connected dirt routes, simultaneous multi-speed
Santa gifts, all helicopter landing/orientation phases, cargo/postman handling,
rotor weather/snow coupling and actor exclusion, AH-64/Airwolf yaw frames,
abandoned-aircraft crash arcs, heat-melted foreground snow, gradually fading
fiery and nuclear impacts, all transporter styles, blue-edged lightning, artificial
horizon structure, height-countdown snow release, and optional Rust/Python
encoder parity,
detailed reindeer and flyby pixel complexity, dashboard dimensions
and CPU/memory labels, per-option TUI icons and guidance, snapshot-window hold
behaviour, and an executable saved command containing literal shell
continuation backslashes. It also cross-checks draw-time exposed-surface indexing
and confirms that `none`, `ground` and `full` isolate their intended subsystems.

For continuation architecture, limitations, native phase-two work and a
zero-context runbook, read [HANDOVER-2026-09-12.md](HANDOVER-2026-09-12.md).
