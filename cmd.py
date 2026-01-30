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

# --- BATTLEZONE HUD COLORS ---
BZ_BG = "#0a0a0a"
BZ_FG = "#d4d4d4"
BZ_GREEN = "#00ff00"
BZ_DARK_GREEN = "#004400"
BZ_CYAN = "#00ffff"

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
                       background="#1a1a1a", foreground=BZ_CYAN, 
                       relief='solid', borderwidth=1, font=("Consolas", "9"))
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

class BZModMaster:
    def __init__(self, root):
        self.root = root
        self.root.title("Gemini BZ98R Mod Engine v3.5 - HUD Interface")
        self.root.geometry("1150x850")
        self.root.configure(bg=BZ_BG)
        
        self.custom_font_name = "BZONE" if os.path.exists("bzone.ttf") else "Consolas"
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.bin_dir = os.path.join(self.base_dir, "bin")
        self.config = self.load_config()
        
        self.use_physical_var = tk.BooleanVar(value=self.config.get("use_physical", False))
        self.path_var = tk.StringVar(value=self.config.get("game_path", ""))
        self.steamcmd_var = tk.StringVar(value=self.config.get("steamcmd_path", ""))
        self.cache_var = tk.StringVar(value=self.config.get("cache_path", os.path.join(self.base_dir, "workshop_cache")))
        
        self.mod_id_var = tk.StringVar()
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

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('default')
        main_font = (self.custom_font_name, 10)
        bold_font = (self.custom_font_name, 11, "bold")

        style.configure(".", background=BZ_BG, foreground=BZ_FG, font=main_font, bordercolor=BZ_DARK_GREEN)
        style.configure("TFrame", background=BZ_BG)
        style.configure("TNotebook", background=BZ_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#1a1a1a", foreground=BZ_FG, padding=[10, 2])
        style.map("TNotebook.Tab", background=[("selected", BZ_DARK_GREEN)], foreground=[("selected", BZ_GREEN)])
        style.configure("TLabelframe", background=BZ_BG, bordercolor=BZ_GREEN)
        style.configure("TLabelframe.Label", background=BZ_BG, foreground=BZ_GREEN, font=bold_font)
        style.configure("TLabel", background=BZ_BG, foreground=BZ_FG)
        style.configure("TEntry", fieldbackground="#1a1a1a", foreground=BZ_CYAN, insertcolor=BZ_GREEN)
        style.configure("BZ.Horizontal.TProgressbar", thickness=15, background=BZ_GREEN, troughcolor="#050505")
        style.configure("TButton", background="#1a1a1a", foreground=BZ_FG)
        style.map("TButton", background=[("active", BZ_DARK_GREEN)], foreground=[("active", BZ_GREEN)])
        style.configure("Success.TButton", foreground=BZ_GREEN, font=bold_font)

        self.tabs = ttk.Notebook(self.root)
        self.dl_tab = ttk.Frame(self.tabs)
        self.manage_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.dl_tab, text=" DOWNLOADER ")
        self.tabs.add(self.manage_tab, text=" MANAGE MODS ")
        self.tabs.pack(fill="both", expand=True)

        cfg = ttk.LabelFrame(self.dl_tab, text=" SYSTEM CONFIGURATION ", padding=10)
        cfg.pack(fill="x", padx=10, pady=5)
        
        # Game Path Row
        ttk.Label(cfg, text="Game Path:").grid(row=0, column=0, sticky="w")
        tk.Label(cfg, text="ⓘ", fg=BZ_CYAN, bg=BZ_BG).grid(row=0, column=1, padx=5)
        self.path_entry = ttk.Entry(cfg, textvariable=self.path_var)
        self.path_entry.grid(row=0, column=2, sticky="ew", padx=5)
        ttk.Button(cfg, text="BROWSE", width=10, command=self.browse_game).grid(row=0, column=3, pady=2)

        # SteamCMD Row
        ttk.Label(cfg, text="SteamCMD:").grid(row=1, column=0, sticky="w")
        tk.Label(cfg, text="ⓘ", fg=BZ_CYAN, bg=BZ_BG).grid(row=1, column=1, padx=5)
        self.steamcmd_entry = ttk.Entry(cfg, textvariable=self.steamcmd_var)
        self.steamcmd_entry.grid(row=1, column=2, sticky="ew", padx=5)
        ttk.Button(cfg, text="BROWSE", width=10, command=self.browse_steamcmd).grid(row=1, column=3, pady=2)

        # Mod Cache Row
        ttk.Label(cfg, text="Mod Cache:").grid(row=2, column=0, sticky="w")
        tk.Label(cfg, text="ⓘ", fg=BZ_CYAN, bg=BZ_BG).grid(row=2, column=1, padx=5)
        self.cache_entry = ttk.Entry(cfg, textvariable=self.cache_var)
        self.cache_entry.grid(row=2, column=2, sticky="ew", padx=5)
        ttk.Button(cfg, text="BROWSE", width=10, command=self.browse_cache).grid(row=2, column=3, pady=2)

        cfg.columnconfigure(2, weight=1)

# --- MOD QUEUE SECTION ---
        prev = ttk.LabelFrame(self.dl_tab, text=" MOD QUEUE ", padding=10)
        prev.pack(fill="x", padx=10, pady=5)

        # Container frame for the thumbnail to enforce 150x150 dimensions
        thumb_container = tk.Frame(prev, bg="#050505", width=150, height=150, 
                                 highlightthickness=1, highlightbackground=BZ_DARK_GREEN)
        thumb_container.pack(side="left", padx=10)
        thumb_container.pack_propagate(False) # This works on Frames to lock the size

        self.thumb_label = tk.Label(thumb_container, bg="#050505") 
        self.thumb_label.pack(expand=True, fill="both")
        
        # Info frame for Title and ID Input
        info_frame = ttk.Frame(prev)
        info_frame.pack(side="left", fill="both", expand=True)
        
        if HAS_DND:
            self.mod_entry.drop_target_register(DND_TEXT)
            self.mod_entry.dnd_bind('<<Drop>>', lambda e: self.mod_id_var.set(e.data.strip("{}")))
        self.mod_id_var.trace_add("write", self.on_input_change)

        btn_row = ttk.Frame(info_frame)
        btn_row.pack(fill="x")
        self.dl_btn = ttk.Button(btn_row, text="INSTALL MOD", command=self.start_download, style="Success.TButton")
        self.dl_btn.pack(side="left")
        self.launch_btn = ttk.Button(btn_row, text="LAUNCH GAME", command=self.launch_game)
        self.launch_btn.pack(side="right")

        ttk.Label(self.dl_tab, text=" HUD LOG ", foreground=BZ_GREEN, font=bold_font).pack(anchor="w", padx=10)
        self.log_box = tk.Text(self.dl_tab, state="disabled", font=("Consolas", 10), bg="#050505", fg=BZ_FG, height=15)
        self.log_box.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_box.tag_config("timestamp", foreground="#444444")
        self.log_box.tag_config("success", foreground=BZ_GREEN)
        self.log_box.tag_config("warning", foreground="#ffff00")
        self.log_box.tag_config("error", foreground="#ff0000")

        self.progress = ttk.Progressbar(self.dl_tab, style="BZ.Horizontal.TProgressbar", mode="indeterminate")
        self.progress.pack(fill="x", padx=10, pady=10)

        style.configure("Treeview", background="#0a0a0a", foreground=BZ_FG, fieldbackground="#0a0a0a")
        style.map("Treeview", background=[("selected", BZ_DARK_GREEN)])
        self.tree = ttk.Treeview(self.manage_tab, columns=("Name", "ID", "Type", "Date"), show="headings")
        for col in ["Name", "ID", "Type", "Date"]: self.tree.heading(col, text=col.upper())
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)

    def log(self, msg, tag=None):
        self.log_box.config(state="normal")
        ts = datetime.now().strftime("[%H:%M] ")
        self.log_box.insert("end", ts, "timestamp")
        low = msg.lower()
        if not tag:
            if any(x in low for x in ["success", "deployed", "up-to-date"]): tag = "success"
            elif any(x in low for x in ["error", "fail"]): tag = "error"
            elif any(x in low for x in ["starting", "verifying", "checking"]): tag = "warning"
        self.log_box.insert("end", f"{msg}\n", tag)
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def start_download(self):
        mid = self.sanitize_id(self.mod_id_var.get())
        if not mid: return
        
        # FINAL GATEKEEPER: Check validation flag
        if hasattr(self, 'is_valid_mod') and not self.is_valid_mod:
            messagebox.showerror("Validation Error", "Target Mod ID does not belong to Battlezone 98 Redux.\nDownload Aborted.")
            return

        self.dl_btn.config(state="disabled", text="ENGINE ACTIVE")
        self.progress.config(mode="indeterminate")
        self.progress.start(10)
        threading.Thread(target=self.download_logic, args=(mid,), daemon=True).start()

    def download_logic(self, mod_id):
        try:
            self.ensure_steamcmd()
            cache = os.path.abspath(self.cache_var.get())
            mod_path = os.path.join(cache, "steamapps/workshop/content", BZ98R_APPID, mod_id)
            
            if os.path.exists(mod_path):
                self.log(f"Mod {mod_id} detected. Checking for updates...", "warning")
            else:
                self.log(f"Initializing new download for Mod {mod_id}...")

            # FIX: force_install_dir BEFORE login
            cmd = [self.steamcmd_var.get(), "+force_install_dir", cache, "+login", "anonymous",
                   "+workshop_download_item", BZ98R_APPID, mod_id, "+quit"]
            
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            for line in p.stdout:
                clean = line.strip()
                if clean:
                    self.log(clean)
                    if "Verifying" in clean: self.root.after(0, lambda: self.dl_btn.config(text="VERIFYING..."))
                    percent_match = re.search(r'\((\d+\.\d+)%\)', clean)
                    if percent_match:
                        val = float(percent_match.group(1))
                        self.root.after(0, lambda v=val: self.update_progress(v))
            p.wait()

            src = os.path.normpath(mod_path)
            dst = os.path.normpath(os.path.join(self.path_var.get(), "mods", mod_id))
            
            if os.path.exists(src):
                if not os.path.exists(os.path.dirname(dst)): os.makedirs(os.path.dirname(dst))
                if self.use_physical_var.get():
                    if os.path.exists(dst): shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    if not os.path.exists(dst): subprocess.run(f'mklink /J "{dst}" "{src}"', shell=True)
                self.log(f"Deployment complete: {mod_id}", "success")
                self.root.after(0, lambda: self.dl_btn.config(text="DEPLOYED"))
                self.root.after(3000, lambda: self.dl_btn.config(text="INSTALL MOD", state="normal"))
            self.root.after(0, self.refresh_list)
        except Exception as e: self.log(f"CRITICAL: {e}", "error")
        finally:
            self.root.after(0, self.progress.stop)

    def update_progress(self, value):
        self.progress.stop()
        self.progress.config(mode="determinate", value=value)
        if value < 100: self.dl_btn.config(text=f"DOWNLOADING {int(value)}%")

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
                
                # VALIDATION: Check for Battlezone 98 Redux App ID (301650)
                app_match = re.search(r'steamcommunity\.com/app/(\d+)', html)
                current_app = app_match.group(1) if app_match else None
                
                if current_app and current_app != BZ98R_APPID:
                    self.is_valid_mod = False
                    self.root.after(0, lambda: self.mod_name_label.config(text="INVALID GAME DETECTED", foreground="#ff0000"))
                    return
                
                self.is_valid_mod = True
                name = re.search(r'<div class="workshopItemTitle">(.*?)</div>', html)
                thumb = re.search(r'id="ActualImage"\s+src="([^"]+)"', html)
                if not thumb: thumb = re.search(r'<link rel="image_src" href="([^"]+)">', html)
                title = name.group(1).strip() if name else f"ID: {mid}"
                
                self.root.after(0, lambda: self.mod_name_label.config(text=title, foreground=BZ_CYAN))
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
        self.log("HUD Engine Initializing...")
        
        # Check Game Path
        game_exe = os.path.join(self.path_var.get(), "battlezone98redux.exe")
        if not os.path.exists(game_exe):
            self.log("CRITICAL: Battlezone 98 Redux executable not found!", "error")
            # We use a custom red highlight for the entry field
            self.root.after(0, lambda: self.path_entry.configure(foreground="#ff0000"))
        
        # Check SteamCMD
        if not os.path.exists(self.steamcmd_var.get()):
            self.log("WARNING: SteamCMD missing. Will attempt auto-download on first use.", "warning")
            self.root.after(0, lambda: self.steamcmd_entry.configure(foreground="#ffff00"))

        self.log("Ready for mod deployment.")

    def ensure_steamcmd(self):
        if not os.path.exists(self.steamcmd_var.get()):
            os.makedirs(self.bin_dir, exist_ok=True)
            zip_p = os.path.join(self.bin_dir, "sc.zip")
            urllib.request.urlretrieve(STEAMCMD_URL, zip_p)
            with zipfile.ZipFile(zip_p, 'r') as z: z.extractall(self.bin_dir)
            self.steamcmd_var.set(os.path.join(self.bin_dir, "steamcmd.exe"))

    def check_admin(self):
        if not ctypes.windll.shell32.IsUserAnAdmin(): self.log("NOTICE: Non-Admin mode detected.", "error")

    def browse_game(self): 
        p = filedialog.askdirectory()
        if p:
            self.path_var.set(os.path.normpath(p))
            self.path_entry.configure(foreground=BZ_CYAN) # Reset color
            self.save_config()
            self.log(f"Game path updated: {p}", "success")

    def browse_steamcmd(self): 
        p = filedialog.askopenfilename(filetypes=[("EXE", "*.exe")])
        if p:
            self.steamcmd_var.set(os.path.normpath(p))
            self.steamcmd_entry.configure(foreground=BZ_CYAN) # Reset color
            self.save_config()
            self.log(f"SteamCMD path updated: {p}", "success")
    def browse_cache(self): 
        p = filedialog.askdirectory(); self.cache_var.set(os.path.normpath(p)); self.save_config()

    def refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        m_dir = os.path.join(self.path_var.get(), "mods")
        if os.path.exists(m_dir):
            for f in os.listdir(m_dir):
                if os.path.isdir(os.path.join(m_dir, f)):
                    dt = datetime.fromtimestamp(os.path.getmtime(os.path.join(m_dir, f))).strftime('%Y-%m-%d')
                    self.tree.insert("", "end", values=(f, f, "DEPLOYED", dt))

    def launch_game(self):
        exe = os.path.join(self.path_var.get(), "battlezone98redux.exe")
        if os.path.exists(exe):
            self.launch_btn.config(text="LAUNCHING...")
            subprocess.Popen([exe], cwd=self.path_var.get())
            self.root.after(5000, lambda: self.launch_btn.config(text="LAUNCH GAME"))
    def auto_detect_gog(self):
        for g_id in GOG_REG_IDS:
            for arch in ["SOFTWARE\\WOW6432Node", "SOFTWARE"]:
                try:
                    reg = f"{arch}\\GOG.com\\Games\\{g_id}"
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg, 0, winreg.KEY_READ | winreg.KEY_WOW64_32KEY)
                    path, _ = winreg.QueryValueEx(key, "path")
                    self.path_var.set(os.path.normpath(path)); self.save_config(); return
                except: pass
if __name__ == "__main__":
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    app = BZModMaster(root)
    root.mainloop()
