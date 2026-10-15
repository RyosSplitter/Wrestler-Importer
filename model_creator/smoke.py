"""Asset-free frozen Windows functional check, including actual Tk controls."""
from pathlib import Path
import tempfile
import time

from .core import PARTS, build, create_project, dump, load_source, preview
from .fixtures import pair


def run(app,output):
    output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='creator-smoke-',dir=output.parent) as temp:
        root=Path(temp);a=root/'Synthetic A.pac';b=root/'Synthetic B.pac'
        for path,data in zip((a,b),pair()):path.write_bytes(data)
        project=create_project(a,b,root/'Project');app.load(project);app.root.update()
        for p in PARTS:app.choices[p].set(app.labels[int(p in ('Head','Arms'))])
        if app.selected()!=dict(Head=1,Torso=0,Arms=1,Legs=0):raise ValueError('Part selectors differ.')
        app.controls[-1].event_generate('<<ComboboxSelected>>');deadline=time.monotonic()+90
        while (app.preview_after is not None or app.busy) and time.monotonic()<deadline:app.root.update();time.sleep(.02)
        if app.model is None or app.result is not None:raise ValueError('Selections must preview before building a PAC.')
        app.assemble();deadline=time.monotonic()+90
        while app.busy and time.monotonic()<deadline:app.root.update();time.sleep(.02)
        if app.busy or app.result is None:raise ValueError('GUI assembly worker did not finish.')
        from unittest.mock import patch
        old=app.choices['Legs'].get();app.choices['Legs'].set(app.labels[1])
        with patch('model_creator.gui.messagebox.showinfo'):
            if app.require_result():raise ValueError('Stale selections exported an older PAC.')
        app.choices['Legs'].set(old)
        for view in ('front','back','left'):
            image=preview(app.model,app.textures,view,256,pose='crouch',green=True);image.save(output.with_name('creator-'+view+'.png'))
        from desktop.workspace import inspect_workspace
        from desktop.edit_folder import export_folder,pack_folder
        inspect_workspace(app.result/'created-model.pac',root/'inspection',resolution=64)
        export_folder(root/'inspection/manifest.json',root/'editable');pack_folder(root/'editable',root/'roundtrip.pac')
        if (root/'roundtrip.pac').read_bytes()!=(app.result/'created-model.pac').read_bytes():raise ValueError('Editable folder roundtrip differs.')
        from PIL import ImageGrab
        app.root.lift();app.root.update();time.sleep(.4);app.root.update()
        x,y=app.root.winfo_rootx(),app.root.winfo_rooty();w,h=app.root.winfo_width(),app.root.winfo_height()
        ImageGrab.grab(bbox=(x,y,x+w,y+h)).save(output.with_name('creator-window.png'))
        dump(output,dict(passed=True,part_selectors=True,live_selection_preview_before_export=True,stale_export_blocked=True,background_assembly=True,native_export=True,
                         analytical_poses=len(app.last_report['qa']['poses']),preview_views=True,
                         editable_texture_roundtrip_exact=True,pac_bytes=app.last_report['pac_bytes'],assets='Original synthetic geometry only'))
