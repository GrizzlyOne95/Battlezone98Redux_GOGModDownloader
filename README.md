# Battlezone 98 Redux - GOG Mod Downloader

A tool to download and manage Steam Workshop mods for non-Steam versions of Battlezone 98 Redux.

<img width="1152" height="882" alt="image" src="https://github.com/user-attachments/assets/e8a8766e-e375-4fa7-89df-5ce66886f4ae" />

<img width="1152" height="882" alt="image" src="https://github.com/user-attachments/assets/ee798aa0-df0f-42b9-9a5a-0068b9c6a2cf" />

## Features
*   **Steam Workshop Integration**: Downloads mods using SteamCMD.
*   **Mod Management**: Enable, disable, update, or delete mods via a GUI.
*   **Smart Linking**: Uses Windows Junctions to link mods to the game folder without duplicating files.
*   **Auto-Detection**: Locates GOG installations and SteamCMD automatically.

## Requirements
*   Windows 10/11
*   Battlezone 98 Redux
*   Python 3.x (if running from source)

## Usage
1.  Run the application as Administrator (required for creating Junction links).
2.  **Downloader Tab**:
    *   Ensure Game Path and SteamCMD paths are correct.
    *   Paste a Steam Workshop URL or ID. You can also drag a link from Steam right into the box!
    *   Click "Install Mod".
3.  **Manage Mods Tab**:
    *   Right-click mods to Enable (Link) or Disable (Unlink).
    *   Check for updates to keep mods synchronized with the Workshop.

## Installation
*   **Source**: Install dependencies (`pip install Pillow tkinterdnd2`) and run `cmd.py`.
