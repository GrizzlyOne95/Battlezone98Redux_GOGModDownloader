# Battlezone Mod Engine

A cross-platform tool to download and manage Steam Workshop mods for non-Steam versions of Battlezone 98 Redux or Battlezone Combat Commander.

<img width="1152" height="882" alt="image" src="https://github.com/user-attachments/assets/96ce052b-9391-4829-b358-eb26496fe3e8" />

<img width="1152" height="882" alt="image" src="https://github.com/user-attachments/assets/fb06ae01-2f95-4a86-8e69-e3dec221b72b" />



## Features
*   **Steam Workshop Integration**: Downloads mods using SteamCMD. No credentials or login are needed. 
*   **Multi-Game Support**: Supports both **Battlezone 98 Redux** and **Battlezone Combat Commander**.
*   **Mod Management**: Enable, disable, update, or delete mods via a GUI.
*   **Smart Linking**: Uses Windows Junctions or Linux symlinks to link mods to the game folder without duplicating files.
*   **Auto-Detection**: Locates GOG, Heroic, and Steam installations automatically on both Windows and Linux.
*   **Cross-Platform**: Works on Windows 10/11 and Linux (tested with Arch).

## Requirements
*   **Windows**: Windows 10/11
*   **Linux**: Any modern distribution with Python 3 and tkinter
*   Battlezone 98 Redux or Battlezone Combat Commander (GOG, Heroic, or Steam version)

## Installation

### Linux
```bash
# Install dependencies
sudo pacman -S python python-pillow tk  # Arch/Manjaro
# OR
sudo apt install python3 python3-pil python3-tk  # Debian/Ubuntu

# Optional: Install tkinterdnd2 for drag-and-drop support
pip install tkinterdnd2

# Run the application
python cmd.py
```

### Windows
*   **From Source**: Install dependencies (`pip install Pillow tkinterdnd2`) and run `cmd.py`.
*   **Run as Administrator** (required for creating Junction links on Windows).

## Usage
1.  Run the application (as Administrator on Windows, normal user on Linux).
2.  **Downloader Tab**:
    *   Ensure Game Path and SteamCMD paths are correct.
    *   Paste a Steam Workshop URL or ID. You can also drag a link from Steam right into the box!
    *   Click "Install Mod".
3.  **Manage Mods Tab**:
    *   Right-click mods to Enable (Link) or Disable (Unlink).
    *   Check for updates to keep mods synchronized with the Workshop.

## Troubleshooting
*   **Windows SmartScreen**: If Windows blocks the app, click **More info** → **Run anyway**. This occurs because the executable is not digitally signed.
*   **Linux**: Make sure your user has permission to create symlinks (usually enabled by default).
*   **Heroic Games Launcher**: Install games through Heroic, and the tool will auto-detect the installation path.
