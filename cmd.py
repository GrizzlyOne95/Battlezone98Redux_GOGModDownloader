import os
import sys
import re
import json
import shutil
import zipfile
import winreg
import ctypes
import subprocess
import threading
import urllib.request
from datetime import datetime
from io import BytesIO
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# --- EXTERNAL LIBRARIES ---
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    # Requires: pip install tkinterdnd2
    from tkinterdnd2 import DND_TEXT, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

# --- CONFIGURATION ---
STEAMCMD_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
CONFIG_FILE = "bz_mod_config.json"

class ToolTip:
    def __init__(self, widget, text, bg="#1a1a1a", fg="#00ffff"):
        self.widget = widget
        self.text = text
        self.bg = bg
        self.fg = fg
        self.tip_window = None
        widget.bind("<Enter>", self.show_tip)
        widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + 20
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify='left',
                       background=self.bg, foreground=self.fg, 
                       relief='solid', borderwidth=1, font=("Consolas", "9"))
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

class BZModMaster:
    def __init__(self, root):
        self.root = root
        self.root.title("Battlezone Mod Engine")
        self.root.geometry("1150x850")
        
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
            self.resource_dir = sys._MEIPASS
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
            self.resource_dir = self.base_dir

        # --- GAME DEFINITIONS ---
        self.games = {
            "BZ98R": {
                "name": "Battlezone 98 Redux",
                "appid": "301650",
                "exe": "battlezone98redux.exe",
                "font_file": "BZONE.ttf",
                "font_name": "BZONE",
                "icon_file": "bz98.png",
                "colors": {
                    "bg": "#0a0a0a", "fg": "#d4d4d4",
                    "highlight": "#00ff00", "dark_highlight": "#004400", "accent": "#00ffff"
                }
            },
            "BZCC": {
                "name": "Battlezone Combat Commander",
                "appid": "624970",
                "exe": "battlezone2.exe",
                "font_file": "BGM.ttf",
                "font_name": "BankGothic",
                "icon_file": "bz2.png",
                "colors": {
                    "bg": "#0a0a0a", "fg": "#d4d4d4",
                    "highlight": "#00aaff", "dark_highlight": "#002244", "accent": "#88ccff"
                }
            }
        }

        self.load_custom_fonts()
        self.load_game_icons()

        icon_path = os.path.join(self.resource_dir, "modman.ico")
        if os.path.exists(icon_path):
            try: self.root.iconbitmap(icon_path)
            except: pass

        self.bin_dir = os.path.join(self.base_dir, "bin")
        self.config = self.load_config()
        
        # Determine active game
        self.current_game_key = self.config.get("last_game", "BZ98R")
        if self.current_game_key not in self.games: self.current_game_key = "BZ98R"
        
        self.apply_theme_vars()
        self.root.configure(bg=self.colors["bg"])

        self.use_physical_var = tk.BooleanVar(value=self.config.get("use_physical", False))
        
        # Load game-specific path or fallback to legacy global path
        saved_path = self.config.get(f"path_{self.current_game_key}", "")
        if not saved_path and self.current_game_key == "BZ98R":
            saved_path = self.config.get("game_path", "")
            
        self.path_var = tk.StringVar(value=saved_path)
        self.steamcmd_var = tk.StringVar(value=self.config.get("steamcmd_path", ""))
        self.cache_var = tk.StringVar(value=self.config.get("cache_path", os.path.join(self.base_dir, "workshop_cache")))
        
        self.mod_id_var = tk.StringVar()
        self.image_cache = {}
        
        # Threading & Process Control
        self.stop_event = threading.Event()
        self.active_processes = []
        self.task_count = 0
        self.task_lock = threading.Lock()

        self.setup_ui()
        self.check_admin()
        
        if not self.path_var.get(): self.auto_detect_gog()
        if not self.steamcmd_var.get(): self.auto_detect_steamcmd()
        threading.Thread(target=self.initialize_engine, daemon=True).start()

    def load_custom_fonts(self):
        self.available_fonts = []
        for key, g in self.games.items():
            font_path = os.path.join(self.resource_dir, g["font_file"])
            if os.path.exists(font_path):
                try: 
                    # Check return value: > 0 means success
                    if ctypes.windll.gdi32.AddFontResourceExW(font_path, 0x10, 0) > 0:
                        self.available_fonts.append(g["font_name"])
                except: pass

    def load_game_icons(self):
        self.game_icons = {}
        if not HAS_PIL: return
        for key, g in self.games.items():
            try:
                p = os.path.join(self.resource_dir, g["icon_file"])
                if os.path.exists(p):
                    img = Image.open(p).resize((48, 48), Image.Resampling.LANCZOS)
                    self.game_icons[key] = ImageTk.PhotoImage(img)
            except: pass

    def apply_theme_vars(self):
        g = self.games[self.current_game_key]
        self.colors = g["colors"]
        # Fallback to Consolas if custom font didn't load
        self.current_font = g["font_name"] if g["font_name"] in self.available_fonts else "Consolas"

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f: 
                    data = json.load(f)
                    # Convert relative paths back to absolute
                    for key in ["game_path", "steamcmd_path", "cache_path", "path_BZ98R", "path_BZCC"]:
                        if key in data and data[key] and not os.path.isabs(data[key]):
                            data[key] = os.path.normpath(os.path.join(self.base_dir, data[key]))
                    return data
            except: return {}
        return {}

    def save_config(self, *args):
        def make_rel(path):
            if not path: return ""
            try:
                if os.path.splitdrive(path)[0].lower() == os.path.splitdrive(self.base_dir)[0].lower():
                    return os.path.relpath(path, self.base_dir)
            except: pass
            return path

        # Update current game path in config before saving
        self.config[f"path_{self.current_game_key}"] = self.path_var.get()
        self.config["last_game"] = self.current_game_key
        self.config["steamcmd_path"] = self.steamcmd_var.get()
        self.config["cache_path"] = self.cache_var.get()
        self.config["use_physical"] = self.use_physical_var.get()

        # Convert paths to relative for storage
        storage_config = self.config.copy()
        for k, v in storage_config.items():
            if "path" in k and isinstance(v, str):
                storage_config[k] = make_rel(v)

        with open(CONFIG_FILE, 'w') as f: json.dump(storage_config, f, indent=4)

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('default')
        
        self.update_styles(style)

        # --- TABS MAIN STRUCTURE ---
        self.tabs = ttk.Notebook(self.root)
        self.dl_tab = ttk.Frame(self.tabs)
        self.manage_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.dl_tab, text=" DOWNLOADER ")
        self.tabs.add(self.manage_tab, text=" MANAGE MODS ")
        self.tabs.pack(fill="both", expand=True)
        self.tabs.bind("<<NotebookTabChanged>>", self.on_tab_change)

        # ==========================================
        # TAB 1: DOWNLOADER
        # ==========================================
        
        # System Configuration
        cfg = ttk.LabelFrame(self.dl_tab, text=" SYSTEM CONFIGURATION ", padding=10)
        cfg.pack(fill="x", padx=10, pady=5)
        
        # Game Switcher Row
        game_row = ttk.Frame(cfg)
        game_row.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        ttk.Label(game_row, text="TARGET GAME:", font=(self.current_font, 12, "bold")).pack(side="left")
        
        game_names = [g["name"] for g in self.games.values()]
        self.game_selector = ttk.Combobox(game_row, values=game_names, state="readonly", width=40)
        
        target_name = self.games[self.current_game_key]["name"]
        if target_name in game_names:
            self.game_selector.current(game_names.index(target_name))
        else:
            self.game_selector.current(0)
            
        self.game_selector.pack(side="left", padx=10)
        self.game_selector.bind("<<ComboboxSelected>>", self.switch_game)

        self.icon_label = tk.Label(game_row, bg=self.colors["bg"])
        self.icon_label.pack(side="left", padx=5)
        self.update_game_icon()

        # Path Rows
        paths = [
            ("Game Path:", self.path_var, self.browse_game, "path_entry", 
             "Where the game executable is installed."),
            ("SteamCMD:", self.steamcmd_var, self.browse_steamcmd, "steamcmd_entry", 
             "If you have SteamCMD installed, point to it here.\nIf you aren't sure you can leave it default or choose a new location."),
            ("Mod Cache:", self.cache_var, self.browse_cache, "cache_entry", 
             "Location where mods are downloaded locally before being linked to the game.")
        ]

        for i, (txt, var, cmd, attr, tip) in enumerate(paths):
            row_idx = i + 1
            ttk.Label(cfg, text=txt).grid(row=row_idx, column=0, sticky="w")
            h_lbl = tk.Label(cfg, text="?", width=2, bg="#222", fg=self.colors['accent'], font=("Consolas", 8, "bold"), cursor="hand2")
            h_lbl.grid(row=row_idx, column=1, padx=(0, 5))
            ToolTip(h_lbl, tip, bg="#1a1a1a", fg=self.colors['accent'])
            ent = ttk.Entry(cfg, textvariable=var)
            ent.grid(row=row_idx, column=2, sticky="ew", padx=5)
            setattr(self, attr, ent) 
            ttk.Button(cfg, text="BROWSE", width=10, command=cmd).grid(row=row_idx, column=3, pady=2)
        cfg.columnconfigure(2, weight=1)

        # Mod Queue (Preview & Input)
        prev = ttk.LabelFrame(self.dl_tab, text=" MOD QUEUE ", padding=10)
        prev.pack(fill="x", padx=10, pady=5)
        
        thumb_container = tk.Frame(prev, bg="#050505", width=150, height=150, 
                                 highlightthickness=1, highlightbackground=self.colors['dark_highlight'])
        thumb_container.pack(side="left", padx=10)
        thumb_container.pack_propagate(False)
        self.thumb_container = thumb_container # Ref for theme update

        self.thumb_label = tk.Label(thumb_container, bg="#050505")
        self.thumb_label.pack(expand=True, fill="both")
        
        info_frame = ttk.Frame(prev)
        info_frame.pack(side="left", fill="both", expand=True)
        
        self.mod_name_label = ttk.Label(info_frame, text="READY FOR COMMAND", foreground=self.colors['accent'], font=(self.current_font, 11, "bold"))
        self.mod_name_label.pack(anchor="w", pady=(0, 5))
        
        ttk.Label(info_frame, text="MOD URL OR ID:", font=(self.current_font, 8)).pack(anchor="w")
        self.mod_entry = ttk.Entry(info_frame, textvariable=self.mod_id_var)
        self.mod_entry.pack(fill="x", pady=5)
        
        if HAS_DND:
            self.mod_entry.drop_target_register(DND_TEXT)
            self.mod_entry.dnd_bind('<<Drop>>', lambda e: self.mod_id_var.set(e.data.strip("{}")))
        self.mod_id_var.trace_add("write", self.on_input_change)

        btn_row = ttk.Frame(info_frame)
        btn_row.pack(fill="x", pady=5)
        self.dl_btn = ttk.Button(btn_row, text="INSTALL MOD", command=self.start_download, style="Success.TButton")
        self.dl_btn.pack(side="left", padx=(0, 5))
        self.launch_btn = ttk.Button(btn_row, text="LAUNCH GAME", command=self.launch_game)
        self.launch_btn.pack(side="left")
        self.stop_btn = ttk.Button(btn_row, text="STOP", command=self.stop_operation, state="disabled")
        self.stop_btn.pack(side="left", padx=5)

        # HUD Log
        ttk.Label(self.dl_tab, text=" HUD LOG ", foreground=self.colors['highlight'], font=(self.current_font, 11, "bold")).pack(anchor="w", padx=10)
        self.log_box = tk.Text(self.dl_tab, state="disabled", font=("Consolas", 10), bg="#050505", fg=self.colors['fg'], height=12)
        self.log_box.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Log tags
        self.log_box.tag_config("timestamp", foreground="#444444")
        self.log_box.tag_config("success", foreground=self.colors['highlight'])
        self.log_box.tag_config("warning", foreground="#ffff44")
        self.log_box.tag_config("error", foreground="#ff4444")
        self.log_box.tag_config("info", foreground=self.colors['accent'])

        self.progress = ttk.Progressbar(self.dl_tab, style="BZ.Horizontal.TProgressbar", mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=10)
        
        self.progress_label = tk.Label(self.dl_tab, text="IDLE", bg="#050505", fg="#666666", font=("Consolas", 8))
        self.progress_label.place(in_=self.progress, relx=0.5, rely=0.5, anchor="center")

        # ==========================================
        # TAB 2: MANAGE MODS
        # ==========================================
        
        self.tree = ttk.Treeview(self.manage_tab, columns=("Name", "ID", "Status", "Version", "Date"), show="tree headings")
        self.tree.column("#0", width=45, anchor="center", stretch=False)
        self.tree.heading("#0", text="")
        for col in ["Name", "ID", "Status", "Version", "Date"]: 
            self.tree.heading(col, text=col.upper(), command=lambda c=col: self.sort_tree(c, False))
            self.tree.column(col, anchor="center", width=100)
        self.tree.column("Name", width=250) 
        
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.tree.bind("<Button-3>", self.show_mod_menu)
        self.tree.bind("<ButtonPress-1>", self.on_tree_press)
        self.tree.bind("<B1-Motion>", self.on_tree_motion)
        manage_ctrl = ttk.Frame(self.manage_tab)
        manage_ctrl.pack(fill="x", padx=10, pady=5)
        
        ttk.Button(manage_ctrl, text="CHECK FOR UPDATES", command=self.refresh_list).pack(side="left")
        ttk.Button(manage_ctrl, text="UPDATE ALL", command=self.update_all_mods).pack(side="right")

        # Context Menu
        self.mod_menu = tk.Menu(self.root, tearoff=0, bg="#1a1a1a", fg=self.colors['fg'])
        self.mod_menu.add_command(label="ENABLE (LINK)", command=self.enable_mod)
        self.mod_menu.add_command(label="DISABLE (UNLINK)", command=self.disable_mod)
        self.mod_menu.add_separator()
        self.mod_menu.add_command(label="UPDATE MOD", command=lambda: self.update_selected_mod(force=False))
        self.mod_menu.add_command(label="FORCE UPDATE", command=lambda: self.update_selected_mod(force=True))
        self.mod_menu.add_command(label="DELETE FROM DISK", command=self.delete_mod_physically)

        self.update_tree_tags()

    def update_styles(self, style):
        main_font = (self.current_font, 10)
        bold_font = (self.current_font, 11, "bold")
        c = self.colors

        # --- GLOBAL STYLES ---
        style.configure(".", background=c["bg"], foreground=c["fg"], font=main_font, bordercolor=c["dark_highlight"])
        style.configure("TFrame", background=c["bg"])
        style.configure("TNotebook", background=c["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", background="#1a1a1a", foreground=c["fg"], padding=[10, 2])
        style.map("TNotebook.Tab", background=[("selected", c["dark_highlight"])], foreground=[("selected", c["highlight"])])
        style.configure("TLabelframe", background=c["bg"], bordercolor=c["highlight"])
        style.configure("TLabelframe.Label", background=c["bg"], foreground=c["highlight"], font=bold_font)
        style.configure("TLabel", background=c["bg"], foreground=c["fg"])
        style.configure("TEntry", fieldbackground="#1a1a1a", foreground=c["accent"], insertcolor=c["highlight"])
        style.configure("BZ.Horizontal.TProgressbar", thickness=15, background=c["highlight"], troughcolor="#050505")
        style.configure("TButton", background="#1a1a1a", foreground=c["fg"])
        style.map("TButton", background=[("active", c["dark_highlight"])], foreground=[("active", c["highlight"])])
        style.configure("Success.TButton", foreground=c["highlight"], font=bold_font)
        
        style.configure("Treeview", background="#0a0a0a", foreground=c["fg"], fieldbackground="#0a0a0a", rowheight=40)
        style.map("Treeview", background=[("selected", c["accent"])], foreground=[("selected", "#000000")])

    def update_game_icon(self):
        if not hasattr(self, 'icon_label'): return
        c = self.colors
        icon = self.game_icons.get(self.current_game_key)
        
        if icon:
            self.icon_label.config(image=icon, bg=c["bg"], highlightbackground=c["highlight"], highlightthickness=1, bd=0)
            self.icon_label.image = icon
        else:
            self.icon_label.config(image="", width=0, bd=0, highlightthickness=0)

    def update_tree_tags(self):
        c = self.colors
        self.tree.tag_configure('active', foreground=c['highlight'])
        self.tree.tag_configure('inactive', foreground="#666666")

    def switch_game(self, event=None):
        selected_name = self.game_selector.get()
        
        # Find key by name
        new_key = next((k for k, v in self.games.items() if v["name"] == selected_name), "BZ98R")
        
        if new_key == self.current_game_key: return
        
        # Save current state
        self.save_config()
        
        # Switch
        self.current_game_key = new_key
        self.apply_theme_vars()
        
        # Update Path Var
        saved_path = self.config.get(f"path_{self.current_game_key}", "")
        self.path_var.set(saved_path)
        
        # Update UI Styles
        style = ttk.Style()
        self.update_styles(style)
        
        # Update Manual Widgets
        c = self.colors
        self.root.configure(bg=c["bg"])
        self.log_box.configure(fg=c["fg"])
        self.log_box.tag_config("success", foreground=c['highlight'])
        self.log_box.tag_config("info", foreground=c['accent'])
        
        self.mod_name_label.configure(foreground=c['accent'], font=(self.current_font, 11, "bold"))
        self.thumb_container.configure(highlightbackground=c['dark_highlight'])
        self.mod_menu.configure(fg=c['fg'])
        
        self.update_tree_tags()
        self.update_game_icon()
        
        self.log(f"Switched to {self.games[new_key]['name']}", "info")
        self.initialize_engine()
        self.refresh_list()
        self.save_config()

    def log(self, message, tag=None):
        self.root.after(0, lambda: self._log_impl(message, tag))

    def _log_impl(self, message, tag=None):
        self.log_box.config(state="normal")
        ts = datetime.now().strftime("[%H:%M:%S] ")
        self.log_box.insert("end", ts, "timestamp")
        
        if tag:
            self.log_box.insert("end", f"{message}\n", tag)
        else:
            self.log_box.insert("end", f"{message}\n")
            
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def start_task(self):
        with self.task_lock:
            if self.task_count == 0:
                self.stop_event.clear()
                self.root.after(0, lambda: self.stop_btn.config(state="normal"))
            self.task_count += 1

    def end_task(self, callback=None):
        with self.task_lock:
            self.task_count -= 1
            if self.task_count <= 0:
                self.task_count = 0
                self.root.after(0, lambda: self.stop_btn.config(state="disabled"))
                self.root.after(0, self.reset_progress)
                if callback:
                    self.root.after(1000, callback)

    def stop_operation(self):
        self.stop_event.set()
        self.log("Stopping operations...", "warning")
        for p in list(self.active_processes):
            try: p.terminate()
            except: pass

    def start_download(self):
        mid = self.sanitize_id(self.mod_id_var.get())
        if not mid: 
            self.dl_btn.config(text="NO MOD ID")
            self.root.after(2000, lambda: self.dl_btn.config(text="INSTALL MOD", state="normal"))
            return
        
        # FINAL GATEKEEPER: Check validation flag
        if hasattr(self, 'is_valid_mod') and not self.is_valid_mod:
            messagebox.showerror("Validation Error", "Target Mod ID does not belong to Battlezone 98 Redux.\nDownload Aborted.")
            return

        self.dl_btn.config(state="disabled", text="ENGINE ACTIVE")
        self.progress.config(mode="indeterminate")
        self.progress.start(10)
        self.progress_label.config(text="INITIALIZING...", fg=self.colors['accent'])
        self.start_task()
        
        sc_path = self.steamcmd_var.get()
        cache_path = self.cache_var.get()
        game_path = self.path_var.get()
        use_physical = self.use_physical_var.get()
        
        threading.Thread(target=self.download_logic, args=(mid, sc_path, cache_path, game_path, use_physical), daemon=True).start()

    def download_logic(self, mod_id, sc_path, cache_path, game_path, use_physical):
        try:
            current_appid = self.games[self.current_game_key]["appid"]
            final_sc_path = self.ensure_steamcmd(sc_path)
            cache = os.path.abspath(cache_path)
            mod_path = os.path.join(cache, "steamapps/workshop/content", current_appid, mod_id)
            
            if os.path.exists(mod_path):
                self.log(f"Mod {mod_id} detected. Checking for updates...", "warning")
            else:
                self.log(f"Initializing new download for Mod {mod_id}...")

            # FIX: force_install_dir BEFORE login
            cmd = [final_sc_path, "+force_install_dir", cache, "+login", "anonymous",
                   "+workshop_download_item", current_appid, mod_id, "+quit"]
            
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            self.active_processes.append(p)
            
            for line in p.stdout:
                if self.stop_event.is_set():
                    p.terminate()
                    break
                clean = line.strip()
                if clean:
                    self.log(clean)
                    if "Verifying" in clean: self.root.after(0, lambda: self.dl_btn.config(text="VERIFYING..."))
                    percent_match = re.search(r'\((\d+\.\d+)%\)', clean)
                    if percent_match:
                        val = float(percent_match.group(1))
                        self.root.after(0, lambda v=val: self.update_progress(v))
            p.wait()
            if p in self.active_processes: self.active_processes.remove(p)

            src = os.path.normpath(mod_path)
            dst = os.path.normpath(os.path.join(game_path, "mods", mod_id))
            
            if os.path.exists(src):
                if not os.path.exists(os.path.dirname(dst)): os.makedirs(os.path.dirname(dst))
                if use_physical:
                    if os.path.exists(dst): shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    if not os.path.exists(dst): subprocess.run(f'mklink /J "{dst}" "{src}"', shell=True)
                self.log(f"Deployment complete: {mod_id}", "success")
                self.root.after(0, lambda: self.dl_btn.config(text="DEPLOYED"))
                self.root.after(3000, lambda: self.dl_btn.config(text="INSTALL MOD", state="normal"))
            
        except Exception as e: self.log(f"CRITICAL: {e}", "error")
        finally:
            self.end_task(self.refresh_list if not self.stop_event.is_set() else None)

    def update_progress(self, value):
        self.progress.stop()
        self.progress.config(mode="determinate", value=value)
        self.progress_label.config(text=f"DOWNLOADING {int(value)}%")
        if value < 100: self.dl_btn.config(text=f"DOWNLOADING {int(value)}%")

    def reset_progress(self):
        self.progress.stop()
        self.progress.config(mode="determinate", value=0)
        self.progress_label.config(text="IDLE", fg="#666666")

    def on_input_change(self, *args):
        mid = self.sanitize_id(self.mod_id_var.get())
        if mid and len(mid) >= 8:
            threading.Thread(target=self.fetch_preview, args=(mid,), daemon=True).start()

    def fetch_preview(self, mid):
        try:
            url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={mid}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as r:
                html = r.read().decode('utf-8')
                
                # VALIDATION: Check for Current Game App ID
                target_appid = self.games[self.current_game_key]["appid"]
                app_match = re.search(r'steamcommunity\.com/app/(\d+)', html)
                current_app = app_match.group(1) if app_match else None
                
                if current_app and current_app != target_appid:
                    self.is_valid_mod = False
                    self.root.after(0, lambda: self.mod_name_label.config(text="INVALID GAME DETECTED", foreground="#ff0000"))
                    return
                
                self.is_valid_mod = True
                name = re.search(r'<div class="workshopItemTitle">(.*?)</div>', html)
                thumb = re.search(r'id="ActualImage"\s+src="([^"]+)"', html)
                if not thumb: thumb = re.search(r'<link rel="image_src" href="([^"]+)">', html)
                title = name.group(1).strip() if name else f"ID: {mid}"
                
                self.root.after(0, lambda: self.mod_name_label.config(text=title, foreground=self.colors['accent']))
                if HAS_PIL and thumb:
                    with urllib.request.urlopen(thumb.group(1)) as i:
                        img = Image.open(BytesIO(i.read())).resize((150, 150), Image.Resampling.LANCZOS)
                        photo = ImageTk.PhotoImage(img)
                        self.root.after(0, lambda p=photo: self.update_thumb(p))
        except Exception as e:
            self.log(f"Metadata Fetch Error: {e}", "error")

    def update_thumb(self, photo):
        self.thumb_label.config(image=photo)
        self.thumb_label.image = photo 

    def sanitize_id(self, input_str):
        match = re.search(r'id=(\d+)', input_str)
        return match.group(1) if match else (input_str.strip() if input_str.strip().isdigit() else None)

    def initialize_engine(self):
        game_name = self.games[self.current_game_key]["name"]
        self.log(f"{game_name} Engine Initializing...", "info")
        
        # Check Game Path - Logic adjusted for your test environment
        game_exe = os.path.join(self.path_var.get(), self.games[self.current_game_key]["exe"])
        if not os.path.exists(game_exe):
            self.log("NOTICE: Executable not found. Running in Virtual/Test mode.", "warning")
            self.path_entry.configure(foreground="#ffff44") # Yellow for "Mock Mode"
        else:
            self.log(f"System Link Established: {game_exe}", "success")
            self.path_entry.configure(foreground=self.colors['accent'])
        
        # Check SteamCMD
        if not os.path.exists(self.steamcmd_var.get()):
            self.log("WARNING: SteamCMD missing. Downloads disabled.", "warning")
            self.steamcmd_entry.configure(foreground="#ffff44")
        else:
            self.log("SteamCMD Binary: Verified.", "success")

        self.log("Ready for mod deployment.", "info")

    def ensure_steamcmd(self, target):
        if not target:
            target = os.path.join(self.bin_dir, "steamcmd.exe")
            self.root.after(0, lambda: self.steamcmd_var.set(target))
            
        if not os.path.exists(target):
            target_dir = os.path.dirname(target)
            self.log(f"SteamCMD missing. Downloading to {target_dir}...", "warning")
            os.makedirs(target_dir, exist_ok=True)
            zip_p = os.path.join(target_dir, "sc.zip")
            try:
                urllib.request.urlretrieve(STEAMCMD_URL, zip_p)
                with zipfile.ZipFile(zip_p, 'r') as z: z.extractall(target_dir)
                os.remove(zip_p)
                self.log("SteamCMD installed successfully.", "success")
            except Exception as e:
                self.log(f"SteamCMD Setup Error: {e}", "error")
                raise e
        return target

    def check_admin(self):
        if not ctypes.windll.shell32.IsUserAnAdmin():
            self.log("NOTICE: Non-Admin mode detected.", "error")
            self.show_admin_warning()

    def show_admin_warning(self):
        self.admin_frame = tk.Frame(self.dl_tab, bg="#330000", pady=2)
        children = self.dl_tab.winfo_children()
        if children:
            self.admin_frame.pack(side="top", fill="x", padx=10, pady=(5,0), before=children[0])
        else:
            self.admin_frame.pack(side="top", fill="x", padx=10, pady=5)
            
        lbl = tk.Label(self.admin_frame, text="⚠ ADMIN RIGHTS REQUIRED FOR SYMLINKS", 
                       bg="#330000", fg="#ff5555", font=("Consolas", 10, "bold"))
        lbl.pack(side="left", padx=10)
        
        btn = ttk.Button(self.admin_frame, text="RELAUNCH AS ADMIN", command=self.relaunch_admin)
        btn.pack(side="right", padx=5, pady=2)
        ToolTip(lbl, "Windows requires Administrator privileges to create 'Junction' links.\nWithout this, mods cannot be linked to the game folder.")

    def relaunch_admin(self):
        try:
            if getattr(sys, 'frozen', False):
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, "", None, 1)
            else:
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{os.path.abspath(sys.argv[0])}"', None, 1)
            self.root.destroy()
        except Exception as e:
            self.log(f"Relaunch failed: {e}", "error")

    def browse_game(self): 
        p = filedialog.askdirectory()
        if p:
            self.path_var.set(os.path.normpath(p))
            self.path_entry.configure(foreground=self.colors['accent']) # Reset color
            self.save_config()
            self.log(f"Game path updated: {p}", "success")

    def browse_steamcmd(self): 
        result = messagebox.askyesnocancel("SteamCMD Setup", "Do you already have SteamCMD installed?\n\nYES: Browse for existing steamcmd.exe\nNO: Select a folder to download a new copy\nCANCEL: Abort")
        if result is None: return
        if result:
            p = filedialog.askopenfilename(filetypes=[("Executable", "steamcmd.exe"), ("All Executables", "*.exe")])
            if p:
                self.steamcmd_var.set(os.path.normpath(p))
                self.steamcmd_entry.configure(foreground=self.colors['accent'])
                self.save_config()
                self.log(f"SteamCMD path updated: {p}", "success")
        else:
            p = filedialog.askdirectory(title="Select Install Location for SteamCMD")
            if p:
                target = os.path.join(p, "steamcmd.exe")
                self.steamcmd_var.set(os.path.normpath(target))
                self.steamcmd_entry.configure(foreground=self.colors['accent'])
                self.save_config()
                self.log(f"SteamCMD will be installed to: {p}", "info")
    def browse_cache(self): 
        p = filedialog.askdirectory(); self.cache_var.set(os.path.normpath(p)); self.save_config()

    def on_tab_change(self, event):
        """Triggers a refresh only when the Manage Mods tab is selected."""
        if self.tabs.index("current") == 1:
            self.refresh_list()

    def refresh_list(self):
        """Deep scans for Workshop content and verifies Game Path links."""
        self.tree.delete(*self.tree.get_children())
        self.log("--- SCANNING MOD DATASETS ---", "info")
        
        base_cache = os.path.abspath(self.cache_var.get())
        game_path = os.path.abspath(self.path_var.get())
        
        # SteamCMD nested structure for BZ98R
        current_appid = self.games[self.current_game_key]["appid"]
        content_dir = os.path.join(base_cache, "steamapps", "workshop", "content", current_appid)
        game_mods_dir = os.path.join(game_path, "mods")

        # 1. Path Safety Check
        if not os.path.exists(content_dir):
            self.log("Path Error: Steam Workshop content folder not found.", "error")
            self.log(f"Searching: {content_dir}", "timestamp")
            return

        # 2. Gather Mod IDs
        try:
            mod_ids = [d for d in os.listdir(content_dir) if os.path.isdir(os.path.join(content_dir, d))]
            self.log(f"Scan found {len(mod_ids)} assets in local cache.", "success")
        except Exception as e:
            self.log(f"Directory Access Error: {e}", "error")
            return

        # 3. Populate Treeview
        for mid in mod_ids:
            mod_path = os.path.join(content_dir, mid)
            # Check if this ID is currently linked in the game's /mods folder
            link_path = os.path.join(game_mods_dir, mid)
            
            # Using lexists to catch symlinks even if the target is broken
            is_linked = os.path.lexists(link_path)
            status = "ENABLED" if is_linked else "DISABLED"
            
            m_time = os.path.getmtime(mod_path)
            dt = datetime.fromtimestamp(m_time).strftime('%Y-%m-%d')
            
            item = self.tree.insert("", "end", values=("Fetching...", mid, status, "Verifying...", dt))
            
            # Row Styling
            if is_linked:
                self.tree.item(item, tags=('active',))
            else:
                self.tree.item(item, tags=('inactive',))

            # Fire off the corrected background thread
            threading.Thread(target=self.fetch_mod_info_for_tree, args=(item, mid, dt), daemon=True).start()

        self.update_tree_tags()

    def fetch_mod_info_for_tree(self, item, mid, local_date):
        """Fetches mod name and checks for updates by comparing local vs workshop dates."""
        try:
            url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={mid}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as r:
                html = r.read().decode('utf-8')
                
                name_match = re.search(r'<div class="workshopItemTitle">(.*?)</div>', html)
                # Look for the date Steam says it was last updated
                date_match = re.search(r'<(?:div|span) class="detailsStatRight">([^<]+)</(?:div|span)>', html)
                
                title = name_match.group(1).strip() if name_match else mid
                remote_date = date_match.group(1).strip() if date_match else "Unknown"
                
                # Check if the local folder is older than the workshop update
                # For now, we'll just display both; we can add datetime parsing later
                version_status = f"Remote: {remote_date}"
                
                self.root.after(0, lambda: self.tree.set(item, "Name", title))
                self.root.after(0, lambda: self.tree.set(item, "Version", version_status))
        except Exception as e:
            self.root.after(0, lambda: self.tree.set(item, "Name", f"ID: {mid} (Fetch Error)"))

    def launch_game(self):
        exe = os.path.join(self.path_var.get(), self.games[self.current_game_key]["exe"])
        if os.path.exists(exe):
            self.launch_btn.config(text="LAUNCHING...")
            subprocess.Popen([exe], cwd=self.path_var.get())
            self.root.after(5000, lambda: self.launch_btn.config(text="LAUNCH GAME"))
        else:
            self.launch_btn.config(text="EXE MISSING")
            self.root.after(2000, lambda: self.launch_btn.config(text="LAUNCH GAME"))
    def auto_detect_gog(self):
        # Only auto-detect for BZ98R for now, or add BZCC IDs if known
        gog_ids = ["1454067812", "1459427445"]
        for g_id in gog_ids:
            for arch in ["SOFTWARE\\WOW6432Node", "SOFTWARE"]:
                try:
                    reg = f"{arch}\\GOG.com\\Games\\{g_id}"
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg, 0, winreg.KEY_READ | winreg.KEY_WOW64_32KEY)
                    path, _ = winreg.QueryValueEx(key, "path")
                    self.path_var.set(os.path.normpath(path)); self.save_config(); return
                except: pass

    def auto_detect_steamcmd(self):
        candidates = [
            os.path.join(self.bin_dir, "steamcmd.exe"),
            r"C:\steamcmd\steamcmd.exe",
            os.path.expandvars(r"%ProgramFiles(x86)%\SteamCMD\steamcmd.exe"),
            os.path.expandvars(r"%ProgramFiles%\SteamCMD\steamcmd.exe"),
            os.path.join(os.getcwd(), "steamcmd.exe")
        ]
        for p in candidates:
            if os.path.exists(p):
                self.steamcmd_var.set(os.path.normpath(p))
                self.save_config()
                return
                
    def on_tab_change(self, event):
        """Auto-refreshes the list when the user clicks the Manage tab."""
        if self.tabs.index("current") == 1:
            self.refresh_list()

    def sort_tree(self, col, reverse):
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        try:
            l.sort(key=lambda t: int(t[0]) if t[0].isdigit() else t[0], reverse=reverse)
        except ValueError:
            l.sort(reverse=reverse)

        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)

        self.tree.heading(col, command=lambda: self.sort_tree(col, not reverse))

    def on_tree_press(self, event):
        item = self.tree.identify_row(event.y)
        if item: self.selection_start = item

    def on_tree_motion(self, event):
        item = self.tree.identify_row(event.y)
        if item and hasattr(self, 'selection_start') and self.selection_start:
            if self.tree.identify_region(event.x, event.y) == "cell":
                children = self.tree.get_children()
                try:
                    start_idx = children.index(self.selection_start)
                    end_idx = children.index(item)
                    if start_idx > end_idx: start_idx, end_idx = end_idx, start_idx
                    self.tree.selection_set(children[start_idx : end_idx + 1])
                except ValueError: pass

    def show_mod_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            if item not in self.tree.selection():
                self.tree.selection_set(item)
            self.mod_menu.post(event.x_root, event.y_root)

    def refresh_list(self):
        """Scans SteamCMD cache and determines if mods are 'enabled' in the test folder."""
        self.progress_label.config(text="SCANNING...", fg=self.colors['accent'])
        self.image_cache.clear()
        self.progress.config(mode="indeterminate"); self.progress.start(10)
        
        # Offload file system scanning to a background thread
        cache_path = self.cache_var.get()
        game_path = self.path_var.get()
        
        self.start_task()
        threading.Thread(target=self._refresh_scan_logic, args=(cache_path, game_path), daemon=True).start()

    def _refresh_scan_logic(self, cache_path, game_path):
        try:
            base_cache = os.path.abspath(cache_path)
            game_dir = os.path.abspath(game_path)
            
            # Correct nested SteamCMD structure
            current_appid = self.games[self.current_game_key]["appid"]
            content_dir = os.path.join(base_cache, "steamapps", "workshop", "content", current_appid)
            game_mods_dir = os.path.join(game_dir, "mods")
            
            self.log("--- SCANNING FOR ASSETS ---", "info")

            # Ensure the test 'mods' folder exists
            if not os.path.exists(game_mods_dir):
                try: os.makedirs(game_mods_dir)
                except: pass

            if not os.path.exists(content_dir):
                self.log(f"SCAN FAILED: No cache at {content_dir}", "error")
                return

            try:
                mod_ids = [d for d in os.listdir(content_dir) if os.path.isdir(os.path.join(content_dir, d))]
                self.log(f"Found {len(mod_ids)} assets in Steam cache.", "success")
            except:
                return

            # Collect data to pass back to UI thread
            scan_data = []
            for mid in mod_ids:
                if self.stop_event.is_set(): return
                mod_path = os.path.join(content_dir, mid)
                link_path = os.path.join(game_mods_dir, mid)
                
                # Use lexists to see if the link is present in your test folder
                is_enabled = os.path.lexists(link_path)
                status = "ENABLED" if is_enabled else "DISABLED"
                
                try:
                    m_time = os.path.getmtime(mod_path)
                    dt = datetime.fromtimestamp(m_time).strftime('%Y-%m-%d')
                except:
                    m_time = 0
                    dt = "Unknown"
                
                scan_data.append((mid, status, is_enabled, m_time, dt))

            self.root.after(0, lambda: self._populate_tree(scan_data))
        finally:
            self.end_task()

    def _populate_tree(self, scan_data):
        self.tree.delete(*self.tree.get_children())
        
        for mid, status, is_enabled, m_time, dt in scan_data:
            display_status = f"{status} (Checking...)"
            
            item = self.tree.insert("", "end", values=("Fetching...", mid, display_status, "Checking...", dt))
            
            if is_enabled:
                self.tree.item(item, tags=('active',))
            else:
                self.tree.item(item, tags=('inactive',))

            threading.Thread(target=self.fetch_mod_info_for_tree, args=(item, mid, m_time, status), daemon=True).start()

        self.root.after(0, self.update_tree_tags)

    def safe_tree_set(self, item, col, value):
        try:
            if self.tree.exists(item):
                self.tree.set(item, col, value)
        except tk.TclError:
            pass

    def add_tag(self, item, tag):
        if self.tree.exists(item):
            tags = list(self.tree.item(item, "tags"))
            if tag not in tags:
                tags.append(tag)
                self.tree.item(item, tags=tags)

    def set_tree_image(self, item, raw_data, mid):
        if not self.tree.exists(item): return
        try:
            img = Image.open(BytesIO(raw_data))
            img.thumbnail((36, 36), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.image_cache[mid] = photo
            self.tree.item(item, image=photo)
        except Exception: pass

    def fetch_mod_info_for_tree(self, item, mid, local_ts, base_status):
        """Fetches mod name and checks for updates."""
        try:
            url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={mid}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as r:
                html = r.read().decode('utf-8')
                
                name_match = re.search(r'<div class="workshopItemTitle">(.*?)</div>', html)
                title = name_match.group(1).strip() if name_match else mid
                
                # Image Fetch
                thumb_match = re.search(r'id="ActualImage"\s+src="([^"]+)"', html)
                if not thumb_match: thumb_match = re.search(r'<link rel="image_src" href="([^"]+)">', html)
                if HAS_PIL and thumb_match:
                    try:
                        with urllib.request.urlopen(thumb_match.group(1)) as i:
                            raw = i.read()
                        self.root.after(0, lambda: self.set_tree_image(item, raw, mid))
                    except: pass

                # Check for "Updated" date on Steam
                date_match = re.search(r'<(?:div|span) class="detailsStatRight">([^<]+)</(?:div|span)>', html)
                remote_date_str = date_match.group(1).strip() if date_match else "Unknown"
                
                is_out_of_date = False
                if remote_date_str != "Unknown":
                    try:
                        # Clean string: "23 Oct, 2016 @ 3:47pm" -> remove @
                        clean_str = remote_date_str.replace("@", "").strip()
                        r_dt = None
                        for fmt in ["%d %b, %Y %I:%M%p", "%d %b %I:%M%p"]:
                            try:
                                r_dt = datetime.strptime(clean_str, fmt)
                                break
                            except ValueError: pass
                        
                        if r_dt:
                            if r_dt.year == 1900: r_dt = r_dt.replace(year=datetime.now().year)
                            l_dt = datetime.fromtimestamp(local_ts)
                            if r_dt.date() > l_dt.date():
                                is_out_of_date = True
                    except: pass

                final_status = base_status
                if is_out_of_date:
                    final_status = f"{base_status} (OUT OF DATE)"
                    self.root.after(0, lambda: self.add_tag(item, "update_needed"))
                    v_status = f"Remote: {remote_date_str}"
                else:
                    v_status = "UP TO DATE"
                
                self.root.after(0, lambda: self.safe_tree_set(item, "Name", title))
                self.root.after(0, lambda: self.safe_tree_set(item, "Version", v_status))
                self.root.after(0, lambda: self.safe_tree_set(item, "Status", final_status))
        except:
            self.root.after(0, lambda: self.safe_tree_set(item, "Name", f"ID: {mid} (Fetch Error)"))
            self.root.after(0, lambda: self.safe_tree_set(item, "Status", base_status))

    def enable_mod(self):
        """Creates a Junction link from the deep cache to the game folder for all selected mods."""
        selected = self.tree.selection()
        if not selected: return
        
        # Extract data on main thread
        mods_to_enable = [str(self.tree.item(item)['values'][1]) for item in selected]
        cache_path = self.cache_var.get()
        game_path = self.path_var.get()
        
        self.start_task()
        threading.Thread(target=self._enable_mod_worker, args=(mods_to_enable, cache_path, game_path), daemon=True).start()

    def _enable_mod_worker(self, mods, cache_path, game_path):
        try:
            for mid in mods:
                if self.stop_event.is_set(): break
                current_appid = self.games[self.current_game_key]["appid"]
                src = os.path.join(cache_path, "steamapps", "workshop", "content", current_appid, mid)
                dst = os.path.join(game_path, "mods", mid)
                
                try:
                    if not os.path.exists(os.path.dirname(dst)): os.makedirs(os.path.dirname(dst))
                    if os.path.lexists(dst): continue
                    # Use Junction (/J) for best compatibility with game engines
                    subprocess.run(f'mklink /J "{dst}" "{src}"', shell=True, check=True, capture_output=True)
                    self.log(f"Mod {mid} enabled (Junction created).", "success")
                except Exception as e:
                    self.log(f"Link Error for {mid}: {e}", "error")
        finally:
            self.end_task(self.refresh_list if not self.stop_event.is_set() else None)

    def disable_mod(self):
        """Disables all selected mods by removing their Junction links."""
        selected = self.tree.selection()
        if not selected: return
        
        mods_to_disable = [str(self.tree.item(item)['values'][1]) for item in selected]
        game_path = self.path_var.get()
        self.start_task()
        threading.Thread(target=self._disable_mod_worker, args=(mods_to_disable, game_path), daemon=True).start()

    def _disable_mod_worker(self, mods, game_path):
        try:
            for mid in mods:
                if self.stop_event.is_set(): break
                dst = os.path.join(game_path, "mods", mid)
                
                try:
                    if os.path.lexists(dst):
                        # In Windows, 'os.rmdir' is the correct way to remove a Junction 
                        # without deleting the contents of the source folder.
                        if os.path.isdir(dst):
                            os.rmdir(dst) 
                        else:
                            os.remove(dst) # Handle file symlinks
                        self.log(f"Mod {mid} decoupled from game engine.", "info")
                except Exception as e:
                    self.log(f"DECOUPLE ERROR for {mid}: {e}", "error")
        finally:
            self.end_task(self.refresh_list if not self.stop_event.is_set() else None)

    def is_junction(self, path):
        """Helper to detect if a directory is a Windows Junction."""
        return bool(os.path.isdir(path) and (ctypes.windll.kernel32.GetFileAttributesW(path) & 0x400))
    def update_all_mods(self):
        """Batch triggers SteamCMD for every item currently in the list."""
        items = self.tree.get_children()
        if not items:
            self.log("No mods detected in cache for update.", "warning")
            return
        
        to_update = []
        for item in items:
            if "update_needed" in self.tree.item(item, "tags"):
                to_update.append(str(self.tree.item(item)['values'][1]))
        
        if not to_update:
            self.log("All mods are up to date.", "success")
            return

        self.log(f"Initializing batch update for {len(to_update)} mods...", "info")
        
        sc_path = self.steamcmd_var.get()
        cache_path = self.cache_var.get()
        game_path = self.path_var.get()
        use_physical = self.use_physical_var.get()
        
        for mid in to_update:
            self.start_task()
            threading.Thread(target=self.download_logic, args=(mid, sc_path, cache_path, game_path, use_physical), daemon=True).start()

    def delete_mod_physically(self):
        """Wipes the selected mods from the SteamCMD cache and breaks any links."""
        selected = self.tree.selection()
        if not selected: return

        count = len(selected)
        if count == 1:
            mid = str(self.tree.item(selected[0])['values'][1])
            prompt_message = f"Permanently delete Mod ID {mid} from disk?"
        else:
            prompt_message = f"Permanently delete {count} selected mods from disk?"

        if messagebox.askyesno("TERMINATE ASSET(S)", prompt_message):
            mods_to_delete = [str(self.tree.item(item)['values'][1]) for item in selected]
            cache_path = self.cache_var.get()
            game_path = self.path_var.get()
            self.start_task()
            threading.Thread(target=self._delete_mod_worker, args=(mods_to_delete, cache_path, game_path), daemon=True).start()

    def _delete_mod_worker(self, mods, cache_path, game_path):
        try:
            for mid in mods:
                    if self.stop_event.is_set(): break
                    # 1. Break Link
                    link_path = os.path.join(game_path, "mods", mid)
                    if os.path.lexists(link_path):
                        try:
                            if os.path.isdir(link_path):
                                os.rmdir(link_path)
                            else:
                                os.remove(link_path)
                        except Exception as e:
                            self.log(f"Note: Could not remove link for {mid} during purge: {e}", "warning")

                    # 2. Delete Folder from cache
                    current_appid = self.games[self.current_game_key]["appid"]
                    mod_cache_path = os.path.join(cache_path, "steamapps/workshop/content", current_appid, mid)
                    try:
                        if os.path.exists(mod_cache_path):
                            shutil.rmtree(mod_cache_path)
                            self.log(f"Asset {mid} purged from local storage.", "warning")
                    except Exception as e:
                        self.log(f"Purge Error for {mid}: {e}", "error")
                
        finally:
            self.end_task(self.refresh_list if not self.stop_event.is_set() else None)

    def update_selected_mod(self, force=False):
        """Triggers a re-download via SteamCMD for the selected mods."""
        selected = self.tree.selection()
        if not selected: return
        for item in selected:
            mid = str(self.tree.item(item)['values'][1])
            
            if not force and "update_needed" not in self.tree.item(item, "tags"):
                self.log(f"Mod {mid} is up to date.", "info")
                continue

            self.log(f"Updating mod {mid}...", "info")
            
            sc_path = self.steamcmd_var.get()
            cache_path = self.cache_var.get()
            game_path = self.path_var.get()
            use_physical = self.use_physical_var.get()
            
            self.start_task()
            threading.Thread(target=self.download_logic, args=(mid, sc_path, cache_path, game_path, use_physical), daemon=True).start()
if __name__ == "__main__":
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    app = BZModMaster(root)
    root.mainloop()