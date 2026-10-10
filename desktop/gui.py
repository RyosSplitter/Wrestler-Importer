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

BG='#f0f0f0';PANEL='#e3e5e8';FG='#202020';MUTED='#606060'

class Application:
    def __init__(self):
        from tkinterdnd2 import TkinterDnD,DND_FILES
        self.root=TkinterDnD.Tk();self.drag_drop=True
        self.root.title(NAME);self.root.configure(bg=BG);self.root.geometry('1040x720');self.root.minsize(940,640)
        self.settings=load_settings();self.source=None;self.process=None;self.result=None;self.saved=None;self.closing=False
        self.inspector=None;self.inspect_root=None;self.view='front-left';self.zoom='full';self.photo=None
        self.base=tk.StringVar(value=self.settings.get('base',''));self.status=tk.StringVar(value='Choose your PSP base once, then drop an HCTP PAC.')
        # Session-only and deliberately OFF, even when an earlier job enabled it.
        self.adaptive_textures=tk.BooleanVar(value=False)
        self.info=tk.StringVar(value='No source selected');self.output=tk.StringVar(value='Your converted PSP output will appear here.')
        # Vista is Tk's native Windows 7-era control theme. Keep native button,
        # checkbox, focus and disabled rendering; use a light fallback elsewhere.
        style=ttk.Style(self.root)
        style.theme_use('vista' if 'vista' in style.theme_names() else 'clam')
        self.ui_theme=style.theme_use()
        self.root.option_add('*Font',('Segoe UI',9))
        style.configure('.',font=('Segoe UI',9))
        style.configure('TFrame',background=BG)
        style.configure('TLabel',background=BG,foreground=FG)
        style.configure('TLabelframe',background=BG)
        style.configure('TLabelframe.Label',background=BG,foreground=FG)
        style.configure('Muted.TLabel',foreground=MUTED)
        style.configure('TButton',padding=(8,3))
        if self.ui_theme!='vista':
            style.configure('TButton',background='#f5f5f5',bordercolor='#a0a0a0',lightcolor='#ffffff',darkcolor='#cccccc')
            style.map('TButton',background=[('pressed','#dce9f5'),('active','#edf5fc')])
            style.configure('TCheckbutton',background=BG,foreground=FG)
            style.configure('TMenubutton',background='#f5f5f5',foreground=FG,padding=(6,3))
            style.configure('TProgressbar',troughcolor='#ffffff',background='#52a651')

        header=ttk.Frame(self.root,padding=(12,10,12,6));header.pack(fill='x')
        ttk.Label(header,text='PS2PSP PAC Converter',font=('Segoe UI',12)).pack(side='left')
        ttk.Label(header,text='by RyosPrime',style='Muted.TLabel').pack(side='left',padx=10)
        ttk.Label(header,text='v'+VERSION,style='Muted.TLabel').pack(side='right')
        ttk.Separator(self.root).pack(fill='x',padx=12)

        # Reserve the status bar before the expanding body so it remains visible
        # at the minimum window size and at enlarged Windows text scales.
        footer=ttk.Frame(self.root,padding=(12,6,12,10));footer.pack(side='bottom',fill='x')
        self.progress=ttk.Progressbar(footer,maximum=100);self.progress.pack(fill='x',pady=(0,6))
        status_row=ttk.Frame(footer);status_row.pack(fill='x')
        self.button(status_row,'Logs',self.open_logs).pack(side='right',padx=(8,0))
        self.status_label=ttk.Label(status_row,textvariable=self.status,style='Muted.TLabel',wraplength=850)
        self.status_label.pack(side='left',fill='x',expand=True)
        status_row.bind('<Configure>',lambda e:self.status_label.configure(wraplength=max(200,e.width-90)))

        body=ttk.Frame(self.root,padding=(12,10,12,0));body.pack(fill='both',expand=True)
        left=ttk.Frame(body,width=340);left.pack(side='left',fill='y',padx=(0,12));left.pack_propagate(False)
        right=ttk.Frame(body);right.pack(side='left',fill='both',expand=True)
        source_group=ttk.LabelFrame(left,text='Source PAC',padding=10);source_group.pack(fill='x')
        menu=ttk.Menubutton(source_group,text=FORMATS[2].label)
        choices=tk.Menu(menu,tearoff=False)
        for item in FORMATS:choices.add_command(label=item.label+(' — Coming soon' if not item.supported else ''),state='normal' if item.supported else 'disabled')
        menu.configure(menu=choices);menu.pack(fill='x',pady=(0,10))
        self.source_menu=choices
        self.drop=tk.Label(source_group,text='Drop an HCTP .pac here\nor click to browse',bg='#ffffff',fg=MUTED,
            height=5,cursor='hand2',relief='sunken',borderwidth=1,wraplength=290)
        self.drop.pack(fill='x');self.drop.bind('<Button-1>',lambda e:self.browse_source());self.drop.drop_target_register(DND_FILES)
        self.drop.dnd_bind('<<Drop>>',self.dropped)
        ttk.Label(source_group,textvariable=self.info,style='Muted.TLabel',wraplength=310,justify='left').pack(fill='x',pady=(8,0))
        base_group=ttk.LabelFrame(left,text='PSP base PAC',padding=10);base_group.pack(fill='x',pady=(10,0))
        ttk.Label(base_group,textvariable=self.base,wraplength=310,justify='left').pack(fill='x',pady=(0,8))
        self.base_button=self.button(base_group,'Choose PSP base PAC...',self.choose_base);self.base_button.pack(fill='x')
        ttk.Label(base_group,text='Remembered on this computer.',style='Muted.TLabel').pack(anchor='w',pady=(6,0))
        options=ttk.LabelFrame(left,text='Options',padding=10);options.pack(fill='x',pady=(10,0))
        # The wrapped classic checkbox retains the exact option label and keeps
        # it readable at larger system font scales without clipping the sidebar.
        self.adaptive_checkbox=tk.Checkbutton(options,text='Adaptive Texture Optimization (Experimental)',
            variable=self.adaptive_textures,bg=BG,fg=FG,selectcolor='#ffffff',activebackground=BG,
            activeforeground=FG,anchor='w',justify='left',wraplength=280)
        self.adaptive_checkbox.pack(fill='x')
        ttk.Label(left,text='Target: SVR 2011 PSP\nHCTP and compatible custom PACs supported.',
            style='Muted.TLabel',wraplength=330,justify='left').pack(fill='x',pady=12)

        preview_group=ttk.LabelFrame(right,text='PSP preview',padding=8);preview_group.pack(fill='both',expand=True)
        conversion_actions=ttk.Frame(preview_group);conversion_actions.pack(fill='x',pady=(0,8))
        self.convert=self.button(conversion_actions,'Convert',self.start,primary=True);self.convert.pack(side='left',padx=(0,6))
        self.cancel=self.button(conversion_actions,'Cancel',self.cancel_job);self.cancel.pack(side='left');self.cancel.configure(state='disabled')
        ttk.Label(conversion_actions,text='Textured preview',style='Muted.TLabel').pack(side='right')
        # Pack the fixed view controls first so the preview receives only the
        # remaining space, keeping buttons accessible when the window shrinks.
        controls=ttk.Frame(preview_group);controls.pack(side='bottom',fill='x',pady=(8,0))
        for label,view in (('¾','front-left'),('Front','front'),('Rear','back'),('Left','left'),('Right','right')):
            self.button(controls,label,lambda v=view:self.set_view(v)).pack(side='left',padx=(0,4))
        self.button(controls,'Zoom',self.toggle_zoom).pack(side='right')
        self.preview=tk.Label(preview_group,text='Convert a model to preview the PSP output',bg=PANEL,fg=MUTED,
            cursor='hand2',relief='sunken',borderwidth=1)
        self.preview.pack(fill='both',expand=True);self.preview.bind('<Configure>',lambda e:self.show_preview());self.preview.bind('<Button-1>',lambda e:self.enlarge())
        actions=ttk.Frame(right);actions.pack(side='bottom',fill='x',pady=(4,6))
        self.save=self.button(actions,'Save PAC As...',self.export);self.save.pack(side='left');self.save.configure(state='disabled')
        self.button(actions,'QA report',self.open_report).pack(side='left',padx=6)
        self.button(actions,'Open folder',self.open_folder).pack(side='left')
        self.output_label=ttk.Label(right,textvariable=self.output,style='Muted.TLabel',wraplength=630,justify='left')
        self.output_label.pack(side='bottom',fill='x',pady=(8,4))
        right.bind('<Configure>',lambda e:self.output_label.configure(wraplength=max(200,e.width)))
        self.root.protocol('WM_DELETE_WINDOW',self.close);self.root.after(200,self.poll)

    def button(self,parent,text,command,primary=False):
        return ttk.Button(parent,text=text,command=command,width=max(5,len(text)+2),
            default='active' if primary else 'normal')
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
        (self.job/'request.json').write_text(json.dumps(dict(source=self.source,base=self.base.get(),source_format='hctp',adaptive_textures=self.adaptive_textures.get())),encoding='utf-8')
        self.result=None;self.save.configure(state='disabled');self.convert.configure(state='disabled');self.base_button.configure(state='disabled');self.cancel.configure(state='normal')
        self.adaptive_checkbox.configure(state='disabled')
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
                self.adaptive_checkbox.configure(state='normal')
                try:
                    if not (self.job/'success.json').exists():
                        failure=json.loads((self.job/'failure.json').read_text(encoding='utf-8'));self.status.set(failure['error'])
                        if not failure['cancelled']:messagebox.showerror('Conversion stopped',failure['error']+'\n\nUse Logs for diagnostics.')
                    else:
                        self.result=json.loads((self.job/'success.json').read_text(encoding='utf-8'));r=self.result
                        self.output.set(f"{Path(r['pac']).name}  •  {r['bytes']:,} bytes\nNative checks passed • {r.get('model_count',1)} models • {r.get('total_meshes',r['meshes'])} meshes • {r.get('total_triangles',r['triangles']):,} triangles\nQA: {r['review_flags']} findings to review • PPSSPP validation required")
                        if r.get('adaptive_textures'):
                            self.output.set(self.output.get()+f"\nAdaptive textures: {r['adaptive_textures']['review_flags']} texture tradeoffs — open QA report")
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
