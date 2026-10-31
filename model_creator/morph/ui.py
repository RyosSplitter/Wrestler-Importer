"""Morph Studio controls integrated into the Creator sidebar and preview."""
import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox

from desktop.blender_runtime import resolve
from .document import Document,signature
from .deform import CONTROLS,active,parameters


class Panel:
    def __init__(self,app,page):
        self.app=app;self.root=app.root;self.doc=None;self.context=None;self.sessions={};self.pending=None
        scroll=ttk.Scrollbar(page,orient='vertical');scroll.pack(side='right',fill='y')
        self.canvas=tk.Canvas(page,width=245,height=1,highlightthickness=0,yscrollcommand=scroll.set)
        self.canvas.pack(fill='both',expand=True);scroll.configure(command=self.canvas.yview)
        contents=ttk.Frame(self.canvas);window=self.canvas.create_window(0,0,window=contents,anchor='nw')
        contents.bind('<Configure>',lambda _:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(window,width=e.width))
        page=contents
        self.syncing=False;self.gesture=None;self.history_after=None;self.preview_after=None
        self.runtime_file=Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'PSP Model Creator'/'morph-runtime.json'
        try:self.runtime=json.loads(self.runtime_file.read_text(encoding='utf-8')).get('path')
        except (OSError,ValueError):self.runtime=None
        self.info=tk.StringVar(value='Choose Whole donor on Body parts. Body morphs keep the native rig and topology.')
        ttk.Label(page,textvariable=self.info,wraplength=230).pack(fill='x',pady=(0,5))
        self.variables={};self.scales=[];self.labels={}
        for name,(label,maximum) in CONTROLS.items():
            row=ttk.Frame(page);row.pack(fill='x')
            ttk.Label(row,text=label).pack(side='left')
            self.labels[name]=tk.StringVar(value='0%');ttk.Label(row,textvariable=self.labels[name]).pack(side='right')
            ttk.Button(row,text='Reset',width=5,command=lambda n=name:self.reset_one(n)).pack(side='right',padx=2)
            variable=tk.DoubleVar(value=0);self.variables[name]=variable
            scale=ttk.Scale(page,from_=-1,to=1,variable=variable,command=lambda _,n=name:self.changed(n))
            scale.pack(fill='x',pady=(0,2));scale.state(['disabled']);self.scales.append(scale)
            scale.bind('<ButtonRelease-1>',lambda _:self.finish_gesture())
        actions=ttk.Frame(page);actions.pack(fill='x',pady=3)
        for text,command in (('Undo',lambda:self.undo()),('Redo',lambda:self.undo(True)),('Reset all',self.reset)):
            ttk.Button(actions,text=text,width=8,command=command).pack(side='left',padx=(0,2))
        self.original=tk.BooleanVar(value=False)
        ttk.Checkbutton(page,text='Compare original',variable=self.original,command=self.request_preview).pack(anchor='w')
        ttk.Button(page,text='Choose existing Blender runtime…',command=self.choose_runtime).pack(fill='x',pady=4)
        self.runtime_label=tk.StringVar();ttk.Label(page,textvariable=self.runtime_label,wraplength=230).pack(fill='x')
        ttk.Label(page,text='Body shape only. Joint positions stay fixed.\nLength and face controls are later phases.',wraplength=230).pack(fill='x',pady=5)
        self.update_runtime()
        def wheel(event):
            self.canvas.yview_scroll(-1 if getattr(event,'num',0)==4 or getattr(event,'delta',0)>0 else 1,'units');return 'break'
        def bind_wheel(widget):
            widget.bind('<MouseWheel>',wheel);widget.bind('<Button-4>',wheel);widget.bind('<Button-5>',wheel)
            for child in widget.winfo_children():bind_wheel(child)
        bind_wheel(contents)

    def key(self):
        return (tuple(self.app.choices[p].get() for p in self.app.choices),round(float(self.app.waist_y.get()),7))

    def update_runtime(self):
        try:self.runtime_label.set('Runtime found: '+resolve(self.runtime).name);return True
        except ValueError:self.runtime_label.set('Blender 4.3.2 required for morph export. Select the Suite runtime.');return False

    def choose_runtime(self):
        if self.app.busy:return
        path=filedialog.askopenfilename(title='Select existing Blender 4.3.2 executable',filetypes=[('Blender executable','blender.exe blender'),('All files','*')])
        if not path:return
        from desktop.blender_runtime import version
        def work():version(resolve(path));return path
        def done(value):
            self.runtime=value;self.runtime_file.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.runtime_file.with_suffix('.new');temporary.write_text(json.dumps(dict(path=value)),encoding='utf-8');temporary.replace(self.runtime_file)
            self.update_runtime();self.enable()
        self.app.task(work,done)

    def loading(self,recipe=None):
        self.finish_gesture();self.doc=None;self.context=None;self.sessions={};self.pending=recipe;self.sync()
        self.original.set(False)
        for scale in self.scales:scale.state(['disabled'])

    def baseline(self,raw,reason=None):
        key=self.key();self.finish_gesture();self.doc=None;self.context=key
        try:
            if reason:raise ValueError(reason)
            if key not in self.sessions or self.sessions[key].raw!=raw:self.sessions[key]=Document(raw)
            while len(self.sessions)>8:self.sessions.pop(next(iter(self.sessions)))
            self.doc=self.sessions[key]
            if self.pending:self.doc.restore(self.pending);self.pending=None
            self.info.set('Reversible body proportions. Assemble and validate before saving the PAC.')
        except ValueError as exc:
            self.info.set(str(exc))
            if self.pending:raise
        self.sync();self.enable()

    def enable(self):
        ready=self.doc is not None and self.context==self.key() and self.update_runtime()
        for scale in self.scales:scale.state(['!disabled'] if ready else ['disabled'])

    def values(self):return parameters({n:round(v.get(),4) for n,v in self.variables.items()})

    def sync(self):
        self.syncing=True
        values=self.doc.values if self.doc else parameters()
        for n,v in values.items():self.variables[n].set(v);self.labels[n].set(f'{v*CONTROLS[n][1]*100:+.1f}%')
        self.syncing=False

    def changed(self,name):
        if self.syncing or self.doc is None or self.context!=self.key():return
        if self.gesture is None:self.gesture=(self.doc,self.doc.values.copy())
        self.doc.set(self.values(),history=False)
        for n,v in self.doc.values.items():self.labels[n].set(f'{v*CONTROLS[n][1]*100:+.1f}%')
        if self.history_after:self.root.after_cancel(self.history_after)
        self.history_after=self.root.after(350,self.finish_gesture)
        self.request_preview()

    def finish_gesture(self):
        if self.history_after:self.root.after_cancel(self.history_after);self.history_after=None
        if self.gesture:
            doc,old=self.gesture
            if doc.values!=old:doc.undo_stack.append(old);doc.undo_stack=doc.undo_stack[-100:];doc.redo_stack=[]
            self.gesture=None

    def undo(self,redo=False):
        self.finish_gesture()
        if self.doc and self.context==self.key() and self.doc.undo(redo):self.sync();self.request_preview()

    def reset(self):
        self.finish_gesture()
        self.pending=None
        if self.doc:self.doc.set(parameters());self.original.set(False);self.sync();self.enable();self.request_preview()

    def reset_one(self,name):
        self.finish_gesture()
        if self.doc and self.context==self.key():
            values=self.doc.values.copy();values[name]=0.;self.doc.set(values);self.sync();self.request_preview()

    def request_preview(self):
        self.app.preview_revision+=1
        if self.preview_after:self.root.after_cancel(self.preview_after)
        self.preview_after=self.root.after(100,self.show)

    def show(self):self.preview_after=None;self.app.refresh()

    def recipe(self):
        self.finish_gesture()
        if self.pending:return self.pending
        if self.doc and self.context==self.key() and active(self.doc.values):return self.doc.recipe()
        return None

    def preview_job(self,fallback):
        if self.doc and self.context==self.key():
            document=self.doc;values=parameters() if self.original.get() else self.doc.values.copy()
            return lambda:document.model(values)
        return lambda:fallback

    def matches(self,report):
        expected=report.get('morph',{}).get('signature');recipe=self.recipe()
        return expected==(signature(recipe) if recipe else None)
