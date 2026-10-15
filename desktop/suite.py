"""Classic desktop suite shell; conversion remains the existing isolated worker."""
import json
from pathlib import Path
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import uuid
import webbrowser

from PIL import Image, ImageTk

from desktop.storage import data_dir, save_settings

TABS = ('Converter', 'PSP Model Editor', 'Textures', 'Quality Assurance', 'Model Creator')


class SuiteShell:
    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.process = None
        self.log = None
        self.manifest = None
        self.job = None
        self.active_source = None
        self.pending_source = None
        self.model_index = 0
        self.view = 'front-left'
        self.photo = self.texture_photo = None
        self.closing = False
        self.status = tk.StringVar(value='Open a native PSP PAC to inspect its models and textures.')
        header = ttk.Frame(self.root, padding=(12, 8))
        header.pack(fill='x')
        ttk.Label(header, text='PSP Model Suite', font=('Segoe UI', 12)).pack(side='left')
        ttk.Label(header, text='by RyosPrime', style='Muted.TLabel').pack(side='left', padx=10)
        ttk.Label(header, text='Foundation preview', style='Muted.TLabel').pack(side='right')
        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill='both', expand=True, padx=6, pady=(0, 6))
        self.pages = {}
        for name in TABS:
            page = ttk.Frame(self.tabs)
            self.tabs.add(page, text=name)
            self.pages[name] = page
        self.converter = self.pages['Converter']
        self.build_editor()
        self.build_textures()
        self.build_qa()
        self.build_creator()
        remembered = app.settings.get('editor_pac_folder')
        if remembered:
            self.pac_browser.set_folder(remembered, remember=False, show_errors=False)
        self.root.after(150, self.poll)

    def button(self, parent, text, command):
        return self.app.button(parent, text, command)

    def build_editor(self):
        page = self.pages['PSP Model Editor']
        toolbar = ttk.Frame(page, padding=10)
        toolbar.pack(fill='x')
        self.open_button = self.button(toolbar, 'Open PSP PAC...', self.browse)
        self.open_button.pack(side='left')
        self.export_button = self.button(toolbar, 'Export previews...', self.export)
        self.export_button.pack(side='left', padx=6)
        self.copy_button = self.button(toolbar, 'Save unchanged copy...', self.save_copy)
        self.copy_button.pack(side='left')
        for button in (self.export_button, self.copy_button):
            button.configure(state='disabled')
        ttk.Label(page, textvariable=self.status, wraplength=880, padding=(10, 0, 10, 6)).pack(fill='x')
        split = ttk.Panedwindow(page, orient='horizontal')
        split.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        from desktop.pac_browser import PacBrowser
        self.pac_browser = PacBrowser(split, on_select=self.open_pac, on_folder=self.remember_folder)
        left, right = ttk.Frame(split), ttk.LabelFrame(split, text='Native PSP rest preview', padding=8)
        split.add(self.pac_browser, weight=0)
        split.add(left, weight=2)
        split.add(right, weight=3)
        self.editor_split = split
        self.editor_layout_ready = False
        def initial_layout(event=None):
            if not self.editor_layout_ready and split.winfo_width()>500:
                split.sashpos(0, 210)
                split.sashpos(1, max(420, split.winfo_width()-430))
                self.editor_layout_ready = True
        split.bind('<Configure>', initial_layout)
        self.model_tree = ttk.Treeview(left, columns=('vertices', 'triangles', 'state'), selectmode='browse')
        self.model_tree.heading('#0', text='Model / mesh')
        self.model_tree.column('#0', width=155, minwidth=80)
        for name, title, width in [('vertices', 'Vertices', 65), ('triangles', 'Triangles', 65), ('state', 'Status', 85)]:
            self.model_tree.heading(name, text=title)
            self.model_tree.column(name, width=width, minwidth=45)
        scroll = ttk.Scrollbar(left, orient='vertical', command=self.model_tree.yview)
        horizontal = ttk.Scrollbar(left, orient='horizontal', command=self.model_tree.xview)
        self.model_tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        scroll.pack(side='right', fill='y')
        horizontal.pack(side='bottom', fill='x')
        self.model_tree.pack(fill='both', expand=True)
        self.model_tree.bind('<<TreeviewSelect>>', self.select_model)
        views = ttk.Frame(right)
        views.pack(fill='x', pady=(0, 8))
        for label, view in [('¾', 'front-left'), ('Front', 'front'), ('Rear', 'back'), ('Left', 'left'), ('Right', 'right')]:
            self.button(views, label, lambda v=view: self.set_view(v)).pack(side='left', padx=(0, 3))
        self.preview = tk.Label(right, bg='#484848', fg='white', text='Open a PSP PAC to preview it.')
        self.preview.pack(fill='both', expand=True)
        self.preview.bind('<Configure>', lambda event: self.show_preview())
        ttk.Label(right, text='Offline rest geometry. Game shading and animation may differ.',
                  style='Muted.TLabel', wraplength=420).pack(fill='x', pady=(6, 0))

    def build_textures(self):
        page = self.pages['Textures']
        toolbar = ttk.Frame(page, padding=10)
        toolbar.pack(fill='x')
        self.button(toolbar, 'Open PSP PAC...', self.browse).pack(side='left')
        self.button(toolbar, 'Conversion texture options', lambda: self.tabs.select(self.converter)).pack(side='left', padx=6)
        ttk.Label(page, text='Inspect original embedded textures here. Choose conversion policies in Converter.',
                  padding=(10, 0, 10, 8)).pack(fill='x')
        split = ttk.Panedwindow(page, orient='horizontal')
        split.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        left, right = ttk.Frame(split), ttk.Frame(split)
        split.add(left, weight=2)
        split.add(right, weight=3)
        self.texture_tree = ttk.Treeview(left, columns=('size', 'palette', 'bytes'), selectmode='browse')
        self.texture_tree.heading('#0', text='Texture / section')
        self.texture_tree.column('#0', width=170, minwidth=80)
        for name, title in [('size', 'Dimensions'), ('palette', 'CLUT'), ('bytes', 'Bytes')]:
            self.texture_tree.heading(name, text=title)
            self.texture_tree.column(name, width=75, minwidth=45)
        scroll = ttk.Scrollbar(left, orient='vertical', command=self.texture_tree.yview)
        self.texture_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.texture_tree.pack(fill='both', expand=True)
        self.texture_tree.bind('<<TreeviewSelect>>', self.show_texture)
        self.texture_image = tk.Label(right, bg='#e3e5e8', text='Select a texture to inspect it.')
        self.texture_image.pack(fill='both', expand=True)
        self.texture_image.bind('<Configure>', self.show_texture)
        self.texture_info = tk.StringVar(value='Images are displayed at their original resolution or smaller.')
        ttk.Label(right, textvariable=self.texture_info, wraplength=440, padding=8).pack(fill='x')

    def build_qa(self):
        page = self.pages['Quality Assurance']
        toolbar = ttk.Frame(page, padding=10)
        toolbar.pack(fill='x')
        self.button(toolbar, 'Latest conversion report', self.conversion_report).pack(side='left')
        self.button(toolbar, 'Open saved QA report...', self.saved_report).pack(side='left', padx=6)
        self.button(toolbar, 'Inspection folder', self.open_folder).pack(side='left')
        self.qa_text = tk.Text(page, wrap='word', bg='white', fg='#202020', relief='sunken', borderwidth=1)
        scroll = ttk.Scrollbar(page, orient='vertical', command=self.qa_text.yview)
        self.qa_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y', pady=(0, 10))
        self.qa_text.pack(fill='both', expand=True, padx=(10, 0), pady=(0, 10))
        self.update_qa()

    def build_creator(self):
        page = self.pages['Model Creator']
        ttk.Label(page, text='Model Creator — planned', font=('Segoe UI', 12), padding=16).pack(anchor='w')
        ttk.Label(page, text='The creator will assemble compatible bodies, limbs, heads and hair on a PSP skeleton.\n'
                  'Asset libraries, attachment rules and creator exports are not available in this foundation preview.',
                  padding=(16, 0, 16, 12), wraplength=800, justify='left').pack(anchor='w')
        group = ttk.LabelFrame(page, text='Development sequence', padding=12)
        group.pack(fill='x', padx=16)
        for text in ('1. Native PSP inspection and exact-copy validation — available in Model Editor',
                     '2. Validated texture replacement, UV editing and geometry reimport — planned',
                     '3. Compatible modular parts, seam handling and skinning — planned',
                     '4. Body, head, limb and hair libraries — planned; no game assets bundled'):
            ttk.Label(group, text=text, wraplength=800).pack(anchor='w', pady=5)
        formats = ttk.LabelFrame(page, text='Converter roadmap', padding=12)
        formats.pack(fill='x', padx=16, pady=12)
        ttk.Label(formats, text='Available: HCTP → SVR 2011 PSP\n'
                  'Planned: SYM, JBI, PS2 SVR, PS3/X360 SVR and WK adapters; PS1 texture styling.\n'
                  'Each source format needs its own sample analysis and compatibility tests.',
                  wraplength=800, justify='left').pack(anchor='w')

    def browse(self):
        if self.busy():
            return
        path = filedialog.askopenfilename(title='Open native PSP wrestler PAC', filetypes=[('PAC files', '*.pac *.PAC')])
        if path:
            self.open_pac(path)

    def busy(self):
        return self.process is not None

    def remember_folder(self, path):
        self.app.settings['editor_pac_folder'] = str(path)
        save_settings(self.app.settings)

    def open_pac(self, path):
        if self.closing:
            return
        path = Path(path).resolve()
        if self.busy():
            # Keep list/keyboard navigation live. Only the latest request wins;
            # never display an older completed job over a newer selected file.
            self.pending_source = path if path!=self.active_source else None
            self.status.set('Waiting to open '+path.name+' — finishing the current read-only inspection.')
            return
        self.active_source = path
        self.pending_source = None
        self.job = data_dir()/'suite'/'jobs'/uuid.uuid4().hex
        self.job.mkdir(parents=True)
        self.log = (self.job/'inspection.log').open('w', encoding='utf-8')
        try:
            self.process = subprocess.Popen(self.app.entry()+['--suite-inspect', str(Path(path).resolve()), str(self.job)],
                                            stdout=self.log, stderr=self.log,
                                            creationflags=0x08000000 if __import__('os').name=='nt' else 0)
        except OSError as exc:
            self.log.close()
            self.log = None
            self.status.set('Unable to start inspection: '+str(exc))
            messagebox.showerror('PSP inspection', str(exc))
            return
        self.status.set('Inspecting '+Path(path).name+' — previous workspace remains available when inspection fails.')
        self.open_button.configure(state='disabled')

    def poll(self):
        if self.process is not None and self.process.poll() is not None:
            code = self.process.returncode
            self.process = None
            self.log.close()
            self.log = None
            pending = self.pending_source
            self.pending_source = None
            self.active_source = None
            if not self.closing:
                self.open_button.configure(state='normal')
                if pending is not None:
                    self.open_pac(pending)
                else:
                    try:
                        response = json.loads((self.job/'result.json').read_text(encoding='utf-8'))
                        if code or not response['ok']:
                            raise ValueError(response.get('error', 'Inspection worker failed.'))
                        self.load_workspace(response['manifest'])
                    except (ValueError, OSError, KeyError) as exc:
                        self.status.set('Inspection failed. Previous workspace retained. Logs: '+str(self.job))
                        messagebox.showerror('PSP inspection', str(exc)+'\n\nLogs: '+str(self.job))
        if not self.closing or self.busy():
            self.root.after(150, self.poll)

    def load_workspace(self, path):
        from desktop.workspace import verified_snapshot
        manifest, _ = verified_snapshot(path)
        self.manifest_path = Path(path)
        self.manifest = manifest
        self.model_tree.delete(*self.model_tree.get_children())
        self.texture_tree.delete(*self.texture_tree.get_children())
        for model in manifest['models']:
            key = 'model_'+str(model['index'])
            self.model_tree.insert('', 'end', iid=key,
                text=f"Section {model['section']}: {model.get('name', 'Unknown layout')}",
                values=(model.get('vertices', '?'), model.get('triangles', '?'), 'Unsupported' if model['error'] else 'Audited'))
            if model.get('audit'):
                audit = json.loads((self.manifest_path.parent/model['audit']).read_text(encoding='utf-8'))
                for mesh in audit['mesh_reports']:
                    self.model_tree.insert(key, 'end', text=f"Mesh {mesh['mesh']}",
                        values=(mesh['vertices'], mesh['triangles'], str(mesh['vertex_stride'])+' B/vertex'))
        for row in manifest['textures']:
            self.texture_tree.insert('', 'end', iid=str(row['index']), text=f"{row['name']} / {row['section']}",
                values=(f"{row['width']} × {row['height']}" if row.get('png') else 'Unsupported',
                        row.get('palette_entries', '?'), row['bytes']))
        for button in (self.export_button, self.copy_button):
            button.configure(state='normal')
        self.model_index = 0
        self.model_tree.selection_set('model_0')
        if manifest['textures']:
            self.texture_tree.selection_set('0')
        else:
            self.texture_image.configure(image='', text='No named texture table found.')
        self.status.set(f"{Path(manifest['source']).name} • {manifest['bytes']:,} bytes • "
                        f"{len(manifest['models'])} models • {len(manifest['textures'])} textures • "
                        f"{len(manifest['findings'])} inspection findings")
        self.update_qa()
        self.show_preview()
        self.show_texture()

    def select_model(self, event=None):
        selected = self.model_tree.selection()
        if not selected:
            return
        key = selected[0]
        while self.model_tree.parent(key):
            key = self.model_tree.parent(key)
        self.model_index = int(key.split('_')[1])
        self.show_preview()

    def set_view(self, view):
        self.view = view
        self.show_preview()

    def show_preview(self):
        if not self.manifest:
            return
        model = self.manifest['models'][self.model_index]
        image_path = model['views'].get(self.view)
        if not image_path:
            self.preview.configure(image='', text=model['error'] or model['preview_error'] or 'Preview unavailable.')
            return
        with Image.open(self.manifest_path.parent/image_path) as source:
            image = source.copy()
        image.thumbnail((max(1, self.preview.winfo_width()-8), max(1, self.preview.winfo_height()-8)))
        self.photo = ImageTk.PhotoImage(image, master=self.root)
        self.preview.configure(image=self.photo, text='')

    def show_texture(self, event=None):
        if not self.manifest or not self.texture_tree.selection():
            return
        row = self.manifest['textures'][int(self.texture_tree.selection()[0])]
        if not row['png']:
            self.texture_image.configure(image='', text='Unsupported texture layout: '+str(row['error']))
            return
        with Image.open(self.manifest_path.parent/row['png']) as source:
            image = source.convert('RGBA')
        image.thumbnail((max(1, self.texture_image.winfo_width()-16), max(1, self.texture_image.winfo_height()-16)))
        from PIL import ImageDraw
        background = Image.new('RGBA', image.size, '#ffffff')
        draw = ImageDraw.Draw(background)
        for y in range(0, image.height, 8):
            for x in range(0, image.width, 8):
                if (x//8+y//8)%2:
                    draw.rectangle((x, y, x+7, y+7), fill='#cccccc')
        background.alpha_composite(image)
        self.texture_photo = ImageTk.PhotoImage(background, master=self.root)
        self.texture_image.configure(image=self.texture_photo, text='')
        self.texture_info.set(f"{row['name']} — {row['width']}×{row['height']}, {row['palette_entries']} palette entries, "
                              f"{row['used_colors']} used RGBA colors, {row['bytes']:,} encoded bytes\n"
                              f"Transparency: {'present' if row['alpha'] else 'opaque'} • no upscaling")

    def update_qa(self):
        text = 'QUALITY ASSURANCE\n\nConversion reports retain the existing source comparison, stage traces, '
        text += 'anatomical checks and analytical poses. Open the latest conversion report above.\n\n'
        if self.manifest:
            m = self.manifest
            text += f"PSP inspection: {Path(m['source']).name}\nSHA-256: {m['source_sha256']}\n"
            text += 'Native YOBJ audits validate supported pointers, ranges, indices, palettes and weights.\n'
            text += f"Converter export profile: {'PASS' if m['converter_export_profile']['passed'] else 'REVIEW / unsupported'}\n"
            text += f"Configured conversion budget: {m['bytes']:,} / {m['conversion_budget_bytes']:,} bytes\n"
            text += 'The conversion budget is not a proven universal native PAC size limit.\n'
            text += 'No geometric source comparison or animation validation was run by native inspection.\n\n'
            text += '\n'.join(m['findings']) if m['findings'] else 'No inspection findings for the supported profile.'
        else:
            text += 'Open a native PSP PAC in Model Editor to see its structural inspection here.'
        text += '\n\nStructural success does not establish in-game compatibility. Preserve accepted baselines and test changes in PPSSPP.'
        self.qa_text.configure(state='normal')
        self.qa_text.delete('1.0', 'end')
        self.qa_text.insert('1.0', text)
        self.qa_text.configure(state='disabled')

    def conversion_report(self):
        if self.app.result:
            self.app.open_report()
        else:
            messagebox.showinfo('Quality Assurance', 'Run a conversion first, or open a saved QA report.')

    def saved_report(self):
        path = filedialog.askopenfilename(title='Open saved QA report', filetypes=[('HTML reports', '*.html')])
        if path:
            webbrowser.open(Path(path).resolve().as_uri())

    def open_folder(self):
        if self.manifest:
            self.app.open_path(self.manifest_path.parent)

    def save_copy(self):
        if not self.manifest:
            return
        path = filedialog.asksaveasfilename(title='Save byte-identical PSP PAC copy (new filename)',
            defaultextension='.pac', initialfile=Path(self.manifest['source']).stem+'-copy.pac', filetypes=[('PSP PAC', '*.pac')])
        if path:
            from desktop.workspace import copy_original
            try:
                copy_original(self.manifest_path, path)
                self.status.set('Saved byte-identical PAC copy: '+path)
            except (ValueError, OSError) as exc:
                messagebox.showerror('Copy withheld', str(exc))

    def export(self):
        if not self.manifest:
            return
        path = filedialog.asksaveasfilename(title='Export native YOBJ and OBJ/texture previews',
            defaultextension='.zip', initialfile=Path(self.manifest['source']).stem+'-previews.zip', filetypes=[('ZIP archive', '*.zip')])
        if path:
            from desktop.workspace import export_previews
            try:
                export_previews(self.manifest_path, path)
                self.status.set('Exported previews: '+path)
            except (ValueError, OSError) as exc:
                messagebox.showerror('Preview export', str(exc))

    def close(self):
        self.closing = True
        self.pending_source = None
        self.pac_browser.cancel_selection()
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
