"""Standalone LaDe stub for testing without Adobe's repo."""
from __future__ import annotations
import numpy as np
from PIL import Image

def generate(prompt, layer_names, width, height, num_inference_steps=28, seed=42,
             flux_path=None, vae_path=None):
    rng = np.random.default_rng(seed)
    result = {}
    for i, name in enumerate(layer_names):
        arr = np.zeros((height, width, 4), dtype=np.uint8)
        base = rng.integers(40, 220, size=3)
        arr[..., 0] = base[0]; arr[..., 1] = base[1]; arr[..., 2] = base[2]; arr[..., 3] = 255
        result[name] = Image.fromarray(arr, "RGBA")
    return result
