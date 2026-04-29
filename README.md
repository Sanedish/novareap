# NovaReap by `Sanedish`

> NovaReap - Simple, compact, excellence. 

NovaReap is a **highly robust, pip-installable CLI tool** that downloads music from **Tidal**, resolves **Spotify links**, scrapes **Apple Music**, and utilizes **YouTube audio** as fallback when needed — all while extensively embedding metadata and cover art, **fully** autmatically.

---

## Features

- 🎵 Direct **Tidal downloads** (tracks, albums, playlists)
- 🔗 **Spotify URL support** (metadata + smart fallback matching)
- 🍏 **Apple Music scraping**
- ▶️ **YouTube / Spotify fallback** via `yt-dlp` & `spotipy`
- 🏷️ **FULL** & Automatic **metadata + cover art embedding** through `mutagen`
- ⚡ **Concurrent downloads** with progress UI (`rich`)
- ♻️ User-frienly -- **skip existing files** if existing
- 🧪 Built-in **setup wizard** and **diagnostics**

---


## 📥Quick start / Install [pip]
Simply run:
```bash
pip install novareap

novareap doctor 
novareap setup
```
`doctor` checks if dependencies are correctly installed [i.e `mutagen` for metadata].
`setup` is.. well.. setup.. it will prompt you to configure the tool and log in using tidal to authorize tidalapi.

---


## 📦 Raw Setup Requirements:

```txt
Python 3.13

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

## [Windows] Base Setup:

```powershell
winget install Python.Python.3.13
winget install Gyan.FFmpeg
```

Restart your terminal, then verify:

```powershell
python --version
ffmpeg -version
```

---

### Raw-install NovaReap [git]

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

## 📋First-Time Setup

Run:

```bash
novareap setup
```

Or [raw install]
```bash
cd novareap
python cli.py setup
```

This will:
- Authenticate Tidal [as mentioned in `Quick Start`]
- Create config + configure the download directory
- Sanity-check dependencies (FFmpeg, yt-dlp, metadata support)
- Optionally configure Spotify for fallback and link resolution

Skip Spotify setup:

```bash
novareap setup --skip-spotify
```
Or simply leave fields blank to skip.


Manually authenticate Tidal:

```bash
novareap auth
```

---


## Usage

Download a track, album, or playlist:

```bash
novareap download <url>
```
raw:
```bash
python cli.py download <url>
```

Examples:

```bash
novareap download https://tidal.com/track/123
novareap download https://tidal.com/album/123
novareap download https://open.spotify.com/track/...
novareap download https://music.apple.com/...
```
same logic applies to raw.


Downloading multiple URLs at once:

```bash
novareap download <url1> <url2> <url3>
```

---

## 🔧 NovaReap Commads

| Command     | Description |
|------------|------------|
| `setup`     | First-time setup wizard |
| `doctor`    | Check installed dependencies and highlight missing ones |
| `info`      | Show config + environment |
| `configure` | Edit config interactively |
| `auth`      | Authenticate Tidal |
| `download`  | Download content |
| `meta`      | Manually add metadata to existing files |

---

## 📦 Flags

| Option | Default | Description |
|-------|--------|------------|
| `-q, --quality` | `master` | Tidal quality (`low`, `high`, `lossless`, `master`) |
| `-o, --output` | `~/Music/NovaReap` | Output directory |
| `-c, --concurrent` | `3` | Parallel downloads |
| `--no-skip` | off | Re-download existing files |
| `--no-metadata` | off - metadata enabled | Disable metadata tagging |
| `--config` | `~/.config/novareap/config.json`| Custom config file |

---

## 🏷️ Metadata

NovaReap will automatically embed:

- **Title / Artist / Album**
- **Track number / Year / Genre**
- **Cover art***
- **Audio format info** (FLAC, bit depth, etc.)

You can however use manual tagging:

```bash
novareap meta "path/to/file.flac"
```

---

## ⚙️ Configuration

Default config path:

```
~/.config/novareap/config.json
```

By default, we save configs as follows:

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

Currently, Spotify is used for **metadata only** (not audio downloading).

1. Create an app: https://developer.spotify.com/dashboard  
2. Copy client ID + secret  
3. Run:

```bash
novareap configure
```
Enter your credentials - done! :3

---

## 🔧 Troubleshooting

Run sanity check:

```bash
novareap doctor
```

Common issues may be resolved by following the below:

- ❌ `python` not recognized → reinstall with PATH enabled  
- ❌ `ffmpeg` not found → install, add to path, restart terminal  
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

## License

MIT