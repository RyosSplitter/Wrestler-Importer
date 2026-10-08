"""App orchestration around the unchanged, pinned opacity-fix primitives."""
from dataclasses import dataclass
from datetime import datetime
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid

from app import VERSION

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / 'stable_pipeline'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_backend(root=BACKEND):
    profile = json.loads((root / 'profile.json').read_text(encoding='utf-8'))
    for name, expected in profile['files'].items():
        if Path(name).name != name or digest(root / name) != expected:
            raise ValueError('The opacity-fix backend has changed. Extract a fresh beta package.')
    return profile


@dataclass(frozen=True)
class Job:
    source: str
    base: str
    reference: str
    editor: str
    blender: str
    output_parent: str
    target_game: str = 'SVR 2011 PSP'

    def validate(self):
        for field in ('source', 'base', 'reference', 'editor', 'blender'):
            path = Path(getattr(self, field))
            if not path.is_file():
                raise ValueError(f'{field.title()} file was not found: {path}')
        if Path(self.source).suffix.lower() != '.pac' or Path(self.base).suffix.lower() != '.pac':
            raise ValueError('Choose a PS2 source PAC and a PSP base PAC.')
        if Path(self.source).resolve() == Path(self.base).resolve():
            raise ValueError('The source and PSP base must be different files.')
        if not self.output_parent.strip():
            raise ValueError('Choose an export folder.')
        parent = Path(self.output_parent).resolve()
        if parent.exists() and not parent.is_dir():
            raise ValueError('The export location must be a folder.')
        if self.target_game not in ('SVR 2006 PSP', 'SVR 2007 PSP', 'SVR 2008 PSP',
                                    'SVR 2009 PSP', 'SVR 2010 PSP', 'SVR 2011 PSP'):
            raise ValueError('Choose a PSP SVR target game.')


def run_job(job, progress=lambda percent, message: None):
    """Publish a fresh folder only after PAC and preview checks succeed."""
    if sys.version_info[:2] != (3, 13):
        raise ValueError('This beta needs Python 3.13 to use the supplied PSP editor.')
    job.validate()
    profile = verify_backend()
    from stable_pipeline.editor_bridge import EDITOR_SHA256, export
    from stable_pipeline.convert_hctp import verify_serialized
    from stable_pipeline.hctp_read import load_hctp
    from stable_pipeline.pac_inspect import inspect_pac
    from stable_pipeline.pac_repack import repack
    from stable_pipeline.prepare_model import prepare
    from stable_pipeline.texture_convert import convert_pac, write_preview_textures
    from stable_pipeline.yobj_read import load_model

    source, base, reference = map(Path, (job.source, job.base, job.reference))
    editor, blender = Path(job.editor), Path(job.blender)
    progress(5, 'Checking the selected files and tools')
    if digest(editor) != EDITOR_SHA256:
        raise ValueError('Select the original yobj_mesh_editor_PSP_GUI.exe supplied for this project.')
    version = subprocess.run([str(blender), '--version'], capture_output=True, text=True,
                             timeout=30, check=True).stdout
    if not re.search(r'^Blender 4\.3\.2(?:\s|$)', version, re.MULTILINE):
        raise ValueError('Select Blender 4.3.2. This beta pins the version used for your working model.')

    progress(12, 'Reading the HCTP model and PSP reference')
    model = load_hctp(source)
    target, donor = load_model(base, psp_geometry=True), load_model(reference, psp_geometry=True)
    source_hash, base_hash, reference_hash = digest(source), digest(base), digest(reference)
    parent = Path(job.output_parent).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    working = Path(tempfile.mkdtemp(prefix='.partial-', dir=parent))
    try:
        progress(28, 'Reducing the model with the working opacity-fix profile')
        source_json, reduced_json = working / 'source.json', working / 'reduced-source.json'
        source_json.write_text(json.dumps(model, allow_nan=False), encoding='utf-8')
        env = os.environ.copy()
        for key, folder in (('BLENDER_USER_CONFIG', 'blender-config'),
                            ('BLENDER_USER_EXTENSIONS', 'blender-extensions'),
                            ('MESA_SHADER_CACHE_DIR', 'mesa-cache')):
            env[key] = str(working / folder)
        with (working / 'reduction.log').open('w', encoding='utf-8') as log:
            subprocess.run([str(blender), '--background', '--python-exit-code', '1', '--python',
                            str(BACKEND / 'blender_reduce.py'), '--', str(source_json),
                            str(reduced_json), '0.3'], stdout=log, stderr=subprocess.STDOUT,
                           env=env, check=True)
        reduced = json.loads(reduced_json.read_text(encoding='utf-8'))
        progress(48, 'Aligning the model and transferring PSP weights')
        prepared, preparation = prepare(reduced, target, donor)
        progress(65, 'Preparing PSP textures')
        textures = convert_pac(source, working / 'textures', max_dimension=64, bits=4)
        prepared['texture_bits'] = [t['bits'] for t in sorted(textures['textures'], key=lambda t: t['index'])]
        prepared_json = working / 'prepared.json'
        prepared_json.write_text(json.dumps(prepared, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        base_data = base.read_bytes()
        sections = [s for s in inspect_pac(base_data)['sections'] if s['id'] == 2 and s['kind'] == 'model_section']
        if len(sections) != 1:
            raise ValueError('The PSP base must contain exactly one supported model section.')
        section = sections[0]
        base_yobj = base_data[section['offset']:section['offset']+section['size']]
        base_file = working / 'base-model.bin'
        base_file.write_bytes(base_yobj)
        progress(78, 'Building the PSP model and Noesis preview')
        preview = working / 'preview'
        with (working / 'editor.log').open('w', encoding='utf-8') as log:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                export(editor, base_file, prepared_json, preview)
        progress(88, 'Checking the exported model and textures')
        verification = verify_serialized(prepared, base_yobj, preview / 'prepared.yobj')
        preview_files = write_preview_textures(textures, working / 'textures', preview)
        progress(96, 'Packing the PSP PAC')
        stem = re.sub(r'[^A-Za-z0-9_.-]', '_', source.stem)[:48].strip('.') or 'wrestler'
        pac = working / (stem+'-PSP-opacity-fix.pac')
        packing = repack(base, preview / 'prepared.yobj', working / 'textures', pac,
                         max_bytes=profile['beta_pac_limit_bytes'])
        sample = profile['sample']
        baseline_match = None
        if (source_hash == sample['source_sha256'] and base_hash == sample['base_sha256']
                and reference_hash == sample['reference_sha256']):
            baseline_match = packing['sha256'] == sample['pac_sha256']
            if not baseline_match:
                raise ValueError('This sample differs from the confirmed working PAC. Export withheld; keep the diagnostic logs.')
        packed = pac.read_bytes()
        model_section = next(s for s in inspect_pac(packed)['sections'] if s['id'] == 2)
        if packed[model_section['offset']:model_section['offset']+model_section['size']] != (preview / 'prepared.yobj').read_bytes():
            raise ValueError('The Noesis preview differs from the PAC model.')
        report = {'app_version': VERSION, 'profile_id': profile['profile_id'],
                  'backend_revision': profile['backend_revision'], 'source_game': 'HCTP PS2',
                  'target_game': job.target_game, 'source_sha256': source_hash,
                  'base_sha256': base_hash, 'reference_sha256': reference_hash,
                  'sample_byte_identical_to_uploaded_working_pac': baseline_match,
                  'preparation': preparation, 'textures': textures, 'reduction': reduced['reduction_report'],
                  'native_serialization': verification, 'preview_texture_files': preview_files,
                  'pac': packing, 'pac_filename': pac.name,
                  'status': 'File checks passed. Validate the exported wrestler in PPSSPP.'}
        (working / 'conversion-report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        (working / 'README-export.txt').write_text(
            f'Wrestler Importer {VERSION}\nProfile: opacity-fix-v1\nPAC: {pac.name}\n'
            f'Size: {packing["output_bytes"]/1024:g} KiB\n\n'
            'Inject the PAC using your working PAC/ARC-update workflow. Test in PPSSPP.\n'
            'preview/prepared.yobj is exactly the model inside this PAC. Named PNG/GIM\n'
            'textures and a DAE are beside it for Noesis viewing. Originals were read only.\n', encoding='utf-8')
        final = parent / (stem+'-PSP-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
        working.rename(final)
        progress(100, 'Conversion complete')
        return {'output': str(final), 'pac': str(final / pac.name),
                'preview': str(final / 'preview'), 'bytes': packing['output_bytes'],
                'baseline_match': baseline_match, 'sha256': packing['sha256']}
    except Exception as exc:
        raise RuntimeError(f'{exc}\nDiagnostic files: {working}') from exc
