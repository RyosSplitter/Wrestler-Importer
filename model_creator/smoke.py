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
        for button in app.export_buttons:
            bottom=button.winfo_rooty()+button.winfo_height();right=button.winfo_rootx()+button.winfo_width()
            if not button.winfo_ismapped() or button.winfo_height()<button.winfo_reqheight() or bottom>min(y+h,app.root.winfo_screenheight()-35) or right>x+w:
                raise ValueError('An export control is outside the visible window/screen.')
        ImageGrab.grab(bbox=(x,y,x+w,y+h)).save(output.with_name('creator-window.png'))
        dump(output,dict(passed=True,part_selectors=True,live_selection_preview_before_export=True,stale_export_blocked=True,all_export_buttons_visible=True,background_assembly=True,native_export=True,
                         analytical_poses=len(app.last_report['qa']['poses']),preview_views=True,
                         editable_texture_roundtrip_exact=True,pac_bytes=app.last_report['pac_bytes'],assets='Original synthetic geometry only'))
    run_library(app,output)


def run_library(app,output):
    """Exercise the actual bundled data and GUI, not just metadata existence."""
    import json
    from .library import Library
    library=Library()
    for i in range(len(library.entries)):library.source(i)
    app.open_library();app.root.update()
    labels={entry['label']:app.labels[i] for i,entry in enumerate(app.library.entries)}
    for part in PARTS:app.choices[part].set(labels['Christian'])
    app.choices['Head'].set(labels['CM-Punk-Ring']);app.dirty()
    deadline=time.monotonic()+120
    while (app.preview_after is not None or app.busy) and time.monotonic()<deadline:app.root.update();time.sleep(.02)
    if app.model is None or app.result is not None:raise ValueError('Prepared selections did not preview without an import')
    if app.model['report']['descriptor_count']!=2:raise ValueError('Prepared hair descriptor group was lost')
    app.assemble();deadline=time.monotonic()+120
    while app.busy and time.monotonic()<deadline:app.root.update();time.sleep(.02)
    if app.busy or app.result is None:raise ValueError('Prepared-library native PAC build failed')
    from desktop.workspace import inspect_workspace
    from desktop.edit_folder import export_folder,pack_folder
    with tempfile.TemporaryDirectory(prefix='creator-array-edit-') as temp:
        temp=Path(temp)
        inspect_workspace(app.result/'created-model.pac',temp/'inspection',resolution=64,native_descriptor_arrays=True)
        export_folder(temp/'inspection/manifest.json',temp/'editable');pack_folder(temp/'editable',temp/'repacked.pac')
        if (temp/'repacked.pac').read_bytes()!=(app.result/'created-model.pac').read_bytes():raise ValueError('Multi-descriptor texture edit roundtrip differs')
    from PIL import ImageGrab
    app.root.lift();app.root.update();time.sleep(.3);app.root.update()
    x,y=app.root.winfo_rootx(),app.root.winfo_rooty();w,h=app.root.winfo_width(),app.root.winfo_height()
    for button in app.export_buttons:
        if button.winfo_height()<button.winfo_reqheight() or button.winfo_rooty()+button.winfo_height()>y+h:raise ValueError('Library export button clipped')
    ImageGrab.grab(bbox=(x,y,x+w,y+h)).save(output.with_name('creator-library-window.png'))
    report=json.loads(output.read_text());report.update(prepared_models=len(library.entries),
        prepared_library_all_native_readers_passed=True,prepared_live_preview_without_import=True,
        prepared_hair_groups_preserved=True,prepared_mixed_pac_bytes=app.last_report['pac_bytes'],
        prepared_array_texture_roundtrip_exact=True,assets='Synthetic fixtures plus explicitly supplied prepared native library')
    dump(output,report)
    run_donor_import(app,output)


def run_donor_import(app,output):
    """Exercise the new button path on a disposable library, then restart it."""
    import json
    from .library import Library
    from .core import digest
    with tempfile.TemporaryDirectory(prefix='creator-import-',dir=output.parent) as temp:
        temp=Path(temp);library=temp/'creator_library';(library/'pacs').mkdir(parents=True)
        first,second=pair();(library/'pacs/first.pac').write_bytes(first)
        dump(library/'catalog.json',dict(schema='psp-model-creator.library/1',models=[dict(label='Original',file='pacs/first.pac',sha256=digest(first))]))
        incoming=temp/'New native donor.PAC';incoming.write_bytes(second)
        bad=temp/'Unsupported.pac';bad.write_bytes(b'not a PAC')
        app.reload_library(library);app.root.update();deadline=time.monotonic()+90
        while (app.preview_after is not None or app.busy) and time.monotonic()<deadline:app.root.update();time.sleep(.02)
        from unittest.mock import patch
        with patch('model_creator.gui.filedialog.askopenfilenames',return_value=(str(incoming),str(bad),str(incoming))):app.add_donors()
        deadline=time.monotonic()+90
        while (app.preview_after is not None or app.busy) and time.monotonic()<deadline:app.root.update();time.sleep(.02)
        r=app.last_import_report
        if len(r['added'])!=1 or len(r['duplicates'])!=1 or len(r['rejected'])!=1:raise ValueError('Import batch results differ')
        incoming.unlink();app.reload_library(library);app.root.update()
        for part in PARTS:app.choices[part].set(app.labels[int(part=='Head')])
        app.dirty();deadline=time.monotonic()+90
        while (app.preview_after is not None or app.busy) and time.monotonic()<deadline:app.root.update();time.sleep(.02)
        if app.model is None or len(app.labels)!=2:raise ValueError('Imported donor failed preview after reload/input removal')
        app.assemble();deadline=time.monotonic()+90
        while app.busy and time.monotonic()<deadline:app.root.update();time.sleep(.02)
        if app.result is None or not app.last_report['within_budget']:raise ValueError('Imported donor failed guarded assembly')
        if Library(library).source(1)['data']!=second:raise ValueError('Import changed native PAC bytes')
        # A size overrun warns in the GUI and still permits an actual Save PAC.
        # A deliberately tiny target exercises the policy on valid synthetic
        # geometry without weakening any native/rigging checks.
        with patch('model_creator.core.MAX_BYTES',1),patch('model_creator.gui.messagebox.showwarning') as warning:
            app.assemble();deadline=time.monotonic()+90
            while app.busy and time.monotonic()<deadline:app.root.update();time.sleep(.02)
            if app.result is None or app.last_report['within_budget'] or not app.last_report.get('budget_warning'):raise ValueError('Oversize export policy did not retain its warning')
            if not warning.called:raise ValueError('Oversized GUI build did not display a warning')
        destination=temp/'Saved-over-budget.pac'
        with patch('model_creator.gui.filedialog.asksaveasfilename',return_value=str(destination)):app.export_pac()
        if not destination.is_file() or destination.read_bytes()!=(app.result/'created-model.pac').read_bytes():raise ValueError('Size warning still blocked actual Save PAC')
        report=json.loads(output.read_text());report.update(add_donors_button=True,import_batch_add_duplicate_reject=True,
            imported_donor_persists_without_original=True,imported_donor_mixed_preview_and_export=True,
            oversized_gui_warning_shown=True,oversized_pac_export_allowed=True)
        dump(output,report)
