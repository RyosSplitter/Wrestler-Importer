"""Experiment-only frozen entry; existing converter/reducer remain unchanged.

The geometry invocation keeps its existing CLI but imports bpy in a fresh child.
Only the experimental process overrides desktop.core.blender_path.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback


def load_bpy():
    import bpy
    if getattr(sys, 'frozen', False) and not hasattr(bpy, 'app'):
        # Resolve the physical wheel entry explicitly if the frozen importer
        # selected an incomplete proxy/namespace instead of the native package.
        import importlib.util
        import importlib.machinery
        binary = Path(sys._MEIPASS)/'bpy/__init__.pyd'
        if not binary.is_file(): raise RuntimeError('Missing bpy native entry: '+str(binary))
        print('Frozen bpy initial module:', repr(getattr(bpy, '__file__', None)), repr(bpy.__spec__), flush=True)
        sys.modules.pop('bpy', None)
        loader = importlib.machinery.ExtensionFileLoader('bpy', str(binary))
        spec = importlib.util.spec_from_file_location('bpy', binary, loader=loader,
            submodule_search_locations=[str(binary.parent)])
        bpy = importlib.util.module_from_spec(spec)
        sys.modules['bpy'] = bpy
        loader.exec_module(bpy)
    if not hasattr(bpy, 'app'): raise RuntimeError('bpy native initialization did not expose bpy.app')
    return bpy


def self_check(output):
    result = dict(status='failed', platform=sys.platform, python=sys.version,
                  executable=sys.executable, clean_windows_verified=False)
    try:
        from experiments.bpy.fixture import model, PROFILE
        from collections import Counter
        import math
        with tempfile.TemporaryDirectory(prefix='ps2psp-bpy-check-') as temp:
            root = Path(temp)
            source = model()
            (root/'source.json').write_text(json.dumps(source))
            (root/'profile.json').write_text(json.dumps(PROFILE))
            entry = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).resolve())]
            command = entry + ['--background', '--python', 'desktop/geometry_worker.py', '--',
                str(root/'source.json'), str(root/'output.json'), str(root/'profile.json')]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
            result['geometry_child_log'] = completed.stdout + completed.stderr
            if completed.returncode: raise RuntimeError('Geometry child exited %d'%completed.returncode)
            reduced = json.loads((root/'output.json').read_text())
            if not reduced['triangle_count'] < source['triangle_count']: raise ValueError('No actual decimation')
            for m in reduced['meshes']:
                for a in m['materials']:
                    if any(not 0 <= i < len(m['vertices']) for t in a['triangles'] for i in t):
                        raise ValueError('Invalid output index')
                for v in m['vertices']:
                    if not all(math.isfinite(x) for key in ('position', 'normal', 'uv', 'weights') for x in v[key]):
                        raise ValueError('Nonfinite attribute')
                    if abs(sum(v['weights'])-1) > 1e-6: raise ValueError('Non-normalized weights')
                    if abs(math.sqrt(sum(x*x for x in v['normal']))-1) > 1e-5: raise ValueError('Invalid normal')
                    if v['color'] != [180, 120, 80, 255]: raise ValueError('Corner colors changed')
            def faces(m, tid):
                return Counter(tuple(sorted(tuple(msh['vertices'][i]['position']) + tuple(msh['vertices'][i]['uv']) + tuple(msh['vertices'][i]['weights']) for i in t))
                    for msh in m['meshes'] for a in msh['materials'] if a['texture_id'] == tid for t in a['triangles'])
            for tid in (0, 4):
                if faces(source, tid) != faces(reduced, tid): raise ValueError('Protected torso/ocular surface changed')
            result['geometry'] = dict(original_triangles=source['triangle_count'], final_triangles=reduced['triangle_count'],
                protected_torso_and_ocular_exact=True, normalized_weights=True, finite_unit_normals=True,
                corner_attributes=True, head_floor=reduced['reduction_report']['complete_head_triangles'])
            # Audit generated native vectors; never ship user/reference PACs.
            from tools.generate_conformance_fixtures import vectors
            from desktop.core import validate_pac
            native, _ = validate_pac(vectors()['psp-quad.pac'])
            result['native_fixture'] = native['report']
            smoke = subprocess.run(entry + ['--smoke-test', str(root/'gui.json')], capture_output=True, text=True, timeout=90)
            if smoke.returncode: raise RuntimeError('GUI smoke failed: '+smoke.stdout+smoke.stderr)
            result['gui'] = json.loads((root/'gui.json').read_text())
        result['status'] = 'pass'
    except Exception:
        result['error'] = traceback.format_exc()
    Path(output).write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    return 0 if result['status'] == 'pass' else 1


def main():
    if '--background' in sys.argv:
        # Per-job configuration remains writable; no persistent Blender install.
        os.environ.setdefault('BLENDER_USER_CONFIG', str(Path(tempfile.gettempdir())/'ps2psp-bpy-config'))
        os.environ.setdefault('BLENDER_USER_EXTENSIONS', str(Path(tempfile.gettempdir())/'ps2psp-bpy-extensions'))
        bpy = load_bpy()
        from desktop.geometry_worker import run
        print('Standalone bpy', bpy.app.version_string, bpy.app.build_hash.decode(), flush=True)
        run(*sys.argv[sys.argv.index('--')+1:])
        return 0
    if '--version' in sys.argv:
        bpy = load_bpy()
        print('Standalone bpy '+bpy.app.version_string, flush=True)
        return 0
    from desktop import core
    core.blender_path = lambda: Path(sys.executable)
    if len(sys.argv)>1 and sys.argv[1]=='--bpy-self-check': return self_check(sys.argv[2])
    import ps2psp_converter
    return ps2psp_converter.main()


if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
