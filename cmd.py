import os
import re
import shutil
import zipfile
import winreg
import subprocess
import threading
import urllib.request
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# --- CONFIGURATION ---
BZ98R_APPID = "301650"
GOG_REG_PATH = r"SOFTWARE\WOW6432Node\GOG.com\Games\1459427445"
STEAMCMD_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"

class BZModMaster:
    def __init__(self, root):
        self.root = root
        self.root.title("BZ98R Mod Engine v2.0")
        self.root.geometry("950x750")
        
        # 1. Define variables first
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.bin_dir = os.path.join(self.base_dir, "bin")
        self.steamcmd_exe = os.path.join(self.bin_dir, "steamcmd.exe")
        self.cache_dir = os.path.join(self.base_dir, "workshop_cache")
        self.use_physical_var = tk.BooleanVar(value=False)
        self.name_cache = {} 

        # 2. Build the UI
        self.setup_ui()
        
        # 3. Run logic AFTER UI is ready (Safe to log now)
        self.auto_detect_gog()

    def setup_ui(self):
        # Styles
        self.style = ttk.Style()
        self.style.configure("Danger.TButton", foreground="red", font=('TkDefaultFont', 9, 'bold'))
        self.style.configure("Success.TButton", foreground="green", font=('TkDefaultFont', 9, 'bold'))

        self.tabs = ttk.Notebook(self.root)
        self.dl_tab = ttk.Frame(self.tabs)
        self.manage_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.dl_tab, text="Downloader")
        self.tabs.add(self.manage_tab, text="Manage & Conflicts")
        self.tabs.pack(fill="both", expand=True)

        # --- DOWNLOADER TAB ---
        p_frame = ttk.LabelFrame(self.dl_tab, text="Settings & Path", padding=10)
        p_frame.pack(fill="x", padx=10, pady=5)
        self.path_var = tk.StringVar()
        ttk.Entry(p_frame, textvariable=self.path_var).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(p_frame, text="Browse", command=self.browse_path).pack(side="right")
        
        opt_frame = ttk.Frame(self.dl_tab, padding=5)
        opt_frame.pack(fill="x")
        ttk.Checkbutton(opt_frame, text="Physical Storage (Copy files)", variable=self.use_physical_var).pack(side="left", padx=10)
        ttk.Button(opt_frame, text="Launch Game", command=self.launch_game, style="Success.TButton").pack(side="right", padx=10)

        dl_frame = ttk.Frame(self.dl_tab, padding=10)
        dl_frame.pack(fill="x")
        ttk.Label(dl_frame, text="Workshop ID:").pack(side="left")
        self.mod_id_var = tk.StringVar()
        ttk.Entry(dl_frame, textvariable=self.mod_id_var, width=15).pack(side="left", padx=5)
        self.dl_btn = ttk.Button(dl_frame, text="Download & Install", command=self.start_download)
        self.dl_btn.pack(side="left", padx=10)

        # The Log Box
        self.log_box = tk.Text(self.dl_tab, state="disabled", font=("Consolas", 9), height=15)
        self.log_box.pack(fill="both", expand=True, padx=10, pady=10)
        self.progress = ttk.Progressbar(self.dl_tab, mode="indeterminate")
        self.progress.pack(fill="x", padx=10, pady=5)

        # --- MANAGEMENT TAB ---
        m_top = ttk.Frame(self.manage_tab, padding=5)
        m_top.pack(fill="x")
        ttk.Button(m_top, text="Deactivate All", command=lambda: self.toggle_all(False)).pack(side="left", padx=2)
        ttk.Button(m_top, text="Re-enable All", command=lambda: self.toggle_all(True)).pack(side="left", padx=2)
        ttk.Button(m_top, text="Clean Unlinked Cache", command=self.clean_cache).pack(side="left", padx=20)
        ttk.Button(m_top, text="Scan Conflicts", command=self.scan_conflicts, style="Danger.TButton").pack(side="right", padx=2)

        m_mid = ttk.Frame(self.manage_tab, padding=10)
        m_mid.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(m_mid, columns=("Name", "ID", "Type"), show="headings")
        self.tree.heading("Name", text="Mod Name")
        self.tree.heading("ID", text="Workshop ID")
        self.tree.heading("Type", text="Status/Type")
        self.tree.pack(fill="both", expand=True, side="left")
        
        btn_bar = ttk.Frame(self.manage_tab, padding=5)
        btn_bar.pack(fill="x")
        ttk.Button(btn_bar, text="Refresh List", command=self.refresh_list).pack(side="left", padx=5)
        ttk.Button(btn_bar, text="Open in Explorer", command=self.open_explorer).pack(side="left", padx=5)
        ttk.Button(btn_bar, text="Remove Mod", command=self.unlink_mod).pack(side="right", padx=5)

    def log(self, msg):
        """The missing method that was causing the AttributeError."""
        self.log_box.config(state="normal")
        self.log_box.insert("end", f"> {msg}\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def auto_detect_gog(self):
        try:
            access = winreg.KEY_READ | winreg.KEY_WOW64_32KEY
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, GOG_REG_PATH, 0, access)
            path, _ = winreg.QueryValueEx(key, "path")
            self.path_var.set(os.path.normpath(path))
            self.log(f"GOG Path found: {path}")
            winreg.CloseKey(key)
        except (FileNotFoundError, OSError):
            self.log("GOG Registry not found. Running in manual mode.")

    def launch_game(self):
        game_path = self.path_var.get().strip()
        exe_path = os.path.join(game_path, "battlezone98redux.exe")
        if os.path.exists(exe_path):
            self.log("Launching BZ98R...")
            subprocess.Popen([exe_path], cwd=game_path)
        else:
            messagebox.showerror("Error", "EXE not found. Please browse for game folder.")

    def clean_cache(self):
        """Scans cache for mods NOT found in the current game mods folder."""
        mods_dir = os.path.join(self.path_var.get(), "mods")
        workshop_data_dir = os.path.join(self.cache_dir, "steamapps", "workshop", "content", BZ98R_APPID)
        
        if not os.path.exists(workshop_data_dir):
            return self.log("Cache is empty.")

        active_ids = {f.replace("DISABLED_", "") for f in os.listdir(mods_dir)} if os.path.exists(mods_dir) else set()
        cleaned_count = 0
        
        for cached_id in os.listdir(workshop_data_dir):
            if cached_id not in active_ids:
                shutil.rmtree(os.path.join(workshop_data_dir, cached_id))
                cleaned_count += 1
        
        self.log(f"Cache Cleanup: Removed {cleaned_count} unlinked mod folders.")

    def scan_conflicts(self):
        mods_dir = os.path.join(self.path_var.get(), "mods")
        if not os.path.exists(mods_dir): return
        file_map, material_map = {}, {}
        self.log("--- STARTING CONFLICT SCAN ---")
        for mod_id in os.listdir(mods_dir):
            if mod_id.startswith("DISABLED_"): continue
            mod_path = os.path.join(mods_dir, mod_id)
            for root, _, files in os.walk(mod_path):
                for f in files:
                    file_map.setdefault(f.lower(), []).append(mod_id)
                    if f.lower().endswith(".material"):
                        try:
                            with open(os.path.join(root, f), 'r') as m:
                                names = re.findall(r'material\s+([^\s{]+)', m.read())
                                for n in names: material_map.setdefault(n, []).append(mod_id)
                        except: pass
        conflicts = [f"FILE: '{fn}' in {o}" for fn, o in file_map.items() if len(o) > 1]
        conflicts += [f"MAT: '{mn}' in {o}" for mn, o in material_map.items() if len(o) > 1]
        for c in conflicts: self.log(f"CONFLICT: {c}")
        if not conflicts: self.log("No conflicts found.")

    def get_workshop_name(self, mod_id):
        if mod_id in self.name_cache: return self.name_cache[mod_id]
        try:
            url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={mod_id}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as res:
                html = res.read().decode('utf-8')
                match = re.search(r'<div class="workshopItemTitle">(.*?)</div>', html)
                if match:
                    self.name_cache[mod_id] = match.group(1).strip()
                    return self.name_cache[mod_id]
        except: pass
        return f"Unknown Mod ({mod_id})"

    def threaded_name_fetch(self, mod_id, is_disabled):
        clean_id = mod_id.replace("DISABLED_", "")
        name = self.get_workshop_name(clean_id)
        status = "DISABLED" if is_disabled else ("Junction" if os.path.isjunction(os.path.join(self.path_var.get(), "mods", mod_id)) else "Physical")
        self.root.after(0, lambda: self.tree.insert("", "end", values=(name, mod_id, status)))

    def refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        mods_dir = os.path.join(self.path_var.get(), "mods")
        if not os.path.exists(mods_dir): return
        for folder in os.listdir(mods_dir):
            if os.path.isdir(os.path.join(mods_dir, folder)):
                threading.Thread(target=self.threaded_name_fetch, args=(folder, folder.startswith("DISABLED_")), daemon=True).start()

    def start_download(self):
        mid, gp = self.mod_id_var.get().strip(), self.path_var.get().strip()
        if not mid.isdigit() or not os.path.exists(gp): return messagebox.showerror("Error", "Check path/ID")
        self.dl_btn.config(state="disabled"); self.progress.start()
        threading.Thread(target=self.download_logic, args=(mid, gp), daemon=True).start()

    def download_logic(self, mod_id, game_path):
        try:
            if not os.path.exists(self.steamcmd_exe):
                self.log("Downloading SteamCMD..."); os.makedirs(self.bin_dir, exist_ok=True)
                z = os.path.join(self.base_dir, "t.zip")
                urllib.request.urlretrieve(STEAMCMD_URL, z)
                with zipfile.ZipFile(z, 'r') as zf: zf.extractall(self.bin_dir)
                os.remove(z)
            
            cmd = [self.steamcmd_exe, "+force_install_dir", os.path.normpath(self.cache_dir), "+login", "anonymous", "+workshop_download_item", BZ98R_APPID, mod_id, "+quit"]
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in p.stdout: self.log(line.strip())
            p.wait()

            src = os.path.normpath(os.path.join(self.cache_dir, "steamapps/workshop/content", BZ98R_APPID, mod_id))
            dst = os.path.normpath(os.path.join(game_path, "mods", mod_id))
            if os.path.exists(src):
                if not os.path.exists(os.path.dirname(dst)): os.makedirs(os.path.dirname(dst))
                if self.use_physical_var.get():
                    if os.path.exists(dst): shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    if not os.path.exists(dst): subprocess.run(f'mklink /J "{dst}" "{src}"', shell=True)
            self.root.after(0, self.refresh_list)
        except Exception as e: self.log(f"Error: {e}")
        finally:
            self.progress.stop(); self.root.after(0, lambda: self.dl_btn.config(state="normal"))

    # Helpers
    def browse_path(self):
        p = filedialog.askdirectory()
        if p: self.path_var.set(os.path.normpath(p))
    def open_explorer(self):
        sel = self.tree.selection()
        if sel: os.startfile(os.path.join(self.path_var.get(), "mods", self.tree.item(sel[0])['values'][1]))
    def toggle_all(self, e):
        m = os.path.join(self.path_var.get(), "mods")
        if not os.path.exists(m): return
        for f in os.listdir(m):
            p = os.path.join(m, f)
            if e and f.startswith("DISABLED_"): os.rename(p, os.path.join(m, f[9:]))
            elif not e and not f.startswith("DISABLED_"): os.rename(p, os.path.join(m, f"DISABLED_{f}"))
        self.refresh_list()
    def unlink_mod(self):
        sel = self.tree.selection()
        if not sel: return
        t = os.path.join(self.path_var.get(), "mods", self.tree.item(sel[0])['values'][1])
        if os.path.isjunction(t): os.rmdir(t)
        else: shutil.rmtree(t)
        self.refresh_list()

if __name__ == "__main__":
    root = tk.Tk()
    app = BZModMaster(root)
    root.mainloop()
