# rubik

## Terminal Cube Preview

For a lightweight home-grown renderer that draws the cube directly in your terminal,
run:

```bash
python cube.py
```

It streams a continuously rotating ASCII cube with ANSI colors. Press `Ctrl+C` to exit.

### GPU requirements

The terminal renderer now runs entirely on the GPU via [CuPy](https://cupy.dev/). Install
the CUDA build that matches your driver stack (for current NVIDIA drivers on a 4090 this
is typically `cupy-cuda12x`):

```bash
pip install cupy-cuda12x
```

If CuPy or a CUDA-capable GPU is missing the program aborts immediately so you can fix
your environment before attempting to render.
