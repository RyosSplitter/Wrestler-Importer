"""Sequential batch orchestration around the existing isolated PAC worker.

Each costume gets its own job directory and process. Failed conversions never
become review candidates, and successful candidates remain available on cancel.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from desktop.adapters import adapter

TERMINAL = ('succeeded', 'skipped', 'cancelled', 'not-run')


def write_state(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.batch-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def counts(items):
    return {state: sum(row['state'] == state for row in items)
            for state in ('pending', 'running', *TERMINAL)}


def summary_text(state):
    totals = counts(state['items'])
    heading = ('Batch cancelled' if state['phase'] == 'cancelled' else
               'Batch stopped' if state['phase'] == 'failed' else 'Batch complete')
    lines = [heading,
             f"{totals['succeeded']} succeeded | {totals['skipped']} skipped | "
             f"{totals['cancelled']} cancelled | {totals['not-run']} not run",
             state.get('error', ''),
             'Successful candidates can be previewed and saved in Batch Converter.', '']
    for row in state['items']:
        lines.append(row['state'].upper() + '  ' + row['label'])
        if row.get('error'):
            lines.append('  ' + row['error'])
        if row.get('job'):
            lines.append('  Job: ' + row['job'])
    return '\n'.join(lines) + '\n'


def plan_files(files, source_format, *, cancelled=lambda: False):
    """Enumerate costumes in the background; retain bad files as skipped rows."""
    reader = adapter(source_format)
    items, seen = [], set()
    for value in files:
        path = Path(value).resolve()
        key = os.path.normcase(str(path))
        if key in seen:
            continue
        seen.add(key)
        row = dict(source=str(path), source_entry='', label=path.name, state='pending', error='')
        try:
            if cancelled():
                row['state'] = 'not-run'
                entries = []
            else:
                if not path.is_file() or path.suffix.lower() != '.pac':
                    raise ValueError('Choose an existing .pac file.')
                limit = 64 if source_format == 'wwe13-wii' else 32
                if path.stat().st_size > limit * 1024 * 1024:
                    raise ValueError(f'The supported input budget is {limit} MiB.')
                catalogue = reader.catalogue(path) if source_format in ('jbi', 'wwe13-wii') else {}
                entries = catalogue.get('entries', [])
            if entries:
                for costume in entries:
                    ident = costume['id']
                    items.append(dict(row, source_entry=ident, label=path.name + ' [' + ident + ']'))
            else:
                items.append(row)
        except Exception as exc:
            items.append(dict(row, state='skipped', error=str(exc)))
    for index, row in enumerate(items):
        row['id'] = str(index)
    return items


def load_result(row):
    if row['state'] != 'succeeded':
        return None
    result = json.loads((Path(row['job']) / 'success.json').read_text(encoding='utf-8'))
    if Path(result['source']).resolve() != Path(row['source']).resolve():
        raise ValueError('Batch result belongs to a different source.')
    if result.get('source_entry', '') != row['source_entry']:
        raise ValueError('Batch result belongs to a different costume.')
    return result


def run_batch(request_path, entry, *, spawn=subprocess.Popen, pause=time.sleep):
    request_path = Path(request_path).resolve()
    root = request_path.parent
    state = dict(schema='pac-batch/1', phase='planning', items=[], current=None,
                 percent=0, message='Finding source costumes…')
    child = None
    cancel = root / 'cancel'
    try:
        options = json.loads(request_path.read_text(encoding='utf-8'))
        template = options['options']
        if template.get('texture_mode') == 'Priority Selection' or template.get('priority_textures'):
            raise ValueError('Per-model texture priorities require the single converter.')
        write_state(root / 'state.json', state)
        state['items'] = plan_files(options['files'], template['source_format'], cancelled=cancel.exists)
        state['phase'] = 'running'
        write_state(root / 'state.json', state)
        for row in state['items']:
            if cancel.exists():
                break
            if row['state'] != 'pending':
                continue
            job = root / 'models' / f"{int(row['id']):05d}"
            job.mkdir(parents=True)
            row.update(state='running', job=str(job))
            model_request = dict(template, source=row['source'], source_entry=row['source_entry'])
            write_state(job / 'request.json', model_request)
            state.update(current=row['id'], percent=0, message='Starting ' + row['label'])
            write_state(root / 'state.json', state)
            try:
                with (job / 'worker.log').open('w', encoding='utf-8') as log:
                    child = spawn(list(entry) + ['--worker', str(job / 'request.json')],
                                  stdout=log, stderr=log,
                                  creationflags=0x08000000 if os.name == 'nt' else 0)
                    while child.poll() is None:
                        if cancel.exists():
                            (job / 'cancel').touch(exist_ok=True)
                        events = job / 'events.jsonl'
                        if events.is_file():
                            for line in reversed(events.read_text(encoding='utf-8').splitlines()):
                                try:
                                    event = json.loads(line)
                                    percent, message = event['percent'], event['message']
                                    if (percent, message) != (state['percent'], state['message']):
                                        state.update(percent=percent, message=message)
                                        write_state(root / 'state.json', state)
                                    break
                                except (ValueError, KeyError):
                                    continue  # Worker may be writing its last line.
                        pause(.15)
                    code = child.returncode
                    child = None
                if code == 0 and (job / 'success.json').is_file():
                    row['state'] = 'succeeded'
                    result = load_result(row)
                    if not Path(result['pac']).is_file() or not Path(result['preview']).is_dir():
                        raise ValueError('Worker returned an incomplete review candidate; see its logs.')
                else:
                    failure_path = job / 'failure.json'
                    failure = json.loads(failure_path.read_text(encoding='utf-8')) if failure_path.is_file() else {}
                    row.update(state='cancelled' if failure.get('cancelled') or cancel.exists() else 'skipped',
                               error=failure.get('error') or f'Worker exited with code {code}; see its logs.')
            except Exception as exc:
                row.update(state='cancelled' if cancel.exists() else 'skipped', error=str(exc))
            state.update(current=None, percent=0)
            write_state(root / 'state.json', state)
        for row in state['items']:
            if row['state'] == 'pending':
                row['state'] = 'not-run'
        state.update(phase='cancelled' if cancel.exists() else 'completed', current=None,
                     percent=100, message='Review successful models and save the ones you want.')
    except Exception as exc:
        state.update(phase='failed', error=str(exc), current=None, message=str(exc))
        for row in state['items']:
            if row['state'] in ('running', 'pending'):
                row.update(state='not-run', error='Batch stopped before this conversion completed.')
    finally:
        # The worker process remains owned until it exits, even on an unexpected
        # orchestration failure; do not orphan Blender/QA descendants.
        if child is not None:
            (Path(row['job']) / 'cancel').touch(exist_ok=True)
            child.wait()
        write_state(root / 'state.json', state)
        write_state(root / 'summary.json', state)
        (root / 'summary.txt').write_text(summary_text(state), encoding='utf-8')
    return 1 if state['phase'] == 'failed' else 0


def save_reviewed(state, row, destination, batch_root):
    """Protect every batch input and all working candidates, then reuse Save As."""
    from desktop.storage import save_as
    result = load_result(row)
    if result is None:
        raise ValueError('Select a successful conversion to save.')
    destination = Path(destination).resolve()
    if destination.is_relative_to(Path(batch_root).resolve()):
        raise ValueError('Save outside the batch working folder.')
    protected = {Path(item['source']).resolve() for item in state['items']}
    protected.add(Path(result['base']).resolve())
    if destination in protected or (destination.exists() and any(
            path.exists() and os.path.samefile(destination, path) for path in protected)):
        raise ValueError('Save As cannot overwrite any batch source or the PSP base.')
    return save_as(result, destination)
