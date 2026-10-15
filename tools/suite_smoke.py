"""Exercise real Tk tabs, isolated inspection, preview export and exact PAC copy.

Run via ps2psp_converter.py --suite-smoke-test OUTPUT.json, including frozen builds.
Uses generated conformance models only. Screenshots are actual application captures.
"""
import json
from pathlib import Path
import tempfile
import time

from desktop.suite import TABS
from desktop.workspace import copy_original, export_previews
from tools.generate_conformance_fixtures import vectors, pac
from tools.psp_mesh_merge_trial import sections


def run(app, output):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    shell = app.suite
    if shell is None:
        raise ValueError('Suite smoke requires the suite shell.')
    app.root.update()
    if tuple(shell.tabs.tab(i, 'text') for i in range(len(TABS))) != TABS:
        raise ValueError('Suite tabs are missing.')
    # Navigating modules must not reset converter choices, input or base settings.
    old_base = app.base.get()
    app.base.set('C:/Example/PSP base.pac')
    app.texture_mode.set('ATO')
    app.update_texture_mode()
    for page in shell.pages.values():
        shell.tabs.select(page)
        app.root.update()
    if app.base.get()!='C:/Example/PSP base.pac' or app.texture_mode.get()!='ATO':
        raise ValueError('Suite navigation reset converter state.')
    app.base.set(old_base)
    app.texture_mode.set('Default')
    app.update_texture_mode()
    files = vectors()
    texture = next(raw for s,raw in sections(files['psp-quad.pac']) if s['id']==9)
    data = pac([(2,files['psp-quad.yobj']),(9,texture),(26,files['psp-quad.yobj']),
                (50,b'Preserved opaque suite test data')])
    with tempfile.TemporaryDirectory(prefix='suite-smoke-', dir=output.parent) as temp:
        root = Path(temp)
        source = root/'Synthetic-PSP.pac'
        source.write_bytes(data)
        shell.open_pac(source)
        deadline = time.monotonic()+90
        while shell.busy() and time.monotonic()<deadline:
            app.root.update()
            time.sleep(.01)
        if shell.busy():
            raise TimeoutError('Suite inspection worker did not finish; inspect '+str(shell.job))
        if shell.manifest is None:
            raise ValueError('Suite inspection did not load its result: '+shell.status.get())
        if len(shell.model_tree.get_children())!=2 or len(shell.texture_tree.get_children())!=1:
            raise ValueError('Suite omitted an auxiliary model or texture.')
        shell.tabs.select(shell.pages['PSP Model Editor'])
        app.root.update()
        for i in (0,1):
            shell.model_tree.selection_set('model_'+str(i))
            app.root.update()
            for view in ('front','back','left','right','front-left'):
                shell.set_view(view)
                app.root.update()
                if shell.photo is None or not shell.preview.cget('image'):
                    raise ValueError('Native model preview is missing.')
        copy_original(shell.manifest_path, root/'copy.pac')
        if (root/'copy.pac').read_bytes()!=data or source.read_bytes()!=data:
            raise ValueError('Suite round trip modified the input PAC.')
        export_previews(shell.manifest_path, root/'preview.zip')
        for name in TABS:
            shell.tabs.select(shell.pages[name])
            app.root.update()
            if name=='Textures' and not shell.texture_image.cget('image'):
                raise ValueError('Texture gallery is missing.')
            from PIL import ImageGrab
            app.root.lift()
            app.root.update()
            x,y=app.root.winfo_rootx(),app.root.winfo_rooty()
            image=ImageGrab.grab(bbox=(x,y,x+app.root.winfo_width(),y+app.root.winfo_height()))
            image.save(output.with_name('suite-'+name.lower().replace(' ','-')+'.png'))
        app.root.geometry('940x640')
        shell.tabs.select(shell.converter)
        app.root.update()
        if app.convert.winfo_rooty()+app.convert.winfo_height()>app.preview.winfo_rooty():
            raise ValueError('Convert is no longer above the converter preview.')
        shell.tabs.select(shell.pages['PSP Model Editor'])
        app.root.update()
        if shell.copy_button.winfo_rootx()+shell.copy_button.winfo_width()>app.root.winfo_rootx()+app.root.winfo_width():
            raise ValueError('Editor toolbar clipped at minimum size.')
    report=dict(suite_tabs=list(TABS), actual_gui_exercised=True, isolated_worker_verified=True,
                converter_state_preserved=True, models=2, textures=1,
                all_model_views_verified=True, exact_pac_copy=True, input_unchanged=True,
                preview_export_verified=True, minimum_size_verified=True,
                creator_status='planned', game_assets_used=False)
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    shell.tabs.select(shell.converter)
    return report
