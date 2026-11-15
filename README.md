# Gallery Image Downloader

An interactive Python wrapper around `gallery-dl` for downloading gallery images into a named folder on your Desktop. It relays download progress, labels skipped and downloaded files, and prints a summary when the run ends.

## Requirements

- **Python 3.8 or later**. Checked with Python 3.14.
- An internet connection and a gallery URL supported by `gallery-dl`.
- The package listed in [`requirements.txt`](requirements.txt): **`gallery-dl`**.

The script itself uses Python's standard library. Installing `gallery-dl` also installs its required dependencies, including `requests`. Image downloads do not require `beautifulsoup4`, Pillow, `yt-dlp`, or ffmpeg.

## Installation

### Windows PowerShell

Clone this repository and install its requirements in a virtual environment:

```powershell
git clone https://github.com/foxgptrepo88-code/gallery-image-downloader.git
cd gallery-image-downloader
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Alternatively, choose **Code → Download ZIP** on GitHub, extract the archive, and open PowerShell in the extracted folder. Run the commands above starting at `python -m venv .venv`.

These instructions call the virtual environment's Python directly, so activating a PowerShell script or changing execution policy is unnecessary. If Windows provides Python through `py`, use `py -3 -m venv .venv` when creating the environment.

### macOS and Linux

After cloning or extracting the repository:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

In the examples below, replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`.

## Usage

Start without arguments to enter a gallery URL and destination folder interactively:

```powershell
.\.venv\Scripts\python.exe galleryimage_download.py
```

Or supply the gallery URL, then choose the destination folder when prompted:

```powershell
.\.venv\Scripts\python.exe galleryimage_download.py "https://example.com/foo/"
```

Replace the example URL with a real supported gallery URL. URL validation checks its format; it does not establish whether a site or gallery is supported by `gallery-dl`.

The destination prompt accepts a **folder name**, such as `Gallery Photos`. The script creates or reuses that folder on your Desktop:

- Windows uses the configured Desktop, including OneDrive redirects.
- Linux respects `XDG_DESKTOP_DIR` when it is configured.
- Other systems fall back to `~/Desktop`.

Invalid folder names can be corrected. Symbolic-link destinations and names already used by files are rejected.

Enter **Q**, **quit**, or **exit** at either input prompt to cancel. Press **Ctrl+C** to interrupt an active download. Interactive terminal runs wait for Enter before closing.

### Help

```powershell
.\.venv\Scripts\python.exe galleryimage_download.py --help
.\.venv\Scripts\python.exe galleryimage_download.py -h
```

| Argument | Meaning |
| --- | --- |
| `URL` | Optional gallery URL; prompted when omitted |
| `-h`, `--help` | Show usage, arguments, options, and examples without starting a download |

The built-in help uses the short command name `download`. Use the Python invocation above unless you have configured your own `download` shortcut. This repository does not install that shortcut automatically.

## Download behavior

The wrapper starts `gallery-dl` as a module using the same Python interpreter that runs the script. Its filter includes **JPG, JPEG, PNG, WebP, GIF, BMP, and AVIF** images. Video downloads are outside this wrapper's image filter.

- Request and download sleep intervals are set to two seconds.
- Automatic retries are set to zero.
- Existing files are handled by `gallery-dl`; its default behavior skips files already present under the expected filenames. To continue later, rerun the same URL and select the same destination folder.
- Detected HTTP 403/429, Cloudflare challenge, or “Access denied” output stops the child process and prints an access-restriction notice.
- Other messages from `gallery-dl` are displayed in the console.

Site support, filenames, and available images depend on `gallery-dl` and the source website. Existing `gallery-dl` configuration may also affect the underlying downloader. The wrapper does not add a login flow or an access-challenge bypass.

## Summary and rerunning

The console summary shows:

- Images present before and after the run.
- New image paths added during the run.
- Whether an access restriction was detected.
- The child process's exit code and the save location.

Image counts include supported image extensions in destination subdirectories. “New images” counts newly added paths; it does not compare image contents or count unique pictures across different filenames.

Progress and results are printed to the console. The script does not create an HTML report or page checkpoints. Continue an interrupted gallery by rerunning it into the same folder so the underlying downloader can skip existing files.

## Troubleshooting

| Message or symptom | What to do |
| --- | --- |
| `No module named gallery_dl` | Install `requirements.txt` using the same virtual-environment Python used to run the script. |
| Invalid gallery URL | Include `http://` or `https://`, remove spaces, and use the actual gallery URL. |
| No suitable extractor or unsupported URL | Check whether `gallery-dl` supports the site and the particular URL format. A correctly formatted URL can still be unsupported. |
| HTTP 403/429 or an access-restriction notice | Check the source site's availability and retry later when access is available. The wrapper stops further requests when it detects the restriction. |
| Gallery stopped partway through | Rerun the same URL and choose the same Desktop folder. Existing files are normally skipped. |
| No new images in the summary | Files may already exist, or the source may not expose supported images. Read the preceding `gallery-dl` messages. |

If a supported site changes, update `gallery-dl` in the virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade gallery-dl
```

All gallery URL examples use `https://example.com/foo/` as a placeholder and must be replaced before downloading.
