"""Minimal portable interface. Processing always runs outside the UI process."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import filedialog,messagebox,ttk
import uuid
import webbrowser
from PIL import Image,ImageTk
from desktop import NAME,VERSION
from desktop.adapters import FORMATS
from desktop.storage import data_dir,load_settings,save_settings,save_as

BG='#111113';PANEL='#1b1b1f';FG='#f2f2f3';MUTED='#a5a5af';RED='#d72d40'

class Application:
    def __init__(self):
        from tkinterdnd2 import TkinterDnD,DND_FILES
        self.root=TkinterDnD.Tk();self.drag_drop=True
        self.root.title(NAME);self.root.configure(bg=BG);self.root.geometry('1140x820');self.root.minsize(970,730)
        self.settings=load_settings();self.source=None;self.process=None;self.result=None;self.saved=None;self.closing=False
        self.inspector=None;self.inspect_root=None;self.view='front-left';self.zoom='full';self.photo=None
        self.base=tk.StringVar(value=self.settings.get('base',''));self.status=tk.StringVar(value='Choose your PSP base once, then drop an HCTP PAC.')
        self.info=tk.StringVar(value='No source selected');self.output=tk.StringVar(value='Your converted PSP output will appear here.')
        style=ttk.Style(self.root);style.theme_use('clam');style.configure('TProgressbar',troughcolor=PANEL,background=RED,bordercolor=PANEL)
        title=tk.Frame(self.root,bg=BG);title.pack(fill='x',padx=28,pady=(23,20))
        tk.Label(title,text='PS2PSP',font=('Segoe UI',25,'bold'),fg=FG,bg=BG).pack(side='left')
        tk.Label(title,text='PAC CONVERTER  /  by RyosPrime',font=('Segoe UI',11),fg=MUTED,bg=BG).pack(side='left',padx=18)
        tk.Label(title,text='HCTP PREVIEW',font=('Segoe UI',10,'bold'),fg=RED,bg=BG).pack(side='right')
        body=tk.Frame(self.root,bg=BG);body.pack(fill='both',expand=True,padx=28)
        left=tk.Frame(body,bg=BG,width=370);left.pack(side='left',fill='y',padx=(0,24));left.pack_propagate(False)
        right=tk.Frame(body,bg=BG);right.pack(side='left',fill='both',expand=True)
        self.label(left,'SOURCE CONTAINER')
        menu=tk.Menubutton(left,text=FORMATS[2].label+'  ▾',bg=PANEL,fg=FG,font=('Segoe UI',10),padx=12,pady=12,anchor='w',relief='flat')
        choices=tk.Menu(menu,tearoff=False,bg=PANEL,fg=FG,disabledforeground='#65656d')
        for item in FORMATS:choices.add_command(label=item.label+(' — Coming soon' if not item.supported else ''),state='normal' if item.supported else 'disabled')
        menu.configure(menu=choices);menu.pack(fill='x',pady=(8,20))
        self.source_menu=choices
        self.drop=tk.Label(left,text='Drop an HCTP .pac here\n\nor click to browse',bg=PANEL,fg=FG,font=('Segoe UI',13),height=5,cursor='hand2',highlightbackground='#3a3a42',highlightthickness=1)
        self.drop.pack(fill='x');self.drop.bind('<Button-1>',lambda e:self.browse_source());self.drop.drop_target_register(DND_FILES)
        self.drop.dnd_bind('<<Drop>>',self.dropped)
        tk.Label(left,textvariable=self.info,bg=BG,fg=MUTED,font=('Segoe UI',10),wraplength=365,justify='left').pack(fill='x',pady=(12,22))
        self.label(left,'YOUR PSP BASE  /  remembered locally')
        tk.Label(left,textvariable=self.base,bg=BG,fg=MUTED,font=('Segoe UI',9),wraplength=365,justify='left').pack(fill='x',pady=8)
        self.base_button=self.button(left,'Choose PSP base PAC',self.choose_base);self.base_button.pack(fill='x')
        tk.Label(left,text='Target: SVR 2011 PSP\nCompatible custom HCTP containers accepted.\nOther PS2 formats are coming soon.',bg=BG,fg=MUTED,font=('Segoe UI',10),justify='left').pack(fill='x',pady=20)
        conversion_actions=tk.Frame(left,bg=BG);conversion_actions.pack(fill='x',pady=6)
        self.convert=self.button(conversion_actions,'Convert',self.start,primary=True);self.convert.pack(side='left',fill='x',expand=True,padx=(0,8))
        self.cancel=self.button(conversion_actions,'Cancel',self.cancel_job);self.cancel.pack(side='left',fill='x',expand=True);self.cancel.configure(state='disabled')
        self.label(right,'FINAL PSP OUTPUT  /  textured offline preview')
        self.preview=tk.Label(right,text='Convert a model to preview the PSP output',bg=PANEL,fg=MUTED,font=('Segoe UI',12),cursor='hand2')
        self.preview.pack(fill='both',expand=True,pady=(8,12));self.preview.bind('<Configure>',lambda e:self.show_preview());self.preview.bind('<Button-1>',lambda e:self.enlarge())
        controls=tk.Frame(right,bg=BG);controls.pack(fill='x')
        for label,view in (('¾','front-left'),('Front','front'),('Rear','back'),('Left','left'),('Right','right')):
            self.button(controls,label,lambda v=view:self.set_view(v)).pack(side='left',padx=(0,5))
        self.button(controls,'Zoom',self.toggle_zoom).pack(side='right')
        tk.Label(right,textvariable=self.output,bg=BG,fg=MUTED,font=('Segoe UI',10),wraplength=670,justify='left').pack(fill='x',pady=12)
        actions=tk.Frame(right,bg=BG);actions.pack(fill='x')
        self.save=self.button(actions,'Save PAC As…',self.export,primary=True);self.save.pack(side='left');self.save.configure(state='disabled')
        self.button(actions,'QA report',self.open_report).pack(side='left',padx=10)
        self.button(actions,'Open Folder',self.open_folder).pack(side='left')
        footer=tk.Frame(self.root,bg=BG);footer.pack(fill='x',padx=28,pady=(18,24))
        self.progress=ttk.Progressbar(footer,maximum=100);self.progress.pack(fill='x')
        tk.Label(footer,textvariable=self.status,bg=BG,fg=MUTED,font=('Segoe UI',10),anchor='w',wraplength=1060).pack(fill='x',pady=(10,0))
        self.button(footer,'Logs',self.open_logs).pack(side='right',pady=6)
        self.root.protocol('WM_DELETE_WINDOW',self.close);self.root.after(200,self.poll)

    def label(self,parent,text):tk.Label(parent,text=text,bg=BG,fg=MUTED,font=('Segoe UI',9,'bold'),anchor='w').pack(fill='x')
    def button(self,parent,text,command,primary=False):
        return tk.Button(parent,text=text,command=command,bg=RED if primary else PANEL,fg=FG,activebackground='#9b2532' if primary else '#34343a',activeforeground=FG,relief='flat',borderwidth=0,padx=14,pady=10,font=('Segoe UI',10,'bold' if primary else 'normal'),cursor='hand2',disabledforeground='#68686e')
    def entry(self):return [sys.executable] if getattr(sys,'frozen',False) else [sys.executable,str(Path(__file__).resolve().parents[1]/'ps2psp_converter.py')]
    def spawn(self,args):return subprocess.Popen(self.entry()+args,creationflags=0x08000000 if os.name=='nt' else 0)
    def busy(self):return self.process is not None
    def browse_source(self):
        if self.busy():return
        selected=filedialog.askopenfilename(title='Select HCTP source PAC',filetypes=[('PAC files','*.pac *.PAC')])
        if selected:self.select_source(selected)
    def dropped(self,event):
        if self.busy():return
        files=self.root.tk.splitlist(event.data)
        if len(files)!=1:messagebox.showerror(NAME,'Drop one .pac file at a time.');return
        self.select_source(files[0])
    def select_source(self,path):
        if self.inspector is not None:messagebox.showinfo(NAME,'Wait for the current input check to finish.');return
        path=Path(path)
        if not path.is_file() or path.suffix.lower()!='.pac':messagebox.showerror(NAME,'Select an existing .pac file.');return
        self.source=None;self.result=None;self.save.configure(state='disabled');self.convert.configure(state='disabled')
        self.drop.configure(text=path.name);self.info.set('Checking container and PS2 textures…');self.output.set('Your converted PSP output will appear here.');self.preview.configure(image='',text='Checking source…')
        self.inspect_root=Path(tempfile.mkdtemp(prefix='inspect-',dir=data_dir()));self.pending_source=str(path.resolve())
        self.inspector=self.spawn(['--inspect',self.pending_source,str(self.inspect_root/'result.json')])
    def choose_base(self):
        if self.busy():return
        chosen=filedialog.askopenfilename(title='Select your own PSP SVR base wrestler PAC',filetypes=[('PAC files','*.pac *.PAC')])
        if chosen:self.base.set(chosen);self.settings['base']=chosen;save_settings(self.settings)
    def start(self):
        if self.busy() or self.inspector is not None:return
        if not self.source:messagebox.showerror(NAME,'Choose a supported HCTP source first.');return
        if not Path(self.base.get()).is_file():self.choose_base()
        if not Path(self.base.get()).is_file():return
        from desktop.core import Request
        try:Request(self.source,self.base.get()).validate()
        except Exception as e:messagebox.showerror(NAME,str(e));return
        self.job=data_dir()/'jobs'/uuid.uuid4().hex;self.job.mkdir(parents=True)
        (self.job/'request.json').write_text(json.dumps(dict(source=self.source,base=self.base.get(),source_format='hctp')),encoding='utf-8')
        self.result=None;self.save.configure(state='disabled');self.convert.configure(state='disabled');self.base_button.configure(state='disabled');self.cancel.configure(state='normal')
        self.output.set('Building an experimental PSP candidate…');self.preview.configure(image='',text='Converting…');self.progress['value']=0
        self.process=self.spawn(['--worker',str(self.job/'request.json')]);self.status.set('Starting isolated conversion job…')
    def cancel_job(self):
        if self.busy():(self.job/'cancel').touch();self.status.set('Cancelling and cleaning incomplete output…');self.cancel.configure(state='disabled')
    def poll(self):
        if self.inspector is not None and self.inspector.poll() is not None:
            try:
                r=json.loads((self.inspect_root/'result.json').read_text())
                if not r['ok']:raise ValueError(r['error'])
                self.source=self.pending_source;v=r['info'];self.info.set(f"{v['format']} • {v['model']}\n{v['bytes']:,} bytes • {v['triangles']:,} main-model triangles\n{v.get('model_count',1)} models • {v['textures']} textures")
                self.status.set('Source validated. Ready to convert.')
            except Exception as e:self.info.set('Input rejected');self.status.set(str(e));messagebox.showerror('Input check',str(e))
            import shutil
            shutil.rmtree(self.inspect_root,ignore_errors=True);self.inspector=None;self.convert.configure(state='normal')
        if self.busy():
            events=self.job/'events.jsonl'
            if events.exists():
                try:
                    rows=events.read_text(encoding='utf-8').splitlines();r=json.loads(rows[-1]);self.progress['value']=max(self.progress['value'],r['percent']);self.status.set(r['message'])
                except (ValueError,IndexError):pass
            if self.process.poll() is not None:
                self.process=None;self.cancel.configure(state='disabled');self.convert.configure(state='normal');self.base_button.configure(state='normal')
                try:
                    if not (self.job/'success.json').exists():
                        failure=json.loads((self.job/'failure.json').read_text(encoding='utf-8'));self.status.set(failure['error'])
                        if not failure['cancelled']:messagebox.showerror('Conversion stopped',failure['error']+'\n\nUse Logs for diagnostics.')
                    else:
                        self.result=json.loads((self.job/'success.json').read_text(encoding='utf-8'));r=self.result
                        self.output.set(f"{Path(r['pac']).name}  •  {r['bytes']:,} bytes\nNative checks passed • {r.get('model_count',1)} models • {r.get('total_meshes',r['meshes'])} meshes • {r.get('total_triangles',r['triangles']):,} triangles\nQA: {r['review_flags']} findings to review • PPSSPP validation required")
                        self.save.configure(state='normal');self.status.set('Review the PSP preview and QA report before saving.');self.show_preview()
                except Exception as e:self.status.set('Worker ended unexpectedly; inspect Logs.');messagebox.showerror(NAME,str(e))
        if self.closing and not self.busy() and self.inspector is None:self.root.destroy();return
        self.root.after(200,self.poll)
    def set_view(self,view):self.view=view;self.show_preview()
    def toggle_zoom(self):self.zoom='zoom' if self.zoom=='full' else 'full';self.show_preview()
    def image_path(self):return Path(self.result['preview'])/(self.view+'-'+self.zoom+'.png')
    def show_preview(self):
        if not self.result:return
        image=Image.open(self.image_path());image.thumbnail((max(150,self.preview.winfo_width()-12),max(150,self.preview.winfo_height()-12)))
        self.photo=ImageTk.PhotoImage(image);self.preview.configure(image=self.photo,text='')
    def enlarge(self):
        if not self.result:return
        top=tk.Toplevel(self.root);top.title('Final PSP output — '+self.view);top.configure(bg=PANEL)
        image=Image.open(self.image_path());image.thumbnail((self.root.winfo_screenwidth()-80,self.root.winfo_screenheight()-120));photo=ImageTk.PhotoImage(image)
        label=tk.Label(top,image=photo,bg=PANEL);label.image=photo;label.pack()
    def export(self):
        if not self.result:return
        if self.result['review_flags'] and not messagebox.askyesno('QA findings require review',f"The QA report has {self.result['review_flags']} review findings. This candidate still needs PPSSPP testing. Save it as an experimental PAC?"):return
        chosen=filedialog.asksaveasfilename(title='Save experimental PSP PAC',defaultextension='.pac',initialfile=Path(self.result['pac']).name,filetypes=[('PSP PAC','*.pac')])
        if not chosen:return
        try:self.saved=save_as(self.result,chosen);self.status.set('Saved '+self.saved)
        except Exception as e:messagebox.showerror('Export withheld',str(e))
    def open_report(self):
        if self.result:webbrowser.open(Path(self.result['report']).as_uri())
    def open_path(self,path):
        if os.name=='nt':os.startfile(str(path))
        else:subprocess.Popen(['xdg-open',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    def open_folder(self):
        if self.saved:self.open_path(Path(self.saved).parent)
        elif self.result:self.open_path(Path(self.result['pac']).parent)
    def open_logs(self):self.open_path(self.job if hasattr(self,'job') else data_dir())
    def close(self):
        self.closing=True
        if self.busy():self.cancel_job()
        elif self.inspector is None:self.root.destroy()
