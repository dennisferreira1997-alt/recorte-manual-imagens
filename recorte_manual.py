"""
recorte_manual.py
=================
Ferramenta visual (Tkinter + Pillow) para recortar regioes de interesse (ROIs)
de um conjunto de imagens, no estilo dos recortes usados no artigo das
especiarias: varias sub-imagens extraidas de cada foto da amostra.

Tres modos de trabalho, combinaveis:

  1) SELECAO LIVRE   - arrasta o mouse e desenha o retangulo em cada imagem.
  2) TAMANHO FIXO    - define largura x altura em pixels e so clica no centro
                       da regiao desejada (todos os recortes ficam do mesmo
                       tamanho, essencial para comparar histogramas de cor).
  3) ROI TRAVADA     - marca a regiao uma vez e ela e reaproveitada em todas as
                       imagens seguintes (basta apertar Enter em cada uma), ou
                       aplicada de uma vez a pasta inteira ("Aplicar a todas").

Cada ROI pode ainda ser subdividida em uma grade linhas x colunas, gerando
N sub-recortes por regiao (util para multiplicar amostras por foto).

Todos os recortes sao feitos na resolucao ORIGINAL da imagem (o zoom da tela
so afeta a visualizacao) e as coordenadas sao gravadas em um CSV, de modo que
o recorte e reproduzivel/reexecutavel depois.

USO BASICO (janela grafica)
---------------------------
    .venv\\Scripts\\python.exe recorte_manual.py
    .venv\\Scripts\\python.exe recorte_manual.py --entrada imagens --saida recortes

USO EM LOTE (sem janela)
------------------------
    # mesma ROI em todas as imagens da pasta, dividida em 2x3 sub-recortes
    python recorte_manual.py --entrada imagens --saida recortes \\
        --roi 300,200,600,400 --grade 2x3 --lote

    # refazer exatamente os recortes de uma sessao anterior
    python recorte_manual.py --entrada imagens --saida recortes2 \\
        --csv recortes/recortes_coords.csv

ATALHOS DE TECLADO
------------------
    Enter          salva os recortes da imagem atual e avanca
    Seta direita   proxima imagem          Seta esquerda   imagem anterior
    Delete         remove a ultima ROI     C               limpa as ROIs
    T              liga/desliga ROI travada
    + / -          zoom                    0               ajustar a janela
    F1             janela "Sobre" (creditos)

CREDITOS
--------
    Desenvolvido pelo grupo de pesquisa GAAA
    (Grupo de Abordagens Analiticas Alternativas)
    Software criado por Dennis da Silva Ferreira
"""

import argparse
import csv
import os
import sys
from pathlib import Path

from PIL import Image, ImageOps

EXTENSOES = ('.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.webp')
NOME_CSV = 'recortes_coords.csv'

# ---- identificacao do programa (usada na janela "Sobre" e no executavel) ----
APP_NOME = 'Recorte Manual de Imagens'
APP_VERSAO = '1.0'
APP_AUTOR = 'Dennis da Silva Ferreira'
APP_GRUPO = 'Grupo de Abordagens Analiticas Alternativas (GAAA)'
APP_ANO = '2026'
ARQUIVO_LOGO = 'gaaa_logo.jpg'
ARQUIVO_ICONE = 'gaaa.ico'
COLUNAS_CSV = ['imagem', 'roi', 'grade_linha', 'grade_coluna',
               'x', 'y', 'largura', 'altura',
               'largura_original', 'altura_original', 'arquivo_saida']


def caminho_recurso(nome):
    """
    Localiza um arquivo da pasta `assets` tanto rodando o .py quanto dentro do
    executavel gerado pelo PyInstaller (que descompacta tudo em sys._MEIPASS).

    Retorna None quando o recurso nao esta disponivel, para que a interface
    continue funcionando mesmo sem a logomarca.
    """
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    for candidato in (base / 'assets' / nome, base / nome):
        if candidato.exists():
            return candidato
    return None


# =============================================================================
# 1. NUCLEO SEM INTERFACE (tambem usado pelo modo em lote)
# =============================================================================
def listar_imagens(pasta):
    """Retorna a lista ordenada de imagens de uma pasta (sem recursao)."""
    pasta = Path(pasta)
    return sorted(p for p in pasta.iterdir()
                  if p.is_file() and p.suffix.lower() in EXTENSOES)


def abrir_imagem(caminho):
    """Abre a imagem em RGB ja corrigindo a orientacao gravada no EXIF."""
    img = Image.open(caminho)
    img = ImageOps.exif_transpose(img)
    return img.convert('RGB')


def recortar_roi(x, y, largura, altura, limites):
    """Ajusta uma ROI para dentro dos limites (largura, altura) da imagem."""
    lim_w, lim_h = limites
    x0 = max(0, min(int(round(x)), lim_w))
    y0 = max(0, min(int(round(y)), lim_h))
    x1 = max(0, min(int(round(x + largura)), lim_w))
    y1 = max(0, min(int(round(y + altura)), lim_h))
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    return x0, y0, x1 - x0, y1 - y0


def dividir_em_grade(roi, n_linhas, n_colunas):
    """
    Divide uma ROI (x, y, largura, altura) em n_linhas x n_colunas blocos.

    Retorna uma lista de tuplas (linha, coluna, x, y, largura, altura) com
    bordas inteiras e sem sobreposicao; (1, 1, ...) quando a grade e 1x1.
    """
    x, y, largura, altura = roi
    n_linhas = max(1, int(n_linhas))
    n_colunas = max(1, int(n_colunas))

    bordas_x = [x + round(largura * i / n_colunas) for i in range(n_colunas + 1)]
    bordas_y = [y + round(altura * j / n_linhas) for j in range(n_linhas + 1)]

    blocos = []
    for j in range(n_linhas):
        for i in range(n_colunas):
            bx, by = bordas_x[i], bordas_y[j]
            bw, bh = bordas_x[i + 1] - bx, bordas_y[j + 1] - by
            if bw > 0 and bh > 0:
                blocos.append((j + 1, i + 1, bx, by, bw, bh))
    return blocos


def salvar_recortes(caminho_imagem, rois, pasta_saida, n_linhas=1, n_colunas=1,
                    formato='png', subpasta_por_imagem=False, img=None):
    """
    Recorta e grava no disco todas as ROIs de uma imagem.

    Parametros
    ----------
    caminho_imagem : Path - imagem de origem
    rois : lista de (x, y, largura, altura) em pixels da imagem ORIGINAL
    pasta_saida : Path - destino dos recortes
    n_linhas, n_colunas : subdivisao de cada ROI em grade
    formato : 'png', 'jpg', 'tif', ... (extensao do arquivo de saida)
    subpasta_por_imagem : se True, cria pasta_saida/<nome_da_imagem>/

    Retorna
    -------
    lista de dicionarios prontos para o CSV de coordenadas
    """
    caminho_imagem = Path(caminho_imagem)
    if img is None:
        img = abrir_imagem(caminho_imagem)

    destino = Path(pasta_saida)
    if subpasta_por_imagem:
        destino = destino / caminho_imagem.stem
    destino.mkdir(parents=True, exist_ok=True)

    formato = formato.lower().lstrip('.')
    nome_pillow = 'JPEG' if formato in ('jpg', 'jpeg') else None
    registros = []

    for indice, roi in enumerate(rois, start=1):
        x, y, largura, altura = recortar_roi(*roi, limites=img.size)
        if largura <= 0 or altura <= 0:
            continue

        for linha, coluna, bx, by, bw, bh in dividir_em_grade(
                (x, y, largura, altura), n_linhas, n_colunas):

            sufixo = f'_roi{indice:02d}'
            if n_linhas > 1 or n_colunas > 1:
                sufixo += f'_l{linha}c{coluna}'
            arquivo = destino / f'{caminho_imagem.stem}{sufixo}.{formato}'

            recorte = img.crop((bx, by, bx + bw, by + bh))
            if nome_pillow == 'JPEG':
                recorte.save(arquivo, 'JPEG', quality=95, subsampling=0)
            else:
                recorte.save(arquivo)

            registros.append({
                'imagem': caminho_imagem.name,
                'roi': indice,
                'grade_linha': linha,
                'grade_coluna': coluna,
                'x': bx, 'y': by, 'largura': bw, 'altura': bh,
                'largura_original': img.size[0],
                'altura_original': img.size[1],
                'arquivo_saida': str(arquivo.relative_to(pasta_saida)),
            })

    return registros


def registrar_no_csv(pasta_saida, registros):
    """Acrescenta os registros ao CSV de coordenadas (criando o cabecalho)."""
    if not registros:
        return None
    pasta_saida = Path(pasta_saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)
    caminho = pasta_saida / NOME_CSV
    novo = not caminho.exists()
    with open(caminho, 'a', newline='', encoding='utf-8') as f:
        escritor = csv.DictWriter(f, fieldnames=COLUNAS_CSV)
        if novo:
            escritor.writeheader()
        escritor.writerows(registros)
    return caminho


def aplicar_em_lote(pasta_entrada, pasta_saida, rois, n_linhas=1, n_colunas=1,
                    formato='png', subpasta_por_imagem=False, log=print):
    """Aplica as mesmas ROIs a todas as imagens da pasta (sem interface)."""
    imagens = listar_imagens(pasta_entrada)
    if not imagens:
        log(f'Nenhuma imagem encontrada em {pasta_entrada}')
        return 0

    total = 0
    for caminho in imagens:
        registros = salvar_recortes(caminho, rois, pasta_saida,
                                    n_linhas, n_colunas, formato,
                                    subpasta_por_imagem)
        registrar_no_csv(pasta_saida, registros)
        total += len(registros)
        log(f'{caminho.name}: {len(registros)} recorte(s)')
    log(f'Total: {total} recortes em {pasta_saida}')
    return total


def refazer_do_csv(caminho_csv, pasta_entrada, pasta_saida, formato='png',
                   log=print):
    """
    Reexecuta os recortes descritos em um CSV gerado por esta ferramenta.

    Cada linha do CSV ja traz x/y/largura/altura finais (grade resolvida), por
    isso os recortes saem identicos aos da sessao original.
    """
    pasta_entrada, pasta_saida = Path(pasta_entrada), Path(pasta_saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)
    formato = formato.lower().lstrip('.')

    with open(caminho_csv, newline='', encoding='utf-8') as f:
        linhas = list(csv.DictReader(f))

    cache_nome, cache_img = None, None
    total = 0
    for linha in linhas:
        nome = linha['imagem']
        if nome != cache_nome:
            caminho = pasta_entrada / nome
            if not caminho.exists():
                log(f'AVISO: {nome} nao encontrada em {pasta_entrada}')
                cache_nome, cache_img = nome, None
                continue
            cache_nome, cache_img = nome, abrir_imagem(caminho)
        if cache_img is None:
            continue

        x, y = int(linha['x']), int(linha['y'])
        w, h = int(linha['largura']), int(linha['altura'])
        saida = pasta_saida / Path(linha['arquivo_saida']).with_suffix(f'.{formato}')
        saida.parent.mkdir(parents=True, exist_ok=True)
        recorte = cache_img.crop((x, y, x + w, y + h))
        if formato in ('jpg', 'jpeg'):
            recorte.save(saida, 'JPEG', quality=95, subsampling=0)
        else:
            recorte.save(saida)
        total += 1

    log(f'{total} recortes refeitos em {pasta_saida}')
    return total


# =============================================================================
# 2. INTERFACE GRAFICA
# =============================================================================
def aplicar_icone(janela):
    """Coloca o icone do GAAA na barra de titulo (ignorado se nao houver .ico)."""
    icone = caminho_recurso(ARQUIVO_ICONE)
    if icone is None:
        return
    try:
        janela.iconbitmap(str(icone))
    except Exception:
        pass


def mostrar_sobre(pai=None):
    """Abre a janela 'Sobre' com a logomarca do grupo de pesquisa e os creditos."""
    import tkinter as tk
    from tkinter import ttk

    janela = tk.Toplevel(pai) if pai is not None else tk.Tk()
    janela.title(f'Sobre - {APP_NOME}')
    janela.configure(bg='white')
    janela.resizable(False, False)
    aplicar_icone(janela)

    quadro = ttk.Frame(janela, padding=16)
    quadro.pack(fill='both', expand=True)

    logo = caminho_recurso(ARQUIVO_LOGO)
    if logo is not None:
        try:
            from PIL import ImageTk
            imagem = abrir_imagem(logo)
            caixa = 240          # a logomarca cabe em um quadrado de 240 px
            escala = min(1.0, caixa / imagem.size[0], caixa / imagem.size[1])
            imagem = imagem.resize((max(1, int(imagem.size[0] * escala)),
                                    max(1, int(imagem.size[1] * escala))),
                                   Image.LANCZOS)
            janela.foto_logo = ImageTk.PhotoImage(imagem)   # evita a coleta
            ttk.Label(quadro, image=janela.foto_logo).pack(pady=(0, 12))
        except Exception:
            pass

    ttk.Label(quadro, text=f'{APP_NOME}  v{APP_VERSAO}',
              font=('', 13, 'bold')).pack()
    ttk.Label(quadro, text='Recorte de regioes de interesse (ROIs) em lotes de imagens',
              wraplength=340, justify='center',
              foreground='#444444').pack(pady=(2, 12))

    ttk.Separator(quadro).pack(fill='x', pady=4)
    ttk.Label(quadro, text='Desenvolvido pelo grupo de pesquisa GAAA',
              wraplength=340, justify='center', font=('', 10, 'bold')).pack(pady=(8, 0))
    ttk.Label(quadro, text=APP_GRUPO, wraplength=340, justify='center',
              foreground='#444444').pack()
    ttk.Label(quadro, text=f'Software criado por {APP_AUTOR}',
              wraplength=340, justify='center').pack(pady=(8, 0))
    ttk.Label(quadro, text=f'{APP_ANO} - uso academico e cientifico',
              foreground='#777777').pack(pady=(6, 10))

    ttk.Button(quadro, text='Fechar', command=janela.destroy).pack()

    janela.update_idletasks()
    if pai is not None:
        x = pai.winfo_rootx() + (pai.winfo_width() - janela.winfo_width()) // 2
        y = pai.winfo_rooty() + (pai.winfo_height() - janela.winfo_height()) // 3
        janela.geometry(f'+{max(0, x)}+{max(0, y)}')
        janela.transient(pai)
        janela.grab_set()
    janela.bind('<Escape>', lambda e: janela.destroy())
    janela.focus_set()
    return janela


class RecortadorApp:
    """Janela de recorte manual: canvas com a imagem + painel de controle."""

    def __init__(self, raiz, pasta_entrada=None, pasta_saida=None,
                 formato='png'):
        import tkinter as tk
        from tkinter import ttk

        self.tk, self.ttk = tk, ttk
        self.raiz = raiz
        raiz.title(f'{APP_NOME} v{APP_VERSAO} - GAAA')
        # nunca maior que a tela: em notebooks de 768 px o painel lateral ficaria
        # cortado e o botao "Sobre" sairia da area visivel
        largura = min(1200, raiz.winfo_screenwidth() - 80)
        altura = min(780, raiz.winfo_screenheight() - 120)
        raiz.geometry(f'{max(900, largura)}x{max(600, altura)}')
        raiz.minsize(900, 600)
        aplicar_icone(raiz)

        self.pasta_entrada = Path(pasta_entrada) if pasta_entrada else None
        self.pasta_saida = Path(pasta_saida) if pasta_saida else None
        self.imagens = []
        self.indice = 0
        self.img = None            # PIL.Image da imagem atual
        self.foto = None           # referencia do ImageTk (evita coleta)
        self.escala = 1.0
        self.zoom_manual = None    # None = ajustar a janela
        self.rois = []             # ROIs da imagem atual, coords originais
        self.rois_travadas = []    # ROIs reaproveitadas na proxima imagem
        self.salvas = set()
        self._arraste = None
        self._roi_temp = None

        # ---- variaveis dos controles ----
        self.var_travar = tk.BooleanVar(value=False)
        self.var_fixo = tk.BooleanVar(value=False)
        self.var_larg = tk.StringVar(value='400')
        self.var_alt = tk.StringVar(value='400')
        self.var_linhas = tk.StringVar(value='1')
        self.var_colunas = tk.StringVar(value='1')
        self.var_formato = tk.StringVar(value=formato)
        self.var_subpasta = tk.BooleanVar(value=False)
        self.var_status = tk.StringVar(value='Abra a pasta com as imagens.')
        self.var_cursor = tk.StringVar(value='')

        self._montar_interface()
        self._ligar_eventos()

        if self.pasta_entrada:
            self.carregar_pasta(self.pasta_entrada)

    # ------------------------------------------------------------------ layout
    def _montar_interface(self):
        tk, ttk = self.tk, self.ttk

        painel = ttk.Frame(self.raiz, padding=8)
        painel.pack(side='right', fill='y')

        # o rodape e empacotado primeiro, ancorado embaixo, para que os creditos
        # continuem visiveis mesmo quando a janela esta baixa e o painel enche
        rodape = ttk.Frame(painel)
        rodape.pack(side='bottom', fill='x', pady=(6, 0))
        ttk.Separator(rodape).pack(fill='x', pady=4)
        ttk.Button(rodape, text='Sobre (F1)',
                   command=lambda: mostrar_sobre(self.raiz)).pack(fill='x', pady=2)
        ttk.Label(rodape, text=f'GAAA - {APP_AUTOR}', wraplength=230,
                  foreground='#777777', font=('', 8)).pack(anchor='w')

        area = ttk.Frame(self.raiz)
        area.pack(side='left', fill='both', expand=True)

        self.canvas = tk.Canvas(area, bg='#222222', highlightthickness=0,
                                cursor='crosshair')
        barra_v = ttk.Scrollbar(area, orient='vertical', command=self.canvas.yview)
        barra_h = ttk.Scrollbar(area, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=barra_v.set, xscrollcommand=barra_h.set)
        barra_v.pack(side='right', fill='y')
        barra_h.pack(side='bottom', fill='x')
        self.canvas.pack(side='left', fill='both', expand=True)

        ttk.Label(painel, text='Pastas', font=('', 10, 'bold')).pack(anchor='w')
        ttk.Button(painel, text='Abrir pasta de imagens...',
                   command=self.escolher_entrada).pack(fill='x', pady=2)
        ttk.Button(painel, text='Pasta de saida...',
                   command=self.escolher_saida).pack(fill='x', pady=2)
        self.rotulo_saida = ttk.Label(painel, text='saida: -', wraplength=230,
                                      foreground='#555555')
        self.rotulo_saida.pack(anchor='w', pady=(0, 6))

        ttk.Separator(painel).pack(fill='x', pady=4)
        ttk.Label(painel, text='Imagem', font=('', 10, 'bold')).pack(anchor='w')
        self.rotulo_imagem = ttk.Label(painel, text='-', wraplength=230)
        self.rotulo_imagem.pack(anchor='w')
        nav = ttk.Frame(painel)
        nav.pack(fill='x', pady=4)
        ttk.Button(nav, text='<< Anterior',
                   command=lambda: self.trocar_imagem(-1)).pack(side='left', expand=True, fill='x')
        ttk.Button(nav, text='Proxima >>',
                   command=lambda: self.trocar_imagem(1)).pack(side='left', expand=True, fill='x')

        zoom = ttk.Frame(painel)
        zoom.pack(fill='x')
        ttk.Button(zoom, text='-', width=3,
                   command=lambda: self.ajustar_zoom(1 / 1.25)).pack(side='left')
        ttk.Button(zoom, text='+', width=3,
                   command=lambda: self.ajustar_zoom(1.25)).pack(side='left')
        ttk.Button(zoom, text='Ajustar a janela',
                   command=self.zoom_ajustar).pack(side='left', expand=True, fill='x')

        ttk.Separator(painel).pack(fill='x', pady=4)
        ttk.Label(painel, text='Modo de selecao', font=('', 10, 'bold')).pack(anchor='w')
        ttk.Checkbutton(painel, text='Tamanho fixo (clique no centro)',
                        variable=self.var_fixo).pack(anchor='w')
        tamanho = ttk.Frame(painel)
        tamanho.pack(fill='x', pady=2)
        ttk.Label(tamanho, text='larg').pack(side='left')
        ttk.Entry(tamanho, textvariable=self.var_larg, width=6).pack(side='left', padx=2)
        ttk.Label(tamanho, text='x alt').pack(side='left')
        ttk.Entry(tamanho, textvariable=self.var_alt, width=6).pack(side='left', padx=2)
        ttk.Label(tamanho, text='px').pack(side='left')
        ttk.Checkbutton(painel, text='Travar ROIs para as proximas imagens',
                        variable=self.var_travar,
                        command=self.atualizar_travamento).pack(anchor='w', pady=2)

        ttk.Separator(painel).pack(fill='x', pady=4)
        ttk.Label(painel, text='Grade dentro de cada ROI',
                  font=('', 10, 'bold')).pack(anchor='w')
        grade = ttk.Frame(painel)
        grade.pack(fill='x', pady=2)
        ttk.Label(grade, text='linhas').pack(side='left')
        ttk.Entry(grade, textvariable=self.var_linhas, width=4).pack(side='left', padx=2)
        ttk.Label(grade, text='colunas').pack(side='left')
        ttk.Entry(grade, textvariable=self.var_colunas, width=4).pack(side='left', padx=2)
        ttk.Button(grade, text='Ver', width=5,
                   command=self.redesenhar).pack(side='left', padx=2)

        ttk.Separator(painel).pack(fill='x', pady=4)
        ttk.Label(painel, text='ROIs da imagem atual',
                  font=('', 10, 'bold')).pack(anchor='w')
        self.lista = tk.Listbox(painel, height=7, exportselection=False)
        self.lista.pack(fill='x', pady=2)
        botoes_roi = ttk.Frame(painel)
        botoes_roi.pack(fill='x')
        ttk.Button(botoes_roi, text='Remover (Del)',
                   command=self.remover_roi).pack(side='left', expand=True, fill='x')
        ttk.Button(botoes_roi, text='Limpar (C)',
                   command=self.limpar_rois).pack(side='left', expand=True, fill='x')

        ttk.Separator(painel).pack(fill='x', pady=4)
        ttk.Label(painel, text='Saida', font=('', 10, 'bold')).pack(anchor='w')
        fmt = ttk.Frame(painel)
        fmt.pack(fill='x', pady=2)
        ttk.Label(fmt, text='formato').pack(side='left')
        ttk.Combobox(fmt, textvariable=self.var_formato, width=7,
                     values=('png', 'jpg', 'tif'),
                     state='readonly').pack(side='left', padx=4)
        ttk.Checkbutton(painel, text='Subpasta por imagem',
                        variable=self.var_subpasta).pack(anchor='w')
        ttk.Button(painel, text='Salvar recortes e avancar (Enter)',
                   command=self.salvar_e_avancar).pack(fill='x', pady=(6, 2))
        ttk.Button(painel, text='Aplicar estas ROIs a TODAS as imagens',
                   command=self.aplicar_todas).pack(fill='x', pady=2)

        ttk.Separator(painel).pack(fill='x', pady=4)
        ttk.Label(painel, textvariable=self.var_cursor,
                  foreground='#444444').pack(anchor='w')
        ttk.Label(painel, textvariable=self.var_status, wraplength=230,
                  foreground='#0a5a0a').pack(anchor='w', pady=4)

    def _ligar_eventos(self):
        self.canvas.bind('<ButtonPress-1>', self.mouse_press)
        self.canvas.bind('<B1-Motion>', self.mouse_drag)
        self.canvas.bind('<ButtonRelease-1>', self.mouse_release)
        self.canvas.bind('<Motion>', self.mouse_move)
        self.canvas.bind('<Configure>', lambda e: self.redesenhar())
        self.canvas.bind('<MouseWheel>', self.mouse_wheel)
        self.lista.bind('<<ListboxSelect>>', lambda e: self.redesenhar())

        for sequencia, funcao in (
                ('<Right>', lambda e: self.trocar_imagem(1)),
                ('<Left>', lambda e: self.trocar_imagem(-1)),
                ('<Return>', lambda e: self.salvar_e_avancar()),
                ('<Delete>', lambda e: self.remover_roi()),
                ('<BackSpace>', lambda e: self.remover_roi()),
                ('<c>', lambda e: self.limpar_rois()),
                ('<C>', lambda e: self.limpar_rois()),
                ('<t>', lambda e: self.alternar_travamento()),
                ('<T>', lambda e: self.alternar_travamento()),
                ('<plus>', lambda e: self.ajustar_zoom(1.25)),
                ('<equal>', lambda e: self.ajustar_zoom(1.25)),
                ('<minus>', lambda e: self.ajustar_zoom(1 / 1.25)),
                ('<Key-0>', lambda e: self.zoom_ajustar()),
                ('<F1>', lambda e: mostrar_sobre(self.raiz)),
        ):
            self.raiz.bind(sequencia, self._so_fora_de_campos(funcao))

    def _so_fora_de_campos(self, funcao):
        """Evita que os atalhos disparem enquanto o foco esta em um Entry."""
        def envolvido(evento):
            foco = self.raiz.focus_get()
            if foco is not None and foco.winfo_class() in ('TEntry', 'Entry', 'TCombobox'):
                return None
            return funcao(evento)
        return envolvido

    # ------------------------------------------------------------------ pastas
    def escolher_entrada(self):
        from tkinter import filedialog
        pasta = filedialog.askdirectory(title='Pasta com as imagens')
        if pasta:
            self.carregar_pasta(Path(pasta))

    def escolher_saida(self):
        from tkinter import filedialog
        pasta = filedialog.askdirectory(title='Pasta de saida dos recortes')
        if pasta:
            self.pasta_saida = Path(pasta)
            self.rotulo_saida.config(text=f'saida: {self.pasta_saida}')

    def carregar_pasta(self, pasta):
        from tkinter import messagebox
        imagens = listar_imagens(pasta)
        if not imagens:
            messagebox.showwarning('Sem imagens',
                                   f'Nenhuma imagem ({", ".join(EXTENSOES)}) em:\n{pasta}')
            return
        self.pasta_entrada = Path(pasta)
        self.imagens = imagens
        self.indice = 0
        self.salvas.clear()
        if self.pasta_saida is None:
            self.pasta_saida = self.pasta_entrada / 'recortes'
        self.rotulo_saida.config(text=f'saida: {self.pasta_saida}')
        self.var_status.set(f'{len(imagens)} imagens carregadas.')
        self.carregar_imagem_atual()

    # ----------------------------------------------------------------- imagens
    def carregar_imagem_atual(self):
        caminho = self.imagens[self.indice]
        self.img = abrir_imagem(caminho)
        self.zoom_manual = None
        self.rois = [tuple(r) for r in self.rois_travadas] if self.var_travar.get() else []
        marca = ' [salva]' if caminho.name in self.salvas else ''
        self.rotulo_imagem.config(
            text=f'{self.indice + 1}/{len(self.imagens)}  {caminho.name}\n'
                 f'{self.img.size[0]} x {self.img.size[1]} px{marca}')
        self.redesenhar()

    def trocar_imagem(self, passo):
        if not self.imagens:
            return
        novo = self.indice + passo
        if not 0 <= novo < len(self.imagens):
            self.var_status.set('Fim da lista de imagens.')
            return
        if self.var_travar.get():
            self.rois_travadas = [tuple(r) for r in self.rois]
        self.indice = novo
        self.carregar_imagem_atual()

    # -------------------------------------------------------------------- zoom
    def escala_ajuste(self):
        if self.img is None:
            return 1.0
        cw = max(self.canvas.winfo_width(), 50)
        ch = max(self.canvas.winfo_height(), 50)
        iw, ih = self.img.size
        return min(cw / iw, ch / ih)

    def ajustar_zoom(self, fator):
        if self.img is None:
            return
        base = self.zoom_manual if self.zoom_manual else self.escala_ajuste()
        self.zoom_manual = max(0.02, min(8.0, base * fator))
        self.redesenhar()

    def zoom_ajustar(self):
        self.zoom_manual = None
        self.redesenhar()

    def mouse_wheel(self, evento):
        if evento.state & 0x0004:           # Ctrl pressionado = zoom
            self.ajustar_zoom(1.25 if evento.delta > 0 else 1 / 1.25)
        else:
            self.canvas.yview_scroll(-1 if evento.delta > 0 else 1, 'units')

    # --------------------------------------------------------------- desenho
    def redesenhar(self):
        from PIL import ImageTk
        self.canvas.delete('all')
        if self.img is None:
            return

        self.escala = self.zoom_manual if self.zoom_manual else self.escala_ajuste()
        iw, ih = self.img.size
        dw, dh = max(1, int(iw * self.escala)), max(1, int(ih * self.escala))
        reamostragem = Image.LANCZOS if self.escala < 1 else Image.NEAREST
        self.foto = ImageTk.PhotoImage(self.img.resize((dw, dh), reamostragem))
        self.canvas.create_image(0, 0, anchor='nw', image=self.foto)
        self.canvas.configure(scrollregion=(0, 0, dw, dh))

        selecionadas = set(self.lista.curselection())
        n_linhas = self._inteiro(self.var_linhas, 1)
        n_colunas = self._inteiro(self.var_colunas, 1)

        for indice, roi in enumerate(self.rois):
            cor = '#ffd400' if indice in selecionadas else '#00e5ff'
            self._desenhar_roi(roi, cor, rotulo=f'{indice + 1}',
                               n_linhas=n_linhas, n_colunas=n_colunas)
        if self._roi_temp:
            self._desenhar_roi(self._roi_temp, '#ff4d4d', tracejado=True)

        self.atualizar_lista()

    def _desenhar_roi(self, roi, cor, rotulo=None, tracejado=False,
                      n_linhas=1, n_colunas=1):
        x, y, w, h = roi
        s = self.escala
        x0, y0, x1, y1 = x * s, y * s, (x + w) * s, (y + h) * s
        self.canvas.create_rectangle(x0, y0, x1, y1, outline=cor, width=2,
                                     dash=(4, 3) if tracejado else None)
        if rotulo:
            self.canvas.create_text(x0 + 4, y0 + 4, anchor='nw', text=rotulo,
                                    fill=cor, font=('', 11, 'bold'))
        if (n_linhas > 1 or n_colunas > 1) and not tracejado:
            for i in range(1, n_colunas):
                bx = (x + w * i / n_colunas) * s
                self.canvas.create_line(bx, y0, bx, y1, fill=cor, dash=(2, 4))
            for j in range(1, n_linhas):
                by = (y + h * j / n_linhas) * s
                self.canvas.create_line(x0, by, x1, by, fill=cor, dash=(2, 4))

    def atualizar_lista(self):
        selecao = self.lista.curselection()
        self.lista.delete(0, 'end')
        for indice, (x, y, w, h) in enumerate(self.rois, start=1):
            self.lista.insert('end', f'{indice:02d}  x={x} y={y}  {w}x{h}')
        for i in selecao:
            if i < self.lista.size():
                self.lista.selection_set(i)

    # ---------------------------------------------------------------- mouse
    def _para_original(self, evento):
        cx = self.canvas.canvasx(evento.x) / self.escala
        cy = self.canvas.canvasy(evento.y) / self.escala
        return cx, cy

    def _caixa_fixa(self, cx, cy):
        w = self._inteiro(self.var_larg, 100)
        h = self._inteiro(self.var_alt, 100)
        return recortar_roi(cx - w / 2, cy - h / 2, w, h, self.img.size)

    def mouse_press(self, evento):
        if self.img is None:
            return
        cx, cy = self._para_original(evento)
        if self.var_fixo.get():
            self._arraste = 'fixo'
            self._roi_temp = self._caixa_fixa(cx, cy)
        else:
            self._arraste = (cx, cy)
            self._roi_temp = recortar_roi(cx, cy, 0, 0, self.img.size)
        self.redesenhar()

    def mouse_drag(self, evento):
        if self._arraste is None:
            return
        cx, cy = self._para_original(evento)
        if self._arraste == 'fixo':
            self._roi_temp = self._caixa_fixa(cx, cy)
        else:
            x0, y0 = self._arraste
            self._roi_temp = recortar_roi(min(x0, cx), min(y0, cy),
                                          abs(cx - x0), abs(cy - y0),
                                          self.img.size)
        self.redesenhar()
        self.mouse_move(evento)

    def mouse_release(self, evento):
        if self._arraste is None:
            return
        self._arraste = None
        roi = self._roi_temp
        self._roi_temp = None
        if roi and roi[2] >= 2 and roi[3] >= 2:
            self.rois.append(roi)
            if self.var_travar.get():
                self.rois_travadas = [tuple(r) for r in self.rois]
            self.var_status.set(f'ROI {len(self.rois)}: {roi[2]}x{roi[3]} px '
                                f'em ({roi[0]}, {roi[1]})')
        self.redesenhar()

    def mouse_move(self, evento):
        if self.img is None:
            return
        cx, cy = self._para_original(evento)
        texto = f'cursor: ({int(cx)}, {int(cy)}) px   zoom: {self.escala * 100:.0f}%'
        if self._roi_temp:
            texto += f'   selecao: {self._roi_temp[2]}x{self._roi_temp[3]}'
        self.var_cursor.set(texto)

    # ----------------------------------------------------------------- acoes
    def remover_roi(self):
        if not self.rois:
            return
        selecao = self.lista.curselection()
        indice = selecao[0] if selecao else len(self.rois) - 1
        self.rois.pop(indice)
        if self.var_travar.get():
            self.rois_travadas = [tuple(r) for r in self.rois]
        self.redesenhar()

    def limpar_rois(self):
        self.rois = []
        if self.var_travar.get():
            self.rois_travadas = []
        self.redesenhar()

    def alternar_travamento(self):
        self.var_travar.set(not self.var_travar.get())
        self.atualizar_travamento()

    def atualizar_travamento(self):
        if self.var_travar.get():
            self.rois_travadas = [tuple(r) for r in self.rois]
            self.var_status.set('ROIs travadas: serao reaproveitadas nas proximas imagens.')
        else:
            self.rois_travadas = []
            self.var_status.set('ROIs destravadas.')

    def salvar_e_avancar(self):
        from tkinter import messagebox
        if self.img is None or not self.imagens:
            return
        if not self.rois:
            messagebox.showinfo('Sem ROI', 'Selecione ao menos uma regiao antes de salvar.')
            return

        caminho = self.imagens[self.indice]
        registros = salvar_recortes(
            caminho, self.rois, self.pasta_saida,
            n_linhas=self._inteiro(self.var_linhas, 1),
            n_colunas=self._inteiro(self.var_colunas, 1),
            formato=self.var_formato.get(),
            subpasta_por_imagem=self.var_subpasta.get(),
            img=self.img)
        registrar_no_csv(self.pasta_saida, registros)
        self.salvas.add(caminho.name)
        self.var_status.set(f'{len(registros)} recorte(s) salvos de {caminho.name}.')

        if self.indice < len(self.imagens) - 1:
            self.trocar_imagem(1)
        else:
            self.carregar_imagem_atual()
            messagebox.showinfo('Fim', 'Ultima imagem da pasta processada.')

    def aplicar_todas(self):
        from tkinter import messagebox
        if not self.rois or not self.imagens:
            messagebox.showinfo('Sem ROI', 'Selecione a regiao antes de aplicar em lote.')
            return
        n_linhas = self._inteiro(self.var_linhas, 1)
        n_colunas = self._inteiro(self.var_colunas, 1)
        por_imagem = len(self.rois) * n_linhas * n_colunas
        pergunta = (f'Aplicar {len(self.rois)} ROI(s) x grade {n_linhas}x{n_colunas} '
                    f'({por_imagem} recortes por imagem) as {len(self.imagens)} '
                    f'imagens da pasta?\n\nSaida: {self.pasta_saida}')
        if not messagebox.askokcancel('Aplicar a todas', pergunta):
            return

        total = aplicar_em_lote(self.pasta_entrada, self.pasta_saida, self.rois,
                                n_linhas, n_colunas, self.var_formato.get(),
                                self.var_subpasta.get(), log=lambda m: None)
        self.salvas.update(p.name for p in self.imagens)
        self.var_status.set(f'{total} recortes gravados em {self.pasta_saida}.')
        messagebox.showinfo('Concluido', f'{total} recortes gravados em:\n{self.pasta_saida}')

    @staticmethod
    def _inteiro(variavel, padrao):
        try:
            return max(1, int(float(variavel.get())))
        except (TypeError, ValueError):
            return padrao


def abrir_janela(pasta_entrada=None, pasta_saida=None, formato='png'):
    """Abre a interface de recorte (chamavel de um notebook ou do terminal)."""
    import tkinter as tk
    raiz = tk.Tk()
    RecortadorApp(raiz, pasta_entrada, pasta_saida, formato)
    raiz.mainloop()


# =============================================================================
# 3. LINHA DE COMANDO
# =============================================================================
def _analisar_argumentos(argv=None):
    p = argparse.ArgumentParser(
        description='Recorte manual/semiautomatico de ROIs em lotes de imagens.')
    p.add_argument('--entrada', help='pasta com as imagens originais')
    p.add_argument('--saida', help='pasta de destino dos recortes')
    p.add_argument('--formato', default='png', help='png (padrao), jpg ou tif')
    p.add_argument('--roi', action='append', default=[],
                   help='ROI fixa "x,y,largura,altura" (pode repetir)')
    p.add_argument('--grade', default='1x1',
                   help='subdivisao de cada ROI, ex. 2x3 (linhas x colunas)')
    p.add_argument('--subpasta', action='store_true',
                   help='criar uma subpasta por imagem de origem')
    p.add_argument('--lote', action='store_true',
                   help='aplicar as --roi a toda a pasta sem abrir a janela')
    p.add_argument('--csv', help='refazer os recortes descritos em um CSV')
    p.add_argument('--sobre', action='store_true',
                   help='abrir apenas a janela "Sobre" (creditos do programa)')
    return p.parse_args(argv)


def main(argv=None):
    args = _analisar_argumentos(argv)

    if args.sobre:
        janela = mostrar_sobre()
        janela.mainloop()
        return 0

    try:
        n_linhas, n_colunas = (int(v) for v in args.grade.lower().split('x'))
    except ValueError:
        print(f'Grade invalida: {args.grade} (use algo como 2x3)')
        return 2

    if args.csv:
        if not args.entrada or not args.saida:
            print('Para --csv informe tambem --entrada e --saida.')
            return 2
        refazer_do_csv(args.csv, args.entrada, args.saida, args.formato)
        return 0

    rois = []
    for texto in args.roi:
        partes = texto.replace(';', ',').split(',')
        if len(partes) != 4:
            print(f'ROI invalida: {texto} (use x,y,largura,altura)')
            return 2
        rois.append(tuple(int(float(v)) for v in partes))

    if args.lote:
        if not args.entrada or not rois:
            print('O modo --lote exige --entrada e ao menos uma --roi.')
            return 2
        saida = args.saida or str(Path(args.entrada) / 'recortes')
        aplicar_em_lote(args.entrada, saida, rois, n_linhas, n_colunas,
                        args.formato, args.subpasta)
        return 0

    abrir_janela(args.entrada, args.saida, args.formato)
    return 0


if __name__ == '__main__':
    sys.exit(main())
