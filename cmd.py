import os
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
    from tkinterdnd2 import DND_TEXT, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

# --- CONFIGURATION ---
BZ98R_APPID = "301650"
GOG_REG_IDS = ["1454067812", "1459427445"]
STEAMCMD_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
CONFIG_FILE = "bz98r_mod_config.json"

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
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
                       background="#ffffe0", relief='solid', borderwidth=1,
                       font=("tahoma", "9", "normal"))
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

class BZModMaster:
    def __init__(self, root):
        self.root = root
        self.root.title("Gemini BZ98R Mod Engine v3.2")
        self.root.geometry("1150x850")
        
        # Define Custom Font
        self.custom_font_name = "BZONE" if os.path.exists("bzone.ttf") else "Consolas"
        
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.bin_dir = os.path.join(self.base_dir, "bin")
        self.name_cache = {}
        self.config = self.load_config()
        
        # Variables
        self.use_physical_var = tk.BooleanVar(value=self.config.get("use_physical", False))
        self.path_var = tk.StringVar(value=self.config.get("game_path", ""))
        self.steamcmd_var = tk.StringVar(value=self.config.get("steamcmd_path", ""))
        self.cache_var = tk.StringVar(value=self.config.get("cache_path", os.path.join(self.base_dir, "workshop_cache")))
        
        self.mod_id_var = tk.StringVar()
        self.search_var = tk.StringVar()

        self.setup_ui()
        self.check_admin()
        
        if not self.path_var.get(): self.auto_detect_gog()
        threading.Thread(target=self.initialize_engine, daemon=True).start()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f: return json.load(f)
            except: return {}
        return {}

    def save_config(self, *args):
        config = {
            "game_path": self.path_var.get(),
            "steamcmd_path": self.steamcmd_var.get(),
            "cache_path": self.cache_var.get(),
            "use_physical": self.use_physical_var.get()
        }
        with open(CONFIG_FILE, 'w') as f: json.dump(config, f)

    def log(self, msg, tag=None):
        self.log_box.config(state="normal")
        timestamp = datetime.now().strftime("[%H:%M:%S] ")
        self.log_box.insert("end", timestamp, "timestamp")
        
        if not tag:
            lower_msg = msg.lower()
            if any(x in lower_msg for x in ["success", "deployed", "complete", "ok"]): tag = "success"
            elif any(x in lower_msg for x in ["error", "fail", "warning"]): tag = "error"
            elif any(x in lower_msg for x in ["starting", "initializing"]): tag = "warning"
        
        self.log_box.insert("end", f"{msg}\n", tag)
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def initialize_engine(self):
        self.log("Initializing Mod Engine...")
        if not self.steamcmd_var.get() or not os.path.exists(self.steamcmd_var.get()):
            detected = self.detect_steamcmd()
            if detected:
                self.steamcmd_var.set(detected)
                self.save_config()
        
        if self.steamcmd_var.get():
            try:
                subprocess.run([self.steamcmd_var.get(), "+quit"], creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
                self.log("SteamCMD readiness check complete.")
            except: pass

    def detect_steamcmd(self):
        for p in [os.path.join(self.bin_dir, "steamcmd.exe"), "C:\\steamcmd\\steamcmd.exe", shutil.which("steamcmd.exe")]:
            if p and os.path.exists(p): return p
        return None

    def setup_ui(self):
        style = ttk.Style()
        main_font = (self.custom_font_name, 10)
        bold_font = (self.custom_font_name, 11, "bold")
        
        # Apply font to ALL ttk components (including Browse buttons and Entries)
        style.configure(".", font=main_font) 
        style.configure("TLabel", font=main_font)
        style.configure("TButton", font=main_font)
        style.configure("TEntry", font=main_font)
        style.configure("TLabelframe.Label", font=bold_font)
        style.configure("Treeview.Heading", font=bold_font)
        style.configure("Treeview", font=main_font)
        
        style.configure("Success.TButton", foreground="#00ff00", font=bold_font)
        style.configure("Action.TButton", font=bold_font)

        self.tabs = ttk.Notebook(self.root)
        self.dl_tab = ttk.Frame(self.tabs)
        self.manage_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.dl_tab, text="Downloader")
        self.tabs.add(self.manage_tab, text="Manage Mods")
        self.tabs.pack(fill="both", expand=True)

        # System Configuration Section
        cfg = ttk.LabelFrame(self.dl_tab, text="System Configuration", padding=10)
        cfg.pack(fill="x", padx=10, pady=5)
        
        path_configs = [
            ("Game Path:", self.path_var, self.browse_game, "Folder where Battlezone 98 Redux is Installed"),
            ("SteamCMD:", self.steamcmd_var, self.browse_steamcmd, "Folder where you have SteamCMD installed."),
            ("Mod Cache:", self.cache_var, self.browse_cache, "Where the downloaded mods will be physically stored.")
        ]

        for i, (label_text, var, browse_cmd, tip_text) in enumerate(path_configs):
            ttk.Label(cfg, text=label_text).grid(row=i, column=0, sticky="w")
            
            # Use hand2 cursor for compatibility
            info_icon = tk.Label(cfg, text="ⓘ", fg="cyan", cursor="hand2")
            info_icon.grid(row=i, column=1, padx=2)
            ToolTip(info_icon, tip_text)
            
            ttk.Entry(cfg, textvariable=var).grid(row=i, column=2, sticky="ew", padx=5)
            # Custom font is applied here via the TButton style
            ttk.Button(cfg, text="Browse", width=8, command=browse_cmd).grid(row=i, column=3)
        
        cfg.columnconfigure(2, weight=1)

        # Mod Queue Section
        prev = ttk.LabelFrame(self.dl_tab, text="Mod Queue", padding=10)
        prev.pack(fill="x", padx=10, pady=5)
        
        self.thumb_label = ttk.Label(prev, width=20)
        self.thumb_label.pack(side="left", padx=10)
        
        info = ttk.Frame(prev)
        info.pack(side="left", fill="both", expand=True)
        self.mod_name_label = ttk.Label(info, text="Drag Link Here or Paste URL/ID", font=bold_font, wraplength=600)
        self.mod_name_label.pack(anchor="w")
        
        self.mod_entry = ttk.Entry(info, textvariable=self.mod_id_var)
        self.mod_entry.pack(fill="x", pady=5)
        
        if HAS_DND:
            self.mod_entry.drop_target_register(DND_TEXT)
            self.mod_entry.dnd_bind('<<Drop>>', self.handle_drop)
            
        self.mod_id_var.trace_add("write", self.on_input_change)
        
        btn_row = ttk.Frame(info)
        btn_row.pack(fill="x")
        self.dl_btn = ttk.Button(btn_row, text="Install Mod", command=self.start_download, style="Success.TButton")
        self.dl_btn.pack(side="left")
        self.launch_btn = ttk.Button(btn_row, text="LAUNCH GAME", command=self.launch_game)
        self.launch_btn.pack(side="right")

        # Console Output
        console_header = ttk.Label(self.dl_tab, text="CONSOLE OUTPUT", font=bold_font)
        console_header.pack(anchor="w", padx=10, pady=(10, 0))

        self.log_box = tk.Text(self.dl_tab, state="disabled", font=("Consolas", 10), 
                               bg="#1e1e1e", fg="#d4d4d4", height=15)
        self.log_box.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.log_box.tag_config("timestamp", foreground="#888888")
        self.log_box.tag_config("success", foreground="#00ff00")
        self.log_box.tag_config("warning", foreground="#dcdcaa")
        self.log_box.tag_config("error", foreground="#f44336")

        self.progress = ttk.Progressbar(self.dl_tab, mode="indeterminate")
        self.progress.pack(fill="x", padx=10, pady=5)

        # Management Tab
        self.tree = ttk.Treeview(self.manage_tab, columns=("Name", "ID", "Type", "Date"), show="headings")
        for col in ["Name", "ID", "Type", "Date"]: self.tree.heading(col, text=col)
        self.tree.pack(fill="both", expand=True, padx=10, pady=5)
        ttk.Button(self.manage_tab, text="Refresh List", command=self.refresh_list).pack(pady=5)

    def handle_drop(self, event):
        data = event.data.strip("{}").strip()
        self.mod_id_var.set(data)

    def on_input_change(self, *args):
        mid = self.sanitize_id(self.mod_id_var.get().strip())
        if mid and len(mid) >= 8:
            threading.Thread(target=self.fetch_preview, args=(mid,), daemon=True).start()

    def sanitize_id(self, input_str):
        clean = input_str.strip("{}").strip()
        match = re.search(r'[?&]id=(\d+)', clean)
        return match.group(1) if match else (clean if clean.isdigit() else None)

    def fetch_preview(self, mod_id):
        try:
            url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={mod_id}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=7) as r:
                html = r.read().decode('utf-8')
                name_match = re.search(r'<div class="workshopItemTitle">(.*?)</div>', html)
                name = name_match.group(1).strip() if name_match else f"Mod {mod_id}"
                thumb_match = re.search(r'id="ActualImage"\s+src="([^"]+)"', html)
                if not thumb_match:
                    thumb_match = re.search(r'<link rel="image_src" href="([^"]+)">', html)
                thumb_url = thumb_match.group(1) if thumb_match else None
                self.root.after(0, lambda: self.mod_name_label.config(text=name))
                if HAS_PIL and thumb_url:
                    with urllib.request.urlopen(thumb_url) as i:
                        img = Image.open(BytesIO(i.read()))
                        img.thumbnail((150, 150))
                        photo = ImageTk.PhotoImage(img)
                        self.root.after(0, lambda p=photo: self.update_thumb(p))
                else:
                    self.root.after(0, lambda: self.thumb_label.config(image=''))
        except:
            self.root.after(0, lambda: self.mod_name_label.config(text=f"Preview Failed: {mod_id}"))

    def update_thumb(self, p):
        self.thumb_label.config(image=p)
        self.thumb_label.image = p

    def browse_cache(self):
        p = filedialog.askdirectory(title="Select Workshop Cache Folder")
        if p:
            self.cache_var.set(os.path.normpath(p))
            self.save_config()

    def start_download(self):
        mod_id = self.sanitize_id(self.mod_id_var.get().strip())
        game_path = self.path_var.get()
        if not mod_id or not game_path or not os.path.exists(game_path):
            messagebox.showerror("Error", "Check Mod ID and Game Path.")
            return
        self.dl_btn.config(state="disabled", text="INSTALLING...")
        self.progress.start(10)
        self.log(f"Starting installation for Mod ID: {mod_id}...")
        threading.Thread(target=self.download_logic, args=(mod_id, game_path), daemon=True).start()

    def download_logic(self, mod_id, game_path):
        try:
            self.ensure_steamcmd()
            cache_path = os.path.abspath(self.cache_var.get())
            cmd = [self.steamcmd_var.get(), "+login", "anonymous", "+force_install_dir", cache_path,
                   "+workshop_download_item", BZ98R_APPID, mod_id, "+quit"]
            
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            for line in p.stdout:
                self.log(line.strip())
            p.wait()

            src = os.path.normpath(os.path.join(cache_path, "steamapps/workshop/content", BZ98R_APPID, mod_id))
            dst = os.path.normpath(os.path.join(game_path, "mods", mod_id))
            
            if os.path.exists(src):
                if not os.path.exists(os.path.dirname(dst)): os.makedirs(os.path.dirname(dst))
                if self.use_physical_var.get():
                    if os.path.exists(dst): shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    if not os.path.exists(dst): subprocess.run(f'mklink /J "{dst}" "{src}"', shell=True)
                self.log(f"Deployed mod: {mod_id}", "success")
                self.root.after(0, lambda: self.dl_btn.config(text="INSTALL COMPLETE", style="Success.TButton"))
                self.root.after(3000, lambda: self.dl_btn.config(text="Install Mod", style="TButton", state="normal"))
            
            self.root.after(0, self.refresh_list)
        except Exception as e: self.log(f"Error: {e}", "error")
        finally:
            self.progress.stop()
            self.root.after(0, lambda: self.dl_btn.config(state="normal"))

    def auto_detect_gog(self):
        for gog_id in GOG_REG_IDS:
            for arch in ["SOFTWARE\\WOW6432Node", "SOFTWARE"]:
                try:
                    reg = f"{arch}\\GOG.com\\Games\\{gog_id}"
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg, 0, winreg.KEY_READ | winreg.KEY_WOW64_32KEY)
                    path, _ = winreg.QueryValueEx(key, "path")
                    self.path_var.set(os.path.normpath(path)); self.save_config(); winreg.CloseKey(key); return
                except: continue

    def ensure_steamcmd(self):
        exe = self.steamcmd_var.get()
        if not exe or not os.path.exists(exe):
            t = os.path.join(self.bin_dir, "steamcmd.exe")
            if not os.path.exists(os.path.dirname(t)): os.makedirs(os.path.dirname(t))
            urllib.request.urlretrieve(STEAMCMD_URL, os.path.join(self.bin_dir, "sc.zip"))
            with zipfile.ZipFile(os.path.join(self.bin_dir, "sc.zip"), 'r') as zf: zf.extractall(self.bin_dir)
            self.steamcmd_var.set(t); self.save_config()

    def check_admin(self):
        if not ctypes.windll.shell32.IsUserAnAdmin():
            self.log("WARNING: Not Admin. NTFS Junctions will fail.", "error")

    def browse_game(self):
        p = filedialog.askdirectory()
        if p: self.path_var.set(os.path.normpath(p)); self.save_config()

    def browse_steamcmd(self):
        p = filedialog.askopenfilename(filetypes=[("EXE", "*.exe")])
        if p: self.steamcmd_var.set(os.path.normpath(p)); self.save_config()

    def refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        m_dir = os.path.join(self.path_var.get(), "mods")
        if not os.path.exists(m_dir): return
        for f in os.listdir(m_dir):
            if os.path.isdir(os.path.join(m_dir, f)):
                dt = datetime.fromtimestamp(os.path.getmtime(os.path.join(m_dir, f))).strftime('%Y-%m-%d')
                is_j = os.path.isjunction(os.path.join(m_dir, f))
                st = "DISABLED" if f.startswith("DISABLED_") else ("Junction" if is_j else "Physical")
                self.tree.insert("", "end", values=(f, f, st, dt))

    def launch_game(self):
        gp = self.path_var.get()
        exe = os.path.join(gp, "battlezone98redux.exe")
        if os.path.exists(exe):
            self.launch_btn.config(text="LAUNCHING...")
            subprocess.Popen([exe], cwd=gp)
            self.root.after(5000, lambda: self.launch_btn.config(text="LAUNCH GAME"))
        else:
            messagebox.showerror("Error", "Executable not found.")

if __name__ == "__main__":
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    app = BZModMaster(root)
    root.mainloop()
