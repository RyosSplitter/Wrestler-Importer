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
from desktop.texture_modes import MODES,HELP

BG='#f0f0f0';PANEL='#e3e5e8';FG='#202020';MUTED='#606060'

class Application:
    def __init__(self, *, suite=True):
        from tkinterdnd2 import TkinterDnD,DND_FILES
        self.root=TkinterDnD.Tk();self.drag_drop=True
        self.root.title('PSP Model Suite by RyosPrime' if suite else NAME);self.root.configure(bg=BG)
        # Leave room for the title bar/taskbar on a 1024x768 desktop. Explicit
        # placement also avoids the window manager's cascading off-screen origin.
        screen_w,screen_h=self.root.winfo_screenwidth(),self.root.winfo_screenheight()
        width=max(940,min(1040,screen_w-64));height=max(640,min(720,screen_h-120))
        x=max(0,(screen_w-width)//2);y=max(0,(screen_h-height)//2-20)
        self.root.geometry(f'{width}x{height}+{x}+{y}');self.root.minsize(940,640)
        self.settings=load_settings();self.source=None;self.process=None;self.result=None;self.saved=None;self.closing=False
        from desktop.conversion_timer import ConversionTimer
        self.conversion_timer=ConversionTimer();self.timing_profile=None;self.event_rows=0
        self.timer_text=tk.StringVar(value=self.conversion_timer.text())
        self.inspector=None;self.inspect_root=None;self.view='front-left';self.zoom='full';self.photo=None
        self.source_format=tk.StringVar(value='hctp');self.source_entry=tk.StringVar(value='')
        self.costume_role=tk.StringVar(value='ring')
        self.wii_geometry=tk.StringVar(value='Standard')
        self.base=tk.StringVar(value=self.settings.get('base',''));self.status=tk.StringVar(value='Choose your PSP base once, then drop an HCTP PAC.')
        # Session-only and deliberately OFF, even when an earlier job enabled it.
        self.texture_mode=tk.StringVar(value='Default')
        self.downgrade_steps=tk.StringVar(value='1 size')
        self.texture_help=tk.StringVar(value=HELP['Default'])
        self.skin_palette_compatibility=tk.BooleanVar(value=True)
        self.priority_textures=();self.source_inspection=None
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

        self.suite=None
        if suite:
            from desktop.suite import SuiteShell
            self.suite=SuiteShell(self)
            container=self.suite.converter
        else:
            container=self.root
            header=ttk.Frame(container,padding=(12,10,12,6));header.pack(fill='x')
            ttk.Label(header,text='PS2PSP PAC Converter',font=('Segoe UI',12)).pack(side='left')
            ttk.Label(header,text='by RyosPrime',style='Muted.TLabel').pack(side='left',padx=10)
            ttk.Label(header,text='v'+VERSION,style='Muted.TLabel').pack(side='right')
            ttk.Separator(container).pack(fill='x',padx=12)

        # Reserve the status bar before the expanding body so it remains visible
        # at the minimum window size and at enlarged Windows text scales.
        footer=ttk.Frame(container,padding=(12,6,12,10));footer.pack(side='bottom',fill='x')
        self.progress=ttk.Progressbar(footer,maximum=100);self.progress.pack(fill='x',pady=(0,6))
        self.timer_label=ttk.Label(footer,textvariable=self.timer_text,style='Muted.TLabel')
        self.timer_label.pack(fill='x',pady=(0,4))
        status_row=ttk.Frame(footer);status_row.pack(fill='x')
        self.button(status_row,'Logs',self.open_logs).pack(side='right',padx=(8,0))
        self.status_label=ttk.Label(status_row,textvariable=self.status,style='Muted.TLabel',wraplength=850)
        self.status_label.pack(side='left',fill='x',expand=True)
        status_row.bind('<Configure>',lambda e:self.status_label.configure(wraplength=max(200,e.width-90)))

        body=ttk.Frame(container,padding=(12,10,12,0));body.pack(fill='both',expand=True)
        sidebar=ttk.Frame(body,width=352);sidebar.pack(side='left',fill='y',padx=(0,12));sidebar.pack_propagate(False)
        self.left_canvas=tk.Canvas(sidebar,width=340,bg=BG,highlightthickness=0)
        self.left_canvas.pack(side='left',fill='both',expand=True)
        self.left_scrollbar=ttk.Scrollbar(sidebar,orient='vertical',command=self.left_canvas.yview)
        self.left_canvas.configure(yscrollcommand=self.left_scrollbar.set)
        left=ttk.Frame(self.left_canvas)
        self.left_window=self.left_canvas.create_window((0,0),window=left,anchor='nw')
        def sidebar_layout(event=None):
            self.left_canvas.configure(scrollregion=self.left_canvas.bbox('all'))
            if left.winfo_reqheight()>self.left_canvas.winfo_height():
                self.left_scrollbar.pack(side='right',fill='y')
            else:self.left_scrollbar.pack_forget();self.left_canvas.yview_moveto(0)
        def sidebar_width(event):
            self.left_canvas.itemconfigure(self.left_window,width=event.width);sidebar_layout()
        left.bind('<Configure>',sidebar_layout);self.left_canvas.bind('<Configure>',sidebar_width)
        self.root.bind('<MouseWheel>',self.scroll_sidebar,add='+')
        self.root.bind('<Button-4>',self.scroll_sidebar,add='+');self.root.bind('<Button-5>',self.scroll_sidebar,add='+')
        right=ttk.Frame(body);right.pack(side='left',fill='both',expand=True)
        source_group=ttk.LabelFrame(left,text='Source PAC',padding=10);source_group.pack(fill='x')
        menu=ttk.Menubutton(source_group,text=FORMATS[2].label);self.source_button=menu
        choices=tk.Menu(menu,tearoff=False)
        for item in FORMATS:choices.add_command(label=item.label+(' — Coming soon' if not item.supported else ''),state='normal' if item.supported else 'disabled',
            command=lambda key=item.key:self.choose_source_format(key))
        menu.configure(menu=choices);menu.pack(fill='x',pady=(0,10))
        self.source_menu=choices
        self.drop=tk.Label(source_group,text='Drop an HCTP .pac here\nor click to browse',bg='#ffffff',fg=MUTED,
            height=4,cursor='hand2',relief='sunken',borderwidth=1,wraplength=290)
        self.drop.pack(fill='x');self.drop.bind('<Button-1>',lambda e:self.browse_source());self.drop.drop_target_register(DND_FILES)
        self.drop.dnd_bind('<<Drop>>',self.dropped)
        self.source_entry_row=ttk.Frame(source_group)
        ttk.Label(self.source_entry_row,text='Archive costume:').pack(side='left',padx=(0,8))
        self.source_entry_dropdown=ttk.Combobox(self.source_entry_row,textvariable=self.source_entry,width=9,state='readonly')
        self.source_entry_dropdown.pack(side='left');self.source_entry_dropdown.bind('<<ComboboxSelected>>',lambda e:self.change_source_entry())
        self.source_entry_count=ttk.Label(self.source_entry_row,style='Muted.TLabel');self.source_entry_count.pack(side='left',padx=8)
        self.costume_role_row=ttk.Frame(source_group)
        ttk.Label(self.costume_role_row,text='Output use:').pack(side='left',padx=(0,8))
        self.costume_role_dropdown=ttk.Combobox(self.costume_role_row,textvariable=self.costume_role,values=('ring','entrance'),state='readonly',width=10)
        self.costume_role_dropdown.pack(side='left')
        ttk.Label(self.costume_role_row,text='Choose explicitly',style='Muted.TLabel').pack(side='left',padx=6)
        self.wii_geometry_row=ttk.Frame(source_group)
        ttk.Label(self.wii_geometry_row,text='Geometry:').pack(side='left',padx=(0,8))
        self.wii_geometry_dropdown=ttk.Combobox(self.wii_geometry_row,textvariable=self.wii_geometry,values=('Standard','Preserve Hands','Preserve Arms'),state='readonly',width=17)
        self.wii_geometry_dropdown.pack(side='left')
        ttk.Label(source_group,textvariable=self.info,style='Muted.TLabel',wraplength=310,justify='left').pack(fill='x',pady=(8,0))
        base_group=ttk.LabelFrame(left,text='PSP base PAC',padding=10);base_group.pack(fill='x',pady=(10,0))
        ttk.Label(base_group,textvariable=self.base,wraplength=310,justify='left').pack(fill='x',pady=(0,8))
        self.base_button=self.button(base_group,'Choose PSP base PAC...',self.choose_base);self.base_button.pack(fill='x')
        ttk.Label(base_group,text='Remembered on this computer.',style='Muted.TLabel').pack(anchor='w',pady=(6,0))
        texture_group=ttk.LabelFrame(left,text='Textures',padding=8);texture_group.pack(fill='x',pady=(8,0))
        self.texture_dropdown=ttk.Combobox(texture_group,textvariable=self.texture_mode,values=MODES,state='readonly')
        self.texture_dropdown.pack(fill='x')
        self.texture_dropdown.bind('<<ComboboxSelected>>',lambda e:self.update_texture_mode())
        self.downgrade_row=ttk.Frame(texture_group)
        ttk.Label(self.downgrade_row,text='Reduce by:').pack(side='left',padx=(0,8))
        self.downgrade_dropdown=ttk.Combobox(self.downgrade_row,textvariable=self.downgrade_steps,
            values=('1 size','2 sizes','3 sizes'),state='readonly',width=12)
        self.downgrade_dropdown.pack(side='left')
        self.texture_help_label=ttk.Label(texture_group,textvariable=self.texture_help,style='Muted.TLabel',wraplength=305,justify='left')
        self.texture_help_label.pack(fill='x',pady=(6,0))
        options=ttk.LabelFrame(left,text='Options',padding=8);options.pack(fill='x',pady=(8,0))
        self.skin_checkbox=tk.Checkbutton(options,text='Single-slot skinning compatibility',
            variable=self.skin_palette_compatibility,bg=BG,fg=FG,selectcolor='#ffffff',activebackground=BG,
            activeforeground=FG,anchor='w',justify='left',wraplength=280)
        self.skin_checkbox.pack(fill='x')
        ttk.Label(left,text="Target: SVR 2011 PSP\nHCTP / JBI supported; WWE ’13 Wii experimental.",
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
    def choose_source_format(self,key):
        if self.busy() or self.inspector is not None:return
        selected=next((f for f in FORMATS if f.key==key and f.supported),None)
        if selected is None:return
        self.source_format.set(key);self.source_button.configure(text=selected.label)
        self.source_entry.set('');self.source_entry_row.pack_forget();self.source_entry_dropdown.configure(values=())
        self.costume_role.set('ring')
        self.wii_geometry.set('Standard')
        if key=='wwe13-wii':
            self.costume_role_row.pack(fill='x',pady=(8,0));self.wii_geometry_row.pack(fill='x',pady=(8,0))
        else:self.costume_role_row.pack_forget();self.wii_geometry_row.pack_forget()
        self.skin_checkbox.configure(state='disabled' if key=='wwe13-wii' else 'normal')
        self.clean_inspection();self.source=None;self.source_inspection=None;self.priority_textures=();self.result=None
        self.save.configure(state='disabled');self.info.set('No source selected')
        self.drop.configure(text='Drop a '+({'jbi':'JBI','wwe13-wii':"WWE ’13 Wii"}.get(key,'HCTP'))+' .pac here\nor click to browse')
        self.preview.configure(image='',text='Convert a model to preview the PSP output')
        self.output.set('Your converted PSP output will appear here.')
        values=('Default',) if key=='wwe13-wii' else tuple(m for m in MODES if key!='jbi' or m!='Legacy')
        self.texture_dropdown.configure(values=values)
        if self.texture_mode.get() not in values:self.texture_mode.set('Default')
        self.update_texture_mode();self.status.set('Choose a '+({'jbi':'JBI archive or extracted costume PAC.','wwe13-wii':"WWE ’13 Wii PAC. Experimental; review each costume and choose ring/entrance explicitly."}.get(key,'supported HCTP source PAC.')))
    def change_source_entry(self):
        if self.busy() or self.inspector is not None:return
        path=self.source or getattr(self,'pending_source',None)
        if path:self.select_source(path,entry_id=self.source_entry.get())
    def browse_source(self):
        if self.busy():return
        selected=filedialog.askopenfilename(title='Select '+self.source_button.cget('text')+' source PAC',filetypes=[('PAC files','*.pac *.PAC')])
        if selected:self.select_source(selected)
    def dropped(self,event):
        if self.busy():return
        files=self.root.tk.splitlist(event.data)
        if len(files)!=1:messagebox.showerror(NAME,'Drop one .pac file at a time.');return
        self.select_source(files[0])
    def select_source(self,path,entry_id=''):
        if self.busy():return
        if self.inspector is not None:messagebox.showinfo(NAME,'Wait for the current input check to finish.');return
        path=Path(path)
        if not path.is_file() or path.suffix.lower()!='.pac':messagebox.showerror(NAME,'Select an existing .pac file.');return
        with path.open('rb') as stream:magic=stream.read(4)
        if magic==b'DPAC' and self.source_format.get()!='jbi':self.choose_source_format('jbi')
        # EPK8 is shared with unimplemented platforms; do not auto-detect Wii
        # from that magic alone or feed Xbox 360 through the Wii decoder.
        self.source_entry.set(entry_id if self.source_format.get() in ('jbi','wwe13-wii') else '')
        self.clean_inspection()
        self.priority_textures=();self.source_inspection=None
        self.source=None;self.result=None;self.save.configure(state='disabled');self.convert.configure(state='disabled')
        self.drop.configure(text=path.name);self.info.set('Checking container and PS2 textures…');self.output.set('Your converted PSP output will appear here.');self.preview.configure(image='',text='Checking source…')
        self.inspect_root=Path(tempfile.mkdtemp(prefix='inspect-',dir=data_dir()));self.pending_source=str(path.resolve())
        self.source_button.configure(state='disabled');self.source_entry_dropdown.configure(state='disabled')
        self.inspector=self.spawn(['--inspect',self.pending_source,str(self.inspect_root/'result.json'),self.source_format.get(),self.source_entry.get()])
    def choose_base(self):
        if self.busy():return
        chosen=filedialog.askopenfilename(title='Select your own PSP SVR base wrestler PAC',filetypes=[('PAC files','*.pac *.PAC')])
        if chosen:self.base.set(chosen);self.settings['base']=chosen;save_settings(self.settings)
    def update_texture_mode(self):
        mode=self.texture_mode.get();self.texture_help.set(HELP[mode])
        if self.source_format.get()=='wwe13-wii':
            self.texture_help.set('Experimental Wii atlas allocation: nearest source alpha, measured T4/T8 storage and palette safeguards. Default only in this preview; other modes remain available for HCTP/JBI.')
        if self.source_format.get()=='jbi' and mode in ('Default','ATO','Priority Selection'):
            self.texture_help.set({'Default':'Validated JBI atlas allocation. Preserves detail within actual PAC and native-base texture budgets.',
                'ATO':'Alternate content-aware texture pass over JBI Default. Geometry, rigging and materials stay unchanged.',
                'Priority Selection':'Choose up to 3 JBI atlas charts to prioritize. Other textures may fund detail; reductions are reported.'}[mode])
        if mode=='Downgrade':self.downgrade_row.pack(fill='x',pady=(6,0),before=self.texture_help_label)
        else:self.downgrade_row.pack_forget()
    def scroll_sidebar(self,event):
        canvas=self.left_canvas
        if not canvas.winfo_rootx()<=event.x_root<canvas.winfo_rootx()+canvas.winfo_width():return
        if not self.left_scrollbar.winfo_ismapped():return
        if event.num in (4,5):step=-1 if event.num==4 else 1
        else:step=-1 if event.delta>0 else 1
        canvas.yview_scroll(step*3,'units')
    def start(self):
        if self.busy() or self.inspector is not None:return
        if not self.source:messagebox.showerror(NAME,'Choose a supported source PAC first.');return
        if not Path(self.base.get()).is_file():self.choose_base()
        if not Path(self.base.get()).is_file():return
        from desktop.core import Request
        try:Request(self.source,self.base.get(),source_format=self.source_format.get(),source_entry=self.source_entry.get(),costume_role=self.costume_role.get()).validate()
        except Exception as e:messagebox.showerror(NAME,str(e));return
        priorities=()
        mode=self.texture_mode.get()
        if mode=='Priority Selection':
            from desktop.texture_review import TextureChooser
            if not self.source_inspection or not self.source_inspection.get('texture_previews'):
                messagebox.showerror(NAME,'Source previews are unavailable. Select the source again.');return
            selection=TextureChooser(self.root,self.source_inspection['texture_previews'],self.priority_textures).show()
            if selection is None:return
            self.priority_textures=selection;priorities=selection
        options=dict(source=self.source,base=self.base.get(),source_format=self.source_format.get(),source_entry=self.source_entry.get(),
            costume_role=self.costume_role.get(),wii_geometry=self.wii_geometry.get(),
            texture_mode=mode,adaptive_textures=mode=='ATO',skin_palette_compatibility=self.skin_palette_compatibility.get(),
            downgrade_steps=int(self.downgrade_steps.get()[0]) if mode=='Downgrade' else 0,
            priority_textures=list(priorities),texture_review_sha256=self.source_inspection['source_sha256'] if priorities else '',
            texture_review_entry=self.source_inspection.get('selected_entry','') if priorities else '')
        try:Request(**options).validate()
        except Exception as e:messagebox.showerror(NAME,str(e));return
        self.job=data_dir()/'jobs'/uuid.uuid4().hex;self.job.mkdir(parents=True)
        (self.job/'request.json').write_text(json.dumps(options),encoding='utf-8')
        self.result=None;self.save.configure(state='disabled');self.convert.configure(state='disabled');self.base_button.configure(state='disabled');self.cancel.configure(state='normal')
        self.texture_dropdown.configure(state='disabled');self.downgrade_dropdown.configure(state='disabled')
        self.skin_checkbox.configure(state='disabled')
        self.source_button.configure(state='disabled');self.source_entry_dropdown.configure(state='disabled')
        self.costume_role_dropdown.configure(state='disabled')
        self.wii_geometry_dropdown.configure(state='disabled')
        self.output.set('Building an experimental PSP candidate…');self.preview.configure(image='',text='Converting…');self.progress['value']=0
        self.process=self.spawn(['--worker',str(self.job/'request.json')]);self.status.set('Starting isolated conversion job…')
        from desktop.conversion_timer import ConversionTimer,profile,read_history
        self.timing_profile=profile(options);self.event_rows=0
        self.conversion_timer=ConversionTimer(read_history(data_dir()/'conversion-timings.json').get(self.timing_profile,[]))
        self.conversion_timer.start();self.timer_text.set(self.conversion_timer.text())
    def cancel_job(self):
        if self.busy():
            (self.job/'cancel').touch();self.status.set('Cancelling and cleaning incomplete output…');self.cancel.configure(state='disabled')
            self.conversion_timer.cancel();self.timer_text.set(self.conversion_timer.text())
    def poll(self):
        if self.inspector is not None and self.inspector.poll() is not None:
            try:
                r=json.loads((self.inspect_root/'result.json').read_text())
                catalogue=r.get('catalogue') or r.get('info') or {}
                entries=catalogue.get('entries',[])
                if entries:
                    self.source_entry_dropdown.configure(values=tuple(e['id'] for e in entries))
                    if not self.source_entry.get():self.source_entry.set(catalogue['selected_entry'])
                    self.source_entry_count.configure(text=str(len(entries))+' entries')
                    self.source_entry_row.pack(fill='x',pady=(8,0))
                else:self.source_entry_row.pack_forget();self.source_entry.set('')
                if not r['ok']:raise ValueError(r['error'])
                self.source=self.pending_source;v=r['info']
                selected=(' • '+v['selected_entry']) if v.get('selected_entry') else ''
                self.info.set(f"{v['format']}{selected} • {v['model']}\n{v.get('entry_bytes',v['bytes']):,} source bytes • {v['triangles']:,} main-model triangles\n{v.get('model_count',1)} models • {v['textures']} textures")
                self.source_inspection=v
                self.status.set('Source validated. Ready to convert.')
            except Exception as e:self.info.set('Input rejected');self.status.set(str(e));messagebox.showerror('Input check',str(e))
            if self.source is None:self.clean_inspection()
            self.inspector=None;self.convert.configure(state='normal')
            self.source_button.configure(state='normal');self.source_entry_dropdown.configure(state='readonly')
        if self.busy():
            events=self.job/'events.jsonl'
            if events.exists():
                try:
                    rows=events.read_text(encoding='utf-8').splitlines()
                    for line in rows[self.event_rows:]:
                        r=json.loads(line);self.event_rows+=1
                        self.progress['value']=max(self.progress['value'],r['percent']);self.status.set(r['message'])
                        self.conversion_timer.observe(r['percent'],r.get('elapsed_seconds'))
                except (ValueError,IndexError):pass
            self.timer_text.set(self.conversion_timer.text())
            if self.process.poll() is not None:
                self.process=None;self.cancel.configure(state='disabled');self.convert.configure(state='normal');self.base_button.configure(state='normal')
                self.texture_dropdown.configure(state='readonly');self.downgrade_dropdown.configure(state='readonly')
                self.skin_checkbox.configure(state='disabled' if self.source_format.get()=='wwe13-wii' else 'normal')
                self.costume_role_dropdown.configure(state='readonly')
                self.wii_geometry_dropdown.configure(state='readonly')
                self.source_button.configure(state='normal');self.source_entry_dropdown.configure(state='readonly')
                try:
                    if not (self.job/'success.json').exists():
                        failure=json.loads((self.job/'failure.json').read_text(encoding='utf-8'));self.status.set(failure['error'])
                        self.finish_timer('cancelled'if failure['cancelled']else'failed')
                        if not failure['cancelled']:messagebox.showerror('Conversion stopped',failure['error']+'\n\nUse Logs for diagnostics.')
                    else:
                        self.result=json.loads((self.job/'success.json').read_text(encoding='utf-8'));r=self.result
                        self.finish_timer('completed')
                        self.output.set(f"{Path(r['pac']).name}  •  {r['bytes']:,} bytes\nNative checks passed • {r.get('model_count',1)} models • {r.get('total_meshes',r['meshes'])} meshes • {r.get('total_triangles',r['triangles']):,} triangles\nQA: {r['review_flags']} findings to review • PPSSPP validation required")
                        if r.get('adaptive_textures'):
                            self.output.set(self.output.get()+f"\nAdaptive textures: {r['adaptive_textures']['review_flags']} texture tradeoffs — open QA report")
                        if r.get('default_textures'):
                            t=r['default_textures']
                            self.output.set(self.output.get()+f"\nDefault textures: {len(t['automatic_priorities'])} automatic detail priorities — open QA report")
                            if t['detail_review_textures']:
                                self.output.set(self.output.get()+"\nDetail remains reduced: "+', '.join(t['detail_review_textures'])+" — inspect the preview or use Priority Selection")
                        if r.get('texture_priorities'):
                            t=r['texture_priorities'];self.output.set(self.output.get()+f"\nTexture priorities: {len(t['names'])} selected; {t['reductions']} still reduced — open QA report")
                            for selected in t['selected_settings']:
                                w,h=selected['selected_dimensions']
                                self.output.set(self.output.get()+f"\n{selected['name']}: {w}×{h}, {selected['selected_used_colors']} used colors")
                            if t.get('donor_textures'):
                                self.output.set(self.output.get()+f"\n{len(t['donor_textures'])} other textures changed to fund priorities — review tradeoffs")
                            if t.get('unimproved_textures'):
                                self.output.set(self.output.get()+"\nNo improvement available for: "+', '.join(t['unimproved_textures'])+" — see budget constraints in QA report")
                        if r.get('texture_downgrade'):
                            self.output.set(self.output.get()+f"\nDowngrade: {r['texture_downgrade']['steps']} steps from Default, 64-pixel floor — open QA report")
                        if r.get('maximum_downgrade'):
                            self.output.set(self.output.get()+f"\nMaximum Downgrade: {r['maximum_downgrade']['changed_textures']} textures reduced; model unchanged — open QA report")
                        self.save.configure(state='normal');self.status.set('Review the PSP preview and QA report before saving.');self.show_preview()
                except Exception as e:self.finish_timer('failed');self.status.set('Worker ended unexpectedly; inspect Logs.');messagebox.showerror(NAME,str(e))
        if self.closing and not self.busy() and self.inspector is None and not (self.suite and self.suite.busy()):self.clean_inspection();self.root.destroy();return
        self.root.after(200,self.poll)
    def finish_timer(self,status):
        trace=self.conversion_timer.finish(status);self.timer_text.set(self.conversion_timer.text())
        if trace is not None:
            from desktop.conversion_timer import save_trace
            try:save_trace(data_dir()/'conversion-timings.json',self.timing_profile,trace)
            except OSError:pass  # Timing history must never block a completed conversion.
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
    def clean_inspection(self):
        import shutil
        if self.inspect_root is not None:shutil.rmtree(self.inspect_root,ignore_errors=True)
        self.inspect_root=None
    def close(self):
        if self.suite and not self.suite.retexture.confirm_replace():return
        self.closing=True
        if self.suite:self.suite.close()
        if self.busy():self.cancel_job()
        elif self.inspector is None and not (self.suite and self.suite.busy()):self.clean_inspection();self.root.destroy()
