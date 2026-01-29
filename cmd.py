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
        self.root.geometry("900x700")
        
        # Internal Paths
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.bin_dir = os.path.join(self.base_dir, "bin")
        self.steamcmd_exe = os.path.join(self.bin_dir, "steamcmd.exe")
        self.cache_dir = os.path.join(self.base_dir, "workshop_cache")
        
        self.use_physical_var = tk.BooleanVar(value=False)
        self.name_cache = {} 
        self.setup_ui()
        self.auto_detect_gog()

    def setup_ui(self):
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
        ttk.Checkbutton(opt_frame, text="Physical Storage (Copy files instead of linking)", 
                        variable=self.use_physical_var).pack(side="left", padx=10)

        dl_frame = ttk.Frame(self.dl_tab, padding=10)
        dl_frame.pack(fill="x")
        ttk.Label(dl_frame, text="Workshop ID:").pack(side="left")
        self.mod_id_var = tk.StringVar()
        ttk.Entry(dl_frame, textvariable=self.mod_id_var, width=15).pack(side="left", padx=5)
        self.dl_btn = ttk.Button(dl_frame, text="Download & Install", command=self.start_download)
        self.dl_btn.pack(side="left", padx=10)

        self.log_box = tk.Text(self.dl_tab, state="disabled", font=("Consolas", 9), height=15)
        self.log_box.pack(fill="both", expand=True, padx=10, pady=10)
        self.progress = ttk.Progressbar(self.dl_tab, mode="indeterminate")
        self.progress.pack(fill="x", padx=10, pady=5)

        # --- MANAGEMENT TAB ---
        m_top = ttk.Frame(self.manage_tab, padding=5)
        m_top.pack(fill="x")
        ttk.Button(m_top, text="Deactivate All", command=lambda: self.toggle_all(False)).pack(side="left", padx=2)
        ttk.Button(m_top, text="Re-enable All", command=lambda: self.toggle_all(True)).pack(side="left", padx=2)
        ttk.Button(m_top, text="Scan Conflicts", command=self.scan_conflicts, color="red").pack(side="right", padx=2)

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

    # --- QOL LOGIC ---

    def open_explorer(self):
        selected = self.tree.selection()
        if not selected: return
        mod_id = self.tree.item(selected[0])['values'][1]
        path = os.path.join(self.path_var.get(), "mods", str(mod_id))
        if os.path.exists(path):
            os.startfile(path)

    def toggle_all(self, enable=True):
        mods_dir = os.path.join(self.path_var.get(), "mods")
        if not os.path.exists(mods_dir): return
        
        count = 0
        for folder in os.listdir(mods_dir):
            old_path = os.path.join(mods_dir, folder)
            if enable and folder.startswith("DISABLED_"):
                new_path = os.path.join(mods_dir, folder.replace("DISABLED_", ""))
                os.rename(old_path, new_path)
                count += 1
            elif not enable and not folder.startswith("DISABLED_"):
                new_path = os.path.join(mods_dir, f"DISABLED_{folder}")
                os.rename(old_path, new_path)
                count += 1
        self.log(f"{'Enabled' if enable else 'Disabled'} {count} mods.")
        self.refresh_list()

    def scan_conflicts(self):
        """Advanced BZ98R Scanner: Filenames and Material definitions."""
        mods_dir = os.path.join(self.path_var.get(), "mods")
        if not os.path.exists(mods_dir): return
        
        file_map = {} # filename -> [mod_ids]
        material_map = {} # mat_name -> [mod_ids]
        
        self.log("--- STARTING CONFLICT SCAN ---")
        for mod_id in os.listdir(mods_dir):
            if mod_id.startswith("DISABLED_"): continue
            mod_path = os.path.join(mods_dir, mod_id)
            
            for root, _, files in os.walk(mod_path):
                for f in files:
                    # 1. Filename Conflict
                    file_map.setdefault(f.lower(), []).append(mod_id)
                    
                    # 2. Material Definition Conflict
                    if f.lower().endswith(".material"):
                        m_path = os.path.join(root, f)
                        try:
                            with open(m_path, 'r') as mat_file:
                                content = mat_file.read()
                                # Regex for Ogre material names: material Name {
                                names = re.findall(r'material\s+([^\s{]+)', content)
                                for n in names:
                                    material_map.setdefault(n, []).append(mod_id)
                        except: pass

        # Report
        conflicts_found = False
        for fname, owners in file_map.items():
            if len(owners) > 1:
                self.log(f"FILE CONFLICT: '{fname}' found in {owners}")
                conflicts_found = True
        
        for mname, owners in material_map.items():
            if len(owners) > 1:
                self.log(f"MATERIAL CONFLICT: '{mname}' defined in {owners}")
                conflicts_found = True
                
        if not conflicts_found:
            self.log("No conflicts detected. Fly safe, pilot.")
        else:
            messagebox.showwarning("Conflicts Detected", "Check logs for details. Overlapping files/materials found!")

    # --- CORE METHODS (UPDATED) ---

    def download_logic(self, mod_id, game_path):
        try:
            self.ensure_steamcmd()
            norm_cache = os.path.normpath(self.cache_dir)
            cmd = [self.steamcmd_exe, "+force_install_dir", norm_cache, "+login", "anonymous", 
                   "+workshop_download_item", BZ98R_APPID, mod_id, "+quit"]
            
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in p.stdout: self.log(line.strip())
            p.wait()

            src = os.path.normpath(os.path.join(self.cache_dir, "steamapps/workshop/content", BZ98R_APPID, mod_id))
            dst = os.path.normpath(os.path.join(game_path, "mods", mod_id))
            
            if os.path.exists(src):
                if not os.path.exists(os.path.dirname(dst)): os.makedirs(os.path.dirname(dst))
                
                if self.use_physical_var.get():
                    self.log("Copying files (Physical)...")
                    if os.path.exists(dst): shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    self.log("Linking files (Junction)...")
                    if not os.path.exists(dst):
                        subprocess.run(f'mklink /J "{dst}" "{src}"', shell=True)
            
            self.root.after(0, self.refresh_list)
            messagebox.showinfo("Success", f"Mod {mod_id} installed.")
        except Exception as e: self.log(f"Error: {e}")
        finally:
            self.progress.stop()
            self.root.after(0, lambda: self.dl_btn.config(state="normal"))

    # (Other helper methods browse_path, auto_detect_gog, refresh_list, get_workshop_name, ensure_steamcmd remain the same as previous)
    def browse_path(self):
        path = filedialog.askdirectory()
        if path: self.path_var.set(os.path.normpath(path))

    def auto_detect_gog(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, GOG_REG_PATH, 0, winreg.KEY_READ)
            path, _ = winreg.QueryValueEx(key, "path")
            self.path_var.set(os.path.normpath(path))
            self.log(f"GOG Path found: {path}")
        except: self.log("GOG Registry not found.")

    def get_workshop_name(self, mod_id):
        if mod_id in self.name_cache: return self.name_cache[mod_id]
        try:
            url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={mod_id}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as res:
                html = res.read().decode('utf-8')
                match = re.search(r'<div class="workshopItemTitle">(.*?)</div>', html)
                if match:
                    name = match.group(1).strip()
                    self.name_cache[mod_id] = name
                    return name
        except: pass
        return f"Unknown Mod ({mod_id})"

    def threaded_name_fetch(self, mod_id, is_disabled):
        name = self.get_workshop_name(mod_id.replace("DISABLED_", ""))
        status = "DISABLED" if is_disabled else "Active"
        self.root.after(0, lambda: self.tree.insert("", "end", values=(name, mod_id, status)))

    def refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        game_path = self.path_var.get().strip()
        mods_dir = os.path.join(game_path, "mods")
        if not os.path.exists(mods_dir): return

        for folder in os.listdir(mods_dir):
            f_path = os.path.abspath(os.path.join(mods_dir, folder))
            is_disabled = folder.startswith("DISABLED_")
            # Show both active junctions and disabled folders
            if os.path.isjunction(f_path) or os.path.isdir(f_path):
                threading.Thread(target=self.threaded_name_fetch, args=(folder, is_disabled), daemon=True).start()

    def unlink_mod(self):
        selected = self.tree.selection()
        if not selected: return
        item = self.tree.item(selected[0])
        mod_id = item['values'][1]
        target = os.path.join(self.path_var.get(), "mods", str(mod_id))
        try:
            if os.path.isjunction(target): os.rmdir(target)
            else: shutil.rmtree(target)
            self.log(f"Removed: {mod_id}")
            self.refresh_list()
        except Exception as e: messagebox.showerror("Error", str(e))

    def ensure_steamcmd(self):
        if not os.path.exists(self.steamcmd_exe):
            self.log("Installing SteamCMD...")
            os.makedirs(self.bin_dir, exist_ok=True)
            z_path = os.path.join(self.base_dir, "temp.zip")
            urllib.request.urlretrieve(STEAMCMD_URL, z_path)
            with zipfile.ZipFile(z_path, 'r') as z: z.extractall(self.bin_dir)
            os.remove(z_path)

    def start_download(self):
        mid = self.mod_id_var.get().strip()
        gp = self.path_var.get().strip()
        if not mid.isdigit() or not os.path.exists(gp): return
        self.dl_btn.config(state="disabled")
        self.progress.start()
        threading.Thread(target=self.download_logic, args=(mid, gp), daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = BZModMaster(root)
    root.mainloop()