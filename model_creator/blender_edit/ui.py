"""Creator notebook integration; edits are separate, reversible validated builds."""
from pathlib import Path
import uuid
from tkinter import ttk,filedialog,messagebox

from .bridge import create_session,launch,import_session


class Panel:
    def __init__(self,app,page):
        self.app=app;self.session=None;self.previous=[]
        ttk.Label(page,text='Edit the assembled model in Blender',wraplength=240).pack(anchor='w',pady=6)
        ttk.Label(page,text='1. Assemble and validate your current morph / UV edits.\n2. Edit in Blender.\n3. Save the .blend and save/pack painted images.\n4. Import the saved file to validate a new build.',wraplength=240,justify='left').pack(fill='x',pady=8)
        ttk.Button(page,text='Choose Blender...',command=self.choose_runtime).pack(fill='x',pady=3)
        ttk.Label(page,textvariable=app.morph_ui.runtime_label,wraplength=240).pack(fill='x',pady=2)
        ttk.Button(page,text='Edit assembled model in Blender...',command=self.open).pack(fill='x',pady=3)
        ttk.Button(page,text='Import saved Blender file...',command=self.import_file).pack(fill='x',pady=3)
        ttk.Button(page,text='Undo Blender import',command=self.undo).pack(fill='x',pady=3)
        ttk.Label(page,text='Supports shape, UV and existing texture edits. Keep topology, material assignments, bones and skin weights unchanged. Unsupported edits are rejected.\n\nThe displayed rig is a bind-position reference; its axes do not reproduce PSP animations.\n\nEach import preserves your previous build. Reassembling starts from Creator choices; it does not replay Blender edits.',wraplength=240,justify='left').pack(fill='x',pady=10)

    def choose_runtime(self):self.app.morph_ui.choose_runtime()

    def open(self):
        app=self.app
        if not app.require_result():return
        parent=filedialog.askdirectory(title='Choose a parent folder for a NEW Blender session')
        if not parent:return
        destination=Path(parent)/('Creator-Blender-'+uuid.uuid4().hex[:8]);source=app.result/'created-model.pac';runtime=app.morph_ui.runtime;library=app.library_project
        def done(blend):
            self.session=blend.parent
            launch(blend,runtime=runtime)
            app.status.set('Blender session: '+str(blend)+'. Save your edits, then Import saved Blender file.')
        app.task(lambda:create_session(source,destination,runtime=runtime,library=library,cancel=app.stop_event.is_set),done)

    def import_file(self):
        app=self.app
        if not app.require_result():return
        blend=filedialog.askopenfilename(title='Choose your saved Creator Blender file',initialdir=str(self.session)if self.session else None,filetypes=[('Blender model','*.blend')])
        if not blend:return
        folder=Path(blend).parent
        if not (folder/'session.json').is_file():
            contract=filedialog.askopenfilename(title='Choose session.json from the original Creator Blender session',filetypes=[('Creator Blender session','session.json')])
            if not contract:return
            folder=Path(contract).parent
        prior=(app.result,app.last_report);output=app.result.parent/('blender-import-'+uuid.uuid4().hex[:8]);current=app.result/'created-model.pac';runtime=app.morph_ui.runtime
        def done(result):
            self.previous.append(prior);self.previous=self.previous[-20:];self.session=folder
            app.result,app.last_report,source=result;app.showing_build=True;app.model=source['model'];app.textures={n:source['textures'][n.casefold()]for n in app.model['texture_names']};app.preview_revision+=1
            app.sidebar.select(3)
            app.status.set(f'Blender edit validated: {app.last_report["pac_bytes"]:,} bytes. Previous build preserved; review the preview before exporting.');app.refresh()
        app.task(lambda:import_session(folder,blend,current,output,runtime=runtime,report=prior[1],cancel=app.stop_event.is_set),done)

    def undo(self):
        app=self.app
        if not app.require_idle():return
        if not self.previous:messagebox.showinfo('Blender','No Blender import to undo.',parent=app.root);return
        from model_creator.core import load_source
        result,report=self.previous[-1]
        if app.result is None or app.last_report.get('blender_edit',{}).get('previous_build')!=str(result):
            messagebox.showinfo('Blender','The active build has changed. Previous Blender builds remain saved on disk.',parent=app.root);return
        source=load_source(result/'created-model.pac',library=app.library_project);self.previous.pop();app.result=result;app.last_report=report;app.model=source['model'];app.textures={n:source['textures'][n.casefold()]for n in app.model['texture_names']};app.showing_build=True;app.preview_revision+=1;app.status.set('Restored previous build. Blender edit remains saved on disk.');app.refresh()
