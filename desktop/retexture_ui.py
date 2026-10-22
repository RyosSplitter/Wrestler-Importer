"""Windows-style offline Retexture node; one reusable document, no converter edits."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

import numpy as np
from PIL import Image, ImageDraw, ImageTk

from desktop.preview import render
from desktop.retexture import Document, read_image, warp


class RetexturePanel:
    def __init__(self,shell,page):
        self.shell=shell;self.root=shell.root;self.page=page;self.doc=None
        self.texture_index=0;self.layer_index=-1;self.color=(220,30,35)
        self.photos=[];self.canvas_photo=self.model_photo=self.reference_photo=None
        self.closed=False;self.loading=False;self.active_stroke=None;self.preview_timer=None
        self.future=None;self.task_done=None;self.preview_pending=False;self.token=0;self.epoch=0
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='retexture')
        self.preview_frames=0;self.last_preview_revision=None
        self.tool=tk.StringVar(value='Brush');self.brush=tk.IntVar(value=4)
        self.zoom=tk.StringVar(value='Fit');self.uv=tk.BooleanVar(value=True)
        self.encoded=tk.BooleanVar(value=True);self.highlight=tk.BooleanVar(value=False)
        self.yaw=tk.DoubleVar(value=35);self.model_zoom=tk.DoubleVar(value=1)
        self.palette=tk.StringVar(value='Native');self.model_choice=tk.StringVar()
        self.message=tk.StringVar(value='Open a PSP PAC or choose Retexture under a model in the editor. All work stays offline.')
        self.info=tk.StringVar(value='Original texture alpha is locked. Export always preserves geometry, UVs and rigging.')
        toolbar=ttk.Frame(page,padding=(8,8,8,3));toolbar.pack(fill='x')
        for text,command in [('Open PAC…',self.open_pac),('Use editor PAC',self.use_current),
                             ('Open project…',self.open_project),('Save project…',self.save_project),
                             ('Check size',self.check_size),('Export PAC…',self.export_pac)]:
            ttk.Button(toolbar,text=text,command=command).pack(side='left',padx=(0,4))
        ttk.Label(page,textvariable=self.message,wraplength=1100,padding=(8,2,8,5)).pack(fill='x')
        panes=ttk.Panedwindow(page,orient='horizontal');panes.pack(fill='both',expand=True,padx=8,pady=(0,6))
        left=ttk.Frame(panes,width=180);middle=ttk.Frame(panes);right=ttk.Frame(panes,width=330)
        panes.add(left,weight=0);panes.add(middle,weight=3);panes.add(right,weight=2)
        self.panes=panes
        ttk.Label(left,text='Textures').pack(anchor='w')
        tframe=ttk.Frame(left);tframe.pack(fill='both',expand=True)
        self.textures=ttk.Treeview(tframe,show='tree',selectmode='browse',height=8)
        self.textures.column('#0',width=170,minwidth=110)
        scroll=ttk.Scrollbar(tframe,orient='vertical',command=self.textures.yview);self.textures.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.textures.pack(fill='both',expand=True)
        self.textures.bind('<<TreeviewSelect>>',self.select_texture)
        ttk.Label(left,text='Layers (topmost first)').pack(anchor='w',pady=(6,2))
        self.layers=tk.Listbox(left,height=6,exportselection=False)
        self.layers.pack(fill='x');self.layers.bind('<<ListboxSelect>>',self.select_layer)
        buttons=ttk.Frame(left);buttons.pack(fill='x',pady=3)
        for text,cmd in [('↑',lambda:self.layer_action('up')),('↓',lambda:self.layer_action('down')),
                         ('Show/hide',lambda:self.layer_action('visible')),('Delete',lambda:self.layer_action('delete'))]:
            ttk.Button(buttons,text=text,width=2 if len(text)==1 else 8,command=cmd).pack(side='left')
        ttk.Button(left,text='Import logo / pattern…',command=self.import_art).pack(fill='x',pady=2)
        ttk.Button(left,text='Layer opacity…',command=self.set_opacity).pack(fill='x',pady=2)
        transforms=ttk.Frame(left);transforms.pack(fill='x')
        for i,(text,cmd) in enumerate([('−15°',lambda:self.transform('rotate',-15)),('+15°',lambda:self.transform('rotate',15)),
                         ('Smaller',lambda:self.transform('scale',.9)),('Larger',lambda:self.transform('scale',1.1))]):
            ttk.Button(transforms,text=text,width=8,command=cmd).grid(row=i//2,column=i%2,sticky='ew')
        flips=ttk.Frame(left);flips.pack(fill='x',pady=2)
        ttk.Button(flips,text='Mirror ↔',command=lambda:self.transform('mirror',0)).pack(side='left',fill='x',expand=True)
        ttk.Button(flips,text='Flip ↕',command=lambda:self.transform('flip',0)).pack(side='left',fill='x',expand=True)
        tools=ttk.Frame(middle);tools.pack(fill='x')
        ttk.Label(tools,text='Tool').pack(side='left')
        ttk.Combobox(tools,textvariable=self.tool,values=('Brush','Erase','Picker','Select rectangle','Protect','Unprotect','Move layer','Warp corners'),state='readonly',width=16).pack(side='left',padx=3)
        self.color_button=tk.Button(tools,text='Color',bg='#dc1e23',fg='white',command=self.choose_color);self.color_button.pack(side='left',padx=3)
        ttk.Label(tools,text='Radius').pack(side='left')
        ttk.Spinbox(tools,from_=1,to=128,textvariable=self.brush,width=4).pack(side='left',padx=3)
        ttk.Combobox(tools,textvariable=self.zoom,values=('Fit','1×','2×','4×','8×','16×'),state='readonly',width=5).pack(side='right')
        self.zoom.trace_add('write',lambda *_:self.redraw())
        selection=ttk.Frame(middle);selection.pack(fill='x',pady=3)
        for i,(label,cmd) in enumerate([('Recolor…',self.recolor),('Similar color…',self.similar_color),('Select all',self.select_all),
                          ('Invert',self.invert_selection),('Clear protection',self.clear_protection)]):
            ttk.Button(selection,text=label,command=cmd).grid(row=i//3,column=i%3,sticky='w',padx=(0,3),pady=1)
        canvas_frame=ttk.Frame(middle);canvas_frame.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(canvas_frame,bg='#c4c7cb',highlightthickness=1,highlightbackground='#999')
        sx=ttk.Scrollbar(canvas_frame,orient='horizontal',command=self.canvas.xview)
        sy=ttk.Scrollbar(canvas_frame,orient='vertical',command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=sx.set,yscrollcommand=sy.set)
        canvas_frame.rowconfigure(0,weight=1);canvas_frame.columnconfigure(0,weight=1)
        self.canvas.grid(row=0,column=0,sticky='nsew');sy.grid(row=0,column=1,sticky='ns');sx.grid(row=1,column=0,sticky='ew')
        self.canvas.bind('<Configure>',lambda e:self.redraw())
        self.canvas.bind('<ButtonPress-1>',self.begin);self.canvas.bind('<B1-Motion>',self.drag);self.canvas.bind('<ButtonRelease-1>',self.end)
        self.canvas.bind('<ButtonPress-2>',lambda e:self.canvas.scan_mark(e.x,e.y))
        self.canvas.bind('<B2-Motion>',lambda e:self.canvas.scan_dragto(e.x,e.y,gain=1))
        footer=ttk.Frame(middle);footer.pack(fill='x',pady=3)
        ttk.Checkbutton(footer,text='UV guides',variable=self.uv,command=self.redraw).pack(side='left')
        ttk.Button(footer,text='Undo',command=lambda:self.undo(False)).pack(side='left',padx=4)
        ttk.Button(footer,text='Redo',command=lambda:self.undo(True)).pack(side='left')
        ttk.Button(footer,text='Export texture PNG…',command=self.export_png).pack(side='right')
        ttk.Label(middle,textvariable=self.info,wraplength=490).pack(fill='x')
        ttk.Label(right,text='Live model preview — drag to rotate').pack(anchor='w')
        self.models=ttk.Combobox(right,textvariable=self.model_choice,state='readonly');self.models.pack(fill='x',pady=3)
        self.models.bind('<<ComboboxSelected>>',lambda e:self.changed(False))
        self.preview=tk.Label(right,bg='#484848',fg='white',text='Load a PAC to preview edits.')
        self.preview.pack(fill='both',expand=True)
        self.preview.bind('<Configure>',lambda e:self.schedule_preview())
        self.preview.bind('<ButtonPress-1>',lambda e:setattr(self,'orbit_start',(e.x,self.yaw.get())))
        self.preview.bind('<B1-Motion>',self.orbit)
        views=ttk.Frame(right);views.pack(fill='x',pady=3)
        for label,angle in [('¾',35),('Front',0),('Rear',180),('Left',90),('Right',270)]:
            ttk.Button(views,text=label,width=5,command=lambda a=angle:self.set_yaw(a)).pack(side='left',padx=(0,2))
        ttk.Scale(right,from_=1,to=3,variable=self.model_zoom,command=lambda _:self.schedule_preview()).pack(fill='x')
        options=ttk.Frame(right);options.pack(fill='x')
        ttk.Checkbutton(options,text='Encoded preview',variable=self.encoded,command=self.schedule_preview).pack(side='left')
        ttk.Checkbutton(options,text='Show usage',variable=self.highlight,command=self.schedule_preview).pack(side='left')
        palette=ttk.Frame(right);palette.pack(fill='x',pady=3)
        ttk.Label(palette,text='Edited colors').pack(side='left')
        self.palette_menu=ttk.Combobox(palette,textvariable=self.palette,values=('Native','128','64','32','24','16'),state='readonly',width=8)
        self.palette_menu.pack(side='left',padx=4);self.palette_menu.bind('<<ComboboxSelected>>',self.palette_changed)
        ttk.Label(right,text='References (display only; not generated automatically)').pack(anchor='w',pady=(6,1))
        refs=ttk.Frame(right);refs.pack(fill='x')
        ttk.Button(refs,text='Add pictures…',command=self.add_reference).pack(side='left')
        ttk.Button(refs,text='Remove',command=self.remove_reference).pack(side='left',padx=3)
        self.reference_list=ttk.Combobox(right,state='readonly');self.reference_list.pack(fill='x',pady=3)
        self.reference_list.bind('<<ComboboxSelected>>',lambda e:self.show_reference())
        self.reference=tk.Label(right,bg='#dfe1e4',height=7,text='Attire reference pictures');self.reference.pack(fill='x')
        self.reference.bind('<Configure>',lambda e:self.show_reference())
        self.root.after(100,self.poll)

    def fail(self,exc):messagebox.showerror('Retexture',str(exc),parent=self.root)

    def action(self,callback):
        try:
            if self.doc is None:raise ValueError('Open a PSP PAC first.')
            if (self.task_done is not None and self.task_done[0]=='operation') or hasattr(self,'after_preview'):
                raise ValueError('Wait for the current export/check to finish.')
            return callback()
        except (ValueError,OSError,KeyError,IndexError,TypeError)as exc:self.fail(exc)

    @property
    def texture(self):return self.doc.textures[self.texture_index]

    def color_limit(self):return 256 if self.palette.get()=='Native'else int(self.palette.get())

    def confirm_replace(self):
        if (self.task_done is not None and self.task_done[0]=='operation') or hasattr(self,'after_preview'):
            messagebox.showinfo('Retexture','Wait for the texture check/export to finish.',parent=self.root);return False
        if self.doc is None or not self.doc.dirty:return True
        answer=messagebox.askyesnocancel('Unsaved texture edits','Save an editable project before leaving these edits?',parent=self.root)
        if answer is None:return False
        if answer:return bool(self.save_project())
        return True

    def attach(self,doc):
        self.token+=1;self.epoch+=1;self.doc=doc;self.texture_index=0;self.layer_index=-1
        self.palette.set('Native'if doc.color_limit==256 else str(doc.color_limit))
        self.textures.delete(*self.textures.get_children());self.photos=[]
        for t in doc.textures:
            thumb=t.original.copy();thumb.thumbnail((40,40));photo=ImageTk.PhotoImage(thumb,master=self.root);self.photos.append(photo)
            self.textures.insert('','end',iid=str(t.index),text=f'{t.name} / {t.section}'+(''if t.editable else' [read-only]'),image=photo)
        self.textures.configure(height=8)
        style=ttk.Style(self.root);style.configure('Retexture.Treeview',rowheight=44);self.textures.configure(style='Retexture.Treeview')
        self.models.configure(values=[f'Section {s}: {m["report"]["model_name"]}'for s,m in doc.models]);self.models.current(0)
        self.reference_list.configure(values=[n for n,im in doc.references])
        if doc.references:self.reference_list.current(0)
        self.textures.selection_set('0');self.select_texture();self.show_reference()
        self.message.set(Path(doc.source).name+' — original PAC and all model records preserved. Save project to retain layers/masks.')

    def use_workspace(self,path):
        from desktop.workspace import verified_snapshot
        manifest,data=verified_snapshot(path)
        if self.doc and self.doc.sha256==manifest['source_sha256']:return True
        if not self.confirm_replace():return False
        self.attach(Document(data,manifest['source']));return True

    def use_current(self):
        if not self.shell.manifest:self.fail(ValueError('Open a PAC in Model Editor first.'));return
        try:self.use_workspace(self.shell.manifest_path)
        except (ValueError,OSError)as exc:self.fail(exc)

    def open_pac(self):
        if not self.confirm_replace():return
        path=filedialog.askopenfilename(title='Retexture a native PSP PAC',filetypes=[('PSP PAC','*.pac *.PAC')])
        if path:
            try:self.attach(Document(Path(path).read_bytes(),path))
            except (ValueError,OSError)as exc:self.fail(exc)

    def open_project(self):
        if not self.confirm_replace():return
        path=filedialog.askopenfilename(title='Open layered texture project',filetypes=[('Retexture project','*.pspret')])
        if path:
            try:self.attach(Document.load(path))
            except Exception as exc:self.fail(exc)

    def save_project(self):
        if not self.doc:return False
        path=filedialog.asksaveasfilename(title='Save layered project to a new file',initialfile=Path(self.doc.source).stem+'-textures.pspret',defaultextension='.pspret',filetypes=[('Retexture project','*.pspret')])
        if not path:return False
        try:self.doc.color_limit=self.color_limit();self.doc.save(path);self.message.set('Project saved with original PAC, layers, masks and reference pictures: '+path);return True
        except (ValueError,OSError)as exc:self.fail(exc);return False

    def select_texture(self,event=None):
        if not self.doc or not self.textures.selection():return
        self.texture_index=int(self.textures.selection()[0]);self.layer_index=-1
        self.refresh_layers();self.redraw();self.schedule_preview()
        t=self.texture;ix,pal=__import__('desktop.texture_optimizer.candidates',fromlist=['read_gim']).read_gim(t.raw)
        self.info.set(f'{t.name}: {t.original.width}×{t.original.height}, {len(pal)} palette entries. '+
                      ('Brush/selection/protection use texture pixels. Alpha locked.'if t.editable else'Effect/non-main texture: read-only.'))

    def refresh_layers(self):
        self.layers.delete(0,'end')
        for l in reversed(self.texture.layers):self.layers.insert('end',('● 'if l.visible else'○ ')+l.name)
        self.layers.insert('end','🔒 Original (unchanged)')
        if 0<=self.layer_index<len(self.texture.layers):self.layers.selection_set(len(self.texture.layers)-1-self.layer_index)

    def select_layer(self,event=None):
        if self.doc and self.layers.curselection():
            self.layer_index=len(self.texture.layers)-1-self.layers.curselection()[0];self.redraw()

    def selected_layer(self):
        if not 0<=self.layer_index<len(self.texture.layers):raise ValueError('Select an editable layer; the original is locked.')
        return self.texture.layers[self.layer_index]

    def changed(self,dirty=True):
        if not self.doc:return
        if dirty:self.doc.touch()
        thumb=self.texture.composite();thumb.thumbnail((40,40))
        photo=ImageTk.PhotoImage(thumb,master=self.root);self.photos[self.texture_index]=photo
        self.textures.item(str(self.texture_index),image=photo)
        self.token+=1;self.refresh_layers();self.redraw();self.schedule_preview()

    def palette_changed(self,event=None):
        if self.doc:self.doc.color_limit=self.color_limit();self.changed()

    def undo(self,redo):
        if self.doc and self.doc.undo(redo):self.layer_index=-1;self.changed(False)

    def choose_color(self):
        value=colorchooser.askcolor(color='#%02x%02x%02x'%self.color,parent=self.root)
        if value[0]:
            self.color=tuple(int(x)for x in value[0]);self.color_button.configure(bg=value[1]);return True
        return False

    def select_all(self):
        if self.doc:self.doc.checkpoint();self.texture.selection=Image.new('L',self.texture.original.size,255);self.changed()

    def invert_selection(self):
        if self.doc:self.doc.checkpoint();self.texture.selection=Image.fromarray(255-np.asarray(self.texture.selection));self.changed()

    def clear_protection(self):
        if self.doc:self.doc.checkpoint();self.texture.protection=Image.new('L',self.texture.original.size,0);self.changed()

    def similar_color(self):
        if not self.doc:return
        tolerance=simpledialog.askinteger('Select similar color','RGB distance tolerance from the current color (0–441):',initialvalue=50,minvalue=0,maxvalue=441,parent=self.root)
        if tolerance is None:return
        self.doc.checkpoint();rgba=np.asarray(self.texture.composite())
        mask=(np.linalg.norm(rgba[:,:,:3].astype(float)-self.color,axis=2)<=tolerance)&(rgba[:,:,3]>0)
        self.texture.selection=Image.fromarray(mask.astype(np.uint8)*255);self.changed()

    def recolor(self):
        def apply():
            if not self.choose_color():return
            self.doc.checkpoint();self.texture.recolor(self.color);self.layer_index=len(self.texture.layers)-1;self.changed()
        self.action(apply)

    def import_art(self):
        def apply():
            path=filedialog.askopenfilename(title='Import a transparent logo or pattern',filetypes=[('Images','*.png *.jpg *.jpeg *.bmp *.webp')])
            if not path:return
            image=read_image(Path(path).read_bytes());self.doc.checkpoint();self.texture.import_layer(image,Path(path).name)
            self.layer_index=len(self.texture.layers)-1;self.tool.set('Move layer');self.changed()
        self.action(apply)

    def layer_action(self,action):
        def apply():
            layer=self.selected_layer();i=self.layer_index;self.doc.checkpoint()
            if action=='delete':self.texture.layers.pop(i);self.layer_index=-1
            elif action=='visible':layer.visible=not layer.visible
            else:
                j=max(0,min(len(self.texture.layers)-1,i+(1 if action=='up'else-1)))
                self.texture.layers[i],self.texture.layers[j]=self.texture.layers[j],self.texture.layers[i];self.layer_index=j
            self.changed()
        self.action(apply)

    def set_opacity(self):
        def apply():
            layer=self.selected_layer();value=simpledialog.askinteger('Layer opacity','Opacity (%)',initialvalue=round(layer.opacity*100),minvalue=0,maxvalue=100,parent=self.root)
            if value is not None:self.doc.checkpoint();layer.opacity=value/100;self.changed()
        self.action(apply)

    def transform(self,kind,value):
        def apply():
            layer=self.selected_layer()
            if layer.paint:raise ValueError('Transform imported artwork layers. Paint/recolor layers use the texture canvas directly.')
            self.doc.checkpoint();q=np.asarray(layer.quad);center=q.mean(0)
            if kind=='scale':q=center+(q-center)*value
            elif kind=='rotate':
                a=np.deg2rad(value);matrix=np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]])
                q=(q-center)@matrix.T+center
            else:layer.image=layer.image.transpose(Image.Transpose.FLIP_LEFT_RIGHT if kind=='mirror'else Image.Transpose.FLIP_TOP_BOTTOM)
            layer.quad=q.tolist();self.changed()
        self.action(apply)

    def redraw(self):
        if not self.doc:return
        image=self.texture.composite();w,h=image.size
        fit=min(max(1,self.canvas.winfo_width()-22)/w,max(1,self.canvas.winfo_height()-22)/h)
        self.scale=fit if self.zoom.get()=='Fit'else float(self.zoom.get()[:-1]);self.scale=max(.1,self.scale)
        size=(max(1,round(w*self.scale)),max(1,round(h*self.scale)))
        yy,xx=np.indices((h,w));checker=np.where(((xx//8+yy//8)%2)[:,:,None],205,245)
        bg=np.repeat(checker,4,axis=2).astype(np.uint8);bg[:,:,3]=255
        display=Image.alpha_composite(Image.fromarray(bg),image)
        protect=Image.new('RGBA',(w,h),(245,50,50,0));protect.putalpha(self.texture.protection.point(lambda a:a//3));display=Image.alpha_composite(display,protect)
        display=display.resize(size,Image.Resampling.NEAREST)
        self.canvas_photo=ImageTk.PhotoImage(display,master=self.root);self.canvas.delete('all')
        self.canvas.create_image(10,10,anchor='nw',image=self.canvas_photo)
        self.canvas.configure(scrollregion=(0,0,size[0]+20,size[1]+20))
        if self.uv.get():
            model=self.doc.models[max(0,self.models.current())][1]
            edges=set()
            matching=[]
            for i,name in enumerate(model['texture_names']):
                try:
                    if self.doc.texture_for(model,name).index==self.texture_index:matching.append(i)
                except ValueError:pass
            for mesh in model['meshes']:
                for mat in mesh['materials']:
                    if mat['texture_id']not in matching:continue
                    for tri in mat['triangles']:
                        for i in range(3):
                            a=tuple(mesh['vertices'][tri[i]]['uv']);b=tuple(mesh['vertices'][tri[(i+1)%3]]['uv'])
                            edges.add(tuple(sorted((a,b))))
            for a,b in edges:
                if all(-.01<=v<=1.01 for v in (*a,*b)):
                    self.canvas.create_line(10+a[0]*size[0],10+a[1]*size[1],10+b[0]*size[0],10+b[1]*size[1],fill='#4c9ab5',width=1)
        bounds=self.texture.selection.getbbox()
        if bounds and bounds!=(0,0,w,h):self.canvas.create_rectangle(*(10+v*self.scale for v in bounds),outline='#ffff00',dash=(4,3))
        if 0<=self.layer_index<len(self.texture.layers):
            layer=self.texture.layers[self.layer_index]
            if not layer.paint:
                points=[(10+x*self.scale,10+y*self.scale)for x,y in layer.quad]
                self.canvas.create_polygon(*sum(([x,y]for x,y in points),[]),outline='#00ffff',fill='')
                for x,y in points:self.canvas.create_rectangle(x-4,y-4,x+4,y+4,fill='#00ffff')

    def point(self,event):return ((self.canvas.canvasx(event.x)-10)/self.scale,(self.canvas.canvasy(event.y)-10)/self.scale)

    def begin(self,event):
        def apply():
            p=self.point(event);t=self.texture;tool=self.tool.get()
            if not (0<=p[0]<t.original.width and 0<=p[1]<t.original.height):return
            if tool=='Picker':
                self.color=tuple(t.composite().getpixel((int(p[0]),int(p[1])))[:3]);self.color_button.configure(bg='#%02x%02x%02x'%self.color);return
            if not t.editable:raise ValueError('This texture is read-only.')
            if tool in ('Move layer','Warp corners'):
                layer=self.selected_layer()
                if layer.paint:raise ValueError('Choose an imported artwork layer to move/warp.')
                original=copy.deepcopy(layer.quad);corner=int(np.linalg.norm(np.asarray(layer.quad)-p,axis=1).argmin())
            else:original=None;corner=None
            self.doc.checkpoint();self.active_stroke=dict(start=p,last=p,tool=tool,quad=original,corner=corner)
            self.drag(event)
        self.action(apply)

    def drag(self,event):
        if not self.active_stroke or not self.doc:return
        s=self.active_stroke;p=self.point(event);t=self.texture;tool=s['tool']
        try:
            if tool in ('Brush','Erase'):t.stroke(s['last'],p,self.color,max(1,self.brush.get()),erase=tool=='Erase')
            elif tool in ('Protect','Unprotect'):
                d=ImageDraw.Draw(t.protection);r=max(1,self.brush.get());d.line((s['last'],p),fill=255 if tool=='Protect'else 0,width=r*2)
                d.ellipse((p[0]-r,p[1]-r,p[0]+r,p[1]+r),fill=255 if tool=='Protect'else 0)
            elif tool=='Select rectangle':
                bounds=[max(0,min(s['start'][0],p[0])),max(0,min(s['start'][1],p[1])),min(t.original.width,max(s['start'][0],p[0])),min(t.original.height,max(s['start'][1],p[1]))]
                t.selection=Image.new('L',t.original.size)
                if bounds[2]>=bounds[0]and bounds[3]>=bounds[1]:ImageDraw.Draw(t.selection).rectangle(bounds,fill=255)
            else:
                layer=self.selected_layer();q=np.asarray(s['quad'],float)
                if tool=='Move layer':q+=np.asarray(p)-s['start']
                else:q[s['corner']]=p
                warp(Image.new('RGBA',(1,1)),q,(1,1));layer.quad=q.tolist()
            s['last']=p;self.doc.touch();self.token+=1;self.redraw();self.schedule_preview()
        except (ValueError,tk.TclError):pass  # Invalid temporary drag retains last valid quad.

    def end(self,event):
        if self.active_stroke:self.active_stroke=None;self.changed(False)

    def add_reference(self):
        if not self.doc:self.fail(ValueError('Load a PAC first.'));return
        paths=filedialog.askopenfilenames(title='Add attire reference pictures',filetypes=[('Images','*.png *.jpg *.jpeg *.webp *.bmp')])
        try:
            for path in paths:
                if len(self.doc.references)>=12:raise ValueError('Up to 12 reference pictures per project.')
                image=read_image(Path(path).read_bytes());image.thumbnail((1024,1024))
                self.doc.references.append((Path(path).name,image));self.doc.touch()
            self.reference_list.configure(values=[n for n,im in self.doc.references])
            if self.doc.references:self.reference_list.current(len(self.doc.references)-1)
            self.show_reference()
        except (ValueError,OSError)as exc:self.fail(exc)

    def remove_reference(self):
        if self.doc and self.reference_list.current()>=0:
            self.doc.references.pop(self.reference_list.current());self.doc.touch()
            self.reference_list.configure(values=[n for n,im in self.doc.references]);self.reference_list.set('')
            if self.doc.references:self.reference_list.current(0)
            self.show_reference()

    def show_reference(self):
        if not self.doc or not self.doc.references:self.reference.configure(image='',text='Attire reference pictures');return
        i=max(0,self.reference_list.current());image=self.doc.references[i][1].copy()
        image.thumbnail((max(1,self.reference.winfo_width()-8),150))
        self.reference_photo=ImageTk.PhotoImage(image,master=self.root);self.reference.configure(image=self.reference_photo,text='',height=0)

    def export_png(self):
        if not self.doc:return
        path=filedialog.asksaveasfilename(title='Export draft texture PNG',initialfile=self.texture.name+'-edited.png',defaultextension='.png',filetypes=[('PNG','*.png')])
        if path:self.texture.composite().save(path)

    def orbit(self,event):
        if hasattr(self,'orbit_start'):self.yaw.set((self.orbit_start[1]+event.x-self.orbit_start[0])%360);self.schedule_preview()

    def set_yaw(self,angle):self.yaw.set(angle);self.schedule_preview()

    def schedule_preview(self):
        if self.closed or not self.doc:return
        # Throttle, not debounce: a continuous brush/warp drag must still produce
        # frames instead of postponing every render until the mouse is released.
        if self.preview_timer:return
        self.preview_timer=self.root.after(100,self.start_preview)

    def start_preview(self):
        self.preview_timer=None
        if self.closed or not self.doc:return
        if self.future is not None:self.preview_pending=True;return
        doc=copy.copy(self.doc);doc.textures=copy.deepcopy(self.doc.textures)
        model=doc.models[max(0,self.models.current())][1];encoded=self.encoded.get();limit=self.color_limit()
        angle=self.yaw.get();zoom=self.model_zoom.get();selected=None
        if self.highlight.get():
            selected=next((n for n in model['texture_names']if doc.texture_for(model,n).index==self.texture_index),None)
        token=(self.epoch,self.token);resolution=320 if self.active_stroke else 480
        def work():return render(model,{},resolution=resolution,zoom=zoom,rgba_textures=doc.images_for(model,encoded,limit),highlight_texture=selected,yaw=angle)
        self.future=self.executor.submit(work);self.task_done=('preview',token)

    def background(self,work,done):
        if self.task_done and self.task_done[0]!='preview':raise ValueError('A texture export/check is already running.')
        # Let any current preview finish before launching the serialized task.
        if self.future is not None:
            self.after_preview=(work,done);self.message.set('Finishing preview, then checking the serialized PAC…');return
        self.future=self.executor.submit(work);self.task_done=('operation',done)

    def check_size(self):
        def apply():
            snapshot=copy.copy(self.doc);snapshot.textures=copy.deepcopy(self.doc.textures);limit=self.color_limit()
            self.message.set('Encoding edits and measuring the actual PAC…')
            def done(result):
                _,report=result;self.last_report=report
                text=f"{report['bytes']:,} / {report['max_pac_bytes']:,} bytes — "+('fits.'if report['fits']else'OVER BUDGET: reduce edited colors or simplify artwork.')
                warnings=[r['name']for r in report['textures']if r.get('changed')and r.get('rgb_rmse',0)>25]
                if warnings:text+=' Significant palette loss: '+', '.join(warnings)+'. Check the encoded preview.'
                self.message.set(text)
                messagebox.showinfo('Actual encoded PAC size',text+'\n\nModel/rigging records and texture memory allocation unchanged.',parent=self.root)
            self.background(lambda:snapshot.candidate(limit),done)
        self.action(apply)

    def export_pac(self):
        def apply():
            path=filedialog.asksaveasfilename(title='Export retextured PAC to a NEW filename',initialdir=str(self.shell.pac_browser.folder or Path(self.doc.source).parent),initialfile=Path(self.doc.source).stem+'-retextured.pac',defaultextension='.pac',filetypes=[('PSP PAC','*.pac')],confirmoverwrite=False)
            if not path:return
            snapshot=copy.copy(self.doc);snapshot.textures=copy.deepcopy(self.doc.textures);limit=self.color_limit()
            self.message.set('Checking encoded textures, native records and final size before export…')
            def done(report):
                self.last_report=report;self.shell.pac_browser.refresh()
                self.message.set(f"Saved {Path(path).name}: {report['bytes']:,} bytes. Model/rigging unchanged. Test appearance in PPSSPP.")
                messagebox.showinfo('Retextured PAC exported',self.message.get()+'\n'+path,parent=self.root)
            self.background(lambda:snapshot.export(path,limit),done)
        self.action(apply)

    def poll(self):
        if self.closed:return
        if self.future is not None and self.future.done():
            future=self.future;kind,value=self.task_done;self.future=None;self.task_done=None
            try:
                result=future.result()
                # A completed frame from this document is useful during a long
                # stroke, even when a newer revision is already queued. Never
                # display an old document over a newly opened PAC/project.
                if kind=='preview' and value[0]==self.epoch:
                    result.thumbnail((max(1,self.preview.winfo_width()-6),max(1,self.preview.winfo_height()-6)))
                    self.model_photo=ImageTk.PhotoImage(result,master=self.root);self.preview.configure(image=self.model_photo,text='')
                    self.preview_frames+=1;self.last_preview_revision=value
                elif kind=='operation':value(result)
            except Exception as exc:
                if kind=='preview':self.preview.configure(image='',text='Preview unavailable: '+str(exc))
                else:self.message.set('Texture operation failed; original and project retained.');self.fail(exc)
            if hasattr(self,'after_preview'):
                work,done=self.after_preview;del self.after_preview;self.background(work,done)
            elif self.preview_pending:self.preview_pending=False;self.schedule_preview()
        self.root.after(100,self.poll)

    def close(self):
        self.closed=True
        if self.preview_timer:self.root.after_cancel(self.preview_timer)
        self.executor.shutdown(wait=False,cancel_futures=True)
