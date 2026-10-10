"""Portable desktop entry point and isolated frozen-worker dispatch."""
import json
from pathlib import Path
import shutil
import sys
import traceback

def worker(job_path):
    from desktop.core import Request,Cancelled,run_job,dump
    job=json.loads(Path(job_path).read_text());root=Path(job_path).parent
    cancel=root/'cancel';working=root/'work';events=root/'events.jsonl'
    def event(percent,message):
        with events.open('a',encoding='utf-8') as f:f.write(json.dumps(dict(percent=percent,message=message))+'\n')
    try:
        result=run_job(Request(**job),working,event,lambda:cancel.exists())
        dump(root/'success.json',result);return 0
    except Exception as exc:
        cancelled=isinstance(exc,Cancelled)
        (root/'error.log').write_text(traceback.format_exc(),encoding='utf-8')
        # Keep diagnostic logs and the error, delete incomplete models/textures.
        if cancelled and working.exists():
            for log in working.glob('*.log'):shutil.copy2(log,root/log.name)
            shutil.rmtree(working)
        dump(root/'failure.json',dict(error=str(exc),cancelled=cancelled,logs=str(root)));return 2 if cancelled else 1

def main():
    if len(sys.argv)>1 and sys.argv[1]=='--worker':return worker(sys.argv[2])
    if len(sys.argv)>1 and sys.argv[1]=='--inspect':
        from desktop.adapters import adapter
        from desktop.core import dump
        try:dump(sys.argv[3],dict(ok=True,info=adapter('hctp').inspect(sys.argv[2])))
        except Exception as exc:dump(sys.argv[3],dict(ok=False,error=str(exc)))
        return 0
    if len(sys.argv)>1 and sys.argv[1]=='--qa':
        from model_qa.pipeline import run
        source,pac,output,prepared,reduced,samples,resolution=sys.argv[2:]
        # Windowed frozen executables have no Python stdout even when a parent
        # redirects OS handles. Restore a real log stream; never open a blocking
        # crash dialog for an isolated background QA failure.
        if sys.stdout is None:
            sys.stdout=open(Path(output).parent/'qa.log','a',encoding='utf-8',buffering=1)
            sys.stderr=sys.stdout
        try:
            stages=[dict(label='selective-weight-transfer',path=prepared,space='target'),
                    dict(label='guarded-decimation',path=reduced,space='target')]
            packed=Path(reduced).parent/'packed.json'
            if packed.is_file() and json.loads(packed.read_text()).get('attribute_precision_report'):
                stages.append(dict(label='bounded-attribute-precision',path=str(packed),space='target'))
            run(source,pac,output,stages=stages,
                samples=int(samples),resolution=int(resolution),progress=lambda m:print(m,flush=True))
            return 0
        except Exception:
            (Path(output).parent/'qa-error.log').write_text(traceback.format_exc(),encoding='utf-8');return 1
    from desktop.gui import Application
    app=Application()
    if len(sys.argv)>1 and sys.argv[1]=='--smoke-test':
        from desktop.core import dump,blender_path
        import subprocess
        version=subprocess.run([str(blender_path()),'--version'],capture_output=True,text=True,timeout=45,check=True).stdout
        app.root.update()
        states=[app.source_menu.entrycget(i,'state') for i in range(4)]
        if states!=['disabled','disabled','normal','disabled']:raise ValueError('Source selector states are incorrect.')
        if not app.root.tk.call('info','commands','::tkdnd::drop_target'):raise ValueError('Drag/drop runtime command missing.')
        if app.adaptive_textures.get() is not False:raise ValueError('Experimental adaptive checkbox must default OFF.')
        if app.adaptive_checkbox.cget('text')!='Adaptive Texture Optimization (Experimental)':raise ValueError('Adaptive checkbox label is incorrect.')
        from desktop.preview import VIEWS
        dump(sys.argv[2],dict(gui=True,drag_drop_command_verified=True,source_menu_states=states,
                              bundled_blender=version.splitlines()[0],preview_views=list(VIEWS),base_required=True,
                              adaptive_textures_default=False,adaptive_checkbox_verified=True))
        app.root.destroy();return 0
    app.root.mainloop();return 0

if __name__=='__main__':raise SystemExit(main())
