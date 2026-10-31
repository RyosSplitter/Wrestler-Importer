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
    run_creator030(app,output)
    run_waistline(app,output)
    run_morph(app,output)
    run_uv(app,output)


def run_morph(app,output):
    import json
    from unittest.mock import patch
    from .morph.fixtures import donor
    from .morph.document import signature
    def wait():
        deadline=time.monotonic()+150
        while (app.busy or app.preview_after is not None or app.refresh_after is not None or app.morph_ui.preview_after is not None) and time.monotonic()<deadline:
            app.root.update();time.sleep(.02)
        app.root.update()
        if app.busy or app.model is None:raise ValueError('Morph preview timed out: '+getattr(app,'last_error',''))
    with tempfile.TemporaryDirectory(prefix='creator-morph-smoke-') as temp:
        root=Path(temp);data=donor();paths=[root/'A.pac',root/'B.pac']
        for path in paths:path.write_bytes(data)
        project=create_project(*paths,root/'Project');app.load(project);app.pose.set('rest');wait()
        studio=app.morph_ui
        if studio.doc is None or 'disabled' in studio.scales[1].state():raise ValueError('Morph runtime or body controls unavailable: '+studio.info.get())
        original=app.preview_frame.tobytes();app.sidebar.select(1);app.root.update()
        studio.scales[1].set(.6);studio.finish_gesture();wait()
        if app.preview_frame.tobytes()==original:raise ValueError('Body slider did not change the existing live preview')
        changed=app.preview_frame.tobytes();studio.undo();wait()
        if app.preview_frame.tobytes()!=original:raise ValueError('Undo did not restore the baseline preview')
        studio.undo(True);wait()
        if app.preview_frame.tobytes()!=changed:raise ValueError('Redo accumulated morph error')
        studio.original.set(True);studio.request_preview();wait()
        if app.preview_frame.tobytes()!=original:raise ValueError('Compare original changed the morph baseline')
        studio.original.set(False);studio.request_preview();wait()
        app.save();metadata=json.loads(Path(project).read_text(encoding='utf-8'))
        if metadata['schema']!='psp-model-creator/2':raise ValueError('Morph project lacks versioned recipe protection')
        app.assemble();wait()
        if app.result is None or 'morph' not in app.last_report:raise ValueError('Blender-backed morph export failed: '+getattr(app,'last_error',''))
        report=app.last_report['morph']
        if not report['native']['topology_uv_weights_materials_bones_exact'] or len(report['qa']['poses'])!=20:raise ValueError('Morph preservation/pose proof incomplete')
        if report['signature']!=signature(studio.recipe()):raise ValueError('Export used stale morph values')
        studio.scales[1].set(.3);studio.finish_gesture();wait()
        with patch('model_creator.gui.messagebox.showinfo'):
            if app.require_result():raise ValueError('Changed morph exported a stale PAC')
        app.load(project);wait()
        if abs(studio.doc.values['chest_width']-.6)>1e-5:raise ValueError('Saved morph did not restore')
        from PIL import ImageGrab
        app.sidebar.select(1);app.root.update();x,y=app.root.winfo_rootx(),app.root.winfo_rooty()
        ImageGrab.grab(bbox=(x,y,x+app.root.winfo_width(),y+app.root.winfo_height())).save(output.with_name('creator-morph-window.png'))
        studio.reset();wait();app.assemble();wait()
        if (app.result/'created-model.pac').read_bytes()!=data:raise ValueError('Reset morph failed exact original PAC export')
        if any(path.read_bytes()!=data for path in paths):raise ValueError('Morph changed a source donor')
        saved=json.loads(output.read_text());saved.update(morph_studio=True,morph_live_preview=True,
            morph_undo_redo=True,morph_compare_original=True,morph_project_roundtrip=True,morph_stale_export_blocked=True,
            morph_blender_runtime=report['runtime'],morph_native_attributes_preserved=True,morph_pose_checks=20,
            morph_reset_export_byte_exact=True,morph_sources_unchanged=True)
        dump(output,saved)


def run_waistline(app,output):
    import json
    from unittest.mock import patch
    from .parts import DEFAULT_WAIST
    from .core import read_project
    def wait():
        deadline=time.monotonic()+120
        while (app.preview_after is not None or app.busy) and time.monotonic()<deadline:
            app.root.update();time.sleep(.02)
        if app.model is None or app.busy:raise ValueError('Waistline preview did not complete: '+getattr(app,'last_error',''))
    with tempfile.TemporaryDirectory(prefix='creator-waistline-') as temporary:
        root=Path(temporary)
        paths=[root/'First.pac',root/'Second.pac']
        for path,data in zip(paths,pair()):path.write_bytes(data)
        project=create_project(*paths,root/'Project');app.load(project)
        app.choices['Legs'].set(app.labels[1]);app.pose.set('rest');app.dirty();wait()
        if abs(app.waist_y.get()-DEFAULT_WAIST)>1e-7:raise ValueError('New projects did not use the waistband default')
        app.waist_slider.set(-2.65);wait()
        app.assemble();wait()
        if app.result is None or abs(app.last_report['waist_y']+2.65)>1e-7:raise ValueError('Export ignored the chosen waistline')
        seam=next(r for r in app.last_report['seams'] if r['joint']=='waist')
        if abs(seam['limit']+2.65)>1e-7:raise ValueError('Seam QA used a different cut plane')
        app.waist_slider.set(-1.8);wait()
        with patch('model_creator.gui.messagebox.showinfo'):
            if app.require_result():raise ValueError('Cutoff change allowed stale export')
        app.save()
        if abs(read_project(project)[0]['waist_y']+1.8)>1e-7:raise ValueError('Saved choices lost the cut height')
        app.load(project);wait()
        if abs(app.waist_y.get()+1.8)>1e-7:raise ValueError('Project reload lost the cut height')
        app.waist_reset.invoke();wait()
        if abs(app.waist_y.get()-DEFAULT_WAIST)>1e-7:raise ValueError('Waist reset failed')
        from PIL import ImageGrab
        app.root.update();x,y=app.root.winfo_rootx(),app.root.winfo_rooty();w,h=app.root.winfo_width(),app.root.winfo_height()
        for widget in (app.waist_slider,app.waist_reset,app.waist_guide_checkbox,app.assemble_button):
            if not widget.winfo_ismapped() or widget.winfo_height()<15 or widget.winfo_rooty()+widget.winfo_height()>y+h:raise ValueError('Torso cutoff controls clipped')
        ImageGrab.grab(bbox=(x,y,x+w,y+h)).save(output.with_name('creator-waistline-window.png'))
        report=json.loads(output.read_text());report.update(waistband_default=True,live_waistline_adjustment=True,
            configured_waistline_export_and_qa=True,cutoff_stale_export_blocked=True,
            waistline_project_roundtrip=True,waistline_reset=True,waistline_controls_visible=True)
        dump(output,report)


def run_creator030(app,output):
    import json
    import numpy as np
    from unittest.mock import patch
    from .core import digest
    from .library import create_project
    from desktop.texture_optimizer.candidates import write_gim,read_gim
    from tools.pac_repack import replace_sections,texture_table
    from tools.yukes_bpe import compress
    with tempfile.TemporaryDirectory(prefix='creator-texture-option-',dir=output.parent) as temp:
        temp=Path(temp);data=pair()[0];palette=np.zeros((16,4),np.uint8);palette[:,3]=255
        palette[:,:3]=np.arange(16,dtype=np.uint8)[:,None]*16
        pixels=np.random.default_rng(37).integers(0,16,(128,128),dtype=np.uint8)
        gim=write_gim(pixels,palette,4);table=texture_table(['skin'],[gim],gim_reader=read_gim)
        data=replace_sections(data,{9:compress(table)});source=temp/'Texture test.pac';source.write_bytes(data)
        project=create_project([load_source(source,library=True)],dict.fromkeys(PARTS,0),temp/'Project');app.load(project);app.max_texture_checkbox.invoke()
        deadline=time.monotonic()+90
        while (app.preview_after is not None or app.busy) and time.monotonic()<deadline:app.root.update();time.sleep(.02)
        if not app.max_textures.get():raise ValueError('Maximum texture checkbox did not enable')
        with patch('model_creator.core.MAX_BYTES',len(data)-2048),patch('model_creator.gui.messagebox.showwarning'):
            app.assemble();deadline=time.monotonic()+180
            while app.busy and time.monotonic()<deadline:app.root.update();time.sleep(.02)
        if app.result is None or not app.last_report['maximum_texture_downgrade'] or not app.last_report['within_budget']:raise ValueError('Maximum texture checkbox did not rescue a real oversized texture table')
        if not app.last_report['maximum_texture_downgrade']['unchanged_non_texture_payloads']:raise ValueError('Texture option altered geometry/rigging')
        app.max_textures.set(False)
        with patch('model_creator.gui.messagebox.showinfo'):
            if app.require_result():raise ValueError('Changed texture option allowed stale export')
        app.max_textures.set(True)
        report=json.loads(output.read_text());report.update(maximum_texture_checkbox=True,maximum_texture_gui_rescue=True,texture_option_stale_export_blocked=True)
        dump(output,report)
    # Exercise the shared native neck bind solver in the actual frozen app.
    app.max_textures.set(False);app.open_library();labels={e['label']:app.labels[i] for i,e in enumerate(app.library.entries)}
    for part in PARTS:app.choices[part].set(labels['Batista'])
    app.choices['Torso'].set(labels['Jeff-Hardy']);app.dirty();deadline=time.monotonic()+90
    while (app.preview_after is not None or app.busy) and time.monotonic()<deadline:app.root.update();time.sleep(.02)
    if app.model is None:raise ValueError('Jeff Hardy torso bind compatibility preview failed')
    with patch('model_creator.gui.messagebox.showwarning'):
        app.assemble();deadline=time.monotonic()+90
        while app.busy and time.monotonic()<deadline:app.root.update();time.sleep(.02)
    if app.result is None or not app.last_report.get('shared_neck_fit',{}).get('applied'):raise ValueError('Shared neck fit did not run in frozen app')
    if any(not c['passed'] for c in app.last_report['local_axis_interior_pose_comparison'].values()):raise ValueError('Frozen Hardy source-pose regression')
    from PIL import ImageGrab
    app.root.update();x,y=app.root.winfo_rootx(),app.root.winfo_rooty();w,h=app.root.winfo_width(),app.root.winfo_height()
    ImageGrab.grab(bbox=(x,y,x+w,y+h)).save(output.with_name('creator-030-window.png'))
    report=json.loads(output.read_text());report.update(frozen_hardy_bind_fit=True,local_axis_pose_regressions_checked=True)
    dump(output,report)


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


def run_uv(app,output):
    """Real canvas gestures, morph/UV preview, portable projects and PAC export."""
    import json
    import numpy as np
    from PIL import Image,ImageGrab
    from unittest.mock import patch
    from .morph.fixtures import donor
    from .uv.document import signature
    from desktop.texture_optimizer.candidates import write_gim,read_gim
    from tools.pac_repack import replace_sections,texture_table
    from tools.yukes_bpe import compress
    from .core import read_project
    def wait():
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            app.root.update()
            if not any((app.busy,app.preview_after,app.refresh_after,app.morph_ui.preview_after,app.uv_ui.preview_after)):break
            time.sleep(.02)
        if app.busy or app.model is None:raise ValueError('UV preview failed: '+getattr(app,'last_error',''))
    with tempfile.TemporaryDirectory(prefix='creator-uv-',dir=output.parent) as temporary:
        t=Path(temporary);palette=np.zeros((16,4),np.uint8);palette[:,3]=255
        palette[:4,:3]=[[185,125,80],[40,50,100],[240,225,180],[100,30,30]]
        yy,xx=np.indices((32,32));pixels=((xx//4+yy//4)%4).astype(np.uint8)
        gim=write_gim(pixels,palette,4);data=replace_sections(donor(),{9:compress(texture_table(['skin'],[gim],gim_reader=read_gim))})
        paths=[t/'A.pac',t/'B.pac']
        for p in paths:p.write_bytes(data)
        project=create_project(*paths,t/'Project');app.load(project);app.green.set(False);app.show_waist.set(False);app.pose.set('rest')
        app.sidebar.select(2);wait();uv=app.uv_ui;doc=uv.doc
        if doc is None or not uv.canvas.winfo_ismapped():raise ValueError('Integrated UV canvas is unavailable')
        original=app.preview_frame.tobytes();uv.select_all()
        # Numeric move changes the shared model preview using real native UVs.
        uv.inputs[('Move UV','U')].set('.12');uv.numeric('Move UV');wait()
        if app.preview_frame.tobytes()==original:raise ValueError('Live UV edits did not alter the 3D preview')
        moved=doc.uv.copy();uv.undo();wait()
        if app.preview_frame.tobytes()!=original:raise ValueError('UV undo did not restore the rendered original')
        uv.undo(True);wait();np.testing.assert_array_equal(doc.uv,moved)
        # Actual Tk mouse drag uses an immutable gesture start and one undo step.
        fi=next(f for f in uv.visible() if abs(np.linalg.det(np.column_stack((doc.uv[doc.faces[f]][1]-doc.uv[doc.faces[f]][0],doc.uv[doc.faces[f]][2]-doc.uv[doc.faces[f]][0]))))>1e-6)
        q=uv.coordinates(doc.uv[doc.faces[fi]].mean(0));uv.mode.set('Move');old=doc.uv.copy();history=len(doc.undo_stack)
        uv.canvas.event_generate('<ButtonPress-1>',x=int(q[0]),y=int(q[1]))
        uv.canvas.event_generate('<B1-Motion>',x=int(q[0]+12),y=int(q[1]+4))
        uv.canvas.event_generate('<ButtonRelease-1>',x=int(q[0]+12),y=int(q[1]+4));wait()
        if np.array_equal(old,doc.uv) or len(doc.undo_stack)!=history+1:raise ValueError('UV canvas drag/history failed')
        uv.undo();wait();np.testing.assert_array_equal(doc.uv,old)
        uv.region.set('Face / head');uv.filter_changed();uv.select_all();uv.isolate.set(True);uv.changed();wait()
        if not doc.selection:raise ValueError('Face region filter selected nothing')
        uv.inputs[('Scale','X')].set('.96');uv.inputs[('Scale','Y')].set('1.03');uv.numeric('Scale')
        uv.inputs[('Rotate °','Angle')].set('3');uv.numeric('Rotate °');uv.distortion.set(True);uv.draw();wait()
        uv.isolate.set(False);uv.region.set('All');uv.filter_changed()
        image=Image.fromarray(palette[pixels]);image.putpixel((0,0),(250,50,40,255));texture=t/'Edited.png';image.save(texture)
        with patch('model_creator.uv.ui.filedialog.askopenfilename',return_value=str(texture)):uv.import_texture()
        wait()
        app.morph_ui.variables['chest_width'].set(.45);app.morph_ui.changed('chest_width');app.morph_ui.finish_gesture();wait()
        recipe=uv.recipe();expected_model=doc.model(app.morph_ui.preview_job(app.model)());app.save()
        metadata,_=read_project(project)
        if metadata['schema']!='psp-model-creator/3' or signature(metadata.get('uv'))!=signature(recipe):raise ValueError('UV project recipe was not saved')
        app.assemble();wait()
        if app.last_report.get('uv',{}).get('signature')!=signature(recipe) or not app.last_report.get('morph'):raise ValueError('Combined morph/UV export missing an edit layer: '+getattr(app,'last_error',''))
        result=load_source(app.result/'created-model.pac')
        actual=[v for m in result['model']['meshes'] for v in m['vertices']];expected=[v for m in expected_model['meshes'] for v in m['vertices']]
        np.testing.assert_array_equal([v['uv'] for v in actual],[v['uv'] for v in expected])
        np.testing.assert_allclose([v['position'] for v in actual],[v['position'] for v in expected],atol=1e-5)
        if result['textures']['skin']!=doc.textures['skin']:raise ValueError('Preview texture differs from exported indexed texture')
        saved=t/'Saved.pac'
        with patch('model_creator.gui.filedialog.asksaveasfilename',return_value=str(saved)):app.export_pac()
        if not saved.is_file():raise ValueError('UV PAC save was unavailable')
        uv.select_all();uv.transform(move=(.01,0));wait()
        with patch('model_creator.gui.messagebox.showinfo'):
            if app.require_result():raise ValueError('UV edit allowed a stale PAC export')
        app.load(project);wait();uv=app.uv_ui
        if signature(uv.recipe())!=signature(recipe) or abs(app.morph_ui.values()['chest_width']-.45)>1e-5:raise ValueError('Reload lost morph/UV edits')
        uv.distortion.set(False);uv.draw();app.root.update()
        x,y=app.root.winfo_rootx(),app.root.winfo_rooty();w,h=app.root.winfo_width(),app.root.winfo_height()
        if uv.canvas.winfo_width()<200 or uv.canvas.winfo_height()<200:raise ValueError('UV canvas clipped')
        ImageGrab.grab(bbox=(x,y,x+w,y+h)).save(output.with_name('creator-uv-window.png'))
        uv.reset();app.morph_ui.reset();wait();app.assemble();wait()
        if (app.result/'created-model.pac').read_bytes()!=data:raise ValueError('UV/morph reset did not export the byte-exact original')
        if any(p.read_bytes()!=data for p in paths):raise ValueError('UV editing modified a source PAC')
        report=json.loads(output.read_text());report.update(uv_editor=True,uv_live_preview=True,uv_canvas_mouse_drag=True,uv_undo_redo=True,
            uv_region_isolation=True,uv_scale_rotation=True,uv_palette_texture_import=True,uv_morph_combined_export=True,
            uv_native_geometry_weights_preserved=True,uv_project_roundtrip=True,uv_stale_export_blocked=True,uv_reset_export_byte_exact=True)
        dump(output,report)
