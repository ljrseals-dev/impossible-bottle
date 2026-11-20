"""OmniPSD stub script — mimics OUTPUT_ROOT contract for wrapper tests."""
from pathlib import Path
import numpy as np
from PIL import Image

INPUT_TXT_DIR = "REPLACE_ME"
OUTPUT_ROOT = "REPLACE_ME"
LORA_PATH = "REPLACE_ME"

def main():
    input_dir = Path(INPUT_TXT_DIR)
    output_dir = Path(OUTPUT_ROOT)
    output_dir.mkdir(parents=True, exist_ok=True)
    for src in sorted(input_dir.glob("*.png")):
        im = Image.open(src).convert("RGBA")
        arr = np.array(im).astype(np.float32)
        lum = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
        bands = np.linspace(0, 255, 7)
        for i in range(6):
            lo, hi = bands[i], bands[i + 1]
            alpha = ((lum >= lo) & (lum < hi)).astype(np.uint8) * 255
            out = arr.astype(np.uint8).copy()
            out[..., 3] = alpha
            Image.fromarray(out, "RGBA").save(output_dir / f"layer_{i:02d}.png")

if __name__ == "__main__":
    main()
