"""
manual_cropping.py
==================
Visual tool (Tkinter + Pillow) for cropping regions of interest (ROIs) from a
set of images, in the style of the crops used in analytical chemistry work:
several sub-images extracted from each photograph of a sample.

Three working modes, which can be combined:

  1) FREE SELECTION - drag the mouse and draw the rectangle on each image.
  2) FIXED SIZE     - set width x height in pixels and just click the centre of
                      the desired region (every crop comes out the same size,
                      which is essential for comparing colour histograms).
  3) LOCKED ROI     - mark the region once and reuse it on all the following
                      images (just press Enter on each one), or apply it to the
                      whole folder at once ("Apply to all").

Each ROI can also be subdivided into a rows x columns grid, producing N
sub-crops per region (useful to multiply samples per photograph).

Every crop is taken at the ORIGINAL resolution of the image (the on-screen zoom
only affects the display) and the coordinates are written to a CSV, so that the
cropping is reproducible and can be re-run later.

The interface is bilingual (Portuguese and English). The language can be
switched at any moment from the selector at the bottom of the control panel,
without restarting, and the choice is remembered for the next run.

BASIC USE (graphical window)
----------------------------
    .venv\\Scripts\\python.exe manual_cropping.py
    .venv\\Scripts\\python.exe manual_cropping.py --input images --output crops
    .venv\\Scripts\\python.exe manual_cropping.py --lang en

BATCH USE (no window)
---------------------
    # the same ROI on every image of the folder, split into 2x3 sub-crops
    python manual_cropping.py --input images --output crops \\
        --roi 300,200,600,400 --grid 2x3 --batch

    # redo exactly the crops of an earlier session
    python manual_cropping.py --input images --output crops2 \\
        --csv crops/crop_coords.csv

KEYBOARD SHORTCUTS
------------------
    Enter          save the crops of the current image and move on
    Right arrow    next image               Left arrow      previous image
    Delete         remove the last ROI      C               clear the ROIs
    T              lock/unlock the ROIs
    + / -          zoom                     0               fit to window
    F1             "About" window (credits)

CREDITS
-------
    Developed by the GAAA research group
    (Grupo de Abordagens Analiticas Alternativas)
    Software created by Dennis da Silva Ferreira
"""

import argparse
import csv
import json
import locale
import os
import sys
from pathlib import Path

from PIL import Image, ImageOps

EXTENSIONS = ('.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.webp')
CSV_NAME = 'crop_coords.csv'

# ---- program identity (used in the "About" window and in the executable) ----
APP_NAME = 'Manual Image Cropping'
APP_VERSION = '1.1'
APP_AUTHOR = 'Dennis da Silva Ferreira'
APP_GROUP = 'Grupo de Abordagens Analiticas Alternativas (GAAA)'
APP_YEAR = '2026'
LOGO_FILE = 'gaaa_logo.jpg'
ICON_FILE = 'app_icon.ico'
CSV_COLUMNS = ['image', 'roi', 'grid_row', 'grid_col',
               'x', 'y', 'width', 'height',
               'original_width', 'original_height', 'output_file']

# Column names used by version 1.0, when the code was in Portuguese. Kept so
# that CSV files from earlier sessions can still be replayed by redo_from_csv.
LEGACY_CSV_COLUMNS = {
    'imagem': 'image',
    'grade_linha': 'grid_row',
    'grade_coluna': 'grid_col',
    'largura': 'width',
    'altura': 'height',
    'largura_original': 'original_width',
    'altura_original': 'original_height',
    'arquivo_saida': 'output_file',
}


# =============================================================================
# 0. LANGUAGES
#    Every string the user can see lives here. Adding a third language is a
#    matter of adding one more entry to TEXTS and to LANGUAGE_NAMES.
# =============================================================================
LANGUAGE_NAMES = {'pt': 'Português', 'en': 'English'}
DEFAULT_LANGUAGE = 'en'

TEXTS = {
    'pt': {
        'subtitle': 'Recorte de regioes de interesse (ROIs) em lotes de imagens',
        # --- About window ---
        'about_title': 'Sobre - {app}',
        'about_developed': 'Desenvolvido pelo grupo de pesquisa GAAA',
        'about_created': 'Software criado por {author}',
        'about_use': '{year} - uso academico e cientifico',
        'close': 'Fechar',
        # --- control panel ---
        'folders': 'Pastas',
        'open_images': 'Abrir pasta de imagens...',
        'choose_output': 'Pasta de saida...',
        'output_is': 'saida: {path}',
        'image': 'Imagem',
        'previous': '<< Anterior',
        'next': 'Proxima >>',
        'fit_window': 'Ajustar a janela',
        'selection_mode': 'Modo de selecao',
        'fixed_size': 'Tamanho fixo (clique no centro)',
        'width_short': 'larg',
        'height_short': 'x alt',
        'pixels': 'px',
        'lock_rois': 'Travar ROIs para as proximas imagens',
        'grid_title': 'Grade dentro de cada ROI',
        'rows': 'linhas',
        'columns': 'colunas',
        'show': 'Ver',
        'rois_title': 'ROIs da imagem atual',
        'remove': 'Remover (Del)',
        'clear': 'Limpar (C)',
        'output': 'Saida',
        'format': 'formato',
        'subfolder': 'Subpasta por imagem',
        'save_next': 'Salvar recortes e avancar (Enter)',
        'apply_all': 'Aplicar estas ROIs a TODAS as imagens',
        'about_button': 'Sobre (F1)',
        'language': 'Idioma',
        # --- status bar ---
        'status_open_folder': 'Abra a pasta com as imagens.',
        'status_loaded': '{n} imagens carregadas.',
        'status_end_of_list': 'Fim da lista de imagens.',
        'status_roi_added': 'ROI {n}: {w}x{h} px em ({x}, {y})',
        'status_locked': 'ROIs travadas: serao reaproveitadas nas proximas imagens.',
        'status_unlocked': 'ROIs destravadas.',
        'status_saved': '{n} recorte(s) salvos de {name}.',
        'status_batch_done': '{n} recortes gravados em {path}.',
        'cursor': 'cursor: ({x}, {y}) px   zoom: {zoom}%',
        'cursor_selection': '   selecao: {w}x{h}',
        'saved_mark': ' [salva]',
        # --- dialogs ---
        'dialog_images': 'Pasta com as imagens',
        'dialog_output': 'Pasta de saida dos recortes',
        'no_images_title': 'Sem imagens',
        'no_images': 'Nenhuma imagem ({extensions}) em:\n{folder}',
        'no_roi_title': 'Sem ROI',
        'no_roi_save': 'Selecione ao menos uma regiao antes de salvar.',
        'no_roi_batch': 'Selecione a regiao antes de aplicar em lote.',
        'end_title': 'Fim',
        'end_message': 'Ultima imagem da pasta processada.',
        'apply_all_title': 'Aplicar a todas',
        'apply_all_question': ('Aplicar {rois} ROI(s) x grade {rows}x{cols} '
                               '({per_image} recortes por imagem) as {n} '
                               'imagens da pasta?\n\nSaida: {path}'),
        'done_title': 'Concluido',
        'done_message': '{n} recortes gravados em:\n{path}',
    },
    'en': {
        'subtitle': 'Cropping of regions of interest (ROIs) in batches of images',
        # --- About window ---
        'about_title': 'About - {app}',
        'about_developed': 'Developed by the GAAA research group',
        'about_created': 'Software created by {author}',
        'about_use': '{year} - academic and scientific use',
        'close': 'Close',
        # --- control panel ---
        'folders': 'Folders',
        'open_images': 'Open image folder...',
        'choose_output': 'Output folder...',
        'output_is': 'output: {path}',
        'image': 'Image',
        'previous': '<< Previous',
        'next': 'Next >>',
        'fit_window': 'Fit to window',
        'selection_mode': 'Selection mode',
        'fixed_size': 'Fixed size (click the centre)',
        'width_short': 'width',
        'height_short': 'x height',
        'pixels': 'px',
        'lock_rois': 'Lock ROIs for the next images',
        'grid_title': 'Grid inside each ROI',
        'rows': 'rows',
        'columns': 'columns',
        'show': 'Show',
        'rois_title': 'ROIs of the current image',
        'remove': 'Remove (Del)',
        'clear': 'Clear (C)',
        'output': 'Output',
        'format': 'format',
        'subfolder': 'Subfolder per image',
        'save_next': 'Save crops and move on (Enter)',
        'apply_all': 'Apply these ROIs to ALL images',
        'about_button': 'About (F1)',
        'language': 'Language',
        # --- status bar ---
        'status_open_folder': 'Open the folder with the images.',
        'status_loaded': '{n} images loaded.',
        'status_end_of_list': 'End of the image list.',
        'status_roi_added': 'ROI {n}: {w}x{h} px at ({x}, {y})',
        'status_locked': 'ROIs locked: they will be reused on the next images.',
        'status_unlocked': 'ROIs unlocked.',
        'status_saved': '{n} crop(s) saved from {name}.',
        'status_batch_done': '{n} crops written to {path}.',
        'cursor': 'cursor: ({x}, {y}) px   zoom: {zoom}%',
        'cursor_selection': '   selection: {w}x{h}',
        'saved_mark': ' [saved]',
        # --- dialogs ---
        'dialog_images': 'Folder with the images',
        'dialog_output': 'Output folder for the crops',
        'no_images_title': 'No images',
        'no_images': 'No image ({extensions}) in:\n{folder}',
        'no_roi_title': 'No ROI',
        'no_roi_save': 'Select at least one region before saving.',
        'no_roi_batch': 'Select the region before applying in batch.',
        'end_title': 'Done',
        'end_message': 'Last image of the folder processed.',
        'apply_all_title': 'Apply to all',
        'apply_all_question': ('Apply {rois} ROI(s) x {rows}x{cols} grid '
                               '({per_image} crops per image) to the {n} '
                               'images of the folder?\n\nOutput: {path}'),
        'done_title': 'Done',
        'done_message': '{n} crops written to:\n{path}',
    },
}


def settings_path():
    """Where the chosen language is remembered between runs."""
    base = os.environ.get('APPDATA') or Path.home()
    return Path(base) / 'ManualImageCropping' / 'settings.json'


def detect_language():
    """Portuguese when the system is in Portuguese, English otherwise."""
    try:
        code = (locale.getlocale()[0] or '').lower()
    except (TypeError, ValueError):
        code = ''
    return 'pt' if code.startswith(('pt', 'portuguese')) else DEFAULT_LANGUAGE


def load_language():
    """Language saved by a previous run, or the one the system suggests."""
    try:
        saved = json.loads(settings_path().read_text(encoding='utf-8')).get('language')
    except (OSError, ValueError):
        saved = None
    return saved if saved in TEXTS else detect_language()


def save_language(language):
    """Remember the choice; failing to write must never break the program."""
    try:
        path = settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'language': language}), encoding='utf-8')
    except OSError:
        pass


class Translator:
    """
    Tiny lookup object: `tr('rows')` returns the text in the current language.

    Missing keys fall back to English and then to the key itself, so a typo
    shows up on screen instead of raising in the middle of the interface.
    """

    def __init__(self, language=None):
        self.language = language if language in TEXTS else load_language()

    def __call__(self, key, **values):
        text = TEXTS[self.language].get(key) or TEXTS[DEFAULT_LANGUAGE].get(key, key)
        return text.format(**values) if values else text

    def set_language(self, language):
        if language in TEXTS and language != self.language:
            self.language = language
            save_language(language)
            return True
        return False


def resource_path(name):
    """
    Locate a file from the `assets` folder, both when running the .py and from
    inside the executable built by PyInstaller (which unpacks everything into
    sys._MEIPASS).

    Returns None when the resource is unavailable, so that the interface keeps
    working even without the logo.
    """
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    for candidate in (base / 'assets' / name, base / name):
        if candidate.exists():
            return candidate
    return None


def shorten_path(path, parts=3):
    """Shorten a long path for display: C:\\a\\b\\c\\d -> ...\\b\\c\\d."""
    pieces = Path(path).parts
    if len(pieces) <= parts:
        return str(path)
    return '...' + os.sep + os.sep.join(pieces[-parts:])


# =============================================================================
# 1. INTERFACE-FREE CORE (also used by the batch mode)
# =============================================================================
def list_images(folder):
    """Return the sorted list of images in a folder (not recursive)."""
    folder = Path(folder)
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in EXTENSIONS)


def open_image(path):
    """Open the image as RGB, already applying the orientation stored in EXIF."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return img.convert('RGB')


def clamp_roi(x, y, width, height, bounds):
    """Fit an ROI inside the (width, height) bounds of the image."""
    max_w, max_h = bounds
    x0 = max(0, min(int(round(x)), max_w))
    y0 = max(0, min(int(round(y)), max_h))
    x1 = max(0, min(int(round(x + width)), max_w))
    y1 = max(0, min(int(round(y + height)), max_h))
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    return x0, y0, x1 - x0, y1 - y0


def split_into_grid(roi, n_rows, n_cols):
    """
    Split an ROI (x, y, width, height) into n_rows x n_cols blocks.

    Returns a list of (row, col, x, y, width, height) tuples with integer edges
    and no overlap; (1, 1, ...) when the grid is 1x1.
    """
    x, y, width, height = roi
    n_rows = max(1, int(n_rows))
    n_cols = max(1, int(n_cols))

    edges_x = [x + round(width * i / n_cols) for i in range(n_cols + 1)]
    edges_y = [y + round(height * j / n_rows) for j in range(n_rows + 1)]

    blocks = []
    for j in range(n_rows):
        for i in range(n_cols):
            bx, by = edges_x[i], edges_y[j]
            bw, bh = edges_x[i + 1] - bx, edges_y[j + 1] - by
            if bw > 0 and bh > 0:
                blocks.append((j + 1, i + 1, bx, by, bw, bh))
    return blocks


def save_crops(image_path, rois, output_folder, n_rows=1, n_cols=1,
               fmt='png', subfolder_per_image=False, img=None):
    """
    Crop and write to disk every ROI of one image.

    Parameters
    ----------
    image_path : Path - source image
    rois : list of (x, y, width, height) in pixels of the ORIGINAL image
    output_folder : Path - destination of the crops
    n_rows, n_cols : subdivision of each ROI into a grid
    fmt : 'png', 'jpg', 'tif', ... (extension of the output file)
    subfolder_per_image : if True, creates output_folder/<image_name>/

    Returns
    -------
    list of dictionaries ready for the coordinate CSV
    """
    image_path = Path(image_path)
    if img is None:
        img = open_image(image_path)

    destination = Path(output_folder)
    if subfolder_per_image:
        destination = destination / image_path.stem
    destination.mkdir(parents=True, exist_ok=True)

    fmt = fmt.lower().lstrip('.')
    pillow_format = 'JPEG' if fmt in ('jpg', 'jpeg') else None
    records = []

    for index, roi in enumerate(rois, start=1):
        x, y, width, height = clamp_roi(*roi, bounds=img.size)
        if width <= 0 or height <= 0:
            continue

        for row, col, bx, by, bw, bh in split_into_grid(
                (x, y, width, height), n_rows, n_cols):

            suffix = f'_roi{index:02d}'
            if n_rows > 1 or n_cols > 1:
                suffix += f'_l{row}c{col}'
            filename = destination / f'{image_path.stem}{suffix}.{fmt}'

            crop = img.crop((bx, by, bx + bw, by + bh))
            if pillow_format == 'JPEG':
                crop.save(filename, 'JPEG', quality=95, subsampling=0)
            else:
                crop.save(filename)

            records.append({
                'image': image_path.name,
                'roi': index,
                'grid_row': row,
                'grid_col': col,
                'x': bx, 'y': by, 'width': bw, 'height': bh,
                'original_width': img.size[0],
                'original_height': img.size[1],
                'output_file': str(filename.relative_to(output_folder)),
            })

    return records


def log_to_csv(output_folder, records):
    """Append the records to the coordinate CSV (writing the header if new)."""
    if not records:
        return None
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    path = output_folder / CSV_NAME
    is_new = not path.exists()
    with open(path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerows(records)
    return path


def apply_in_batch(input_folder, output_folder, rois, n_rows=1, n_cols=1,
                   fmt='png', subfolder_per_image=False, log=print):
    """Apply the same ROIs to every image of the folder (no interface)."""
    images = list_images(input_folder)
    if not images:
        log(f'No image found in {input_folder}')
        return 0

    total = 0
    for path in images:
        records = save_crops(path, rois, output_folder,
                             n_rows, n_cols, fmt,
                             subfolder_per_image)
        log_to_csv(output_folder, records)
        total += len(records)
        log(f'{path.name}: {len(records)} crop(s)')
    log(f'Total: {total} crops in {output_folder}')
    return total


def _normalise_row(row):
    """Accept both the current CSV header and the Portuguese one of v1.0."""
    return {LEGACY_CSV_COLUMNS.get(key, key): value for key, value in row.items()}


def redo_from_csv(csv_path, input_folder, output_folder, fmt='png', log=print):
    """
    Re-run the crops described in a CSV produced by this tool.

    Each CSV row already carries the final x/y/width/height (grid resolved), so
    the crops come out identical to those of the original session. CSV files
    written by version 1.0, with Portuguese column names, are also accepted.
    """
    input_folder, output_folder = Path(input_folder), Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    fmt = fmt.lower().lstrip('.')

    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = [_normalise_row(row) for row in csv.DictReader(f)]

    cached_name, cached_img = None, None
    total = 0
    for row in rows:
        name = row['image']
        if name != cached_name:
            path = input_folder / name
            if not path.exists():
                log(f'WARNING: {name} not found in {input_folder}')
                cached_name, cached_img = name, None
                continue
            cached_name, cached_img = name, open_image(path)
        if cached_img is None:
            continue

        x, y = int(row['x']), int(row['y'])
        w, h = int(row['width']), int(row['height'])
        output = output_folder / Path(row['output_file']).with_suffix(f'.{fmt}')
        output.parent.mkdir(parents=True, exist_ok=True)
        crop = cached_img.crop((x, y, x + w, y + h))
        if fmt in ('jpg', 'jpeg'):
            crop.save(output, 'JPEG', quality=95, subsampling=0)
        else:
            crop.save(output)
        total += 1

    log(f'{total} crops redone in {output_folder}')
    return total


# =============================================================================
# 2. GRAPHICAL INTERFACE
# =============================================================================
def apply_icon(window):
    """Put the GAAA icon on the title bar (skipped if there is no .ico)."""
    icon = resource_path(ICON_FILE)
    if icon is None:
        return
    try:
        window.iconbitmap(str(icon))
    except Exception:
        pass


def show_about(parent=None, tr=None):
    """Open the "About" window with the research group logo and the credits."""
    import tkinter as tk
    from tkinter import ttk

    tr = tr or Translator()
    window = tk.Toplevel(parent) if parent is not None else tk.Tk()
    window.title(tr('about_title', app=APP_NAME))
    window.configure(bg='white')
    window.resizable(False, False)
    apply_icon(window)

    frame = ttk.Frame(window, padding=16)
    frame.pack(fill='both', expand=True)

    logo = resource_path(LOGO_FILE)
    if logo is not None:
        try:
            from PIL import ImageTk
            image = open_image(logo)
            box = 240          # the logo fits inside a 240 px square
            scale = min(1.0, box / image.size[0], box / image.size[1])
            image = image.resize((max(1, int(image.size[0] * scale)),
                                  max(1, int(image.size[1] * scale))),
                                 Image.LANCZOS)
            window.logo_photo = ImageTk.PhotoImage(image)   # avoids collection
            ttk.Label(frame, image=window.logo_photo).pack(pady=(0, 12))
        except Exception:
            pass

    ttk.Label(frame, text=f'{APP_NAME}  v{APP_VERSION}',
              font=('', 13, 'bold')).pack()
    ttk.Label(frame, text=tr('subtitle'), wraplength=340, justify='center',
              foreground='#444444').pack(pady=(2, 12))

    ttk.Separator(frame).pack(fill='x', pady=4)
    ttk.Label(frame, text=tr('about_developed'), wraplength=340,
              justify='center', font=('', 10, 'bold')).pack(pady=(8, 0))
    ttk.Label(frame, text=APP_GROUP, wraplength=340, justify='center',
              foreground='#444444').pack()
    ttk.Label(frame, text=tr('about_created', author=APP_AUTHOR),
              wraplength=340, justify='center').pack(pady=(8, 0))
    ttk.Label(frame, text=tr('about_use', year=APP_YEAR),
              foreground='#777777').pack(pady=(6, 10))

    ttk.Button(frame, text=tr('close'), command=window.destroy).pack()

    window.update_idletasks()
    if parent is not None:
        x = parent.winfo_rootx() + (parent.winfo_width() - window.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - window.winfo_height()) // 3
        window.geometry(f'+{max(0, x)}+{max(0, y)}')
        window.transient(parent)
        window.grab_set()
    window.bind('<Escape>', lambda e: window.destroy())
    window.focus_set()
    return window


class CropperApp:
    """
    Manual cropping window: canvas with the image + control panel.

    The control panel needs more vertical space than many screens offer, so it
    is split in two: the actions that must never disappear (save, apply, about)
    are pinned to the bottom, and everything above them lives in a scrollable
    area. That way the window works at any resolution.
    """

    PANEL_WIDTH = 250

    def __init__(self, root, input_folder=None, output_folder=None, fmt='png',
                 language=None):
        import tkinter as tk
        from tkinter import ttk

        self.tk, self.ttk = tk, ttk
        self.root = root
        self.tr = Translator(language)

        root.title(f'{APP_NAME} v{APP_VERSION} - GAAA')
        # Size and position the window inside the usable area of the screen.
        # The 140 px margin leaves room for the title bar and the taskbar, so
        # the pinned buttons at the bottom of the panel are never hidden by it.
        screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()
        width = max(820, min(1200, screen_w - 80))
        height = max(520, min(780, screen_h - 140))
        root.geometry(f'{width}x{height}'
                      f'+{max(0, (screen_w - width) // 2)}'
                      f'+{max(0, (screen_h - height) // 3)}')
        root.minsize(820, 520)
        apply_icon(root)

        self.input_folder = Path(input_folder) if input_folder else None
        self.output_folder = Path(output_folder) if output_folder else None
        self.images = []
        self.index = 0
        self.img = None            # PIL.Image of the current image
        self.photo = None          # ImageTk reference (avoids collection)
        self.scale = 1.0
        self.manual_zoom = None    # None = fit to window
        self.rois = []             # ROIs of the current image, original coords
        self.locked_rois = []      # ROIs reused on the next image
        self.saved = set()
        self._drag = None
        self._temp_roi = None
        self._translatable = []    # (widget, text key) pairs, for retranslate
        self._status = ('status_open_folder', {})
        self._cursor = None        # last (x, y) under the pointer

        # ---- control variables ----
        self.var_lock = tk.BooleanVar(value=False)
        self.var_fixed = tk.BooleanVar(value=False)
        self.var_width = tk.StringVar(value='400')
        self.var_height = tk.StringVar(value='400')
        self.var_rows = tk.StringVar(value='1')
        self.var_cols = tk.StringVar(value='1')
        self.var_format = tk.StringVar(value=fmt)
        self.var_subfolder = tk.BooleanVar(value=False)
        self.var_status = tk.StringVar(value=self.tr('status_open_folder'))
        self.var_cursor = tk.StringVar(value='')
        self.var_language = tk.StringVar(value=LANGUAGE_NAMES[self.tr.language])

        self._build_interface()
        self._bind_events()

        if self.input_folder:
            self.load_folder(self.input_folder)

    # ------------------------------------------------------------ translation
    def _reg(self, widget, key):
        """Register a widget whose 'text' follows the language, and return it."""
        self._translatable.append((widget, key))
        return widget

    def set_language(self, language):
        """Switch the interface language on the spot, without restarting."""
        if not self.tr.set_language(language):
            return
        self.var_language.set(LANGUAGE_NAMES[language])
        for widget, key in self._translatable:
            widget.config(text=self.tr(key))
        self._update_output_label()
        self._update_image_label()
        self._update_status()
        self._update_cursor_label()

    def _on_language_selected(self, _event=None):
        chosen = self.var_language.get()
        for code, name in LANGUAGE_NAMES.items():
            if name == chosen:
                self.set_language(code)
                return

    def set_status(self, key, **values):
        """Store the status as key + values so it survives a language change."""
        self._status = (key, values)
        self._update_status()

    def _update_status(self):
        key, values = self._status
        self.var_status.set(self.tr(key, **values) if key else '')

    def _update_output_label(self):
        text = self.tr('output_is',
                       path=shorten_path(self.output_folder) if self.output_folder else '-')
        self.label_output.config(text=text)

    def _update_image_label(self):
        if not self.images or self.img is None:
            self.label_image.config(text='-')
            return
        path = self.images[self.index]
        mark = self.tr('saved_mark') if path.name in self.saved else ''
        self.label_image.config(
            text=f'{self.index + 1}/{len(self.images)}  {path.name}\n'
                 f'{self.img.size[0]} x {self.img.size[1]} px{mark}')

    def _update_cursor_label(self):
        if self._cursor is None:
            self.var_cursor.set('')
            return
        cx, cy = self._cursor
        text = self.tr('cursor', x=int(cx), y=int(cy), zoom=f'{self.scale * 100:.0f}')
        if self._temp_roi:
            text += self.tr('cursor_selection',
                            w=self._temp_roi[2], h=self._temp_roi[3])
        self.var_cursor.set(text)

    # ------------------------------------------------------------------ layout
    def _build_interface(self):
        tk, ttk = self.tk, self.ttk

        panel = ttk.Frame(self.root, padding=(8, 8, 4, 8))
        panel.pack(side='right', fill='y')
        panel.pack_propagate(False)
        panel.configure(width=self.PANEL_WIDTH)

        self._build_pinned_actions(panel)
        self._build_scrollable_controls(panel)

        area = ttk.Frame(self.root)
        area.pack(side='left', fill='both', expand=True)

        self.canvas = tk.Canvas(area, bg='#222222', highlightthickness=0,
                                cursor='crosshair')
        scroll_v = ttk.Scrollbar(area, orient='vertical', command=self.canvas.yview)
        scroll_h = ttk.Scrollbar(area, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=scroll_v.set, xscrollcommand=scroll_h.set)
        scroll_v.pack(side='right', fill='y')
        scroll_h.pack(side='bottom', fill='x')
        self.canvas.pack(side='left', fill='both', expand=True)

    def _build_pinned_actions(self, panel):
        """
        Bottom of the panel, always visible.

        Packed before the scrollable area and with side='bottom', so Tk gives
        these widgets their space first: no screen size can push the "save and
        move on" button out of the window.
        """
        ttk = self.ttk

        # the credits line is the same in both languages, so it is not registered
        ttk.Label(panel, text=f'GAAA - {APP_AUTHOR}', wraplength=230,
                  foreground='#777777', font=('', 8)).pack(side='bottom', anchor='w')

        bottom_row = ttk.Frame(panel)
        bottom_row.pack(side='bottom', fill='x', pady=(4, 2))
        self._reg(ttk.Button(bottom_row, text=self.tr('about_button'),
                             command=lambda: show_about(self.root, self.tr)),
                  'about_button').pack(side='right')
        self.combo_language = ttk.Combobox(
            bottom_row, textvariable=self.var_language, state='readonly',
            width=11, values=list(LANGUAGE_NAMES.values()))
        self.combo_language.pack(side='left')
        self.combo_language.bind('<<ComboboxSelected>>', self._on_language_selected)
        self._reg(ttk.Label(panel, text=self.tr('language'),
                            font=('', 8), foreground='#555555'),
                  'language').pack(side='bottom', anchor='w')

        ttk.Separator(panel).pack(side='bottom', fill='x', pady=4)

        self._reg(ttk.Button(panel, text=self.tr('apply_all'),
                             command=self.apply_to_all),
                  'apply_all').pack(side='bottom', fill='x', pady=2)
        self._reg(ttk.Button(panel, text=self.tr('save_next'),
                             command=self.save_and_next),
                  'save_next').pack(side='bottom', fill='x', pady=(2, 2))

        ttk.Label(panel, textvariable=self.var_status, wraplength=230,
                  foreground='#0a5a0a').pack(side='bottom', anchor='w', pady=(4, 2))
        ttk.Label(panel, textvariable=self.var_cursor,
                  foreground='#444444', font=('', 8)).pack(side='bottom', anchor='w')
        ttk.Separator(panel).pack(side='bottom', fill='x', pady=4)

    def _build_scrollable_controls(self, panel):
        """Everything above the pinned actions, inside a scrollable canvas."""
        tk, ttk = self.tk, self.ttk

        holder = ttk.Frame(panel)
        holder.pack(side='top', fill='both', expand=True)

        self.panel_canvas = tk.Canvas(holder, highlightthickness=0, borderwidth=0)
        self.panel_scroll = ttk.Scrollbar(holder, orient='vertical',
                                          command=self.panel_canvas.yview)
        self.panel_canvas.configure(yscrollcommand=self.panel_scroll.set)
        self.panel_canvas.pack(side='left', fill='both', expand=True)
        self._scrollbar_shown = False

        inner = ttk.Frame(self.panel_canvas)
        inner_id = self.panel_canvas.create_window((0, 0), window=inner, anchor='nw')

        def on_inner_configure(_event=None):
            self.panel_canvas.configure(scrollregion=self.panel_canvas.bbox('all'))
            self._update_panel_scrollbar(inner)

        def on_canvas_configure(event):
            self.panel_canvas.itemconfigure(inner_id, width=event.width)
            self._update_panel_scrollbar(inner)

        inner.bind('<Configure>', on_inner_configure)
        self.panel_canvas.bind('<Configure>', on_canvas_configure)

        self._fill_controls(inner)
        self._bind_panel_wheel(inner)
        # start at the top: "open image folder" is the first thing anyone needs
        self.panel_canvas.after_idle(lambda: self.panel_canvas.yview_moveto(0))

    def _update_panel_scrollbar(self, inner):
        """
        Show the panel scrollbar only when the controls do not fit.

        It has to be packed *before* the canvas: the canvas is packed with
        expand=True and would otherwise swallow the whole cavity, leaving the
        scrollbar zero pixels wide and therefore invisible.
        """
        needs = inner.winfo_reqheight() > self.panel_canvas.winfo_height()
        if needs and not self._scrollbar_shown:
            self.panel_scroll.pack(side='right', fill='y',
                                   before=self.panel_canvas)
            self._scrollbar_shown = True
        elif not needs and self._scrollbar_shown:
            self.panel_scroll.pack_forget()
            self._scrollbar_shown = False
        if not needs:
            # when everything fits, a leftover scroll offset would hide the
            # first controls behind the top edge
            self.panel_canvas.yview_moveto(0)

    def _bind_panel_wheel(self, widget):
        """Let the wheel scroll the panel while the pointer is over it."""
        def on_wheel(event):
            if self._scrollbar_shown:
                self.panel_canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')
            return 'break'

        widget.bind('<MouseWheel>', on_wheel)
        self.panel_canvas.bind('<MouseWheel>', on_wheel)
        for child in widget.winfo_children():
            self._bind_panel_wheel_recursive(child, on_wheel)

    def _bind_panel_wheel_recursive(self, widget, handler):
        if widget.winfo_class() != 'Listbox':      # the list scrolls on its own
            widget.bind('<MouseWheel>', handler)
        for child in widget.winfo_children():
            self._bind_panel_wheel_recursive(child, handler)

    def _fill_controls(self, parent):
        """The controls themselves, in the scrollable part of the panel."""
        tk, ttk = self.tk, self.ttk

        self._reg(ttk.Label(parent, text=self.tr('folders'), font=('', 10, 'bold')),
                  'folders').pack(anchor='w')
        self._reg(ttk.Button(parent, text=self.tr('open_images'),
                             command=self.choose_input),
                  'open_images').pack(fill='x', pady=2)
        self._reg(ttk.Button(parent, text=self.tr('choose_output'),
                             command=self.choose_output),
                  'choose_output').pack(fill='x', pady=2)
        self.label_output = ttk.Label(parent, text=self.tr('output_is', path='-'),
                                      wraplength=220, foreground='#555555')
        self.label_output.pack(anchor='w', pady=(0, 6))

        ttk.Separator(parent).pack(fill='x', pady=4)
        self._reg(ttk.Label(parent, text=self.tr('image'), font=('', 10, 'bold')),
                  'image').pack(anchor='w')
        self.label_image = ttk.Label(parent, text='-', wraplength=220)
        self.label_image.pack(anchor='w')
        nav = ttk.Frame(parent)
        nav.pack(fill='x', pady=4)
        self._reg(ttk.Button(nav, text=self.tr('previous'),
                             command=lambda: self.change_image(-1)),
                  'previous').pack(side='left', expand=True, fill='x')
        self._reg(ttk.Button(nav, text=self.tr('next'),
                             command=lambda: self.change_image(1)),
                  'next').pack(side='left', expand=True, fill='x')

        zoom_frame = ttk.Frame(parent)
        zoom_frame.pack(fill='x')
        ttk.Button(zoom_frame, text='-', width=3,
                   command=lambda: self.adjust_zoom(1 / 1.25)).pack(side='left')
        ttk.Button(zoom_frame, text='+', width=3,
                   command=lambda: self.adjust_zoom(1.25)).pack(side='left')
        self._reg(ttk.Button(zoom_frame, text=self.tr('fit_window'),
                             command=self.zoom_fit),
                  'fit_window').pack(side='left', expand=True, fill='x')

        ttk.Separator(parent).pack(fill='x', pady=4)
        self._reg(ttk.Label(parent, text=self.tr('selection_mode'),
                            font=('', 10, 'bold')),
                  'selection_mode').pack(anchor='w')
        self._reg(ttk.Checkbutton(parent, text=self.tr('fixed_size'),
                                  variable=self.var_fixed),
                  'fixed_size').pack(anchor='w')
        size_frame = ttk.Frame(parent)
        size_frame.pack(fill='x', pady=2)
        self._reg(ttk.Label(size_frame, text=self.tr('width_short')),
                  'width_short').pack(side='left')
        ttk.Entry(size_frame, textvariable=self.var_width, width=6).pack(side='left', padx=2)
        self._reg(ttk.Label(size_frame, text=self.tr('height_short')),
                  'height_short').pack(side='left')
        ttk.Entry(size_frame, textvariable=self.var_height, width=6).pack(side='left', padx=2)
        self._reg(ttk.Label(size_frame, text=self.tr('pixels')),
                  'pixels').pack(side='left')
        self._reg(ttk.Checkbutton(parent, text=self.tr('lock_rois'),
                                  variable=self.var_lock, command=self.update_lock),
                  'lock_rois').pack(anchor='w', pady=2)

        ttk.Separator(parent).pack(fill='x', pady=4)
        self._reg(ttk.Label(parent, text=self.tr('grid_title'), font=('', 10, 'bold')),
                  'grid_title').pack(anchor='w')
        grid_frame = ttk.Frame(parent)
        grid_frame.pack(fill='x', pady=2)
        self._reg(ttk.Label(grid_frame, text=self.tr('rows')),
                  'rows').pack(side='left')
        ttk.Entry(grid_frame, textvariable=self.var_rows, width=4).pack(side='left', padx=2)
        self._reg(ttk.Label(grid_frame, text=self.tr('columns')),
                  'columns').pack(side='left')
        ttk.Entry(grid_frame, textvariable=self.var_cols, width=4).pack(side='left', padx=2)
        self._reg(ttk.Button(grid_frame, text=self.tr('show'), width=6,
                             command=self.redraw),
                  'show').pack(side='left', padx=2)

        ttk.Separator(parent).pack(fill='x', pady=4)
        self._reg(ttk.Label(parent, text=self.tr('rois_title'), font=('', 10, 'bold')),
                  'rois_title').pack(anchor='w')
        self.listbox = tk.Listbox(parent, height=6, exportselection=False)
        self.listbox.pack(fill='x', pady=2)
        roi_buttons = ttk.Frame(parent)
        roi_buttons.pack(fill='x')
        self._reg(ttk.Button(roi_buttons, text=self.tr('remove'),
                             command=self.remove_roi),
                  'remove').pack(side='left', expand=True, fill='x')
        self._reg(ttk.Button(roi_buttons, text=self.tr('clear'),
                             command=self.clear_rois),
                  'clear').pack(side='left', expand=True, fill='x')

        ttk.Separator(parent).pack(fill='x', pady=4)
        self._reg(ttk.Label(parent, text=self.tr('output'), font=('', 10, 'bold')),
                  'output').pack(anchor='w')
        format_frame = ttk.Frame(parent)
        format_frame.pack(fill='x', pady=2)
        self._reg(ttk.Label(format_frame, text=self.tr('format')),
                  'format').pack(side='left')
        ttk.Combobox(format_frame, textvariable=self.var_format, width=7,
                     values=('png', 'jpg', 'tif'),
                     state='readonly').pack(side='left', padx=4)
        self._reg(ttk.Checkbutton(parent, text=self.tr('subfolder'),
                                  variable=self.var_subfolder),
                  'subfolder').pack(anchor='w', pady=(0, 4))

    def _bind_events(self):
        self.canvas.bind('<ButtonPress-1>', self.mouse_press)
        self.canvas.bind('<B1-Motion>', self.mouse_drag)
        self.canvas.bind('<ButtonRelease-1>', self.mouse_release)
        self.canvas.bind('<Motion>', self.mouse_move)
        self.canvas.bind('<Configure>', lambda e: self.redraw())
        self.canvas.bind('<MouseWheel>', self.mouse_wheel)
        self.listbox.bind('<<ListboxSelect>>', lambda e: self.redraw())

        for sequence, function in (
                ('<Right>', lambda e: self.change_image(1)),
                ('<Left>', lambda e: self.change_image(-1)),
                ('<Return>', lambda e: self.save_and_next()),
                ('<Delete>', lambda e: self.remove_roi()),
                ('<BackSpace>', lambda e: self.remove_roi()),
                ('<c>', lambda e: self.clear_rois()),
                ('<C>', lambda e: self.clear_rois()),
                ('<t>', lambda e: self.toggle_lock()),
                ('<T>', lambda e: self.toggle_lock()),
                ('<plus>', lambda e: self.adjust_zoom(1.25)),
                ('<equal>', lambda e: self.adjust_zoom(1.25)),
                ('<minus>', lambda e: self.adjust_zoom(1 / 1.25)),
                ('<Key-0>', lambda e: self.zoom_fit()),
                ('<F1>', lambda e: show_about(self.root, self.tr)),
        ):
            self.root.bind(sequence, self._only_outside_fields(function))

    def _only_outside_fields(self, function):
        """Keep the shortcuts from firing while the focus is in an Entry."""
        def wrapped(event):
            focus = self.root.focus_get()
            if focus is not None and focus.winfo_class() in ('TEntry', 'Entry', 'TCombobox'):
                return None
            return function(event)
        return wrapped

    # ----------------------------------------------------------------- folders
    def choose_input(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory(title=self.tr('dialog_images'))
        if folder:
            self.load_folder(Path(folder))

    def choose_output(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory(title=self.tr('dialog_output'))
        if folder:
            self.output_folder = Path(folder)
            self._update_output_label()

    def load_folder(self, folder):
        from tkinter import messagebox
        images = list_images(folder)
        if not images:
            messagebox.showwarning(
                self.tr('no_images_title'),
                self.tr('no_images', extensions=', '.join(EXTENSIONS), folder=folder))
            return
        self.input_folder = Path(folder)
        self.images = images
        self.index = 0
        self.saved.clear()
        if self.output_folder is None:
            self.output_folder = self.input_folder / 'crops'
        self._update_output_label()
        self.set_status('status_loaded', n=len(images))
        self.load_current_image()

    # ------------------------------------------------------------------ images
    def load_current_image(self):
        path = self.images[self.index]
        self.img = open_image(path)
        self.manual_zoom = None
        self.rois = [tuple(r) for r in self.locked_rois] if self.var_lock.get() else []
        self._update_image_label()
        self.redraw()

    def change_image(self, step):
        if not self.images:
            return
        new_index = self.index + step
        if not 0 <= new_index < len(self.images):
            self.set_status('status_end_of_list')
            return
        if self.var_lock.get():
            self.locked_rois = [tuple(r) for r in self.rois]
        self.index = new_index
        self.load_current_image()

    # -------------------------------------------------------------------- zoom
    def fit_scale(self):
        if self.img is None:
            return 1.0
        cw = max(self.canvas.winfo_width(), 50)
        ch = max(self.canvas.winfo_height(), 50)
        iw, ih = self.img.size
        return min(cw / iw, ch / ih)

    def adjust_zoom(self, factor):
        if self.img is None:
            return
        base = self.manual_zoom if self.manual_zoom else self.fit_scale()
        self.manual_zoom = max(0.02, min(8.0, base * factor))
        self.redraw()

    def zoom_fit(self):
        self.manual_zoom = None
        self.redraw()

    def mouse_wheel(self, event):
        if event.state & 0x0004:           # Ctrl held down = zoom
            self.adjust_zoom(1.25 if event.delta > 0 else 1 / 1.25)
        else:
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')

    # --------------------------------------------------------------- drawing
    def redraw(self):
        from PIL import ImageTk
        self.canvas.delete('all')
        if self.img is None:
            return

        self.scale = self.manual_zoom if self.manual_zoom else self.fit_scale()
        iw, ih = self.img.size
        dw, dh = max(1, int(iw * self.scale)), max(1, int(ih * self.scale))
        resampling = Image.LANCZOS if self.scale < 1 else Image.NEAREST
        self.photo = ImageTk.PhotoImage(self.img.resize((dw, dh), resampling))
        self.canvas.create_image(0, 0, anchor='nw', image=self.photo)
        self.canvas.configure(scrollregion=(0, 0, dw, dh))

        selected = set(self.listbox.curselection())
        n_rows = self._as_int(self.var_rows, 1)
        n_cols = self._as_int(self.var_cols, 1)

        for index, roi in enumerate(self.rois):
            colour = '#ffd400' if index in selected else '#00e5ff'
            self._draw_roi(roi, colour, label=f'{index + 1}',
                           n_rows=n_rows, n_cols=n_cols)
        if self._temp_roi:
            self._draw_roi(self._temp_roi, '#ff4d4d', dashed=True)

        self.update_list()

    def _draw_roi(self, roi, colour, label=None, dashed=False,
                  n_rows=1, n_cols=1):
        x, y, w, h = roi
        s = self.scale
        x0, y0, x1, y1 = x * s, y * s, (x + w) * s, (y + h) * s
        self.canvas.create_rectangle(x0, y0, x1, y1, outline=colour, width=2,
                                     dash=(4, 3) if dashed else None)
        if label:
            self.canvas.create_text(x0 + 4, y0 + 4, anchor='nw', text=label,
                                    fill=colour, font=('', 11, 'bold'))
        if (n_rows > 1 or n_cols > 1) and not dashed:
            for i in range(1, n_cols):
                bx = (x + w * i / n_cols) * s
                self.canvas.create_line(bx, y0, bx, y1, fill=colour, dash=(2, 4))
            for j in range(1, n_rows):
                by = (y + h * j / n_rows) * s
                self.canvas.create_line(x0, by, x1, by, fill=colour, dash=(2, 4))

    def update_list(self):
        selection = self.listbox.curselection()
        self.listbox.delete(0, 'end')
        for index, (x, y, w, h) in enumerate(self.rois, start=1):
            self.listbox.insert('end', f'{index:02d}  x={x} y={y}  {w}x{h}')
        for i in selection:
            if i < self.listbox.size():
                self.listbox.selection_set(i)

    # ---------------------------------------------------------------- mouse
    def _to_original(self, event):
        cx = self.canvas.canvasx(event.x) / self.scale
        cy = self.canvas.canvasy(event.y) / self.scale
        return cx, cy

    def _fixed_box(self, cx, cy):
        w = self._as_int(self.var_width, 100)
        h = self._as_int(self.var_height, 100)
        return clamp_roi(cx - w / 2, cy - h / 2, w, h, self.img.size)

    def mouse_press(self, event):
        if self.img is None:
            return
        cx, cy = self._to_original(event)
        if self.var_fixed.get():
            self._drag = 'fixed'
            self._temp_roi = self._fixed_box(cx, cy)
        else:
            self._drag = (cx, cy)
            self._temp_roi = clamp_roi(cx, cy, 0, 0, self.img.size)
        self.redraw()

    def mouse_drag(self, event):
        if self._drag is None:
            return
        cx, cy = self._to_original(event)
        if self._drag == 'fixed':
            self._temp_roi = self._fixed_box(cx, cy)
        else:
            x0, y0 = self._drag
            self._temp_roi = clamp_roi(min(x0, cx), min(y0, cy),
                                       abs(cx - x0), abs(cy - y0),
                                       self.img.size)
        self.redraw()
        self.mouse_move(event)

    def mouse_release(self, event):
        if self._drag is None:
            return
        self._drag = None
        roi = self._temp_roi
        self._temp_roi = None
        if roi and roi[2] >= 2 and roi[3] >= 2:
            self.rois.append(roi)
            if self.var_lock.get():
                self.locked_rois = [tuple(r) for r in self.rois]
            self.set_status('status_roi_added', n=len(self.rois),
                            w=roi[2], h=roi[3], x=roi[0], y=roi[1])
        self.redraw()

    def mouse_move(self, event):
        if self.img is None:
            return
        self._cursor = self._to_original(event)
        self._update_cursor_label()

    # ---------------------------------------------------------------- actions
    def remove_roi(self):
        if not self.rois:
            return
        selection = self.listbox.curselection()
        index = selection[0] if selection else len(self.rois) - 1
        self.rois.pop(index)
        if self.var_lock.get():
            self.locked_rois = [tuple(r) for r in self.rois]
        self.redraw()

    def clear_rois(self):
        self.rois = []
        if self.var_lock.get():
            self.locked_rois = []
        self.redraw()

    def toggle_lock(self):
        self.var_lock.set(not self.var_lock.get())
        self.update_lock()

    def update_lock(self):
        if self.var_lock.get():
            self.locked_rois = [tuple(r) for r in self.rois]
            self.set_status('status_locked')
        else:
            self.locked_rois = []
            self.set_status('status_unlocked')

    def save_and_next(self):
        from tkinter import messagebox
        if self.img is None or not self.images:
            return
        if not self.rois:
            messagebox.showinfo(self.tr('no_roi_title'), self.tr('no_roi_save'))
            return

        path = self.images[self.index]
        records = save_crops(
            path, self.rois, self.output_folder,
            n_rows=self._as_int(self.var_rows, 1),
            n_cols=self._as_int(self.var_cols, 1),
            fmt=self.var_format.get(),
            subfolder_per_image=self.var_subfolder.get(),
            img=self.img)
        log_to_csv(self.output_folder, records)
        self.saved.add(path.name)
        self.set_status('status_saved', n=len(records), name=path.name)

        if self.index < len(self.images) - 1:
            self.change_image(1)
        else:
            self.load_current_image()
            messagebox.showinfo(self.tr('end_title'), self.tr('end_message'))

    def apply_to_all(self):
        from tkinter import messagebox
        if not self.rois or not self.images:
            messagebox.showinfo(self.tr('no_roi_title'), self.tr('no_roi_batch'))
            return
        n_rows = self._as_int(self.var_rows, 1)
        n_cols = self._as_int(self.var_cols, 1)
        question = self.tr('apply_all_question',
                           rois=len(self.rois), rows=n_rows, cols=n_cols,
                           per_image=len(self.rois) * n_rows * n_cols,
                           n=len(self.images), path=self.output_folder)
        if not messagebox.askokcancel(self.tr('apply_all_title'), question):
            return

        total = apply_in_batch(self.input_folder, self.output_folder, self.rois,
                               n_rows, n_cols, self.var_format.get(),
                               self.var_subfolder.get(), log=lambda m: None)
        self.saved.update(p.name for p in self.images)
        self.set_status('status_batch_done', n=total, path=self.output_folder)
        messagebox.showinfo(self.tr('done_title'),
                            self.tr('done_message', n=total, path=self.output_folder))

    @staticmethod
    def _as_int(variable, default):
        try:
            return max(1, int(float(variable.get())))
        except (TypeError, ValueError):
            return default


def open_window(input_folder=None, output_folder=None, fmt='png', language=None):
    """Open the cropping interface (callable from a notebook or the terminal)."""
    import tkinter as tk
    root = tk.Tk()
    CropperApp(root, input_folder, output_folder, fmt, language)
    root.mainloop()


# =============================================================================
# 3. COMMAND LINE
# =============================================================================
def _parse_arguments(argv=None):
    p = argparse.ArgumentParser(
        description='Manual/semi-automatic cropping of ROIs from batches of images.')
    p.add_argument('--input', help='folder with the original images')
    p.add_argument('--output', help='destination folder for the crops')
    p.add_argument('--format', default='png', help='png (default), jpg or tif')
    p.add_argument('--roi', action='append', default=[],
                   help='fixed ROI "x,y,width,height" (may be repeated)')
    p.add_argument('--grid', default='1x1',
                   help='subdivision of each ROI, e.g. 2x3 (rows x columns)')
    p.add_argument('--subfolder', action='store_true',
                   help='create one subfolder per source image')
    p.add_argument('--batch', action='store_true',
                   help='apply the --roi to the whole folder without opening the window')
    p.add_argument('--csv', help='redo the crops described in a CSV')
    p.add_argument('--lang', choices=sorted(TEXTS), default=None,
                   help='interface language: pt or en (default: remembered/system)')
    p.add_argument('--about', action='store_true',
                   help='open only the "About" window (program credits)')
    return p.parse_args(argv)


def main(argv=None):
    args = _parse_arguments(argv)

    if args.about:
        window = show_about(tr=Translator(args.lang))
        window.mainloop()
        return 0

    try:
        n_rows, n_cols = (int(v) for v in args.grid.lower().split('x'))
    except ValueError:
        print(f'Invalid grid: {args.grid} (use something like 2x3)')
        return 2

    if args.csv:
        if not args.input or not args.output:
            print('For --csv also provide --input and --output.')
            return 2
        redo_from_csv(args.csv, args.input, args.output, args.format)
        return 0

    rois = []
    for text in args.roi:
        parts = text.replace(';', ',').split(',')
        if len(parts) != 4:
            print(f'Invalid ROI: {text} (use x,y,width,height)')
            return 2
        rois.append(tuple(int(float(v)) for v in parts))

    if args.batch:
        if not args.input or not rois:
            print('The --batch mode requires --input and at least one --roi.')
            return 2
        output = args.output or str(Path(args.input) / 'crops')
        apply_in_batch(args.input, output, rois, n_rows, n_cols,
                       args.format, args.subfolder)
        return 0

    open_window(args.input, args.output, args.format, args.lang)
    return 0


if __name__ == '__main__':
    sys.exit(main())
