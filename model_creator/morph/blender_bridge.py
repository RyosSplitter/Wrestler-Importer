"""Isolated validated Blender commit; previews use the same body field kernel."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from desktop.blender_runtime import resolve,version
from .document import Document,signature,validate_recipe
from .native_patch import patch
from .qa import validate


def commit(raw,recipe,*,runtime=None,cancel=lambda:False):
    recipe=validate_recipe(recipe);doc=Document(raw);doc.restore(recipe)
    expected,_=doc.evaluate();executable=resolve(runtime);runtime_version=version(executable)
    job=dict(positions=doc.points.tolist(),normals=doc.normals.tolist(),faces=doc.faces.tolist(),
             anchors=doc.anchors,height=doc.height,parameters=doc.values)
    with tempfile.TemporaryDirectory(prefix='creator-morph-') as temp:
        folder=Path(temp);input_path=folder/'input.json';output=folder/'result.json'
        payload=json.dumps(job,allow_nan=False,sort_keys=True).encode();input_path.write_bytes(payload)
        env=os.environ.copy();env['BLENDER_USER_CONFIG']=str(folder/'config');env['BLENDER_USER_EXTENSIONS']=str(folder/'extensions')
        with (folder/'worker.log').open('w',encoding='utf-8') as log:
            child=subprocess.Popen([str(executable),'--background','--factory-startup','--python-exit-code','1',
                '--python',str(Path(__file__).with_name('blender_worker.py')),'--',str(input_path),str(output)],
                stdout=log,stderr=subprocess.STDOUT,env=env,creationflags=0x08000000 if os.name=='nt' else 0)
            start=time.monotonic()
            try:
                while child.poll() is None:
                    if cancel():raise ValueError('Morph validation cancelled')
                    if time.monotonic()-start>120:raise ValueError('Blender morph validation timed out')
                    time.sleep(.05)
                if child.returncode:raise ValueError('Blender morph validation failed: '+(folder/'worker.log').read_text(encoding='utf-8')[-2000:])
            finally:
                if child.poll() is None:
                    child.terminate()
                    try:child.wait(timeout=5)
                    except subprocess.TimeoutExpired:child.kill();child.wait()
        result=json.loads(output.read_text(encoding='utf-8'))
        if result['input_sha256']!=hashlib.sha256(payload).hexdigest() or not result['vertex_ids_exact'] or not result['faces_exact']:
            raise ValueError('Unverified Blender morph result')
        if input_path.read_bytes()!=payload:raise ValueError('Morph worker input changed')
        native,proof=patch(raw,result['positions'],result['normals'])
        from model_creator.native import audit_yobj
        checks=validate(doc,audit_yobj(native),expected)
    return native,dict(recipe=recipe,signature=signature(recipe),runtime=runtime_version,
        blender_preview_error=result['preview_error'],shape_keys=result['shape_keys'],native=proof,qa=checks,
        original_source_immutable=True,geometry_decimation=False)
