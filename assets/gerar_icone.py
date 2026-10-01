"""Gera assets/gaaa.ico a partir de assets/gaaa_logo.jpg (fundo branco, quadrado)."""
from pathlib import Path

from PIL import Image

PASTA = Path(__file__).resolve().parent

logo = Image.open(PASTA / 'gaaa_logo.jpg').convert('RGB')
lado = max(logo.size)
tela = Image.new('RGB', (lado, lado), 'white')
tela.paste(logo, ((lado - logo.size[0]) // 2, (lado - logo.size[1]) // 2))
tela.save(PASTA / 'gaaa.ico',
          sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print('gerado:', PASTA / 'gaaa.ico')
