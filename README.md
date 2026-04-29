# 🎧 NovaReap

> High-quality, multi-source music downloader with smart fallbacks and clean metadata.

NovaReap is a **single-file CLI tool** that downloads music from **Tidal**, resolves **Spotify links**, scrapes **Apple Music**, and falls back to **YouTube audio** when needed — all while embedding metadata and cover art automatically.

---

## ✨ Features

- 🎵 Direct **Tidal downloads** (tracks, albums, playlists)
- 🔗 **Spotify URL support** (metadata + smart fallback matching)
- 🍎 **Apple Music scraping**
- ▶️ **YouTube fallback** via `yt-dlp`
- 🏷️ Automatic **metadata + cover art embedding** (`mutagen`)
- ⚡ **Concurrent downloads** with progress UI (`rich`)
- ♻️ Resume-friendly (**skip existing files**)
- 🧪 Built-in **setup wizard** and **diagnostics**

---

## 🚀 Quick Start

### Windows (fresh install)

```powershell
winget install Python.Python.3.12
winget install Gyan.FFmpeg
```

Restart your terminal, then verify:

```powershell
python --version
ffmpeg -version
```

---

### Install NovaReap

```powershell
git clone https://github.com/<your-username>/novareap.git
cd novareap

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python novareap.py setup
python novareap.py doctor
```

---

## ⚙️ First-Time Setup

Run:

```bash
python novareap.py setup
```

This will:
- Create config + download directory
- Check dependencies (FFmpeg, yt-dlp, metadata support)
- Optionally configure Spotify
- Optionally authenticate Tidal

Skip Spotify setup:

```bash
python novareap.py setup --skip-spotify
```

Authenticate Tidal manually:

```bash
python novareap.py auth
```

---

## 📥 Usage

Download a track, album, or playlist:

```bash
python novareap.py download <url>
```

Examples:

```bash
python novareap.py download https://tidal.com/track/123
python novareap.py download https://tidal.com/album/123
python novareap.py download https://open.spotify.com/track/...
python novareap.py download https://music.apple.com/...
```

Multiple URLs:

```bash
python novareap.py download <url1> <url2> <url3>
```

---

## 🧰 Commands

| Command     | Description |
|------------|------------|
| `setup`     | First-time setup wizard |
| `doctor`    | Diagnose missing dependencies |
| `info`      | Show config + environment |
| `configure` | Edit config interactively |
| `auth`      | Authenticate Tidal |
| `download`  | Download content |
| `meta`      | Add metadata to existing files |

---

## ⚡ Options

| Option | Default | Description |
|-------|--------|------------|
| `-q, --quality` | `master` | Tidal quality (`low`, `high`, `lossless`, `master`) |
| `-o, --output` | `~/Music/NovaReap` | Output directory |
| `-c, --concurrent` | `3` | Parallel downloads |
| `--no-skip` | off | Re-download existing files |
| `--no-metadata` | off | Disable metadata tagging |
| `--config` | default path | Custom config file |

---

## 🏷️ Metadata

NovaReap automatically embeds:

- Title / Artist / Album
- Track number / Year / Genre
- Cover art
- Audio format info (FLAC, bit depth, etc.)

Manual tagging:

```bash
python novareap.py meta "path/to/file.flac"
```

---

## ⚙️ Configuration

Default config path:

```
~/.config/novareap/config.json
```

Example:

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

## 🔑 Spotify Setup (Optional)

Spotify is used for **metadata only** (not audio downloading).

1. Create an app: https://developer.spotify.com/dashboard  
2. Copy client ID + secret  
3. Run:

```bash
python novareap.py configure
```

---

## 🧪 Troubleshooting

Run diagnostics:

```bash
python novareap.py doctor
```

Common issues:

- ❌ `python` not recognized → reinstall with PATH enabled  
- ❌ `ffmpeg` not found → install + restart terminal  
- ❌ YouTube fallback fails → update dependencies  
- ❌ Metadata missing → ensure `mutagen` is installed  
- ❌ Spotify URLs fail → configure credentials  
- ❌ Tidal issues → delete session + re-authenticate  

---

## Legal & Disclaimer

NovaReap is intended **strictly** for:
> Personal, offline access to music you are legally allowed to download.

All downloads and metadata operations are executed through **official** APIs provided by the streaming services and can only be operated after providing valid authentication credentials. This tool simply automates standard access and does not circumvent DRM or illegally spoofed access to protected streams. 

**Do not distribute copyrighted content in any form or any way.** It is your sole responsibility to ensure your use of this software complies with the Terms of Service of the connected platforms and all applicable local laws.

### Limitation of Liability

[cite_start]This project is open-source and distributed under the MIT License[cite: 1]. By using this script, you acknowledge and agree to the following terms:

* [cite_start]THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. [cite: 2]
* [cite_start]IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE. [cite: 3]

---

## 📜 License

MIT