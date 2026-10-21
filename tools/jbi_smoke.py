"""Frozen Windows GUI/worker smoke using procedural JBI contract fixtures."""
from desktop.limits import IN_RING_MAX_PAC_BYTES
import json
from pathlib import Path
import time

from PIL import ImageGrab

from desktop.core import validate_pac
from desktop.storage import save_as
from desktop.texture_optimizer.candidates import read_gim
from tools.jbi_fixture import create
from tools.psp_mesh_merge_trial import sections
from tools.sym_source import sha


def run(app,output,base):
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    source=create(Path(base),output.parent/'fixtures')
    original=source.read_bytes();original_base=Path(base).read_bytes()
    from tkinter import messagebox
    from desktop.texture_review import TextureChooser
    failures=[];old_error=messagebox.showerror;old_chooser=TextureChooser.show
    messagebox.showerror=lambda title,message,**kwargs:failures.append((title,message))
    TextureChooser.show=lambda dialog: (dialog.top.destroy() or (app.source_inspection['texture_previews'][0]['name'],))
    def wait(predicate,timeout=240):
        start=time.monotonic()
        while not predicate():
            app.root.update()
            if failures:raise ValueError(str(failures[-1]))
            if time.monotonic()-start>timeout:raise TimeoutError('Frozen JBI GUI/worker timed out: '+app.status.get())
            time.sleep(.03)
        app.root.update()
        if failures:raise ValueError(str(failures[-1]))
    def screenshot(name):
        app.root.update();x,y=app.root.winfo_rootx(),app.root.winfo_rooty()
        ImageGrab.grab().crop((x,y,x+app.root.winfo_width(),y+app.root.winfo_height())).save(output.parent/name)
    try:
        app.select_source(source)
        wait(lambda:app.inspector is None)
        assert app.source_format.get()=='jbi' and app.source_entry.get()=='0000'
        assert tuple(app.source_entry_dropdown.cget('values'))==('0000','0100')
        assert app.source_inspection['model_count']==3
        assert app.source_inspection['accessory_sections']==[6,7]
        screenshot('jbi-source-selector.png')
        app.priority_textures=(app.source_inspection['texture_previews'][0]['name'],)
        app.source_entry.set('0100');app.change_source_entry()
        wait(lambda:app.inspector is None)
        assert app.source_inspection['selected_entry']=='0100' and app.source_inspection['model_count']==1
        assert app.priority_textures==()
        app.source_entry.set('0000');app.change_source_entry();wait(lambda:app.inspector is None)
        app.base.set(str(Path(base).resolve()))
        outputs={};default_sections=None
        for mode in ('Default','ATO','Priority Selection','Downgrade','Maximum Downgrade'):
            app.texture_mode.set(mode);app.update_texture_mode();app.start()
            wait(lambda:not app.busy())
            assert app.result is not None,app.status.get()
            result=app.result;raw=Path(result['pac']).read_bytes()
            assert result['source_format']=='jbi' and result['source_entry']=='0000'
            assert result['model_count']==3 and result['accessory_sections']==[26,27]
            assert result['bytes']==len(raw)<=IN_RING_MAX_PAC_BYTES
            validate_pac(raw,gim_reader=read_gim)
            assert Path(result['report']).is_file()
            assert app.preview.cget('image')
            assert 'disabled' not in app.save.state()
            unpacked={s['id']:r for s,r in sections(raw)}
            if default_sections is None:default_sections=unpacked
            for sid,r in default_sections.items():
                if sid!=9:assert r==unpacked[sid],(mode,sid)
            destination=output.parent/('export-'+mode.replace(' ','-')+'.pac')
            save_as(result,destination);assert destination.read_bytes()==raw
            outputs[mode]=dict(bytes=len(raw),sha256=sha(raw),models=result['model_count'],
                source_entry=result['source_entry'],native_validation=result['native_validation'],
                review_flags=result['review_flags'],non_texture_payloads_exact=True,save_as_verified=True)
            if mode=='Default':screenshot('jbi-converted-preview.png')
        app.texture_mode.set('Default');app.update_texture_mode();app.start();app.cancel_job()
        wait(lambda:not app.busy())
        assert app.result is None
        failure=json.loads((app.job/'failure.json').read_text())
        assert failure['cancelled'] and not (app.job/'work').exists()
        assert source.read_bytes()==original and Path(base).read_bytes()==original_base
        report=dict(status='pass',fixture='Procedural meshes/TIM2 on the selected development-only PSP rig; not original JBI assets',
            archive_selection=True,entry_switch_clears_priorities=True,source_formats=['jbi','hctp'],
            outputs=outputs,cancellation_clean=True,input_hashes_unchanged=True,
            limitation='Frozen hosted Windows GUI/runtime validation; not a clean user PC or PPSSPP test')
        output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        return report
    finally:
        messagebox.showerror=old_error;TextureChooser.show=old_chooser
