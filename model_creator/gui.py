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

from .core import MAX_BYTES, PARTS, POSES, VERSION, assemble, build, create_project, dump, load_source, preview, read_project
from .parts import DEFAULT_WAIST, WAIST_RANGE
from tools.psp_mesh_audit import audit_yobj


class App:
    def __init__(self, root):
        self.root=root;self.project=None;self.result=None;self.model=None;self.textures=None;self.busy=False;self.events=queue.Queue()
        self.preview_after=None;self.preview_revision=0;self.refresh_after=None;self.library=None;self.library_project=False
        root.title('PSP Model Creator — Experimental '+VERSION)
        width=min(1100,root.winfo_screenwidth()-40);height=min(830,root.winfo_screenheight()-100)
        self.preview_size=min(448,max(256,root.winfo_screenheight()-480))
        root.geometry(f'{width}x{height}+10+10');root.minsize(min(1000,width),min(700,height))
        style=ttk.Style(root)
        if 'vista' in style.theme_names():style.theme_use('vista')
        else:style.theme_use('clam')
        root.option_add('*Font', ('Segoe UI',10))
        shell=ttk.Frame(root,padding=12);shell.pack(fill='both',expand=True)
        toolbar=ttk.Frame(shell);toolbar.pack(fill='x')
        for text,fn in (('Prepared library',self.open_library),('Add donors…',self.add_donors),('New project…',self.new),('Open project…',self.open),('Save choices',self.save),('Help',self.help)):
            ttk.Button(toolbar,text=text,command=fn).pack(side='left',padx=(0,6))
        ttk.Label(shell,text='PSP Model Creator',font=('Segoe UI',19)).pack(anchor='w',pady=(12,2))
        ttk.Label(shell,text='Native PSP parts · Prepared model library · Separate from the converter').pack(anchor='w')
        self.project_label=tk.StringVar(value='Open the prepared library to start, or create a project from your own PACs.')
        ttk.Label(shell,textvariable=self.project_label,wraplength=950).pack(anchor='w',pady=8)
        work=ttk.Frame(shell);work.pack(fill='both',expand=True)
        left=ttk.LabelFrame(work,text='Body parts',padding=12);left.pack(side='left',fill='y',padx=(0,12))
        self.choices={};self.controls=[]
        for part in PARTS:
            ttk.Label(left,text=part).pack(anchor='w',pady=(3,0));v=tk.StringVar();self.choices[part]=v
            box=ttk.Combobox(left,textvariable=v,state='readonly',width=25);box.pack(fill='x');box.bind('<<ComboboxSelected>>',lambda _:self.dirty());self.controls.append(box)
        self.waist_y=tk.DoubleVar(value=DEFAULT_WAIST)
        self.show_waist=tk.BooleanVar(value=True)
        heading=ttk.Frame(left);heading.pack(fill='x',pady=(8,0))
        ttk.Label(heading,text='Torso cutoff').pack(side='left')
        self.waist_reset=ttk.Button(heading,text='Reset',width=6,command=self.reset_waist)
        self.waist_reset.pack(side='right')
        ends=ttk.Frame(left);ends.pack(fill='x')
        ttk.Label(ends,text='Higher').pack(side='left')
        ttk.Label(ends,text='Lower').pack(side='right')
        self.waist_slider=ttk.Scale(ends,from_=WAIST_RANGE[0],to=WAIST_RANGE[1],variable=self.waist_y,command=self.waist_changed)
        self.waist_slider.pack(side='left',fill='x',expand=True,padx=3)
        self.waist_guide_checkbox=ttk.Checkbutton(left,text='Show cut line (rest pose)',variable=self.show_waist,command=self.toggle_waist_guide)
        self.waist_guide_checkbox.pack(anchor='w',pady=(3,0))
        self.max_textures=tk.BooleanVar(value=False)
        self.max_texture_checkbox=ttk.Checkbutton(left,text='Maximum texture downgrade',variable=self.max_textures,command=self.dirty)
        self.max_texture_checkbox.pack(anchor='w',pady=(8,0))
        self.assemble_button=ttk.Button(left,text='Assemble and validate',command=self.assemble);self.assemble_button.pack(fill='x',pady=(8,4))
        donor_tools=ttk.Frame(left);donor_tools.pack(fill='x',pady=4)
        ttk.Button(donor_tools,text='Whole donor',command=self.whole_donor).pack(side='left',expand=True,fill='x')
        ttk.Button(donor_tools,text='Details',command=self.selection_details).pack(side='left',expand=True,fill='x',padx=(4,0))
        ttk.Label(left,text=f'{MAX_BYTES:,}-byte size target.\nOversized exports warn.\nTest exports in PPSSPP.',justify='left').pack(anchor='w',pady=8)
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
        self.export_buttons=[]
        for text,fn in (('Save PAC as…',self.export_pac),('Export preview folder…',self.export_preview),('Export editable textures…',self.export_edit),('Pack edited folder…',self.pack_edit),('QA report',self.report)):
            button=ttk.Button(export,text=text,command=fn);button.pack(side='left',padx=(0,6));self.export_buttons.append(button)
        self.progress=ttk.Progressbar(shell,mode='indeterminate');self.progress.pack(fill='x')
        self.status=tk.StringVar(value='Ready. Originals are copied into a private project and never overwritten.')
        status_label=ttk.Label(shell,textvariable=self.status,wraplength=900)
        # Reserve controls/status BEFORE the expandable preview gets remaining
        # space. Otherwise Tk can shrink late-packed buttons to unlabeled slivers.
        work.pack_forget();export.pack_forget();self.progress.pack_forget()
        status_label.pack(side='bottom',fill='x',pady=6)
        self.progress.pack(side='bottom',fill='x')
        export.pack(side='bottom',fill='x',pady=8)
        work.pack(fill='both',expand=True)
        root.after(75,self.poll)
        if '--smoke-test' not in sys.argv:
            from .library import bundled_root
            if (bundled_root()/'catalog.json').is_file():root.after(150,self.open_library)

    def task(self,fn,done):
        if self.busy:return
        self.busy=True;self.progress.start(12);self.assemble_button.state(['disabled'])
        def worker():
            try:self.events.put(('done',done,fn()))
            except Exception:self.events.put(('error',traceback.format_exc()))
        threading.Thread(target=worker,daemon=True).start()

    def waist_changed(self,*_):
        self.dirty()

    def reset_waist(self):
        self.waist_y.set(DEFAULT_WAIST);self.dirty()

    def toggle_waist_guide(self):
        if self.model is None:self.dirty()
        else:self.refresh()

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
                    self.last_error=event[1]
                    if '--smoke-test' not in sys.argv:messagebox.showerror('Creator stopped',event[1].splitlines()[-1]+'\n\nFull log: '+str(log),parent=self.root)
                else:
                    try:event[1](event[2])
                    except Exception:messagebox.showerror('Creator',traceback.format_exc(),parent=self.root)
        except queue.Empty:pass
        self.root.after(75,self.poll)

    def require_idle(self):
        if self.busy:self.status.set('Please wait for the current operation.');return False
        return True

    def open_library(self):
        if not self.require_idle():return
        self.reload_library()

    def reload_library(self, root=None, preserve=False):
        from .library import Library
        try:
            choices=self.selected() if preserve and self.library is not None else dict.fromkeys(PARTS,0)
            if not preserve:self.waist_y.set(DEFAULT_WAIST)
            self.library=Library(root);self.library_project=True;self.project=None;self.green.set(False)
            self.labels=[f'{i+1}. {e["label"]}' for i,e in enumerate(self.library.entries)]
            for part,box in zip(PARTS,self.controls):box['values']=self.labels;self.choices[part].set(self.labels[choices[part]])
            self.result=None;self.model=None;self.textures=None
            self.project_label.set(f'{len(self.labels)} native donors. No PAC import needed. Rig, seam and structural checks stay mandatory; exceeding the {MAX_BYTES:,}-byte size target gives a warning.')
            self.dirty()
        except Exception as exc:messagebox.showerror('Prepared library',str(exc),parent=self.root)

    def add_donors(self):
        if not self.require_idle():return
        paths=filedialog.askopenfilenames(title='Add native PSP PAC donors (select one or several)',filetypes=[('PSP PAC','*.pac *.PAC')])
        if paths:self.import_donors(paths)

    def import_donors(self, paths):
        """Also callable by the frozen overlay self-check without file dialogs."""
        from .library import add_donors, bundled_root
        root=self.library.root if self.library is not None else bundled_root()
        def work():return add_donors(paths,root,progress=lambda text:self.events.put(('status',text)))
        def done(report):
            self.last_import_report=report
            self.reload_library(root,preserve=self.library is not None)
            summary=f'{len(report["added"])} donor(s) added; {len(report["duplicates"])} already present; {len(report["rejected"])} rejected.'
            self.status.set(summary)
            log=Path(tempfile.gettempdir())/'psp-model-creator-donor-import.json';dump(log,report)
            if '--smoke-test' not in sys.argv:
                reasons='\n'.join(Path(row['file']).name+': '+row['reason'] for row in report['rejected'])
                messagebox.showinfo('Donor import',summary+('\n\n'+reasons if reasons else '')+'\n\nReport: '+str(log),parent=self.root)
        self.task(work,done)

    def whole_donor(self):
        if not self.require_idle() or not hasattr(self,'labels'):return
        label=self.choices['Head'].get()
        for v in self.choices.values():v.set(label)
        self.dirty()

    def selection_details(self):
        if not hasattr(self,'labels'):return
        sources,choices=self.current_sources();lines=[]
        for part in PARTS:
            s=sources[choices[part]];r=s['model']['report']
            lines.append(f'{part}: {s["label"]}\n{len(s["data"]):,} native PAC bytes; {r["vertices"]:,} vertices / {r["triangles"]:,} triangles; {r["meshes"]} meshes / {len(s["model"]["bones"])} bones.\nSHA-256: {s["sha256"]}\n')
        messagebox.showinfo('Native donor details','\n'.join(lines)+f'\nOriginal PAC size is not the size of a mixed assembly. The size target is {MAX_BYTES:,} bytes; oversized exports give a warning.',parent=self.root)

    def current_sources(self):
        if self.library_project and self.library is not None:return self.library.selection(self.selected())
        if self.library_project:
            from .library import read_project as reader
        else:reader=read_project
        _,sources=reader(self.project)
        return sources,self.selected()

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
        if path:self.load(path)

    def load(self,path):
        metadata=json.loads(Path(path).read_text(encoding='utf-8'))
        self.library_project=metadata.get('schema')=='psp-model-creator.library-project/1';self.library=None
        if self.library_project:
            from .library import read_project as reader
        else:reader=read_project
        project,sources=reader(path);self.project=Path(path);self.labels=[s['label'] for s in sources]
        self.max_textures.set(project.get('maximum_textures') is True)
        self.waist_y.set(project['waist_y'])
        # Include source numbers so even identical filenames are distinguishable.
        self.labels=[f'{i+1}. {label}' for i,label in enumerate(self.labels)]
        for part,box in zip(PARTS,self.controls):box['values']=self.labels;self.choices[part].set(self.labels[project['selections'][part]])
        self.project_label.set(str(self.project));self.result=None;self.model=None;self.textures=None
        self.status.set('Project loaded. Preparing selection preview…');self.picture.configure(image='',text='Preparing preview…');self.picture.image=None
        self.dirty()

    def selected(self):return {p:self.labels.index(self.choices[p].get()) for p in PARTS}

    def dirty(self):
        self.preview_revision+=1
        self.model=None;self.textures=None
        self.picture.configure(image='',text='Preparing current selection…');self.picture.image=None
        self.status.set('Updating selection preview. Assemble and validate before exporting this combination.')
        if self.preview_after is not None:self.root.after_cancel(self.preview_after)
        self.preview_after=self.root.after(300,self.live_preview)

    def live_preview(self):
        self.preview_after=None
        if not self.project and not self.library_project:return
        if self.busy:
            self.preview_after=self.root.after(150,self.live_preview);return
        revision=self.preview_revision;library_mode=self.library_project
        choices=self.selected();library=self.library;path=self.project
        view,pose,green=self.view,self.pose.get(),self.green.get()
        waist_y=float(self.waist_y.get());guide=waist_y if self.show_waist.get() else None
        def work():
            if library_mode and library is not None:sources,selections=library.selection(choices)
            else:
                if library_mode:
                    from .library import read_project as project_reader
                else:project_reader=read_project
                _,sources=project_reader(path);selections=choices
            raw,textures,_=assemble(sources,selections,library=library_mode,waist_y=waist_y)
            if library_mode:
                from .native import audit_yobj as reader
            else:reader=audit_yobj
            model=reader(raw)
            return model,textures,preview(model,textures,view,self.preview_size,pose,green,waist_guide=guide)
        def done(result):
            if revision!=self.preview_revision:return
            self.model,self.textures,image=result;photo=ImageTk.PhotoImage(image)
            self.picture.configure(image=photo,text='');self.picture.image=photo
            self.status.set('Current selections previewed. Assemble and validate to check native structure, poses and actual PAC size.')
        self.task(work,done)

    def save(self):
        if not self.require_idle():return
        if self.library_project:
            parent=filedialog.askdirectory(title='Save a NEW library project folder')
            if parent:
                from .library import create_project as snapshot
                sources,selections=self.current_sources();path=snapshot(sources,selections,Path(parent)/('Creator-project-'+uuid.uuid4().hex[:8]))
                data=json.loads(path.read_text(encoding='utf-8'));data['maximum_textures']=self.max_textures.get();data['waist_y']=float(self.waist_y.get());dump(path,data)
                self.status.set('Saved independent snapshots and recipe: '+str(path))
            return
        if not self.project:return
        try:
            project,_=read_project(self.project);project['selections']=self.selected();project['maximum_textures']=self.max_textures.get()
            project['waist_y']=float(self.waist_y.get())
            history=self.project.parent/'history';history.mkdir(exist_ok=True)
            shutil.copy2(self.project,history/(uuid.uuid4().hex+'.json'))
            temp=self.project.with_suffix('.new');dump(temp,project);temp.replace(self.project)
            self.status.set('Choices saved; previous recipe preserved in history.')
        except Exception:messagebox.showerror('Save choices',traceback.format_exc(),parent=self.root)

    def assemble(self):
        if not self.require_idle():return
        if not self.project and not self.library_project:messagebox.showinfo('Creator','Open the prepared library or a project first.',parent=self.root);return
        if self.preview_after is not None:self.root.after_cancel(self.preview_after);self.preview_after=None
        self.preview_revision+=1
        original_selections=self.selected();sources,selections=self.current_sources();library_mode=self.library_project;maximum_textures=self.max_textures.get()
        if library_mode:
            from .library import create_project as snapshot
            parent=Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'PSP Model Creator'/'jobs'/uuid.uuid4().hex
            project=snapshot(sources,selections,parent);output=parent/'build'
            metadata=json.loads(project.read_text(encoding='utf-8'));metadata['maximum_textures']=maximum_textures;metadata['waist_y']=float(self.waist_y.get());dump(project,metadata)
        else:
            self.save();project=self.project;output=self.project.parent/'builds'/uuid.uuid4().hex
        def work():
            report=build(project,selections,output,library=library_mode,allow_oversize=True,maximum_textures=maximum_textures,progress=lambda msg:self.events.put(('status',msg)))
            report['ui_selections']=original_selections
            source=load_source(output/'created-model.pac',library=library_mode)
            return output,report,source
        def done(result):
            self.result,self.last_report,source=result;self.model=source['model'];self.textures={n:source['textures'][n.casefold()] for n in self.model['texture_names']}
            self.status.set(f'Experimental build: {self.last_report["pac_bytes"]:,} / {MAX_BYTES:,} bytes. Native checks passed; review seams and test in PPSSPP.')
            if self.last_report.get('budget_warning'):
                warning=self.last_report['budget_warning']
                self.status.set(f'OVER BUDGET: {warning["pac_bytes"]:,} bytes; {warning["over_by_bytes"]:,} above {warning["target_bytes"]:,}. Export is available; in-game stability is unverified.')
                messagebox.showwarning('PAC exceeds size target',
                    f'This model is {warning["pac_bytes"]:,} bytes — {warning["over_by_bytes"]:,} over the {warning["target_bytes"]:,}-byte target.\n\n'
                    'You can still export it. Oversized PACs may cause crashes or unrelated geometry corruption in-game.\n\n'
                    'Native structural and rigging checks passed. Geometry was preserved. '+
                    ('Texture-only fitting was attempted; see the QA report.' if maximum_textures else 'Texture downgrade was not enabled.'),parent=self.root)
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
        guide=float(self.waist_y.get()) if self.show_waist.get() else None
        def done(image):
            photo=ImageTk.PhotoImage(image);self.picture.configure(image=photo,text='');self.picture.image=photo
        self.task(lambda:preview(model,textures,view,self.preview_size,pose,green,waist_guide=guide),done)

    def set_view(self,view):
        if not self.require_idle():return
        self.view=view;self.refresh()

    def require_result(self):
        if not self.require_idle():return False
        if self.result is None:messagebox.showinfo('Creator','Assemble a model first.',parent=self.root);return False
        if self.last_report.get('ui_selections',self.last_report['selections'])!=self.selected():
            messagebox.showinfo('Selections changed','The preview uses your current choices. Assemble and validate this combination before exporting it. Your previous build is preserved.',parent=self.root);return False
        if bool(self.last_report.get('maximum_texture_downgrade'))!=self.max_textures.get():
            messagebox.showinfo('Texture option changed','Assemble and validate with the current texture option before exporting. The previous build is preserved.',parent=self.root);return False
        if abs(self.last_report.get('waist_y',DEFAULT_WAIST)-float(self.waist_y.get()))>1e-7:
            messagebox.showinfo('Torso cutoff changed','Assemble and validate with the current torso cutoff before exporting. The previous build is preserved.',parent=self.root);return False
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
                root=Path(temp)/'inspection';inspect_workspace(result/'created-model.pac',root,resolution=128,native_descriptor_arrays=self.library_project)
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
        if self.library_project:
            messagebox.showinfo('Prepared library',
                'Select any prepared donor for each part. Selections preview automatically.\n'
                'Assemble and validate before export. Whole-source models retain their original bytes.\n'
                'Mixed builds preserve textures and interior geometry; only attachment seams are stitched.\n'
                'Different body binds, unsafe seams and controller regressions block export. Oversized PACs give a warning and can be exported.\n'
                'Native bind branches follow the selected parts, including the head neck pivot. Source-pose checks remain mandatory.\n'
                'Maximum texture downgrade tries to fit oversized models using textures only; an already fitting model keeps its textures.\n'
                'Hair follows the selected head. Torso supplies the output container; other donor auxiliary PACs are not transferred.\n'
                'Analytical poses are not in-game tests. Review all sides and test in PPSSPP.',parent=self.root)
            return
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
