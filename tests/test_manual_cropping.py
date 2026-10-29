"""
Tests for manual_cropping.py. No external test runner needed:

    python tests/test_manual_cropping.py

The interface tests open a real Tk window off to the side and close it again,
so they need a desktop session (they are skipped when Tk is unavailable).
"""

import csv
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

import manual_cropping as mc

PASSED = []


def check(name, condition, detail=''):
    if not condition:
        raise AssertionError(f'{name} failed. {detail}')
    PASSED.append(name)
    print(f'  ok  {name}')


# =============================================================================
# core
# =============================================================================
def test_core(tmp):
    source = tmp / 'src'
    source.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (400, 300), (10, 120, 200)).save(source / 'sample.png')

    check('clamp_roi keeps the ROI inside the image',
          mc.clamp_roi(-20, -20, 500, 500, (400, 300)) == (0, 0, 400, 300))

    blocks = mc.split_into_grid((0, 0, 300, 240), 2, 3)
    check('split_into_grid returns rows x cols blocks', len(blocks) == 6)
    check('grid blocks tile the ROI without gaps',
          sum(b[4] * b[5] for b in blocks) == 300 * 240)

    records = mc.save_crops(source / 'sample.png', [(50, 40, 300, 240)],
                            tmp / 'out', n_rows=2, n_cols=3, fmt='png')
    check('save_crops writes one record per block', len(records) == 6)
    check('every crop has the same size',
          len({(r['width'], r['height']) for r in records}) == 1)

    mc.log_to_csv(tmp / 'out', records)
    csv_file = tmp / 'out' / mc.CSV_NAME
    check('the coordinate CSV is created', csv_file.exists())

    redone = mc.redo_from_csv(csv_file, source, tmp / 'redo', log=lambda m: None)
    check('redo_from_csv reproduces every crop', redone == 6)
    first = records[0]
    check('a redone crop has the recorded size',
          Image.open(tmp / 'redo' / first['output_file']).size
          == (first['width'], first['height']))

    total = mc.apply_in_batch(source, tmp / 'batch', [(0, 0, 200, 150)],
                              n_rows=1, n_cols=2, fmt='jpg', log=lambda m: None)
    check('apply_in_batch processes the folder', total == 2)


def test_legacy_csv(tmp):
    """CSV files written by v1.0, with Portuguese columns, must still work."""
    source = tmp / 'src'
    legacy = tmp / 'legacy.csv'
    columns = ['imagem', 'roi', 'grade_linha', 'grade_coluna', 'x', 'y',
               'largura', 'altura', 'largura_original', 'altura_original',
               'arquivo_saida']
    with open(legacy, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerow(dict(zip(columns, ['sample.png', 1, 1, 1, 10, 20,
                                           100, 80, 400, 300, 'old.png'])))

    redone = mc.redo_from_csv(legacy, source, tmp / 'redo_legacy',
                              log=lambda m: None)
    check('a v1.0 CSV is still replayed', redone == 1)
    check('the crop from a v1.0 CSV has the recorded size',
          Image.open(tmp / 'redo_legacy' / 'old.png').size == (100, 80))


# =============================================================================
# languages
# =============================================================================
def test_translations():
    keys = {code: set(table) for code, table in mc.TEXTS.items()}
    reference = keys[mc.DEFAULT_LANGUAGE]
    for code, table in keys.items():
        check(f'language "{code}" defines every key',
              table == reference,
              f'missing: {reference - table} | extra: {table - reference}')
    check('every language has a display name',
          set(mc.TEXTS) == set(mc.LANGUAGE_NAMES))

    tr = mc.Translator('pt')
    check('Portuguese lookup', tr('rows') == 'linhas')
    check('placeholders are filled',
          tr('status_loaded', n=7) == '7 imagens carregadas.')
    tr.set_language('en')
    check('switching changes the language', tr('rows') == 'rows')
    check('an unknown key falls back to itself', tr('no_such_key') == 'no_such_key')


def test_language_is_remembered():
    original = mc.load_language()
    try:
        mc.save_language('en')
        check('the language is written to disk', mc.load_language() == 'en')
        mc.save_language('pt')
        check('the language is read back', mc.load_language() == 'pt')
    finally:
        mc.save_language(original)


# =============================================================================
# interface
# =============================================================================
def widget_for(app, key):
    return next(w for w, k in app._translatable if k == key)


def actions_visible(app, root):
    bottom = root.winfo_rooty() + root.winfo_height()
    for key in ('save_next', 'apply_all', 'about_button'):
        widget = widget_for(app, key)
        if not widget.winfo_ismapped():
            return False
        if widget.winfo_rooty() + widget.winfo_height() > bottom + 1:
            return False
    return True


def test_interface(tmp):
    import tkinter as tk

    root = tk.Tk()
    try:
        app = mc.CropperApp(root, tmp / 'src', tmp / 'out', 'png', language='pt')
        root.update_idletasks()
        root.update()
        check('the panel starts scrolled to the top',
              app.panel_canvas.yview()[0] == 0.0,
              f'yview={app.panel_canvas.yview()}')

        # the default window must leave room for the taskbar, otherwise the
        # pinned buttons end up underneath it
        bottom = root.winfo_rooty() + root.winfo_height()
        check('the default window fits the usable area of the screen',
              bottom <= root.winfo_screenheight() - 40,
              f'bottom={bottom} screen={root.winfo_screenheight()}')

        # --- the action buttons must survive every screen size --------------
        for width, height in [(820, 520), (900, 600), (1024, 640),
                              (1200, 744), (1366, 768), (1600, 1000)]:
            root.geometry(f'{width}x{height}')
            root.update_idletasks()
            root.update()
            check(f'actions stay visible at {width}x{height}',
                  actions_visible(app, root))

            inner = app.panel_canvas.nametowidget(
                app.panel_canvas.itemcget(app.panel_canvas.find_all()[0], 'window'))
            fits = inner.winfo_reqheight() <= app.panel_canvas.winfo_height()
            check(f'panel scrollbar matches the content at {width}x{height}',
                  bool(app.panel_scroll.winfo_ismapped()) is not fits)

        # --- switching language must not disturb the work in progress -------
        app.rois = [(10, 10, 50, 50)]
        app.set_status('status_loaded', n=3)
        check('Portuguese button text',
              widget_for(app, 'save_next')['text']
              == 'Salvar recortes e avancar (Enter)')
        check('Portuguese status', app.var_status.get() == '3 imagens carregadas.')

        app.set_language('en')
        root.update_idletasks()
        check('button text follows the language',
              widget_for(app, 'save_next')['text']
              == 'Save crops and move on (Enter)')
        check('section titles follow the language',
              widget_for(app, 'rois_title')['text'] == 'ROIs of the current image')
        check('the status is re-rendered in the new language',
              app.var_status.get() == '3 images loaded.')
        check('the output label follows the language',
              app.label_output['text'].startswith('output:'))
        check('the ROIs survive the language change',
              app.rois == [(10, 10, 50, 50)])

        app.set_language('pt')
        check('switching back restores Portuguese',
              app.var_status.get() == '3 imagens carregadas.')
        check('the ROIs survive switching back',
              app.rois == [(10, 10, 50, 50)])
    finally:
        root.destroy()


# =============================================================================
# command line
# =============================================================================
def test_cli(tmp):
    source = tmp / 'src'
    check('--batch crops the folder',
          mc.main(['--input', str(source), '--output', str(tmp / 'cli'),
                   '--roi', '5,5,100,90', '--grid', '3x1', '--batch']) == 0)
    check('--grid is honoured',
          len(list((tmp / 'cli').glob('*.png'))) == 3)
    check('an invalid --grid is rejected', mc.main(['--grid', 'abc']) == 2)
    check('--csv without --input is rejected',
          mc.main(['--csv', 'x.csv']) == 2)
    check('--batch without --roi is rejected',
          mc.main(['--input', str(source), '--batch']) == 2)


def run():
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        print('core')
        test_core(tmp)
        test_legacy_csv(tmp)
        print('languages')
        test_translations()
        test_language_is_remembered()
        print('command line')
        test_cli(tmp)
        print('interface')
        try:
            import tkinter  # noqa: F401
        except ImportError:
            print('  -- skipped: Tkinter is not available')
        else:
            test_interface(tmp)
    print(f'\n{len(PASSED)} checks passed')


if __name__ == '__main__':
    run()
