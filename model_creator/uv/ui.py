"""Integrated UV canvas and controls; shared Creator preview, no extra runtime."""
import math
import tkinter as tk
from tkinter import ttk,filedialog,messagebox

import numpy as np
from PIL import Image,ImageTk

from .document import Document,REGIONS,signature


class Panel:
    def __init__(self,app,page,workspace):
        self.app=app;self.root=app.root;self.doc=None;self.pending=None;self.context=None;self.sessions={}
        self.preview_after=None;self.gesture=None;self.mapping=None;self.zoom=1.;self.pan=np.zeros(2)
        self.active=False;self.workspace=workspace
        scroll=ttk.Scrollbar(page,orient='vertical');scroll.pack(side='right',fill='y')
        toolbox=tk.Canvas(page,width=290,height=1,highlightthickness=0,yscrollcommand=scroll.set)
        toolbox.pack(fill='both',expand=True);scroll.configure(command=toolbox.yview)
        contents=ttk.Frame(toolbox);window=toolbox.create_window(0,0,window=contents,anchor='nw')
        contents.bind('<Configure>',lambda _:toolbox.configure(scrollregion=toolbox.bbox('all')))
        toolbox.bind('<Configure>',lambda e:toolbox.itemconfigure(window,width=e.width))
        page=contents
        self.info=tk.StringVar(value='Load a donor or assembled selection. UV edits preserve the mesh and rig.')
        ttk.Label(page,textvariable=self.info,wraplength=235).pack(fill='x',pady=(0,6))
        self.texture=tk.StringVar();self.texture_box=ttk.Combobox(page,textvariable=self.texture,state='readonly',width=24)
        ttk.Label(page,text='Active texture').pack(anchor='w');self.texture_box.pack(fill='x');self.texture_box.bind('<<ComboboxSelected>>',self.filter_changed)
        self.region=tk.StringVar(value='All');ttk.Label(page,text='Body region (approximate)').pack(anchor='w',pady=(6,0))
        box=ttk.Combobox(page,textvariable=self.region,values=REGIONS,state='readonly',width=24);box.pack(fill='x');box.bind('<<ComboboxSelected>>',self.filter_changed)
        self.isolate=tk.BooleanVar(value=False);ttk.Checkbutton(page,text='Isolate region in 3D',variable=self.isolate,command=self.changed).pack(anchor='w',pady=3)
        self.mode=tk.StringVar(value='Select')
        row=ttk.Frame(page);row.pack(fill='x')
        for name in ('Select','Move','Scale','Rotate'):ttk.Radiobutton(row,text=name,value=name,variable=self.mode).pack(side='left')
        row=ttk.Frame(page);row.pack(fill='x',pady=4)
        for label,fn in (('Select region',self.select_all),('Clear',self.clear),('Fit',self.fit)):
            ttk.Button(row,text=label,command=fn).pack(side='left',expand=True,fill='x')
        self.inputs={}
        for label,fields,defaults in (('Move UV',('U','V'),('0','0')),('Scale',('X','Y'),('1','1')),('Rotate °',('Angle',),('0',))):
            row=ttk.Frame(page);row.pack(fill='x',pady=1);ttk.Label(row,text=label,width=9).pack(side='left')
            for field,value in zip(fields,defaults):
                var=tk.StringVar(value=value);self.inputs[(label,field)]=var
                ttk.Entry(row,textvariable=var,width=5).pack(side='left',expand=True,fill='x',padx=1)
            ttk.Button(row,text='Apply',width=6,command=lambda n=label:self.numeric(n)).pack(side='right')
        row=ttk.Frame(page);row.pack(fill='x',pady=3)
        for label,axis in (('Mirror U','U'),('Mirror V','V')):ttk.Button(row,text=label,command=lambda a=axis:self.transform(flip=a)).pack(side='left',expand=True,fill='x')
        row=ttk.Frame(page);row.pack(fill='x')
        for label,fn in (('Undo',lambda:self.undo()),('Redo',lambda:self.undo(True)),('Reset selected',lambda:self.reset(True))):ttk.Button(row,text=label,command=fn).pack(side='left',expand=True,fill='x')
        ttk.Button(page,text='Reset all UVs and textures',command=self.reset).pack(fill='x',pady=3)
        ttk.Button(page,text='Load texture PNG…',command=self.import_texture).pack(fill='x')
        self.distortion=tk.BooleanVar(value=False);ttk.Checkbutton(page,text='Show UV area distortion',variable=self.distortion,command=self.draw).pack(anchor='w',pady=3)
        self.original=tk.BooleanVar(value=False);ttk.Checkbutton(page,text='Compare original UVs / texture',variable=self.original,command=self.changed).pack(anchor='w')
        ttk.Label(page,text='Click island · Shift adds/removes\nDrag empty space for box selection\nDrag with Move / Scale / Rotate\nWheel zoom · Middle drag pans\nBlue: denser / red: stretched\nPurple: flipped / collapsed UV\nMirroring changes UVs, not geometry.',wraplength=235).pack(fill='x',pady=4)
        self.canvas=tk.Canvas(workspace,background='#25282d',highlightthickness=0,width=320,height=350)
        self.canvas.pack(fill='both',expand=True)
        self.caption=tk.StringVar(value='UV editor');ttk.Label(workspace,textvariable=self.caption,wraplength=330).pack(fill='x')
        for event,handler in (('<Configure>',lambda _:self.draw()),('<ButtonPress-1>',self.press),('<B1-Motion>',self.drag),('<ButtonRelease-1>',self.release),('<MouseWheel>',self.wheel),('<Button-4>',self.wheel),('<Button-5>',self.wheel),('<ButtonPress-2>',self.pan_start),('<B2-Motion>',self.pan_drag)):
            self.canvas.bind(event,handler)
        self.canvas.bind('<Control-z>',lambda _:self.undo());self.canvas.bind('<Control-y>',lambda _:self.undo(True))
        self.canvas.bind('<Escape>',self.cancel)
        def scroll_tools(event):
            toolbox.yview_scroll(-1 if getattr(event,'num',0)==4 or getattr(event,'delta',0)>0 else 1,'units');return 'break'
        def bind_tools(widget):
            for event in ('<MouseWheel>','<Button-4>','<Button-5>'):widget.bind(event,scroll_tools)
            for child in widget.winfo_children():bind_tools(child)
        bind_tools(contents)

    def key(self):return (tuple(v.get() for v in self.app.choices.values()),round(float(self.app.waist_y.get()),7))
    def ready(self):return self.doc is not None and self.context==self.key() and self.app.model is not None

    def loading(self,recipe=None):
        self.finish();self.doc=None;self.context=None;self.pending=recipe;self.sessions={};self.texture.set('');self.original.set(False);self.fit()

    def baseline(self,raw,textures):
        self.finish();key=self.key();self.context=key
        if key not in self.sessions or self.sessions[key].raw!=raw or self.sessions[key].original_textures!=textures:self.sessions[key]=Document(raw,textures)
        while len(self.sessions)>8:self.sessions.pop(next(iter(self.sessions)))
        self.doc=self.sessions[key]
        if self.pending:self.doc.restore(self.pending);self.pending=None
        names=self.doc.baseline['texture_names'];self.texture_box['values']=names
        if self.texture.get() not in names:self.texture.set(names[0])
        self.info.set('UV islands on the native mesh. Select a region, adjust its placement, then Assemble and validate.')
        self.fit()

    def tab_changed(self):
        self.active=self.app.sidebar.index(self.app.sidebar.select())==2
        if self.active:
            self.workspace.pack(side='left',fill='both',expand=True,before=self.app.picture,padx=(0,6))
            self.app.green.set(False);self.app.show_waist.set(False);self.saved_preview_size=self.app.preview_size;self.app.preview_size=min(288,self.app.preview_size);self.draw()
        else:
            self.workspace.pack_forget()
            if hasattr(self,'saved_preview_size'):self.app.preview_size=self.saved_preview_size
        self.changed()

    def texture_id(self):
        return self.doc.baseline['texture_names'].index(self.texture.get())
    def visible(self):return self.doc.visible_faces(self.texture_id(),self.region.get()) if self.ready() else []

    def filter_changed(self,*_):
        self.finish()
        if self.doc:self.doc.selection.clear()
        self.fit();self.changed()
    def fit(self):self.zoom=1.;self.pan=np.zeros(2);self.draw()
    def select_all(self):
        if self.ready():self.doc.selection=self.doc.vertices(self.visible());self.draw()
    def clear(self):
        if self.doc:self.doc.selection.clear();self.draw()

    def coordinates(self,uv):
        origin,size=self.mapping;return np.asarray(uv)*size+origin
    def uv_at(self,x,y):
        origin,size=self.mapping;return (np.array([x,y])-origin)/size

    def draw(self):
        c=self.canvas;c.delete('all');self.photo=None
        if not self.ready():c.create_text(15,25,anchor='nw',fill='white',text='Load a model to edit its UVs.');return
        doc=self.doc;visible=self.visible();name=self.texture.get()
        from desktop.texture_optimizer.candidates import read_gim
        textures=doc.original_textures if self.original.get() else doc.textures
        indices,colors=read_gim(textures[name]);image=Image.fromarray(colors[indices]);tw,th=image.size
        uv=doc.original if self.original.get() else doc.uv
        used=doc.vertices(visible);p=uv[sorted(used)] if used else np.array([[0,0],[1,1]])
        lo=np.minimum(p.min(0),[0,0]);hi=np.maximum(p.max(0),[1,1]);extent=np.maximum(hi-lo,1e-6)
        width=max(100,c.winfo_width());height=max(100,c.winfo_height())
        factor=min((width-32)/(extent[0]*tw),(height-32)/(extent[1]*th))*self.zoom
        size=np.array([tw,th])*factor;origin=(np.array([width,height])-extent*size)/2-lo*size+self.pan
        if self.gesture and 'mapping' in self.gesture:origin,size=self.gesture['mapping']
        self.mapping=(origin,size)
        # Draw native repeating tiles around authored UV coordinates. Large
        # authored repeats retain their coordinates without allocating huge art.
        iw,ih=max(1,int(size[0])),max(1,int(size[1]))
        if max(iw,ih)<=4096:
            bg=Image.new('RGBA',image.size,(90,90,90,255));bg.alpha_composite(image.convert('RGBA'))
            self.photo=ImageTk.PhotoImage(bg.resize((iw,ih),Image.Resampling.NEAREST))
            xs=range(max(-8,int(math.floor(-origin[0]/size[0]))),min(9,int(math.ceil((width-origin[0])/size[0]))))
            ys=range(max(-8,int(math.floor(-origin[1]/size[1]))),min(9,int(math.ceil((height-origin[1])/size[1]))))
            for u in xs:
                for v in ys:
                    q=origin+np.array([u,v])*size;c.create_image(*q,image=self.photo,anchor='nw')
        c.create_rectangle(*origin,*(origin+size),outline='#f5f5f5',width=2)
        stretch,flipped=doc.distortion(self.display_geometry(),uv=uv) if self.distortion.get() else (None,None)
        for fi in visible:
            tri=doc.faces[fi];xy=self.coordinates(uv[tri]);selected=any(int(i) in doc.selection for i in tri)
            color='#ffff63' if selected else '#6ff7e1'
            if stretch is not None:
                value=stretch[fi]
                color='#d66bff' if flipped[fi] or not np.isfinite(value) else '#ff5c4d' if value<-1 else '#5c9dff' if value>1 else '#65e795'
                c.create_polygon(*xy.reshape(-1),fill=color,stipple='gray50',outline='')
                if selected:color='#ffff63'
            c.create_line(*np.vstack((xy,xy[0])).reshape(-1),fill=color,width=2 if selected else 1)
        if len(doc.selection)<=1200:
            for q in self.coordinates(uv[sorted(doc.selection)]):c.create_oval(q[0]-2,q[1]-2,q[0]+2,q[1]+2,fill='#ffff63',outline='')
        selected=len(doc.selection);islands=len({doc.face_island[f] for f in visible})
        self.caption.set(f'{tw} × {th} · {len(visible)} faces · {islands} islands · {selected} selected records. V increases downward; textures repeat outside 0–1.')
        # A native vertex can be shared by neighbouring regions or materials.
        if selected:
            visible_set=set(visible);outside=any(f not in visible_set and any(int(i) in doc.selection for i in tri) for f,tri in enumerate(doc.faces))
            if outside:self.caption.set(self.caption.get()+' Selection also affects shared vertices outside this filter.')

    def display_geometry(self):
        return self.app.morph_ui.preview_job(self.doc.baseline)()

    def hit(self,x,y):
        if not self.mapping:return None
        point=np.array([x,y]);uv=self.doc.original if self.original.get() else self.doc.uv
        for fi in reversed(self.visible()):
            tri=self.coordinates(uv[self.doc.faces[fi]]);a,b,c=tri;matrix=np.column_stack((b-a,c-a))
            if abs(np.linalg.det(matrix))<1e-8:continue
            u,v=np.linalg.solve(matrix,point-a)
            if u>=-.015 and v>=-.015 and u+v<=1.015:return fi
        return None

    def press(self,event):
        if not self.ready() or self.original.get():return
        self.canvas.focus_set();self.finish();hit=self.hit(event.x,event.y);add=bool(event.state&1)
        if self.mode.get()=='Select':
            if hit is not None:self.doc.select_island(hit,self.visible(),add=add,toggle=add);self.draw();return
            if not add:self.doc.selection.clear()
            self.gesture=dict(kind='box',start=np.array([event.x,event.y]),add=add);return
        if hit is not None and not any(int(i) in self.doc.selection for i in self.doc.faces[hit]):self.doc.select_island(hit,self.visible(),add=add)
        if not self.doc.selection:return
        self.gesture=dict(kind=self.mode.get(),start=np.array([event.x,event.y]),state=self.doc.state(),uv=self.doc.uv.copy(),mapping=(self.mapping[0].copy(),self.mapping[1].copy()))
        self.draw()

    def drag(self,event):
        if not self.gesture:return
        g=self.gesture;point=np.array([event.x,event.y]);start=g['start']
        if g['kind']=='box':
            self.canvas.delete('selection-box');self.canvas.create_rectangle(*start,*point,outline='yellow',dash=(4,2),tags='selection-box');return
        # Hold canvas projection fixed throughout a transform; otherwise fitting
        # changes under the pointer and produces cumulative movement.
        self.mapping=g['mapping'];delta=point-start
        try:
            if g['kind']=='Move':self.doc.transform(move=delta/self.mapping[1],history=False,baseline=g['uv'])
            elif g['kind']=='Scale':self.doc.transform(scale=(math.exp(np.clip(delta[0]/120,-4,4)),)*2,history=False,baseline=g['uv'])
            else:self.doc.transform(degrees=float(delta[0])*.5,history=False,baseline=g['uv'])
            self.changed()
        except ValueError as exc:self.app.status.set(str(exc))

    def release(self,event):
        if not self.gesture:return
        g=self.gesture
        if g['kind']=='box':
            a=np.minimum(g['start'],[event.x,event.y]);b=np.maximum(g['start'],[event.x,event.y]);ids=self.doc.vertices(self.visible())
            self.doc.selection|={i for i in ids if np.all(self.coordinates(self.doc.uv[i])>=a)&np.all(self.coordinates(self.doc.uv[i])<=b)}
        self.finish();self.draw()

    def finish(self):
        if self.gesture and 'state' in self.gesture:
            old=self.gesture['state']
            if not np.array_equal(old[0],self.doc.uv):self.doc.remember(old)
        self.gesture=None

    def cancel(self,*_):
        if self.gesture and 'state' in self.gesture:self.doc.uv,self.doc.textures=self.gesture['state']
        self.gesture=None;self.changed()

    def pan_start(self,event):self.pan_gesture=(np.array([event.x,event.y]),self.pan.copy())
    def pan_drag(self,event):
        start,pan=self.pan_gesture;self.pan=pan+np.array([event.x,event.y])-start;self.draw()
    def wheel(self,event):
        self.zoom=float(np.clip(self.zoom*(1.2 if getattr(event,'num',0)==4 or getattr(event,'delta',0)>0 else 1/1.2),.2,12));self.draw()

    def numeric(self,label):
        try:
            values=[float(v.get()) for (n,_),v in self.inputs.items() if n==label]
            self.transform(**({'move':values} if label=='Move UV' else {'scale':values} if label=='Scale' else {'degrees':values[0]}))
        except ValueError as exc:messagebox.showerror('UV transform',str(exc),parent=self.root)
    def transform(self,**kwargs):
        if not self.ready() or self.original.get():return
        self.finish()
        try:self.doc.transform(**kwargs);self.changed()
        except ValueError as exc:messagebox.showerror('UV transform',str(exc),parent=self.root)
    def undo(self,redo=False):
        self.finish()
        if self.ready() and self.doc.undo(redo):self.changed()
    def reset(self,selection=False):
        self.finish();self.pending=None
        if self.ready():self.doc.reset(selection);self.original.set(False);self.changed()
    def import_texture(self):
        if not self.ready() or not self.app.require_idle():return
        path=filedialog.askopenfilename(title='Load matching-size PNG (original alpha must be preserved)',filetypes=[('Texture PNG','*.png')])
        if not path:return
        try:
            with Image.open(path) as image:proof=self.doc.import_texture(self.texture.get(),image)
            self.original.set(False);self.changed();self.app.status.set(f'Texture loaded with native PSP palette colors; RGB error {proof["rgb_rmse"]:.2f}. Dimensions and original alpha preserved.')
        except Exception as exc:messagebox.showerror('Texture import',str(exc),parent=self.root)

    def changed(self):
        self.draw()
        if self.app.model is None:return
        self.app.preview_revision+=1
        if self.preview_after:self.root.after_cancel(self.preview_after)
        self.preview_after=self.root.after(80,self.show)
    def show(self):self.preview_after=None;self.app.refresh()
    def recipe(self):
        self.finish()
        if self.pending:return self.pending
        return self.doc.recipe() if self.ready() else None
    def preview_job(self,model_job,textures):
        if not self.ready():return model_job,textures
        doc=self.doc;uv=(doc.original if self.original.get() else doc.uv).copy()
        maps=dict(doc.original_textures if self.original.get() else doc.textures)
        if not self.original.get() and getattr(self.app,'showing_build',False):
            recipe=doc.recipe();expected=self.app.last_report.get('uv',{}).get('signature')
            if expected==(signature(recipe) if recipe else None):maps=dict(textures)
        isolate=self.active and self.isolate.get();tid=self.texture_id();region=self.region.get()
        return lambda:doc.model(model_job(),uv,texture=tid,region=region,isolate=isolate),maps
    def matches(self,report):
        recipe=self.recipe();return report.get('uv',{}).get('signature')==(signature(recipe) if recipe else None)
