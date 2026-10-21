"""Portable desktop entry point and isolated frozen-worker dispatch."""
from desktop.limits import IN_RING_MAX_PAC_BYTES
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
    if len(sys.argv)>1 and sys.argv[1]=='--suite-validate':
        from desktop.pac_validator import validate_pac
        from desktop.workspace import dump
        request,job=map(Path,sys.argv[2:4])
        try:
            options=json.loads(request.read_text(encoding='utf-8'))
            report=validate_pac(**options)
            dump(job/'result.json',dict(ok=True,report=report))
            return 0
        except Exception as exc:
            (job/'error.log').write_text(traceback.format_exc(),encoding='utf-8')
            dump(job/'result.json',dict(ok=False,error=str(exc)))
            return 1
    if len(sys.argv)>1 and sys.argv[1]=='--suite-pack':
        from desktop.edit_folder import pack_folder
        from desktop.workspace import dump
        request,job=map(Path,sys.argv[2:4])
        try:
            options=json.loads(request.read_text(encoding='utf-8'))
            report=pack_folder(options['folder'],options['destination'])
            dump(job/'pack-report.json',report)
            dump(job/'result.json',dict(ok=True,report=report))
            return 0
        except Exception as exc:
            (job/'error.log').write_text(traceback.format_exc(),encoding='utf-8')
            dump(job/'result.json',dict(ok=False,error=str(exc)))
            return 1
    if len(sys.argv)>1 and sys.argv[1]=='--suite-inspect':
        from desktop.workspace import inspect_workspace,dump
        source,job=map(Path,sys.argv[2:4])
        try:
            inspect_workspace(source,job/'workspace')
            dump(job/'result.json',dict(ok=True,manifest=str((job/'workspace/manifest.json').resolve())))
            return 0
        except Exception as exc:
            (job/'error.log').write_text(traceback.format_exc(),encoding='utf-8')
            dump(job/'result.json',dict(ok=False,error=str(exc)))
            return 1
    if len(sys.argv)>1 and sys.argv[1]=='--maximum-downgrade':
        from desktop.maximum_downgrade import fit_pac
        source,output=map(Path,sys.argv[2:4]);target=int(sys.argv[4]) if len(sys.argv)>4 else IN_RING_MAX_PAC_BYTES
        if output.exists():raise FileExistsError('Refusing to overwrite '+str(output))
        original=source.read_bytes()
        candidate,report=fit_pac(original,output,target=target)
        if source.read_bytes()!=original:raise ValueError('Input changed during texture fitting')
        (output/'candidate.pac').write_bytes(candidate)
        return 0
    if len(sys.argv)>1 and sys.argv[1]=='--skin-compatibility':
        from desktop.skinning import apply_single_slot_compatibility
        from desktop.core import validate_pac,dump
        from desktop.texture_optimizer.candidates import read_gim
        source,output=map(Path,sys.argv[2:])
        if output.exists():raise FileExistsError('Refusing to overwrite '+str(output))
        original=source.read_bytes()
        candidate,report=apply_single_slot_compatibility(original)
        validate_pac(candidate,gim_reader=read_gim)
        if source.read_bytes()!=original:raise ValueError('Input changed during inspection')
        output.mkdir(parents=True)
        (output/'candidate.pac').write_bytes(candidate)
        dump(output/'skin-compatibility.json',report)
        return 0
    if len(sys.argv)>1 and sys.argv[1]=='--worker':return worker(sys.argv[2])
    if len(sys.argv)>1 and sys.argv[1]=='--inspect':
        from desktop.adapters import adapter
        from desktop.core import dump
        catalogue=None
        try:
            key=sys.argv[4] if len(sys.argv)>4 else 'hctp';reader=adapter(key)
            options={}
            if key=='jbi':
                catalogue=reader.catalogue(sys.argv[2])
                options['entry_id']=sys.argv[5] if len(sys.argv)>5 else ''
            info=reader.inspect(sys.argv[2],Path(sys.argv[3]).parent/'textures',**options)
            dump(sys.argv[3],dict(ok=True,info=info,catalogue=catalogue))
        except Exception as exc:dump(sys.argv[3],dict(ok=False,error=str(exc),catalogue=catalogue))
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
    app=Application(suite='--converter-only' not in sys.argv)
    if len(sys.argv)>1 and sys.argv[1]=='--jbi-smoke-test':
        from tools.jbi_smoke import run
        try:run(app,sys.argv[2],sys.argv[3])
        except Exception:
            Path(sys.argv[2]).parent.mkdir(parents=True,exist_ok=True)
            Path(sys.argv[2]).with_suffix('.error.log').write_text(traceback.format_exc(),encoding='utf-8')
            return 1
        finally:app.close()
        return 0
    if len(sys.argv)>1 and sys.argv[1]=='--suite-smoke-test':
        from tools.suite_smoke import run
        try:run(app,sys.argv[2])
        finally:app.close()
        return 0
    if len(sys.argv)>1 and sys.argv[1]=='--smoke-test':
        from desktop.core import dump,blender_path
        import subprocess
        version=subprocess.run([str(blender_path()),'--version'],capture_output=True,text=True,timeout=45,check=True).stdout
        app.root.update()
        states=[app.source_menu.entrycget(i,'state') for i in range(4)]
        if states!=['normal','disabled','normal','disabled']:raise ValueError('Source selector states are incorrect.')
        app.choose_source_format('jbi');app.root.update()
        if app.source_format.get()!='jbi' or 'Legacy' in app.texture_dropdown.cget('values'):raise ValueError('JBI selector or texture options are incorrect.')
        app.choose_source_format('hctp');app.root.update()
        if not app.root.tk.call('info','commands','::tkdnd::drop_target'):raise ValueError('Drag/drop runtime command missing.')
        from desktop.texture_modes import MODES
        if app.texture_mode.get()!='Default':raise ValueError('Textures must default to Default.')
        if tuple(app.texture_dropdown.cget('values'))!=MODES:raise ValueError('Texture modes are incorrect.')
        if app.downgrade_row.winfo_manager():raise ValueError('Downgrade controls should be hidden in Default mode.')
        app.texture_mode.set('Downgrade');app.update_texture_mode();app.root.update()
        if not app.downgrade_row.winfo_ismapped():raise ValueError('Downgrade selector is missing.')
        if tuple(app.downgrade_dropdown.cget('values'))!=('1 size','2 sizes','3 sizes'):raise ValueError('Downgrade steps are incorrect.')
        app.texture_mode.set('Maximum Downgrade');app.update_texture_mode();app.root.update()
        if app.downgrade_row.winfo_manager():raise ValueError('Maximum mode must allocate automatically, without a fixed step selector.')
        app.texture_mode.set('Downgrade');app.update_texture_mode();app.root.update()
        if app.texture_help_label.winfo_rooty()+app.texture_help_label.winfo_height()>app.progress.winfo_rooty():raise ValueError('Texture controls clipped at minimum window size.')
        old_geometry=app.root.geometry();old_base=app.base.get();old_info=app.info.get()
        app.root.geometry('940x640');app.base.set('C:/Users/Example/Documents/PSP Models/Original/SVR2007 Non-Converted Models/Kurt-Angle-Ring.PAC')
        app.info.set('HCTP PS2 • Example\n500,000 bytes • 3,000 main-model triangles\n3 models • 19 textures');app.root.update()
        app.left_canvas.yview_moveto(1);app.root.update()
        if app.skin_checkbox.winfo_rooty()+app.skin_checkbox.winfo_height()>app.left_canvas.winfo_rooty()+app.left_canvas.winfo_height():raise ValueError('Sidebar controls inaccessible with a long base path.')
        app.base.set(old_base);app.info.set(old_info);app.root.geometry(old_geometry);app.left_canvas.yview_moveto(0)
        app.texture_mode.set('Default');app.update_texture_mode();app.root.update()
        if app.skin_palette_compatibility.get() is not True:raise ValueError('Single-slot compatibility must default ON.')
        if app.skin_checkbox.cget('text')!='Single-slot skinning compatibility':raise ValueError('Skin compatibility checkbox label is incorrect.')
        from desktop.texture_review import TextureChooser,source_previews
        import numpy as np
        import tempfile
        preview_root=Path(tempfile.mkdtemp(prefix='texture-smoke-',dir=Path(sys.argv[2]).parent))
        rgba=np.zeros((32,32,4),np.uint8);rgba[4:28,4:28]=[100,130,170,255]
        entries=source_previews([(i,'Example '+str(i+1),b'',rgba,{}) for i in range(4)],preview_root)
        dialog=TextureChooser(app.root,entries)
        for name in list(dialog.variables)[:3]:dialog.variables[name].set(True)
        dialog.refresh()
        if 'disabled' not in dialog.checkboxes[entries[3]['name']].state():raise ValueError('Fourth texture must be disabled at three selections.')
        dialog.variables[entries[0]['name']].set(False);dialog.refresh()
        if 'disabled' in dialog.checkboxes[entries[3]['name']].state():raise ValueError('Deselect must allow a new texture.')
        dialog.variables[entries[3]['name']].set(True);dialog.refresh();app.root.update()
        if sys.platform=='win32':
            from PIL import ImageGrab
            x,y=dialog.top.winfo_rootx(),dialog.top.winfo_rooty()
            ImageGrab.grab(bbox=(x,y,x+dialog.top.winfo_width(),y+dialog.top.winfo_height())).save(Path(sys.argv[2]).with_name('texture-chooser.png'))
        app.root.after(10,dialog.accept)
        if len(dialog.show())!=3:raise ValueError('Texture chooser did not return three selections.')
        cancelled=TextureChooser(app.root,entries);app.root.after(10,cancelled.top.destroy)
        if cancelled.show() is not None:raise ValueError('Cancelled texture chooser must not convert.')
        shutil.rmtree(preview_root)
        if app.convert.winfo_rooty()+app.convert.winfo_height()>app.preview.winfo_rooty():raise ValueError('Convert must be above the preview.')
        if app.convert.winfo_rootx()<app.preview.winfo_rootx():raise ValueError('Convert must be in the preview column.')
        if 'disabled' not in app.cancel.state() or 'disabled' not in app.save.state():raise ValueError('Cancel and Save must start disabled.')
        if sys.platform=='win32' and app.ui_theme!='vista':raise ValueError('Native Windows control theme missing.')
        from desktop.preview import VIEWS
        dump(sys.argv[2],dict(gui=True,drag_drop_command_verified=True,source_menu_states=states,
                              bundled_blender=version.splitlines()[0],preview_views=list(VIEWS),base_required=True,
                              texture_mode_default='Default',texture_modes=list(MODES),downgrade_controls_verified=True,scrollable_sidebar_verified=True,
                              skin_palette_compatibility_default=True,skin_checkbox_verified=True,
                              three_selection_limit_verified=True,texture_dialog_cancel_verified=True,
                              ui_theme=app.ui_theme,convert_above_preview=True,
                              initial_button_states_verified=True))
        if sys.platform=='win32':
            from PIL import ImageGrab
            app.root.lift();app.root.update()
            x,y=app.root.winfo_rootx(),app.root.winfo_rooty()
            ImageGrab.grab(bbox=(x,y,x+app.root.winfo_width(),y+app.root.winfo_height())).save(Path(sys.argv[2]).with_suffix('.png'))
        app.root.destroy();return 0
    app.root.mainloop();return 0

if __name__=='__main__':raise SystemExit(main())
