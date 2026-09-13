# Diagram atlas

This atlas is the visual index for the complete handover. The prose documents
remain authoritative for exact commands, hashes and limitations; these
diagrams show how the decisions and components relate.

## 1. Evolution of the project

```mermaid
flowchart LR
    A["Unicode Braille U+2800-U+28FF"] --> B["2x4 square-dot experiment"]
    B --> C["PUA 2x4 mapping U+E000-U+E0FF"]
    C --> D["Seamless Unicode 2x4 text font"]
    D --> E["Terminal graphics demos and VGR v1"]
    E --> F["PUA 4x4: 65,536 masks"]
    F --> G["Two-font P0/P1 split"]
    G --> H["Candidate lineage and raster audits"]
    H --> I["Candidate 6 Linux RC"]
    I --> J["Depth and two-colour composition"]
    J --> K["FontPlotter RAM framebuffer service"]
    K --> L["Backups, blits, diagnostics and VGR v2"]
```

## 2. Repository, runtime and display boundary

```mermaid
flowchart TB
    subgraph Source["Source and assets"]
        R1["square-braille-font repository"]
        R2["FontPlotter sibling project"]
        F2["2x4 TTF and OTF"]
        F4["4x4 P0 and P1 TTFs"]
        M["NASA and licensed model assets"]
    end

    subgraph Runtime["Runtime"]
        C["Drawing or demo client"]
        S["Framebuffer service"]
        B["Virtual-pixel buffer<br/>RGBA + depth + occupancy"]
        E["2x4 or 4x4 terminal encoder"]
        V["VGR capture and player"]
    end

    subgraph Terminal["Terminal presentation"]
        T["Terminal cells"]
        FS["Font selection and fallback"]
        RR["Terminal rasterizer"]
        P["Physical pixels"]
    end

    R1 --> F2
    R1 --> F4
    R1 --> C
    R2 --> C
    R2 --> S
    M --> C
    C <--> S
    S <--> B
    B --> E
    E --> V
    E --> T
    V --> T
    F2 --> FS
    F4 --> FS
    T --> FS --> RR --> P
```

## 3. A terminal cell becomes a virtual-pixel grid

```mermaid
flowchart LR
    A["Terminal cell at zero-based (cx, cy)"] --> B["4 columns x 4 rows inside the cell"]
    B --> C["Virtual origin (4*cx, 4*cy)"]
    C --> D["Any virtual pixel (vx, vy)"]
    D --> E["cx = vx div 4<br/>cy = vy div 4"]
    D --> F["lx = vx mod 4<br/>ly = vy mod 4"]
    E --> G["ANSI cursor row = cy + 1<br/>ANSI cursor column = cx + 1"]
    F --> H["bit = 4*ly + (3-lx)"]
```

An 80-column by 24-row terminal therefore exposes a virtual canvas of
`320 x 96` addressable pixels when the 4x4 family is active.

## 4. Exact 4x4 bit layout

The display coordinates increase left-to-right and top-to-bottom. Within each
row, the numeric bit significance is MSB-left:

```text
local x       0       1       2       3
local y 0   bit 3   bit 2   bit 1   bit 0
local y 1   bit 7   bit 6   bit 5   bit 4
local y 2  bit 11  bit 10   bit 9   bit 8
local y 3  bit 15  bit 14  bit 13  bit 12
```

```mermaid
flowchart LR
    V["virtual pixel (vx, vy)"] --> L["local (lx, ly)"]
    L --> B["b = 4*ly + 3-lx"]
    B --> Q["bit value = 1 << b"]
    Q --> O["OR into the cell mask"]
    O --> M["16-bit mask 0x0000-0xFFFF"]
    M --> CP{"mask < 0x8000?"}
    CP -->|yes| P0["P0 codepoint = U+0F0000 + mask"]
    CP -->|no| P1["P1 codepoint = U+100000 + mask-0x8000"]
```

The inverse path recovers the mask from the selected P0 or P1 codepoint and
tests bit `b` to determine whether local pixel `(lx, ly)` is active.

## 5. Why the 4x4 family needs two fonts

```mermaid
flowchart TB
    ALL["65,536 possible 16-bit masks"] --> A["P0: masks 0x0000-0x7FFF<br/>32,768 glyphs<br/>U+0F0000-U+0F7FFF"]
    ALL --> B["P1: masks 0x8000-0xFFFF<br/>32,768 glyphs<br/>U+100000-U+107FFF"]
    A --> C["Font fallback alias selects P0"]
    B --> D["Font fallback alias selects P1"]
    C --> E["Both ranges occupy one terminal column"]
    D --> E
```

The split is a mapping and packaging boundary. It does not change the 16-bit
mask or the drawing mathematics.

## 6. Candidate lineage and evidence gates

```mermaid
flowchart LR
    C3["Candidate 3<br/>100-unit guard on all edges"] --> A1["Removed normal seams"]
    C3 --> F1["Failed horizontal colour ownership"]
    F1 --> C4["Candidate 4<br/>strict x ownership and corrected bearings"]
    C4 --> A2["Passed mapping and horizontal ownership"]
    C4 --> F2["Real terminal exposed row seams"]
    F2 --> C6["Candidate 6<br/>vertical guard only"]
    C6 --> A3["PASS normal/enlarged MATE sizes"]
    C6 --> L["Known limit: two smallest Ctrl-minus sizes may seam"]
```

The release gate always includes the real terminal. Outline bounds, FreeType
and Pango are necessary evidence, but none can prove final raster behaviour by
itself.

## 7. Raster diagnosis layers

```mermaid
flowchart LR
    S["Source mask and expected squares"] --> O["Font outline geometry"]
    O --> H["TrueType hinting and grid fitting"]
    H --> L["Pango line and cell layout"]
    L --> R["Terminal rasterizer at an exact size"]
    R --> I["Captured image and pixel audit"]
    I --> D{"Expected equals observed?"}
    D -->|no| X["Record exact font, size, zoom, terminal and mask"]
    D -->|yes| G["Advance the release gate"]
```

## 8. Depth-aware, two-colour reduction

```mermaid
flowchart TB
    P["Per virtual pixel samples<br/>colour + depth + occupied"] --> Z["Depth test chooses nearest visible sample"]
    Z --> C["Collect visible colours in one terminal cell"]
    C --> BG["Choose background owner"]
    C --> FG["Choose foreground detail owner"]
    BG --> EN["Encode background colour, foreground colour and 16-bit mask"]
    FG --> EN
    EN --> T["One terminal cell with two colour planes"]
```

This policy avoids blindly OR-ing a foreground spacecraft into an already
full planet cell. It deliberately preserves the nearer detail, while accepting
that a terminal cell can display at most one foreground mask plus one
background colour.

## 9. Persistent RAM framebuffer and reversible operations

```mermaid
sequenceDiagram
    participant C as CLI or Python client
    participant S as FontPlotter service
    participant B as Named RAM framebuffer
    participant U as Undo or backup object
    participant T as Terminal blitter

    C->>S: create buffer width x height
    S->>B: allocate pixel records
    C->>S: primitive or batch of operations
    S->>U: retain changed region and metadata
    S->>B: depth-aware, forced or logical update
    C->>S: copy, move, paste, merge or restore
    S->>B: apply selected composition mode
    C->>S: viewport in virtual coordinates
    S->>T: encode only requested region
    C->>S: save buffer, logs or backup on command
```

The service exists so separately invoked clients can share one live memory
buffer. Files are persistence checkpoints, not the normal working store.

## 10. VGR capture and replay

```mermaid
sequenceDiagram
    participant R as Renderer
    participant E as Cell encoder
    participant W as VGR writer
    participant F as VGR file
    participant P as Player
    participant T as Terminal

    loop every captured frame
        R->>E: virtual-pixel frame
        E->>W: masks, colours and metadata
        W->>F: compressed indexed frame packet
    end
    P->>F: read header, dimensions, fps and frames
    loop playback timing
        F-->>P: next frame packet
        P->>T: render at recorded cell dimensions
    end
```

VGR stores rendered terminal-frame data and timing metadata. It is not a video
codec and it is not a raw 3D scene. A recording that contains only a few frames
will remain small regardless of how long a process stayed alive; this is why
frame count and capture progress must be monitored independently of elapsed
wall time.

## 11. Current priorities and proof gates

```mermaid
flowchart TB
    P0["Preserve released 2x4 assets and Candidate 6 evidence"] --> P1["Commit and publish the dirty local work intentionally"]
    P1 --> P2["Promote Candidate 6 only after platform-specific raster proof"]
    P2 --> P3["Keep FontPlotter semantics independent of demos"]
    P3 --> P4["Complete multi-client concurrency and performance work"]
    P4 --> P5["Use visual diagnostics to prove plotting, restore and blit behaviour"]

    G1["Gate: mapping proof"] --> G2["Gate: font outline and width proof"]
    G2 --> G3["Gate: real terminal raster proof"]
    G3 --> G4["Gate: framebuffer semantic proof"]
    G4 --> G5["Gate: end-to-end capture and replay proof"]
```

The first rule for the next collaborator is to preserve evidence. Do not clean
the worktree, overwrite historical candidates or replace a real-terminal
observation with an inferred claim.
