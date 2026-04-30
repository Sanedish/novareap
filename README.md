# NovaReap

> Simple, compact, excellence.

NovaReap is a robust, pip-installable CLI tool that downloads music from **Tidal**, resolves **Spotify links**, scrapes **Apple Music**, and uses **YouTube audio** as a fallback — all while automatically embedding full metadata and cover art.

---

## Features

- 🎵 Direct **Tidal downloads** — tracks, albums, and playlists
- 🔗 **Spotify URL support** — metadata resolution with smart fallback matching
- 🍏 **Apple Music scraping**
- ▶️ **YouTube / Spotify fallback** via `yt-dlp` and `spotipy`
- 🏷️ **Full, automatic metadata and cover art embedding** via `mutagen`
- ⚡ **Concurrent downloads** with a progress UI powered by `rich`
- ♻️ **Skip existing files** to avoid redundant re-downloads
- 🧪 Built-in **setup wizard** and **diagnostics**

---

## Quick Start

```bash
pip install novareap

novareap doctor
novareap setup
```

- `doctor` — verifies that all dependencies (e.g. `mutagen`, `ffmpeg`) are correctly installed
- `setup` — walks you through configuration and Tidal authentication

---

## Requirements

**Python version:** 3.13

```txt
click>=8.3.2,<9
requests>=2.33.1,<3
beautifulsoup4>=4.14.3,<5
rich>=15.0.0,<16
mutagen>=1.47.0,<2
spotipy>=2.26.0,<3
tidalapi>=0.8.11,<0.9
yt-dlp[default]>=2026.2.4
```

---

## Installation

### pip (recommended)

```bash
pip install novareap
```

### From source (Windows)

**1. Install system dependencies:**

```powershell
winget install Python.Python.3.13
winget install Gyan.FFmpeg
```

Restart your terminal, then verify:

```powershell
python --version
ffmpeg -version
```

**2. Clone and install:**

```powershell
git clone https://github.com/Sanedish/novareap.git
cd novareap

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install .

novareap doctor
novareap setup
```

---

## First-Time Setup

```bash
novareap setup
```

This will:

- Authenticate with Tidal
- Create a config file and set your download directory
- Sanity-check dependencies (FFmpeg, yt-dlp, metadata support)
- Optionally configure Spotify credentials for fallback and link resolution

**Skip Spotify setup:**

```bash
novareap setup --skip-spotify
```

Or simply leave the Spotify fields blank when prompted.

**Re-authenticate Tidal manually:**

```bash
novareap auth
```

---

## Usage

Download a track, album, or playlist:

```bash
novareap download <url>
```

**Examples:**

```bash
novareap download https://tidal.com/track/123
novareap download https://tidal.com/album/123
novareap download https://open.spotify.com/track/...
novareap download https://music.apple.com/...
```

**Download multiple URLs at once:**

```bash
novareap download <url1> <url2> <url3>
```

---

## Commands

| Command     | Description                                      |
|-------------|--------------------------------------------------|
| `setup`     | First-time setup wizard                          |
| `doctor`    | Check installed dependencies; highlight missing  |
| `info`      | Show current config and environment              |
| `configure` | Edit config interactively                        |
| `auth`      | Authenticate Tidal                               |
| `download`  | Download content                                 |
| `meta`      | Manually embed metadata into existing files      |

---

## Flags

| Option              | Default                           | Description                        |
|---------------------|-----------------------------------|------------------------------------|
| `-q, --quality`     | `master`                          | Tidal quality: `low`, `high`, `lossless`, `master` |
| `-o, --output`      | `~/Music/NovaReap`                | Output directory                   |
| `-c, --concurrent`  | `3`                               | Number of parallel downloads       |
| `--no-skip`         | off                               | Re-download files that already exist |
| `--no-metadata`     | off                               | Disable metadata tagging           |
| `--config`          | `~/.config/novareap/config.json`  | Path to a custom config file       |

---

## Metadata

NovaReap automatically embeds:

- Title, Artist, Album
- Track number, Year, Genre
- Cover art
- Audio format info (FLAC, bit depth, etc.)

To manually tag an existing file:

```bash
novareap meta "path/to/file.flac"
```

---

## Configuration

Default config path:

```
~/.config/novareap/config.json
```

Default values:

```json
{
  "download_dir": "~/Music/NovaReap",
  "tidal_quality": "master",
  "concurrent_downloads": 3,
  "retry_attempts": 3,
  "retry_delay": 2.0,
  "skip_existing": true,
  "embed_metadata": true,
  "filename_template": "{artist} - {title}"
}
```

---

## Spotify Setup (Optional)

Spotify is currently used for **metadata resolution only** — not audio downloading.

1. Create an app at [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
2. Copy your Client ID and Client Secret
3. Run `novareap configure` and enter your credentials

---

## Troubleshooting

Run a full diagnostics check:

```bash
novareap doctor
```

Common fixes:

| Symptom | Fix |
|---|---|
| `python` not recognized | Reinstall Python with PATH option enabled |
| `ffmpeg` not found | Install FFmpeg, add to PATH, restart terminal |
| YouTube fallback fails | Run `pip install --upgrade yt-dlp` |
| Metadata not embedded | Ensure `mutagen` is installed |
| Spotify URLs fail | Configure Spotify credentials via `novareap configure` |
| Tidal auth issues | Delete the saved session and re-run `novareap auth` |

---

## Legal & Disclaimer

NovaReap is intended **strictly for personal, offline access to music you are legally entitled to download.**

All downloads operate through official platform APIs and require valid authentication credentials. This tool automates standard access only — it does not circumvent DRM or spoof protected streams.

**Do not distribute copyrighted content.** You are solely responsible for ensuring your use of this software complies with the Terms of Service of each connected platform and all applicable local laws.

This project is open-source and distributed under the **MIT License**. The software is provided "as is", without warranty of any kind. The authors are not liable for any claims or damages arising from its use.

---

## License

[MIT](LICENSE)
