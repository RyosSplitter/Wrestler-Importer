"""Exercise actual frozen batch workers, continued failures, preview and Save As."""
import json
from pathlib import Path
import time
from unittest.mock import patch

from PIL import ImageGrab

from desktop.batch import counts, load_result, save_reviewed
from desktop.core import digest
from tools.generate_conformance_fixtures import pac
from tools.jbi_fixture import create
from tools.psp_mesh_merge_trial import sections


def run(app, output, base):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    archive = create(Path(base), output.parent / 'fixtures')
    first, last = archive.parent / '0000.pac', archive.parent / '0100.pac'
    rows = [(section['id'], payload) for section, payload in sections(first.read_bytes())]
    unsupported = archive.parent / 'unsupported.pac'
    unsupported.write_bytes(pac(rows + [(5, dict(rows)[2])]))
    malformed = archive.parent / 'malformed.pac'
    malformed.write_bytes(b'PAC ' + bytes(4))
    sources = [first, unsupported, malformed, last]
    hashes = {str(path): digest(path) for path in [*sources, archive, Path(base)]}
    notices, errors = [], []
    app.open_batch()
    batch = app.batch_window
    started = time.monotonic()

    def wait(predicate, timeout=300):
        start = time.monotonic()
        while not predicate():
            app.root.update()
            if errors:
                raise AssertionError(errors[-1])
            if time.monotonic() - start > timeout:
                raise TimeoutError('Batch smoke timed out: ' + batch.status.get())
            time.sleep(.03)
        app.root.update()

    with patch('tkinter.messagebox.showinfo', side_effect=lambda title, message, **kw: notices.append((title, message))), \
         patch('tkinter.messagebox.showerror', side_effect=lambda title, message, **kw: errors.append((title, message))), \
         patch('tkinter.messagebox.askyesno', return_value=True):
        batch.base.set(str(Path(base).resolve()))
        batch.game.set(next(label for label, key in batch.formats.items() if key == 'wwe13-wii'))
        batch.update_options()
        app.root.update()
        assert batch.wii_row.winfo_ismapped()
        assert tuple(batch.mode_box.cget('values')) == ('Default',)
        batch.game.set(next(label for label, key in batch.formats.items() if key == 'jbi'))
        batch.update_options()
        assert 'Priority Selection' not in batch.mode_box.cget('values')
        batch.add_files(sources)
        batch.add_files([first])
        assert len(batch.files) == 4
        batch.start()
        assert batch.running()
        assert 'disabled' in batch.game_box.state()
        wait(lambda: not batch.running())
        assert [row['state'] for row in batch.state['items']] == ['succeeded', 'skipped', 'skipped', 'succeeded'], batch.state
        assert 'Unsupported JBI accessory' in batch.state['items'][1]['error']
        assert len(notices) == 1
        results = []
        # Review two different successes and save via the actual UI callback.
        for index in (0, 3):
            row = batch.state['items'][index]
            batch.tree.selection_set(row['id'])
            batch.select()
            app.root.update()
            assert batch.preview.cget('image')
            assert 'disabled' not in batch.save_button.state()
            assert batch.result['source'] == row['source']
            for view in ('front', 'back', 'left', 'right', 'front-left'):
                batch.set_view(view)
                assert batch.preview.cget('image')
            batch.toggle_zoom()
            batch.toggle_zoom()
            destination = output.parent / f'saved-{index}.pac'
            with patch('tkinter.filedialog.asksaveasfilename', return_value=str(destination)):
                batch.export()
            assert destination.read_bytes() == Path(batch.result['pac']).read_bytes()
            results.append(dict(source=row['source'], bytes=batch.result['bytes'], sha256=digest(destination)))
        batch.tree.selection_set('1')
        batch.select()
        assert batch.result is None and not batch.preview.cget('image')
        assert 'disabled' in batch.save_button.state()
        assert 'Unsupported JBI accessory' in batch.detail.get()
        batch.tree.selection_set('3')
        batch.select()
        app.root.update()
        x, y = batch.top.winfo_rootx(), batch.top.winfo_rooty()
        ImageGrab.grab().crop((x, y, x + batch.top.winfo_width(), y + batch.top.winfo_height())).save(output.with_suffix('.png'))
        completed = dict(counts(batch.state['items']))

        # The native archive is expanded in the background and each costume
        # is sent through its own real worker, retaining its source entry.
        batch.clear()
        batch.add_files([archive])
        batch.start()
        wait(lambda: not batch.running())
        assert [row['source_entry'] for row in batch.state['items']] == ['0000', '0100']
        assert all(row['state'] == 'succeeded' for row in batch.state['items'])
        for row in batch.state['items']:
            assert load_result(row)['source_entry'] == row['source_entry']

        # Request cancellation after the first result and after the next worker
        # has started; completed models must remain reviewable and saveable.
        batch.clear()
        batch.add_files([first, unsupported, last])
        batch.start()
        wait(lambda: (len(batch.state['items']) == 3 and batch.state['items'][0]['state'] == 'succeeded'
                      and any(row['state'] == 'running' for row in batch.state['items'][1:])) or not batch.running())
        batch.cancel()
        wait(lambda: not batch.running())
        assert batch.state['phase'] == 'cancelled', batch.state
        assert batch.state['items'][0]['state'] == 'succeeded'
        assert counts(batch.state['items'])['cancelled'] + counts(batch.state['items'])['not-run'] >= 1
        row = batch.state['items'][0]
        destination = output.parent / 'saved-after-cancel.pac'
        save_reviewed(batch.state, row, destination, batch.job)
        assert destination.is_file()
        assert all(digest(Path(path)) == wanted for path, wanted in hashes.items())
        report = dict(status='pass', source='Procedural JBI contract models on development-only PSP base',
                      sequential_workers=True, continued_after_conversion_failure=True,
                      malformed_input_skipped=True, per_source_game_options=True,
                      archive_costumes_expanded=True, separate_previews_and_ui_saves=results,
                      failed_row_clears_preview=True, completion_summary=completed,
                      cancellation_retains_completed_outputs=True, sources_and_base_unchanged=True,
                      elapsed_seconds=time.monotonic() - started,
                      limitation='Desktop/runtime functional test; not PPSSPP gameplay validation.')
        output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    batch.close()
    return report
