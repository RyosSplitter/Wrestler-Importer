"""Batch queue and per-candidate review inside the converter."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import uuid

from PIL import Image, ImageTk

from desktop.adapters import FORMATS
from desktop.batch import counts, load_result, save_reviewed, summary_text, write_state
from desktop.conversion_timer import ConversionTimer, profile, read_history, save_trace
from desktop.storage import data_dir
from desktop.texture_modes import MODES


class BatchWindow:
    def __init__(self, app):
        self.app = app
        self.top = tk.Toplevel(app.root)
        self.top.title('Batch Converter — PSP Model Suite')
        width = min(1100, app.root.winfo_screenwidth() - 50)
        height = min(760, app.root.winfo_screenheight() - 100)
        self.top.geometry(f'{width}x{height}')
        self.top.minsize(900, 600)
        self.top.transient(app.root)
        self.top.grab_set()
        self.top.protocol('WM_DELETE_WINDOW', self.close)
        self.process = None
        self.closing = False
        self.files = []
        self.state = dict(phase='idle', items=[])
        self.result = None
        self.current = None
        self.photo = None
        self.job = None
        self.view = 'front-left'
        self.zoom = 'full'
        self.timer = ConversionTimer()
        self.timer_item = None
        self.timing_profile = None
        self.options = {}
        self.seen_state = None
        self.formats = {item.label: item.key for item in FORMATS if item.supported}
        label = next(item.label for item in FORMATS if item.key == app.source_format.get())
        self.game = tk.StringVar(value=label)
        self.base = tk.StringVar(value=app.base.get())
        mode = app.texture_mode.get()
        self.texture_mode = tk.StringVar(value='Default' if mode == 'Priority Selection' else mode)
        self.downgrade = tk.StringVar(value=app.downgrade_steps.get())
        self.role = tk.StringVar(value=app.costume_role.get())
        self.geometry = tk.StringVar(value=app.wii_geometry.get())
        self.seams = tk.BooleanVar(value=app.wii_seam_protection.get())
        self.skin = tk.BooleanVar(value=app.skin_palette_compatibility.get())
        self.status = tk.StringVar(value='Choose the source game, then add models from that game.')
        self.detail = tk.StringVar(value='Select a successful model to preview and save it.')
        self.clock_text = tk.StringVar(value=self.timer.text())
        self.summary = tk.StringVar(value='No batch started.')
        self.saved = {}
        self.controls = []

        options = ttk.LabelFrame(self.top, text='Batch settings', padding=8)
        options.pack(fill='x', padx=10, pady=(10, 6))
        row = ttk.Frame(options)
        row.pack(fill='x')
        ttk.Label(row, text='Source game:').pack(side='left')
        self.game_box = ttk.Combobox(row, textvariable=self.game, values=tuple(self.formats), state='readonly', width=32)
        self.game_box.pack(side='left', padx=6)
        self.game_box.bind('<<ComboboxSelected>>', lambda event: self.update_options())
        ttk.Label(row, text='PSP base:').pack(side='left', padx=(8, 0))
        self.base_entry = ttk.Entry(row, textvariable=self.base, state='readonly')
        self.base_entry.pack(side='left', fill='x', expand=True, padx=6)
        self.base_button = self.button(row, 'Choose…', self.choose_base)
        self.base_button.pack(side='left')
        row = ttk.Frame(options)
        row.pack(fill='x', pady=(8, 0))
        ttk.Label(row, text='Textures:').pack(side='left')
        self.mode_box = ttk.Combobox(row, textvariable=self.texture_mode, state='readonly', width=20)
        self.mode_box.pack(side='left', padx=6)
        self.mode_box.bind('<<ComboboxSelected>>', lambda event: self.update_options())
        self.downgrade_box = ttk.Combobox(row, textvariable=self.downgrade, values=('1 size', '2 sizes', '3 sizes'), state='readonly', width=9)
        self.downgrade_box.pack(side='left')
        self.skin_box = ttk.Checkbutton(row, text='Single-slot skinning compatibility', variable=self.skin)
        self.skin_box.pack(side='left', padx=8)
        self.wii_row = ttk.Frame(options)
        ttk.Label(self.wii_row, text='Wii output:').pack(side='left')
        self.role_box = ttk.Combobox(self.wii_row, textvariable=self.role, values=('ring', 'entrance'), state='readonly', width=10)
        self.role_box.pack(side='left', padx=6)
        self.geometry_box = ttk.Combobox(self.wii_row, textvariable=self.geometry, values=('Standard', 'Preserve Hands', 'Preserve Arms'), state='readonly', width=17)
        self.geometry_box.pack(side='left', padx=6)
        self.seam_box = ttk.Checkbutton(self.wii_row, text='Protect clothing seams', variable=self.seams)
        self.seam_box.pack(side='left', padx=6)
        ttk.Label(options, text='Archives expand into individual costumes. Settings apply to the whole batch. Per-model texture priorities use the single converter.',
                  style='Muted.TLabel', wraplength=1000).pack(fill='x', pady=(6, 0))

        toolbar = ttk.Frame(self.top, padding=(10, 0, 10, 6))
        toolbar.pack(fill='x')
        for text, callback in [('Add models…', self.add_dialog), ('Remove selected', self.remove), ('Clear', self.clear)]:
            self.button(toolbar, text, callback, editing=True).pack(side='left', padx=(0, 5))
        self.start_button = self.button(toolbar, 'Start batch', self.start)
        self.start_button.pack(side='left', padx=(8, 5))
        self.cancel_button = self.button(toolbar, 'Cancel batch', self.cancel)
        self.cancel_button.pack(side='left')
        self.cancel_button.configure(state='disabled')
        self.report_button = self.button(toolbar, 'Batch report', self.open_report)
        self.report_button.pack(side='right')
        self.report_button.configure(state='disabled')

        footer = ttk.Frame(self.top, padding=(10, 6))
        footer.pack(side='bottom', fill='x')
        self.progress = ttk.Progressbar(footer, maximum=100)
        self.progress.pack(fill='x')
        for variable in (self.clock_text, self.summary, self.status):
            ttk.Label(footer, textvariable=variable, wraplength=1000).pack(anchor='w', pady=(3, 0))
        split = ttk.Panedwindow(self.top, orient='horizontal')
        split.pack(fill='both', expand=True, padx=10)
        left, right = ttk.Frame(split), ttk.LabelFrame(split, text='Selected PSP output', padding=6)
        split.add(left, weight=3)
        split.add(right, weight=3)
        self.tree = ttk.Treeview(left, columns=('state', 'detail'), selectmode='browse')
        self.tree.heading('#0', text='Model / costume')
        self.tree.column('#0', width=230, minwidth=100)
        for key, title, width in [('state', 'Status', 85), ('detail', 'Details', 210)]:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=60)
        vertical = ttk.Scrollbar(left, orient='vertical', command=self.tree.yview)
        horizontal = ttk.Scrollbar(left, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        vertical.pack(side='right', fill='y')
        horizontal.pack(side='bottom', fill='x')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', lambda event: self.select())
        views = ttk.Frame(right)
        views.pack(fill='x')
        self.view_buttons = []
        for title, view in [('¾', 'front-left'), ('Front', 'front'), ('Rear', 'back'), ('Left', 'left'), ('Right', 'right')]:
            button = self.button(views, title, lambda v=view: self.set_view(v))
            button.configure(width=5)
            button.pack(side='left', padx=(0, 3))
            self.view_buttons.append(button)
        zoom = self.button(views, 'Zoom', self.toggle_zoom)
        zoom.configure(width=5)
        zoom.pack(side='right')
        self.view_buttons.append(zoom)
        actions = ttk.Frame(right)
        actions.pack(side='bottom', fill='x', pady=(6, 0))
        self.save_button = self.button(actions, 'Save PAC As…', self.export)
        self.save_button.pack(side='left')
        self.save_button.configure(state='disabled')
        self.qa_button = self.button(actions, 'QA report', self.open_qa)
        self.qa_button.pack(side='left', padx=5)
        self.qa_button.configure(state='disabled')
        self.button(actions, 'Logs', self.open_logs).pack(side='right')
        self.detail_label = ttk.Label(right, textvariable=self.detail, wraplength=460, justify='left')
        self.detail_label.pack(side='bottom', fill='x', pady=5)
        self.preview = tk.Label(right, bg='#484848', fg='white', text='Select a successful conversion.')
        self.preview.pack(fill='both', expand=True, pady=(6, 0))
        self.preview.bind('<Configure>', lambda event: self.show_preview())
        right.bind('<Configure>', lambda event: self.detail_label.configure(wraplength=max(150, event.width - 20)))
        self.update_options()
        self.top.after(200, self.poll)

    def button(self, parent, text, callback, editing=False):
        button = ttk.Button(parent, text=text, command=callback)
        if editing:
            self.controls.append(button)
        return button

    def running(self):
        return self.process is not None

    def update_options(self):
        if self.running():
            return
        key = self.formats[self.game.get()]
        modes = ('Default',) if key == 'wwe13-wii' else tuple(
            value for value in MODES if value != 'Priority Selection' and (key == 'hctp' or value != 'Legacy'))
        self.mode_box.configure(values=modes)
        if self.texture_mode.get() not in modes:
            self.texture_mode.set('Default')
        self.downgrade_box.configure(state='readonly' if self.texture_mode.get() == 'Downgrade' else 'disabled')
        self.skin_box.configure(state='disabled' if key == 'wwe13-wii' else 'normal')
        if key == 'wwe13-wii':
            self.wii_row.pack(fill='x', pady=(8, 0))
        else:
            self.wii_row.pack_forget()

    def choose_base(self):
        path = filedialog.askopenfilename(parent=self.top, title='Choose PSP base PAC', filetypes=[('PAC files', '*.pac *.PAC')])
        if path:
            self.base.set(path)

    def add_dialog(self):
        self.add_files(filedialog.askopenfilenames(parent=self.top, title='Add models from the selected source game', filetypes=[('PAC files', '*.pac *.PAC')]))

    def add_files(self, paths):
        if self.running():
            return
        import os
        known = {os.path.normcase(str(Path(path).resolve())) for path in self.files}
        for path in paths:
            path = str(Path(path).resolve())
            key = os.path.normcase(path)
            if key not in known:
                self.files.append(path)
                known.add(key)
        self.show_files()

    def show_files(self):
        self.state = dict(phase='idle', items=[])
        self.current = None
        self.tree.delete(*self.tree.get_children())
        for index, path in enumerate(self.files):
            self.tree.insert('', 'end', iid=str(index), text=Path(path).name, values=('Queued', path))
        self.result = None
        self.save_button.configure(state='disabled')
        self.qa_button.configure(state='disabled')
        self.preview.configure(image='', text='Start the batch, then select a successful conversion.')
        self.detail.set(f'{len(self.files)} source files queued.')

    def remove(self):
        if self.running():
            return
        # Results can contain several costumes per source file. Removing a row
        # removes that source file from the next batch, not its prior candidate.
        for selected in self.tree.selection():
            path = self.state['items'][int(selected)]['source'] if self.state['items'] else self.files[int(selected)]
            self.files = [value for value in self.files if value != path]
        self.state = dict(phase='idle', items=[])
        self.show_files()

    def clear(self):
        if not self.running():
            self.files = []
            self.state = dict(phase='idle', items=[])
            self.show_files()

    def start(self):
        if self.running():
            return
        if not self.files:
            messagebox.showinfo('Batch Converter', 'Add at least one source PAC.', parent=self.top)
            return
        if not Path(self.base.get()).is_file():
            messagebox.showerror('Batch Converter', 'Choose an existing PSP base PAC.', parent=self.top)
            return
        key = self.formats[self.game.get()]
        mode = self.texture_mode.get()
        self.options = dict(base=str(Path(self.base.get()).resolve()), source_format=key,
                            texture_mode=mode, adaptive_textures=mode == 'ATO',
                            downgrade_steps=int(self.downgrade.get()[0]) if mode == 'Downgrade' else 0,
                            skin_palette_compatibility=self.skin.get(),
                            costume_role=self.role.get() if key == 'wwe13-wii' else 'ring',
                            wii_geometry=self.geometry.get() if key == 'wwe13-wii' else 'Standard',
                            wii_seam_protection=self.seams.get() if key == 'wwe13-wii' else False)
        self.job = data_dir() / 'batches' / uuid.uuid4().hex
        self.job.mkdir(parents=True)
        write_state(self.job / 'request.json', dict(files=list(self.files), options=self.options))
        try:
            self.process = self.app.spawn(['--batch-worker', str(self.job / 'request.json')])
        except OSError as exc:
            messagebox.showerror('Batch Converter', str(exc), parent=self.top)
            return
        self.state = dict(phase='planning', items=[])
        self.seen_state = None
        self.saved = {}
        self.result = None
        self.timer_item = None
        self.current = None
        self.tree.delete(*self.tree.get_children())
        self.preview.configure(image='', text='Converting batch…')
        self.save_button.configure(state='disabled')
        self.qa_button.configure(state='disabled')
        self.report_button.configure(state='disabled')
        self.status.set('Finding archive costumes…')
        self.summary.set('Batch running; successful models stay available for review.')
        self.progress['value'] = 0
        self.set_busy(True)

    def set_busy(self, busy):
        for control in (*self.controls, self.start_button, self.base_button):
            control.configure(state='disabled' if busy else 'normal')
        for control in (self.game_box, self.mode_box, self.downgrade_box, self.role_box, self.geometry_box):
            control.configure(state='disabled' if busy else 'readonly')
        for control in (self.seam_box, self.skin_box):
            control.configure(state='disabled' if busy else 'normal')
        self.cancel_button.configure(state='normal' if busy else 'disabled')
        if not busy:
            self.update_options()

    def cancel(self):
        if self.running():
            (self.job / 'cancel').touch(exist_ok=True)
            self.timer.cancel()
            self.status.set('Cancelling current model; completed results will be retained.')
            self.cancel_button.configure(state='disabled')

    def finish_timer(self):
        if self.timer_item is None:
            return
        row = next((row for row in self.state['items'] if row['id'] == self.timer_item), None)
        status = 'completed' if row and row['state'] == 'succeeded' else 'cancelled' if row and row['state'] == 'cancelled' else 'failed'
        trace = self.timer.finish(status)
        if trace:
            try:
                save_trace(data_dir() / 'conversion-timings.json', self.timing_profile, trace)
            except OSError:
                pass
        self.timer_item = None

    def refresh(self):
        current = self.state.get('current')
        if current != self.timer_item:
            self.finish_timer()
            if current is not None:
                self.timing_profile = profile(self.options)
                self.timer = ConversionTimer(read_history(data_dir() / 'conversion-timings.json').get(self.timing_profile, []))
                self.timer.start()
                self.timer_item = current
        if current is not None:
            self.timer.observe(self.state.get('percent', 0))
        rows = self.state['items']
        for row in rows:
            values = (row['state'].capitalize(), self.saved.get(row['id']) or row.get('error', ''))
            if self.tree.exists(row['id']):
                self.tree.item(row['id'], text=row['label'], values=values)
            else:
                self.tree.insert('', 'end', iid=row['id'], text=row['label'], values=values)
        totals = counts(rows)
        self.summary.set(f"{totals['succeeded']} succeeded | {totals['skipped']} skipped | {totals['cancelled']} cancelled | {totals['not-run']} not run | {len(rows)} total")
        completed = sum(totals[key] for key in ('succeeded', 'skipped', 'cancelled', 'not-run'))
        self.progress['value'] = (completed + self.state.get('percent', 0) / 100 if current is not None else completed) * 100 / max(1, len(rows))
        self.status.set(self.state.get('message', ''))
        selection = self.tree.selection()
        if selection:
            selected = next((row for row in rows if row['id'] == selection[0]), None)
            if selected and (selected['id'], selected['state']) != self.current:
                self.select()
        elif totals['succeeded'] and not self.running():
            self.tree.selection_set(next(row['id'] for row in rows if row['state'] == 'succeeded'))
            self.select()

    def poll(self):
        if self.running():
            path = self.job / 'state.json'
            try:
                text = path.read_text(encoding='utf-8')
                if text != self.seen_state:
                    self.state = json.loads(text)
                    self.seen_state = text
                    self.refresh()
            except (OSError, ValueError):
                pass  # Atomic replacement may briefly be unavailable on Windows.
            if self.process.poll() is not None:
                self.process = None
                try:
                    self.state = json.loads((self.job / 'summary.json').read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    self.state.update(phase='failed', current=None, error='Batch worker ended unexpectedly; see Logs.', message='Batch worker ended unexpectedly; see Logs.')
                    for row in self.state['items']:
                        if row['state'] in ('running', 'pending'):
                            row['state'] = 'not-run'
                self.refresh()
                self.finish_timer()
                self.set_busy(False)
                self.report_button.configure(state='normal' if (self.job / 'summary.txt').is_file() else 'disabled')
                if not self.closing:
                    messagebox.showinfo('Batch results', '\n'.join(summary_text(self.state).splitlines()[:5]), parent=self.top)
        self.clock_text.set(('Model ' + str(int(self.timer_item) + 1) + ': ' if self.timer_item is not None else '') + self.timer.text())
        if self.closing and not self.running():
            self.destroy()
            return
        self.top.after(200, self.poll)

    def selected_row(self):
        selection = self.tree.selection()
        return next((row for row in self.state['items'] if selection and row['id'] == selection[0]), None)

    def select(self):
        self.result = None
        self.save_button.configure(state='disabled')
        self.qa_button.configure(state='disabled')
        row = self.selected_row()
        self.current = (row['id'], row['state']) if row else None
        self.preview.configure(image='', text='Select a successful conversion.')
        if row is None:
            return
        if row['state'] != 'succeeded':
            self.detail.set(row['label'] + '\n' + (row.get('error') or row['state'].capitalize()))
            return
        try:
            self.result = load_result(row)
            result = self.result
            self.detail.set(f"{row['label']}\n{result['bytes']:,} bytes | QA: {result['review_flags']} findings to review\n" +
                            (self.saved.get(row['id']) or 'Review the preview and QA report before saving.'))
            self.show_preview()
            self.save_button.configure(state='normal')
            self.qa_button.configure(state='normal')
        except (OSError, ValueError, KeyError) as exc:
            self.result = None
            self.detail.set('Review unavailable: ' + str(exc))

    def set_view(self, view):
        self.view = view
        self.show_preview()

    def toggle_zoom(self):
        self.zoom = 'zoom' if self.zoom == 'full' else 'full'
        self.show_preview()

    def show_preview(self):
        if self.result is None:
            return
        try:
            path = Path(self.result['preview']) / (self.view + '-' + self.zoom + '.png')
            with Image.open(path) as source:
                image = source.copy()
            image.thumbnail((max(100, self.preview.winfo_width() - 10), max(100, self.preview.winfo_height() - 10)))
            self.photo = ImageTk.PhotoImage(image)
            self.preview.configure(image=self.photo, text='')
        except (OSError, ValueError) as exc:
            self.preview.configure(image='', text='Preview unavailable: ' + str(exc))

    def export(self):
        row = self.selected_row()
        if self.result is None or row is None:
            return
        if self.result['review_flags'] and not messagebox.askyesno('QA findings require review',
                f"This model has {self.result['review_flags']} QA findings and needs PPSSPP testing. Save as an experimental PAC?", parent=self.top):
            return
        name = Path(row['source']).stem + ('-' + row['source_entry'] if row['source_entry'] else '') + '-PSP.pac'
        chosen = filedialog.asksaveasfilename(parent=self.top, title='Save selected PSP PAC', initialfile=name,
                                            defaultextension='.pac', filetypes=[('PSP PAC', '*.pac')])
        if not chosen:
            return
        try:
            self.saved[row['id']] = save_reviewed(self.state, row, chosen, self.job)
            self.select()
            self.tree.set(row['id'], 'detail', 'Saved: ' + self.saved[row['id']])
        except Exception as exc:
            messagebox.showerror('Export withheld', str(exc), parent=self.top)

    def open_qa(self):
        if self.result:
            import webbrowser
            webbrowser.open(Path(self.result['report']).as_uri())

    def open_report(self):
        if self.job and (self.job / 'summary.txt').is_file():
            self.app.open_path(self.job / 'summary.txt')

    def open_logs(self):
        row = self.selected_row()
        if row and row.get('job'):
            self.app.open_path(Path(row['job']))
        elif self.job:
            self.app.open_path(self.job)

    def close(self):
        if self.running():
            self.closing = True
            self.cancel()
        else:
            self.destroy()

    def destroy(self):
        self.top.grab_release()
        self.app.batch_window = None
        self.top.destroy()
