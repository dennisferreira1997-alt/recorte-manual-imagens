"""Build assets/gaaa.ico from assets/gaaa_logo.jpg (white background, square)."""
from pathlib import Path

from PIL import Image

FOLDER = Path(__file__).resolve().parent

logo = Image.open(FOLDER / 'gaaa_logo.jpg').convert('RGB')
side = max(logo.size)
canvas = Image.new('RGB', (side, side), 'white')
canvas.paste(logo, ((side - logo.size[0]) // 2, (side - logo.size[1]) // 2))
canvas.save(FOLDER / 'gaaa.ico',
            sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print('written:', FOLDER / 'gaaa.ico')
