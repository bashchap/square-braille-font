# Voyager model source

The packaged `voyager-vtad-hlr.npz` cache is derived from NASA's official
**Voyager 3D Model**, credited by NASA to Visualization Technology Applications
and Development (VTAD):

- Source page: <https://science.nasa.gov/resource/voyager-3d-model/>
- Source format: glTF Binary 2.0
- Verified source SHA-256:
  `5338241f2e89e9cfe3ebb82f519b4cad64c97e66883cccba6fdda98667aec731`

The cache contains only normalized geometry and precomputed hidden-line
topology. It deliberately omits textures. Rebuild it with:

```bash
python3 prepare_model.py --source ../../local-assets/nasa-voyager/Voyager.glb
```

NASA assets remain subject to the
[NASA media usage guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/).
