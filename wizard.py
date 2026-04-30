#!/usr/bin/env python3
"""
First-time Wizard for the NovaReap system - This script will auto-check and install all required dependencies
"""

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# --- 1. Bootstrap Dependencies ---
def run_cmd(cmd, shell=False):
    try:
        subprocess.run(cmd, check=True, shell=shell)
        return True
    except subprocess.CalledProcessError:
        return False

print("Checking Python dependencies...")
if not run_cmd([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]):
    print("Failed to install Python dependencies. Please check your requirements.txt.")
    sys.exit(1)

# Now we can safely import rich
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.panel import Panel

console = Console()

def install_ffmpeg():
    sys_name = platform.system()
    console.print("[cyan]Installing FFmpeg...[/cyan]")
    
    if sys_name == "Windows":
        run_cmd(["winget", "install", "Gyan.FFmpeg"])
    elif sys_name == "Darwin": # macOS
        run_cmd(["brew", "install", "ffmpeg"])
    elif sys_name == "Linux":
        if shutil.which("apt-get"):
            run_cmd(["sudo", "apt-get", "install", "-y", "ffmpeg"])
        elif shutil.which("pacman"):
            run_cmd(["sudo", "pacman", "-S", "--noconfirm", "ffmpeg"])
        elif shutil.which("dnf"):
            run_cmd(["sudo", "dnf", "install", "-y", "ffmpeg"])
        else:
            console.print("[warning]Could not determine Linux package manager. Please install FFmpeg manually.[/warning]")
    else:
        console.print(f"[warning]Unsupported OS '{sys_name}'. Please install FFmpeg manually.[/warning]")

# --- 2. Start Wizard ---
console.print(Panel.fit("[bold green]Welcome to the NovaReap Setup Wizard[/bold green]"))

# FFmpeg check
if not shutil.which("ffmpeg"):
    if Confirm.ask("FFmpeg is missing but required for audio conversion. Attempt auto-install?"):
        install_ffmpeg()
        if not shutil.which("ffmpeg"):
            console.print("[error]FFmpeg install failed or requires terminal restart. Please install manually.[/error]")
else:
    console.print("[success]FFmpeg is already installed.[/success]")

# Config base
config = {
    "download_dir": str(Path.home() / "Music" / "NovaReap"),
    "session_file": str(Path.home() / ".config" / "novareap" / "tidal_session.json"),
    "spotify_client_id": "",
    "spotify_client_secret": "",
    "tidal_quality": "master",
    "youtube_quality": "320",
    "concurrent_downloads": 3,
    "skip_existing": True,
    "embed_metadata": True,
    "filename_template": "{artist} - {title}"
}

# --- Downloader Selection & Creds ---
console.print("\n[bold]Which downloaders do you plan to use?[/bold]")
use_tidal = Confirm.ask("Tidal (Direct Download)", default=True)
use_spotify = Confirm.ask("Spotify (Metadata -> YouTube Fallback Download)", default=True)

if use_spotify:
    console.print("\n[info]Spotify requires an API Client ID and Secret to fetch metadata.[/info]")
    console.print("Get these at: https://developer.spotify.com/dashboard")
    config["spotify_client_id"] = Prompt.ask("Spotify Client ID")
    config["spotify_client_secret"] = Prompt.ask("Spotify Client Secret", password=True)

# --- Quality Selection ---
console.print("\n[bold]Download Quality Preferences[/bold]")

if use_tidal:
    console.print("""
[cyan]Tidal Quality Options:[/cyan]
1. Low      (96kbps AAC  | ~2-3MB  | Fast)
2. High     (320kbps AAC | ~6-8MB  | Moderate)
3. Lossless (16-bit FLAC | ~20MB   | Slower)
4. Master   (24-bit FLAC | ~40MB+  | Slowest)
    """)
    t_choice = Prompt.ask("Select Tidal Quality", choices=["1", "2", "3", "4"], default="4")
    t_map = {"1": "low", "2": "high", "3": "lossless", "4": "master"}
    config["tidal_quality"] = t_map[t_choice]

console.print("""
[cyan]YouTube/Fallback Quality Options (MP3):[/cyan]
1. 128kbps (~3MB)
2. 192kbps (~4.5MB)
3. 256kbps (~6MB)
4. 320kbps (~8MB)
""")
y_choice = Prompt.ask("Select YouTube Quality", choices=["1", "2", "3", "4"], default="4")
y_map = {"1": "128", "2": "192", "3": "256", "4": "320"}
config["youtube_quality"] = y_map[y_choice]

# --- Directory & Extras ---
console.print("\n[bold]Final Settings[/bold]")
config["download_dir"] = Prompt.ask("Download Directory", default=config["download_dir"])
config["concurrent_downloads"] = int(Prompt.ask("Concurrent Downloads (Max parallel workers)", default="3"))

# --- Save Config ---
config_path = Path.home() / ".config" / "novareap" / "config.json"
config_path.parent.mkdir(parents=True, exist_ok=True)

with open(config_path, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)

Path(config["download_dir"]).mkdir(parents=True, exist_ok=True)

console.print(f"\n[bold green]Setup Complete![/bold green] Config saved to {config_path}")

if use_tidal:
    console.print("\n[info]Since you enabled Tidal, let's authenticate your session.[/info]")
    run_cmd([sys.executable, "novareap.py", "auth"])
