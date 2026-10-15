"""Small classic ttk standalone creator. No converter UI/runtime dependency."""
import json
import os
from pathlib import Path
import queue
import shutil
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import traceback
import uuid

from PIL import ImageTk

from .core import PARTS, POSES, VERSION, assemble, build, create_project, dump, load_source, preview, read_project
from tools.psp_mesh_audit import audit_yobj


class App:
    def __init__(self, root):
        self.root=root;self.project=None;self.result=None;self.model=None;self.textures=None;self.busy=False;self.events=queue.Queue()
        self.preview_after=None;self.preview_revision=0;self.refresh_after=None
        root.title('PSP Model Creator — Experimental '+VERSION);root.geometry('1100x830');root.minsize(1000,790)
        style=ttk.Style(root)
        if 'vista' in style.theme_names():style.theme_use('vista')
        else:style.theme_use('clam')
        root.option_add('*Font', ('Segoe UI',10))
        shell=ttk.Frame(root,padding=12);shell.pack(fill='both',expand=True)
        toolbar=ttk.Frame(shell);toolbar.pack(fill='x')
        for text,fn in (('New project…',self.new),('Open project…',self.open),('Save choices',self.save),('Help',self.help)):
            ttk.Button(toolbar,text=text,command=fn).pack(side='left',padx=(0,6))
        ttk.Label(shell,text='PSP Model Creator',font=('Segoe UI',19)).pack(anchor='w',pady=(12,2))
        ttk.Label(shell,text='Prepared Kenny Dykstra / Brian Kendrick pair · Native PSP parts · Separate from the converter').pack(anchor='w')
        self.project_label=tk.StringVar(value='Create a project and select your two original PSP PACs. No game assets are bundled.')
        ttk.Label(shell,textvariable=self.project_label,wraplength=950).pack(anchor='w',pady=8)
        work=ttk.Frame(shell);work.pack(fill='both',expand=True)
        left=ttk.LabelFrame(work,text='Body parts',padding=12);left.pack(side='left',fill='y',padx=(0,12))
        self.choices={};self.controls=[]
        for part in PARTS:
            ttk.Label(left,text=part).pack(anchor='w',pady=(8,3));v=tk.StringVar();self.choices[part]=v
            box=ttk.Combobox(left,textvariable=v,state='readonly',width=25);box.pack(fill='x');box.bind('<<ComboboxSelected>>',lambda _:self.dirty());self.controls.append(box)
        self.assemble_button=ttk.Button(left,text='Assemble and validate',command=self.assemble);self.assemble_button.pack(fill='x',pady=(20,8))
        ttk.Label(left,text='Output limit: 148,000 bytes\nTextures retain native quality.\nOversized results are withheld.\n\nSource 1 supplies the mixed\nPAC container. Source 2 supplies\nselected main-model parts.\n\nSeams and gameplay still need\nvisual and PPSSPP review.',justify='left').pack(anchor='w',pady=8)
        right=ttk.Frame(work);right.pack(fill='both',expand=True)
        top=ttk.Frame(right);top.pack(fill='x',pady=(0,6))
        ttk.Label(top,text='Pose:').pack(side='left');self.pose=tk.StringVar(value='rest')
        box=ttk.Combobox(top,textvariable=self.pose,values=list(POSES),state='readonly',width=15);box.pack(side='left',padx=6);box.bind('<<ComboboxSelected>>',lambda _:self.refresh())
        self.green=tk.BooleanVar(value=True);ttk.Checkbutton(top,text='Green body preview',variable=self.green,command=self.refresh).pack(side='left',padx=10)
        self.picture=ttk.Label(right,text='Choose two PSP PACs to begin.',anchor='center',background='#484848',foreground='white');self.picture.pack(fill='both',expand=True)
        views=ttk.Frame(right);views.pack(fill='x',pady=6);self.view='front-left'
        for label,view in (('¾','front-left'),('Front','front'),('Rear','back'),('Left','left'),('Right','right')):
            ttk.Button(views,text=label,command=lambda v=view:self.set_view(v),width=8).pack(side='left',padx=(0,4))
        export=ttk.Frame(shell);export.pack(fill='x',pady=8)
        for text,fn in (('Save PAC as…',self.export_pac),('Export preview folder…',self.export_preview),('Export editable textures…',self.export_edit),('Pack edited folder…',self.pack_edit),('QA report',self.report)):
            ttk.Button(export,text=text,command=fn).pack(side='left',padx=(0,6))
        self.progress=ttk.Progressbar(shell,mode='indeterminate');self.progress.pack(fill='x')
        self.status=tk.StringVar(value='Ready. Originals are copied into a private project and never overwritten.')
        ttk.Label(shell,textvariable=self.status,wraplength=980).pack(anchor='w',pady=6)
        root.after(75,self.poll)

    def task(self,fn,done):
        if self.busy:return
        self.busy=True;self.progress.start(12);self.assemble_button.state(['disabled'])
        def worker():
            try:self.events.put(('done',done,fn()))
            except Exception:self.events.put(('error',traceback.format_exc()))
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        try:
            while True:
                event=self.events.get_nowait()
                if event[0]=='status':self.status.set(event[1]);continue
                self.busy=False;self.progress.stop();self.assemble_button.state(['!disabled'])
                if event[0]=='error':
                    # Full diagnostic is retained locally and accessible in the dialog.
                    log=Path(tempfile.gettempdir())/'psp-model-creator-last-error.txt';log.write_text(event[1],encoding='utf-8')
                    self.status.set('Operation failed; previous result preserved. '+str(log))
                    messagebox.showerror('Creator stopped',event[1].splitlines()[-1]+'\n\nFull log: '+str(log),parent=self.root)
                else:
                    try:event[1](event[2])
                    except Exception:messagebox.showerror('Creator',traceback.format_exc(),parent=self.root)
        except queue.Empty:pass
        self.root.after(75,self.poll)

    def require_idle(self):
        if self.busy:self.status.set('Please wait for the current operation.');return False
        return True

    def new(self):
        if not self.require_idle():return
        first=filedialog.askopenfilename(title='Source 1: Kenny Dykstra PSP PAC (mixed output container)',filetypes=[('PSP PAC','*.pac *.PAC')])
        if not first:return
        second=filedialog.askopenfilename(title='Source 2: Brian Kendrick PSP PAC',filetypes=[('PSP PAC','*.pac *.PAC')])
        if not second:return
        parent=filedialog.askdirectory(title='Choose where to create a NEW private project folder')
        if not parent:return
        output=Path(parent)/('PSP-Creator-'+uuid.uuid4().hex[:8])
        self.task(lambda:create_project(first,second,output),self.load)

    def open(self):
        if not self.require_idle():return
        path=filedialog.askopenfilename(title='Open creator project.json',filetypes=[('Creator project','*.json')])
        if path:self.task(lambda:(read_project(path),path),lambda result:self.load(result[1]))

    def load(self,path):
        project,sources=read_project(path);self.project=Path(path);self.labels=[s['label'] for s in sources]
        # Include source numbers so even identical filenames are distinguishable.
        self.labels=[f'{i+1}. {label}' for i,label in enumerate(self.labels)]
        for part,box in zip(PARTS,self.controls):box['values']=self.labels;self.choices[part].set(self.labels[project['selections'][part]])
        self.project_label.set(str(self.project));self.result=None;self.model=None;self.textures=None
        self.status.set('Project loaded. Preparing selection preview…');self.picture.configure(image='',text='Preparing preview…');self.picture.image=None
        self.dirty()

    def selected(self):return {p:self.labels.index(self.choices[p].get()) for p in PARTS}

    def dirty(self):
        self.preview_revision+=1
        self.status.set('Updating selection preview. Assemble and validate before exporting this combination.')
        if self.preview_after is not None:self.root.after_cancel(self.preview_after)
        self.preview_after=self.root.after(300,self.live_preview)

    def live_preview(self):
        self.preview_after=None
        if not self.project:return
        if self.busy:
            self.preview_after=self.root.after(150,self.live_preview);return
        revision=self.preview_revision;selections=self.selected();path=self.project
        view,pose,green=self.view,self.pose.get(),self.green.get()
        def work():
            _,sources=read_project(path);raw,textures,_=assemble(sources,selections);model=audit_yobj(raw)
            return model,textures,preview(model,textures,view,448,pose,green)
        def done(result):
            if revision!=self.preview_revision:return
            self.model,self.textures,image=result;photo=ImageTk.PhotoImage(image)
            self.picture.configure(image=photo,text='');self.picture.image=photo
            self.status.set('Current selections previewed. Assemble and validate to create their PAC; preview alone does not enforce the file-size budget.')
        self.task(work,done)

    def save(self):
        if not self.require_idle() or not self.project:return
        try:
            project,_=read_project(self.project);project['selections']=self.selected()
            history=self.project.parent/'history';history.mkdir(exist_ok=True)
            shutil.copy2(self.project,history/(uuid.uuid4().hex+'.json'))
            temp=self.project.with_suffix('.new');dump(temp,project);temp.replace(self.project)
            self.status.set('Choices saved; previous recipe preserved in history.')
        except Exception:messagebox.showerror('Save choices',traceback.format_exc(),parent=self.root)

    def assemble(self):
        if not self.require_idle():return
        if not self.project:messagebox.showinfo('Creator','Create or open a project first.',parent=self.root);return
        if self.preview_after is not None:self.root.after_cancel(self.preview_after);self.preview_after=None
        self.preview_revision+=1
        selections=self.selected();self.save();output=self.project.parent/'builds'/uuid.uuid4().hex
        def work():
            report=build(self.project,selections,output,progress=lambda msg:self.events.put(('status',msg)))
            source=load_source(output/'created-model.pac')
            return output,report,source
        def done(result):
            self.result,self.last_report,source=result;self.model=source['model'];self.textures={n:source['textures'][n.casefold()] for n in self.model['texture_names']}
            self.status.set(f'Experimental build: {self.last_report["pac_bytes"]:,} / 148,000 bytes. Native checks passed; review seams and test in PPSSPP.')
            self.refresh()
        self.task(work,done)

    def refresh(self):
        if self.model is None:return
        if self.busy:
            if self.refresh_after is None:
                def retry():self.refresh_after=None;self.refresh()
                self.refresh_after=self.root.after(150,retry)
            return
        model,textures,view,pose,green=self.model,self.textures,self.view,self.pose.get(),self.green.get()
        def done(image):
            photo=ImageTk.PhotoImage(image);self.picture.configure(image=photo,text='');self.picture.image=photo
        self.task(lambda:preview(model,textures,view,448,pose,green),done)

    def set_view(self,view):
        if not self.require_idle():return
        self.view=view;self.refresh()

    def require_result(self):
        if not self.require_idle():return False
        if self.result is None:messagebox.showinfo('Creator','Assemble a model first.',parent=self.root);return False
        if self.last_report['selections']!=self.selected():
            messagebox.showinfo('Selections changed','The preview uses your current choices. Assemble and validate this combination before exporting it. Your previous build is preserved.',parent=self.root);return False
        return True

    def export_pac(self):
        if not self.require_result():return
        from desktop.edit_folder import publish_new
        path=filedialog.asksaveasfilename(title='Save a NEW experimental PAC',defaultextension='.pac',initialfile='Created-PSP-experimental.pac')
        if path:
            try:publish_new(path,(self.result/'created-model.pac').read_bytes());self.status.set('Saved '+path)
            except Exception as exc:messagebox.showerror('Export PAC',str(exc),parent=self.root)

    def export_preview(self):
        if not self.require_result():return
        parent=filedialog.askdirectory(title='Choose parent folder for a NEW preview export')
        if parent:
            path=Path(parent)/('Creator-preview-'+uuid.uuid4().hex[:8])
            shutil.copytree(self.result,path);self.status.set('Exported PAC, OBJ, PNGs and QA to '+str(path))

    def export_edit(self):
        if not self.require_result():return
        parent=filedialog.askdirectory(title='Choose parent folder for a NEW editable texture export')
        if not parent:return
        result=self.result;destination=Path(parent)/('Creator-textures-'+uuid.uuid4().hex[:8])
        def work():
            from desktop.workspace import inspect_workspace
            from desktop.edit_folder import export_folder
            with tempfile.TemporaryDirectory(prefix='creator-inspect-') as temp:
                root=Path(temp)/'inspection';inspect_workspace(result/'created-model.pac',root,resolution=128)
                export_folder(root/'manifest.json',destination)
            return destination
        self.task(work,lambda path:self.status.set('Edit named PNGs in '+str(path)+', then use Pack edited folder.'))

    def pack_edit(self):
        if not self.require_idle():return
        folder=filedialog.askdirectory(title='Select the exported editable texture folder')
        if not folder:return
        path=filedialog.asksaveasfilename(title='Save a NEW texture-edited PAC',defaultextension='.pac')
        if not path:return
        def work():
            from desktop.edit_folder import pack_folder
            return pack_folder(folder,path)
        self.task(work,lambda _:self.status.set('Texture-edited PAC saved: '+path+'; review its report and test in PPSSPP.'))

    def report(self):
        if not self.require_result():return
        window=tk.Toplevel(self.root);window.title('Creator QA report');window.geometry('850x650')
        text=tk.Text(window,wrap='word');text.pack(fill='both',expand=True);text.insert('end',(self.result/'qa.json').read_text(encoding='utf-8'));text.configure(state='disabled')

    def help(self):
        messagebox.showinfo('Prepared-pair experimental creator',
            '1. New project: select original Kenny PSP PAC first, Brian PSP PAC second.\n'
            '2. Choose Head / Torso / Arms / Legs; the preview updates automatically.\n'
            '3. Check textured and green previews from every side and under poses.\n'
            '4. Save PAC, or export a folder for PNG editing in Photoshop/GIMP.\n'
            '5. Pack edited folder and test a copied ISO in PPSSPP.\n\n'
            'Both original PACs remain in your private project. Each build gets its own folder.\n'
            'The torso supplies shared attachment contours. Hair remains with the head.\n'
            'Mixed assemblies use source 1’s container; source 2 auxiliary models are not assembled.\n'
            'Internal/ambiguous neck intersections require visual review (see QA).\n'
            'This prototype is prepared for this pair. Matching bones alone cannot certify another pair.\n'
            'Analytical poses do not establish in-game compatibility. No Blender or Noesis is needed.',parent=self.root)


def main():
    root=tk.Tk();app=App(root)
    if '--smoke-test' in sys.argv:
        from .smoke import run
        output=Path(sys.argv[sys.argv.index('--smoke-test')+1])
        def smoke():
            try:run(app,output)
            except Exception:
                output.parent.mkdir(parents=True,exist_ok=True);dump(output,dict(passed=False,error=traceback.format_exc()));root.destroy();raise
            root.destroy()
        root.after(100,smoke)
    root.mainloop()
