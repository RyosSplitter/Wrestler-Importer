"""Local source previews and explicit, bounded fidelity selections."""
from pathlib import Path

import numpy as np
from PIL import Image

MAX_SELECTION = 3


def validate_selection(names, available=None):
    if not isinstance(names,(list,tuple)) or any(not isinstance(n,str) or not n for n in names):
        raise ValueError('Texture priorities must be a list of texture names.')
    if len(names)>MAX_SELECTION:raise ValueError('Select at most three textures to prioritize.')
    if len(set(names))!=len(names):raise ValueError('Texture priority names must be unique.')
    if available is not None and set(names)-set(available):
        raise ValueError('Selected textures no longer belong to this source PAC; review textures again.')
    return tuple(names)


def source_previews(decoded, folder):
    """PNG preserves decoded source RGBA, before quantization or conversion."""
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    entries=[]
    for i,name,raw,rgba,details in decoded:
        path=folder/('source-%03d.png'%len(entries))
        Image.fromarray(rgba).save(path)
        visible=rgba[rgba[:,:,3]>0]
        entries.append(dict(name=name,width=rgba.shape[1],height=rgba.shape[0],
            useful_colors=len(np.unique(visible,axis=0)),has_alpha=bool(np.any(rgba[:,:,3]!=255)),
            source_format=details,png=str(path.resolve())))
    return entries


def preview_image(path, size=(120,96)):
    # Checkerboard is presentation only. Never write it into source textures.
    with Image.open(path) as original:
        rgba=original.convert('RGBA');rgba.thumbnail(size,Image.Resampling.NEAREST)
    y,x=np.indices((rgba.height,rgba.width));board=np.where(((x//8+y//8)%2)[:,:,None],210,245)
    background=Image.fromarray(np.broadcast_to(board,(rgba.height,rgba.width,3)).astype(np.uint8)).convert('RGBA')
    background.alpha_composite(rgba)
    return background


class TextureChooser:
    """Scrollable classic dialog; Cancel returns None, Continue returns names."""
    def __init__(self,parent,entries,selected=()):
        import tkinter as tk
        from tkinter import ttk
        from PIL import ImageTk
        self.result=None;self.entries=entries;self.photos=[]
        self.top=tk.Toplevel(parent);self.top.title('Review source textures — choose up to 3')
        self.top.geometry('640x560');self.top.minsize(480,360);self.top.transient(parent)
        ttk.Label(self.top,text='Check up to three textures to prioritize their fidelity.',padding=10).pack(anchor='w')
        ttk.Label(self.top,text='Selected textures receive priority. Other textures may be reduced to fund their detail; all tradeoffs are reported. Model geometry and material color depth stay unchanged.',wraplength=590,padding=(10,0,10,8)).pack(anchor='w')
        footer=ttk.Frame(self.top,padding=10);footer.pack(side='bottom',fill='x')
        self.count=tk.StringVar();ttk.Label(footer,textvariable=self.count).pack(side='left')
        ttk.Button(footer,text='Continue conversion',command=self.accept).pack(side='right')
        ttk.Button(footer,text='Cancel',command=self.top.destroy).pack(side='right',padx=8)
        body=ttk.Frame(self.top);body.pack(fill='both',expand=True)
        canvas=tk.Canvas(body,background='#f0f0f0',highlightthickness=0)
        scrollbar=ttk.Scrollbar(body,orient='vertical',command=canvas.yview);scrollbar.pack(side='right',fill='y')
        canvas.configure(yscrollcommand=scrollbar.set);canvas.pack(side='left',fill='both',expand=True)
        rows=ttk.Frame(canvas);window=canvas.create_window((0,0),window=rows,anchor='nw')
        rows.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(window,width=e.width))
        self.canvas=canvas
        self.top.bind('<MouseWheel>',lambda e:canvas.yview_scroll(-int(e.delta/120),'units'))
        self.top.bind('<Button-4>',lambda e:canvas.yview_scroll(-1,'units'))
        self.top.bind('<Button-5>',lambda e:canvas.yview_scroll(1,'units'))
        self.variables={};self.checkboxes={}
        selected=validate_selection(selected,[r['name'] for r in entries])
        for entry in entries:
            name=entry['name'];row=ttk.Frame(rows,padding=(10,6));row.pack(fill='x')
            photo=ImageTk.PhotoImage(preview_image(entry['png']));self.photos.append(photo)
            label=ttk.Label(row,image=photo,cursor='hand2');label.pack(side='left',padx=(0,12))
            label.bind('<Button-1>',lambda e,r=entry:self.enlarge(r))
            var=tk.BooleanVar(value=name in selected);self.variables[name]=var
            box=ttk.Checkbutton(row,text=f"{name}\n{entry['width']} × {entry['height']} • {entry['useful_colors']:,} visible source colors"+(' • alpha' if entry['has_alpha'] else ''),variable=var,command=self.refresh)
            box.pack(side='left');self.checkboxes[name]=box
        self.refresh();self.top.protocol('WM_DELETE_WINDOW',self.top.destroy)

    def selected(self):return tuple(n for n,v in self.variables.items() if v.get())
    def refresh(self):
        count=len(self.selected());self.count.set(f'{count} / {MAX_SELECTION} selected')
        for name,box in self.checkboxes.items():
            box.configure(state='disabled' if count>=MAX_SELECTION and not self.variables[name].get() else 'normal')
    def accept(self):
        self.result=validate_selection(self.selected(),[r['name'] for r in self.entries]);self.top.destroy()
    def show(self):
        self.top.grab_set();self.top.wait_window();return self.result
    def enlarge(self,entry):
        import tkinter as tk
        from PIL import ImageTk
        top=tk.Toplevel(self.top);top.title(entry['name']+' — source texture')
        image=preview_image(entry['png'],(700,600));image=image.resize((image.width*min(3,700//image.width),image.height*min(3,700//image.width)),Image.Resampling.NEAREST)
        photo=ImageTk.PhotoImage(image);label=tk.Label(top,image=photo);label.image=photo;label.pack()
