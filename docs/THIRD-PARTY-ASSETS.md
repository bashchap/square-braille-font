# Third-party assets

The rendering engines and mesh-import tools are included, but the following
locally tested geometry is intentionally excluded from this repository.

## TOS Enterprise by Raul Mamoru

- Source: Trekmeshes.eu download `dl217`
- The author's supplied terms require attribution and state that the original
  model file must not be traded.
- The downloaded archive and derived `enterprise_tos_wire.npz` remain local.

## Supplied C4D spacecraft

- The source archive was supplied by the project owner for personal testing.
- A C4D HyperFile extraction produced an OBJ and derived NPZ caches.
- The source, OBJ and derived caches remain local until the repository owner
  confirms redistribution rights.

`demos/3d/convert_obj_mesh.py` and `simplify_mesh.py` can rebuild renderer
caches from a separately obtained, properly licensed OBJ file.

## Parametric Enterprise demonstration

`demos/3d/enterprise_flyby.py` generates its geometry programmatically and does
not embed a downloaded mesh. It remains a non-commercial technical font demo;
third-party names and marks belong to their respective owners.

