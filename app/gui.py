"""Tk desktop beta with drag/drop, persistent setup and a separate worker."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import uuid
import webbrowser

from app import VERSION
from app.pipeline import Job, ROOT
from app import settings

BG, PANEL, NAVY, BLUE, TEXT, MUTED = '#f1f5f9', '#ffffff', '#14243b', '#2563eb', '#172b45', '#62748b'


def open_folder(path):
    path = str(Path(path).resolve())
    if os.name == 'nt':
        os.startfile(path)
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', path])
    else:
        subprocess.Popen(['xdg-open', path])


def worker_command(request):
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--worker', str(request)]
    return [sys.executable, str(ROOT / 'wrestler_beta.py'), '--worker', str(request)]


class BetaApp:
    def __init__(self, root, drag_drop=False):
        self.root, self.drag_drop = root, drag_drop
        self.values = settings.load()
        self.process = None
        self.request_dir = None
        self.event_offset = 0
        self.cancelled = False
        self.result = None
        self.busy_widgets = []
        self.source = tk.StringVar(value=self.values['source'])
        self.target = tk.StringVar(value=self.values['target_game'])
        self.destination = tk.StringVar(value=self.values['output_parent'])
        self.status = tk.StringVar(value='Choose an HCTP source PAC to begin')
        self.summary = tk.StringVar(value='Your export and matching Noesis files will appear here.')
        self.setup_status = tk.StringVar()
        root.title(f'Wrestler Importer — {VERSION}')
        root.geometry('1040x740')
        root.minsize(940, 720)
        root.configure(bg=BG)
        root.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TFrame', background=BG)
        style.configure('Card.TFrame', background=PANEL)
        style.configure('TLabel', background=BG, foreground=TEXT, font=('Segoe UI', 10))
        style.configure('Card.TLabel', background=PANEL)
        style.configure('TButton', font=('Segoe UI', 10), padding=(12, 6))
        style.configure('Primary.TButton', background=BLUE, foreground='white', padding=(22, 10), font=('Segoe UI', 11, 'bold'))
        style.map('Primary.TButton', background=[('active', '#1d4ed8'), ('disabled', '#94a3b8')])
        style.configure('TEntry', padding=7)
        style.configure('TCombobox', padding=7)
        style.configure('Horizontal.TProgressbar', background=BLUE, troughcolor='#dbe5f1')
        self.build()
        self.refresh_setup()
        self.refresh_source()

    def build(self):
        header = tk.Frame(self.root, bg=NAVY, height=64)
        header.pack(fill='x')
        header.pack_propagate(False)
        tk.Label(header, text='WRESTLER IMPORTER', bg=NAVY, fg='white', font=('Segoe UI', 18, 'bold')).pack(side='left', padx=28)
        tk.Label(header, text='BETA 0.1.1', bg='#263c58', fg='#a9cdff', padx=12, pady=6,
                 font=('Segoe UI', 10, 'bold')).pack(side='right', padx=28)
        body = ttk.Frame(self.root, padding=16)
        body.pack(fill='both', expand=True)
        aside = tk.Frame(body, bg=BG, width=185)
        aside.pack(side='left', fill='y', padx=(0, 24))
        aside.pack_propagate(False)
        tk.Label(aside, text='PS2 → PSP', bg=BG, fg=TEXT, font=('Segoe UI', 17, 'bold')).pack(anchor='w', pady=(4, 6))
        tk.Label(aside, text='HCTP models\nPSP SVR games', justify='left', bg=BG, fg=MUTED,
                 font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 28))
        for text in ('1   Choose a PAC', '2   Convert', '3   Test in PPSSPP'):
            tk.Label(aside, text=text, bg=BG, fg=TEXT, font=('Segoe UI', 11), pady=10).pack(anchor='w')
        tk.Label(aside, text='WORKING PROFILE', bg=BG, fg=MUTED, font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(32, 8))
        tk.Label(aside, text='Opacity fix v1\n144 KB export limit', justify='left', bg=BG, fg=TEXT,
                 font=('Segoe UI', 10)).pack(anchor='w')
        setup = ttk.Button(aside, text='Tools & base setup', command=self.open_setup)
        setup.pack(anchor='w', pady=(28, 6))
        self.busy_widgets.append(setup)
        tk.Label(aside, textvariable=self.setup_status, wraplength=170, justify='left', bg=BG, fg=MUTED,
                 font=('Segoe UI', 9)).pack(anchor='w')

        main = ttk.Frame(body)
        main.pack(side='left', fill='both', expand=True)
        tk.Label(main, text='Bring a wrestler to PSP', bg=BG, fg=TEXT,
                 font=('Segoe UI', 20, 'bold')).pack(anchor='w')
        tk.Label(main, text='Uses the pipeline from your working opacity-fix model.', bg=BG, fg=MUTED,
                 font=('Segoe UI', 10)).pack(anchor='w', pady=(6, 14))
        source_card = ttk.Frame(main, style='Card.TFrame', padding=14)
        source_card.pack(fill='x')
        self.drop = tk.Label(source_card, text='Drop an HCTP PAC here', bg='#eff6ff', fg=BLUE,
                             font=('Segoe UI', 16, 'bold'), height=2, relief='flat', bd=0, cursor='hand2')
        self.drop.pack(fill='x')
        self.drop.bind('<Button-1>', lambda e: self.choose_source())
        self.path_label = tk.Label(source_card, text='', bg=PANEL, fg=MUTED, wraplength=620,
                                   font=('Segoe UI', 9))
        self.path_label.pack(fill='x', pady=(6, 0))
        if self.drag_drop:
            from tkinterdnd2 import DND_FILES
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind('<<Drop>>', self.on_drop)
        else:
            self.drop.config(text='Choose an HCTP PAC')
        browse = ttk.Button(source_card, text='Browse PAC…', command=self.choose_source)
        browse.pack(pady=(6, 0))
        self.busy_widgets.append(browse)

        row = ttk.Frame(main)
        row.pack(fill='x', pady=(12, 0))
        ttk.Label(row, text='Target game').pack(side='left')
        target = ttk.Combobox(row, textvariable=self.target, state='readonly', width=18,
                             values=['SVR 2006 PSP', 'SVR 2007 PSP', 'SVR 2008 PSP', 'SVR 2009 PSP', 'SVR 2010 PSP', 'SVR 2011 PSP'])
        target.pack(side='left', padx=12)
        self.target_widget = target
        self.busy_widgets.append(target)
        destination = ttk.Frame(main)
        destination.pack(fill='x', pady=8)
        ttk.Label(destination, text='Export folder').pack(anchor='w', pady=(0, 4))
        entry = ttk.Entry(destination, textvariable=self.destination)
        entry.pack(side='left', fill='x', expand=True)
        button = ttk.Button(destination, text='Choose…', command=self.choose_destination)
        button.pack(side='right', padx=(8, 0))
        self.busy_widgets.extend([entry, button])
        actions = ttk.Frame(main)
        actions.pack(fill='x', pady=(4, 8))
        self.convert_button = ttk.Button(actions, text='Convert to PSP', style='Primary.TButton', command=self.start)
        self.convert_button.pack(side='left')
        self.busy_widgets.append(self.convert_button)
        self.cancel_button = ttk.Button(actions, text='Cancel', state='disabled', command=self.cancel)
        self.cancel_button.pack(side='left', padx=10)
        self.progress = ttk.Progressbar(main, mode='determinate', maximum=100)
        self.progress.pack(fill='x')
        ttk.Label(main, textvariable=self.status, wraplength=650).pack(anchor='w', pady=(6, 6))
        result = ttk.Frame(main, style='Card.TFrame', padding=12)
        result.pack(fill='x', pady=(0, 4))
        ttk.Label(result, text='Export', style='Card.TLabel', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        ttk.Label(result, textvariable=self.summary, style='Card.TLabel', wraplength=650).pack(anchor='w', pady=6)
        result_actions = ttk.Frame(result, style='Card.TFrame')
        result_actions.pack(fill='x')
        self.output_button = ttk.Button(result_actions, text='Open PAC folder', state='disabled', command=lambda: open_folder(self.result['output']))
        self.output_button.pack(side='left')
        self.preview_button = ttk.Button(result_actions, text='Open Noesis files', state='disabled', command=lambda: open_folder(self.result['preview']))
        self.preview_button.pack(side='left', padx=8)
        self.logs_button = ttk.Button(result_actions, text='Open logs', state='disabled', command=self.open_logs)
        self.logs_button.pack(side='left')

    def refresh_source(self):
        value = self.source.get()
        if value:
            self.drop.config(text=Path(value).name)
            self.path_label.config(text=value)
        else:
            self.path_label.config(text='PS2 Here Comes the Pain wrestler PAC • one file at a time')

    def refresh_setup(self):
        ready = all(Path(self.values[k]).is_file() for k in ('base', 'reference', 'editor', 'blender'))
        self.setup_status.set('Tools and reference files selected' if ready else 'Select Blender 4.3.2 and your PSP mesh editor before converting.')

    def choose_source(self):
        if self.process:
            return
        file = filedialog.askopenfilename(parent=self.root, title='Choose an HCTP PS2 wrestler PAC', filetypes=[('PAC files', '*.pac *.PAC'), ('All files', '*.*')])
        if file:
            self.select_source(file)

    def select_source(self, file):
        path = Path(file)
        if not path.is_file() or path.suffix.lower() != '.pac':
            messagebox.showerror('Choose a PAC', 'Select one HCTP wrestler PAC file.', parent=self.root)
            return
        self.source.set(str(path.resolve()))
        self.refresh_source()
        self.status.set('Source selected. Ready to convert.')

    def on_drop(self, event):
        if self.process:
            return
        files = self.root.tk.splitlist(event.data)
        if len(files) != 1:
            messagebox.showerror('One file at a time', 'Drop one HCTP PAC to convert.', parent=self.root)
        else:
            self.select_source(files[0])

    def choose_destination(self):
        folder = filedialog.askdirectory(parent=self.root, title='Choose the export folder')
        if folder:
            self.destination.set(folder)

    def open_setup(self):
        if self.process:
            return
        dialog = tk.Toplevel(self.root)
        dialog.title('Tools & base setup')
        dialog.configure(bg=BG)
        dialog.transient(self.root)
        dialog.grab_set()
        panel = ttk.Frame(dialog, padding=24)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='One-time setup', font=('Segoe UI', 17, 'bold')).pack(anchor='w')
        ttk.Label(panel, text='The beta uses Blender 4.3.2 and your original PSP YOBJ editor.\nThe supplied Kurt base and Full Body reference are selected by default.').pack(anchor='w', pady=(8, 18))
        fields = {}
        for key, label in [('blender', 'Blender 4.3.2 executable'), ('editor', 'PSP YOBJ mesh editor executable'),
                           ('base', 'PSP base wrestler PAC'), ('reference', 'Weight reference YOBJ')]:
            ttk.Label(panel, text=label).pack(anchor='w', pady=(8, 4))
            row = ttk.Frame(panel)
            row.pack(fill='x')
            value = tk.StringVar(value=self.values[key])
            fields[key] = value
            ttk.Entry(row, textvariable=value, width=65).pack(side='left', fill='x', expand=True)
            def browse(k=key, v=value, title=label):
                kinds = [('Executable', '*.exe')] if k in ('blender', 'editor') and os.name == 'nt' else [('All files', '*.*')]
                file = filedialog.askopenfilename(parent=dialog, title=title, filetypes=kinds)
                if file:
                    v.set(file)
            ttk.Button(row, text='Browse…', command=browse).pack(side='left', padx=(8, 0))
        links = ttk.Frame(panel)
        links.pack(fill='x', pady=16)
        ttk.Button(links, text='Get Blender 4.3.2', command=lambda: webbrowser.open('https://download.blender.org/release/Blender4.3/')).pack(side='left')
        def restore():
            values = settings.defaults()
            for k in ('base', 'reference'):
                fields[k].set(values[k])
        ttk.Button(links, text='Use included references', command=restore).pack(side='left', padx=8)
        def save():
            chosen = {k: v.get().strip() for k, v in fields.items()}
            for k, value in chosen.items():
                if not Path(value).is_file():
                    messagebox.showerror('File not found', f'Choose a valid {k} file.', parent=dialog)
                    return
            self.values.update(chosen)
            self.save_settings()
            self.refresh_setup()
            dialog.destroy()
        ttk.Button(panel, text='Save setup', style='Primary.TButton', command=save).pack(anchor='e')

    def save_settings(self):
        self.values.update(source=self.source.get(), output_parent=self.destination.get(), target_game=self.target.get())
        settings.save(self.values)

    def set_busy(self, busy):
        for widget in self.busy_widgets:
            widget.configure(state='disabled' if busy else ('readonly' if widget is self.target_widget else 'normal'))
        self.cancel_button.configure(state='normal' if busy else 'disabled')

    def start(self):
        if self.process:
            return
        try:
            self.save_settings()
            job = Job(**self.values)
            job.validate()
        except (ValueError, OSError) as exc:
            messagebox.showerror('Setup needed', str(exc), parent=self.root)
            return
        self.request_dir = settings.data_dir() / 'jobs' / uuid.uuid4().hex
        self.request_dir.mkdir(parents=True)
        request = self.request_dir / 'request.json'
        request.write_text(json.dumps(self.values, indent=2)+'\n', encoding='utf-8')
        self.event_offset, self.cancelled, self.result = 0, False, None
        for button in (self.output_button, self.preview_button):
            button.configure(state='disabled')
        self.logs_button.configure(state='normal')
        self.summary.set('Conversion in progress…')
        self.progress['value'] = 0
        self.status.set('Starting the working opacity-fix pipeline…')
        options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
        try:
            self.process = subprocess.Popen(worker_command(request), **options)
        except OSError as exc:
            messagebox.showerror('Could not start conversion', str(exc), parent=self.root)
            return
        self.set_busy(True)
        self.root.after(150, self.poll)

    def poll(self):
        if self.process is None:
            return
        events = self.request_dir / 'events.jsonl'
        if events.exists():
            with events.open(encoding='utf-8') as stream:
                stream.seek(self.event_offset)
                while True:
                    position = stream.tell()
                    line = stream.readline()
                    if not line or not line.endswith('\n'):
                        self.event_offset = position
                        break
                    try:
                        event = json.loads(line)
                        self.progress['value'] = event['percent']
                        self.status.set(event['message'])
                    except (ValueError, KeyError):
                        pass
        if self.process.poll() is None:
            self.root.after(150, self.poll)
            return
        self.process = None
        self.set_busy(False)
        result = self.request_dir / 'result.json'
        if self.cancelled:
            self.status.set('Conversion cancelled. Original files are unchanged.')
            self.summary.set('No completed export was selected.')
            return
        try:
            response = json.loads(result.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            response = {'ok': False, 'error': 'The conversion worker stopped unexpectedly. Open logs for details.'}
        if response['ok']:
            self.result = response
            self.progress['value'] = 100
            self.status.set('Export complete. Test the PAC in PPSSPP.')
            detail = 'Matching YOBJ, textures and report included.'
            if response.get('size_fitted'):
                detail = f'Size fitted: {response["texture_max_dimension"]}px textures, ratio {response["reduction_ratio"]:g}. Check detail in PPSSPP.'
            self.summary.set(f'{Path(response["pac"]).name}  •  {response["bytes"]/1024:g} KB\n{detail}')
            self.output_button.configure(state='normal')
            self.preview_button.configure(state='normal')
        else:
            self.status.set('Conversion stopped. Open logs for details.')
            self.summary.set('Export was not completed.')
            messagebox.showerror('Conversion stopped', response['error'], parent=self.root)

    def cancel(self):
        if self.process is None:
            return
        self.cancelled = True
        self.cancel_button.configure(state='disabled')
        self.status.set('Stopping conversion…')
        try:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
            else:
                os.killpg(self.process.pid, signal.SIGTERM)
        except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
            if self.process.poll() is None:
                self.process.terminate()

    def open_logs(self):
        if self.request_dir:
            open_folder(self.request_dir)

    def close(self):
        if self.process:
            if not messagebox.askyesno('Stop conversion?', 'Stop the current conversion and close the app?', parent=self.root):
                return
            self.cancel()
        self.save_settings()
        self.root.destroy()


def make_root():
    drag_drop = True
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
    except (ImportError, tk.TclError):
        drag_drop = False
        root = tk.Tk()
    return root, drag_drop


def launch():
    root, drag_drop = make_root()
    BetaApp(root, drag_drop)
    root.mainloop()
