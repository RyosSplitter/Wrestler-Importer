"""Optional real Tk/Blender workflow smoke test (run under an X display)."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

@unittest.skipUnless(os.environ.get('DISPLAY') and shutil.which('blender'),'GUI smoke requires X and Blender')
class BlenderEditorUITests(unittest.TestCase):
    def test_create_import_preview_and_undo(self):
        import tkinter as tk
        from model_creator.gui import App
        from model_creator.fixtures import pair
        from model_creator.core import create_project,PARTS
        with tempfile.TemporaryDirectory()as temp:
            folder=Path(temp);a,b=folder/'a.pac',folder/'b.pac'
            for f,data in zip((a,b),pair()):f.write_bytes(data)
            project=create_project(a,b,folder/'project')
            with patch.object(sys,'argv',['creator','--smoke-test']):
                root=tk.Tk();app=App(root)
            def wait(predicate):
                end=time.monotonic()+50
                while time.monotonic()<end:
                    root.update()
                    if getattr(app,'last_error',None):self.fail(app.last_error)
                    if predicate()and not app.busy:return
                    time.sleep(.02)
                self.fail('GUI worker did not finish: '+app.status.get())
            try:
                app.load(project)
                for part in PARTS:app.choices[part].set(app.labels[0])
                app.dirty();wait(lambda:app.model is not None and app.preview_after is None)
                app.assemble();wait(lambda:app.result is not None)
                previous=app.result;previous_bytes=(previous/'created-model.pac').read_bytes()
                self.assertEqual(app.sidebar.tab(3,'text'),'Blender')
                with patch('model_creator.blender_edit.ui.filedialog.askdirectory',return_value=str(folder)),patch('model_creator.blender_edit.ui.launch'):
                    app.blender_ui.open();wait(lambda:app.blender_ui.session is not None)
                blend=app.blender_ui.session/'model.blend';script=folder/'edit.py';script.write_text("import bpy\nfor o in bpy.context.scene.objects:\n if o.type=='MESH':\n  for v in o.data.vertices:v.co*=1.01\nbpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)\n")
                r=subprocess.run([shutil.which('blender'),'-b',str(blend),'--disable-autoexec','--python-exit-code','1','--python',str(script)],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                with patch('model_creator.blender_edit.ui.filedialog.askopenfilename',return_value=str(blend)):
                    app.blender_ui.import_file();wait(lambda:app.result!=previous)
                self.assertTrue(app.blender_build_active());self.assertTrue(app.require_result())
                self.assertNotEqual((app.result/'created-model.pac').read_bytes(),previous_bytes)
                self.assertEqual((previous/'created-model.pac').read_bytes(),previous_bytes)
                app.sidebar.select(2);root.update();self.assertEqual(app.sidebar.index(app.sidebar.select()),3)
                app.green.set(False);app.show_waist.set(False);app.refresh();wait(lambda:app.preview_frame is not None)
                if os.environ.get('CREATOR_UI_CAPTURE'):
                    from PIL import ImageGrab
                    root.update();ImageGrab.grab(xdisplay=os.environ['DISPLAY']).save(os.environ['CREATOR_UI_CAPTURE'])
                app.blender_ui.undo();wait(lambda:app.result==previous)
                self.assertFalse(app.blender_build_active());self.assertEqual((app.result/'created-model.pac').read_bytes(),previous_bytes)
            finally:
                wait(lambda:not app.busy);root.destroy()
