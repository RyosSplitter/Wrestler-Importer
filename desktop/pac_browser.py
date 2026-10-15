"""PAC folder navigation, independent of decoding and conversion."""
from pathlib import Path
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def pac_files(folder):
    """List only direct child PAC files; never read model data during browsing."""
    folder = Path(folder).resolve()
    def order(path):
        parts = re.split(r'(\d+)', path.name.casefold())
        return tuple((1, int(p)) if p.isdigit() else (0, p) for p in parts), path.name
    return sorted((path for path in folder.iterdir()
                   if path.is_file() and path.suffix.casefold()=='.pac'), key=order)


def matching_files(files, query):
    query = query.strip().casefold()
    return [path for path in files if query in path.name.casefold()]


class PacBrowser(ttk.Frame):
    def __init__(self, parent, *, on_select, on_folder):
        super().__init__(parent, width=210)
        self.on_select = on_select
        self.on_folder = on_folder
        self.folder = None
        self.files = []
        self.visible = []
        self.selected_path = None
        self.selection_timer = None
        self.path_label = tk.StringVar(value='Choose a folder of PAC files.')
        self.count = tk.StringVar(value='No folder selected')
        self.query = tk.StringVar()
        buttons = ttk.Frame(self)
        buttons.pack(fill='x', pady=(0, 6))
        ttk.Button(buttons, text='Choose folder...', command=self.choose_folder).pack(side='left')
        ttk.Button(buttons, text='Refresh', command=self.refresh).pack(side='left', padx=(4, 0))
        self.folder_label = ttk.Label(self, textvariable=self.path_label, wraplength=195, style='Muted.TLabel')
        self.folder_label.pack(fill='x', pady=(0, 6))
        self.bind('<Configure>', lambda e: self.folder_label.configure(wraplength=max(90, e.width-8)))
        ttk.Label(self, text='Filter filenames:').pack(anchor='w')
        self.search = ttk.Entry(self, textvariable=self.query)
        self.search.pack(fill='x', pady=(2, 6))
        self.query.trace_add('write', lambda *args: self.update_list())
        ttk.Label(self, textvariable=self.count, style='Muted.TLabel').pack(anchor='w', pady=(0, 4))
        list_frame = ttk.Frame(self)
        list_frame.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(list_frame, show='tree', selectmode='browse')
        self.tree.column('#0', width=190, minwidth=120, stretch=True)
        vertical = ttk.Scrollbar(list_frame, orient='vertical', command=self.tree.yview)
        horizontal = ttk.Scrollbar(list_frame, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        vertical.pack(side='right', fill='y')
        horizontal.pack(side='bottom', fill='x')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', self.selection_changed)
        self.tree.bind('<Double-1>', self.open_selected)
        self.tree.bind('<Return>', self.open_selected)
        self.bind('<Destroy>', self.destroyed, add='+')

    def choose_folder(self):
        path = filedialog.askdirectory(title='Choose a folder containing PSP PAC files',
                                       initialdir=str(self.folder) if self.folder else None)
        if path:
            self.set_folder(path)

    def set_folder(self, folder, *, remember=True, show_errors=True):
        try:
            files = pac_files(folder)
        except OSError as exc:
            self.count.set('Folder unavailable — choose another folder.')
            if show_errors:
                messagebox.showerror('PAC folder', str(exc))
            return False
        self.cancel_selection()
        changed = self.folder != Path(folder).resolve()
        self.folder = Path(folder).resolve()
        self.files = files
        self.path_label.set(str(self.folder))
        self.selected_path = self.selected_path if self.selected_path in files else None
        if changed:
            self.query.set('')
        self.update_list()
        if remember:
            self.on_folder(self.folder)
        return True

    def refresh(self):
        if self.folder:
            self.set_folder(self.folder, remember=False)

    def update_list(self):
        self.cancel_selection()
        self.visible = matching_files(self.files, self.query.get())
        self.tree.delete(*self.tree.get_children())
        for index, path in enumerate(self.visible):
            self.tree.insert('', 'end', iid=str(index), text=path.name)
        self.count.set(f'{len(self.visible)} / {len(self.files)} PAC files' if self.files
                       else ('No PAC files in this folder.' if self.folder else 'No folder selected'))
        if self.selected_path in self.visible:
            key = str(self.visible.index(self.selected_path))
            self.tree.selection_set(key)
            self.tree.focus(key)
            self.tree.see(key)

    def selected(self):
        selection = self.tree.selection()
        if not selection:
            return None
        index = int(selection[0])
        return self.visible[index] if index<len(self.visible) else None

    def selection_changed(self, event=None):
        path = self.selected()
        if path is None or path==self.selected_path:
            return
        self.cancel_selection()
        # Arrow keys and fast scrolling shouldn't start a decoder for each row.
        self.selection_timer = self.after(220, self.open_selected)

    def open_selected(self, event=None):
        self.cancel_selection()
        path = self.selected()
        if path is not None:
            self.selected_path = path
            self.on_select(path)
        if event is not None:
            return 'break'

    def cancel_selection(self):
        if self.selection_timer is not None:
            self.after_cancel(self.selection_timer)
            self.selection_timer = None

    def destroyed(self, event):
        if event.widget is self:
            self.cancel_selection()
