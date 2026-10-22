"""Actual Tk Retexture-node controls, portable project and texture-only PAC export."""
from pathlib import Path
import json
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image,ImageDraw,ImageGrab

from desktop.retexture import Document
from tools.generate_conformance_fixtures import vectors


def exercise(panel,root,folder):
    """Shared by the frozen Windows smoke and the local standalone Tk check."""
    source=folder/'Original.pac';data=vectors()['psp-quad.pac'];source.write_bytes(data)
    panel.attach(Document(data,source));root.update()
    def wait():
        deadline=time.monotonic()+30
        while (panel.future is not None or panel.preview_timer is not None or panel.preview_pending or hasattr(panel,'after_preview'))and time.monotonic()<deadline:
            root.update();time.sleep(.01)
        if panel.future is not None:raise TimeoutError('Retexture background task did not finish.')
    wait()
    if panel.model_photo is None:raise ValueError('Initial model preview failed.')
    panel.uv.set(False);panel.redraw()
    # Real pointer stroke, selection and protection handling, undo and redo.
    panel.doc.textures[0].protection.putpixel((0,0),255)
    panel.color=(20,90,210);panel.tool.set('Brush')
    def event(x,y):return SimpleNamespace(x=round(10+x*panel.scale),y=round(10+y*panel.scale))
    frames=panel.preview_frames
    panel.begin(event(8,4))
    # Keep the pointer held while edits continue. Debounce-only preview code
    # would produce zero frames until end(); this is an explicit regression.
    start=time.monotonic()
    while time.monotonic()-start<1.5:
        x=8+int((time.monotonic()-start)*15)%16
        panel.drag(event(x,4));root.update();time.sleep(.04)
    if panel.preview_frames<=frames:raise ValueError('Live preview did not update during an active brush stroke.')
    panel.end(event(24,4))
    if not panel.texture.layers:raise ValueError('Pointer painting created no layer.')
    painted=np.array(panel.texture.composite());panel.undo(False);panel.undo(True)
    if not np.array_equal(painted,panel.texture.composite()):raise ValueError('Undo/redo lost paint data.')
    panel.clear_protection();panel.select_all()
    with patch('desktop.retexture_ui.colorchooser.askcolor',return_value=((20,90,210),'#145ad2')):panel.recolor()
    logo=folder/'logo.png';art=Image.new('RGBA',(24,16));ImageDraw.Draw(art).ellipse((2,2,21,13),fill=(250,240,20,255));art.save(logo)
    with patch('desktop.retexture_ui.filedialog.askopenfilename',return_value=str(logo)):panel.import_art()
    panel.transform('rotate',15);panel.transform('scale',.9);panel.transform('mirror',0)
    panel.layer_action('visible')  # Keep export color-simple; layer persists hidden.
    panel.encoded.set(True);panel.changed(False);wait()
    if panel.model_photo is None:raise ValueError('Edited encoded preview failed.')
    project=folder/'Edited.pspret'
    with patch('desktop.retexture_ui.filedialog.asksaveasfilename',return_value=str(project)):
        if not panel.save_project():raise ValueError('Project save failed.')
    restored=Document.load(project)
    if not np.array_equal(restored.textures[0].composite(),panel.texture.composite()):raise ValueError('Saved project lost texture edits.')
    with patch('desktop.retexture_ui.messagebox.showinfo'),patch('desktop.retexture_ui.messagebox.showerror')as errors:
        panel.check_size();wait()
        if errors.called or not panel.last_report['fits']:raise ValueError('Actual encoded size check failed.')
        output=folder/'Edited.pac'
        with patch('desktop.retexture_ui.filedialog.asksaveasfilename',return_value=str(output)):panel.export_pac()
        wait()
        if errors.called or not output.exists():raise ValueError('PAC export from Retexture controls failed.')
    result=Document(output.read_bytes())
    if source.read_bytes()!=data or not panel.last_report['all_model_payloads_exact']:raise ValueError('Retexture modified original/model records.')
    if output.read_bytes()==data:raise ValueError('Edited output still equals original.')
    panel.doc.dirty=False
    return dict(status='pass',pointer_tools=True,live_preview_during_stroke=True,undo_redo=True,layer_transform=True,
                editable_project_round_trip=True,encoded_preview=True,actual_size_checked=True,
                pac_export=True,model_payloads_exact=True,original_preserved=True,
                output_bytes=len(output.read_bytes()),texture_alpha_exact=np.array_equal(
                    np.asarray(result.textures[0].original)[:,:,3],np.asarray(panel.texture.original)[:,:,3]))


def run(app,output):
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    shell=app.suite;app.root.update()
    with tempfile.TemporaryDirectory(prefix='retexture-smoke-',dir=output.parent)as temp:
        folder=Path(temp);source=folder/'Node.pac';source.write_bytes(vectors()['psp-quad.pac'])
        shell.open_pac(source);deadline=time.monotonic()+90
        while shell.busy()and time.monotonic()<deadline:app.root.update();time.sleep(.01)
        if not shell.manifest or not shell.model_tree.exists('retexture_0'):raise ValueError('Retexture editor-tree node missing.')
        shell.model_tree.selection_set('retexture_0');app.root.update()
        if shell.tabs.select()!=str(shell.pages['Retexture']):raise ValueError('Selecting the editor node did not open Retexture.')
        report=exercise(shell.retexture,app.root,folder)
        app.root.geometry('1040x720');app.root.update()
        # All key edit/export tools must remain reachable at the supported minimum.
        app.root.geometry('940x640');app.root.update()
        if shell.retexture.canvas.winfo_width()<180 or shell.retexture.preview.winfo_width()<180:
            raise ValueError('Retexture canvas/preview unusable at minimum window size.')
        app.root.geometry('1200x820');app.root.update()
        box=(app.root.winfo_rootx(),app.root.winfo_rooty(),app.root.winfo_rootx()+app.root.winfo_width(),app.root.winfo_rooty()+app.root.winfo_height())
        ImageGrab.grab(bbox=box).save(output.with_suffix('.png'))
        report['editor_tree_node']=True;report['minimum_window_checked']=True
        output.write_text(json.dumps(report,indent=2)+'\n')
    return report
