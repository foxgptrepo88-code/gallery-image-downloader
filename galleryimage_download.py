#!/usr/bin/env python3
"""Prompt for a gallery and Desktop folder, then relay gallery-dl output."""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

REQUEST_DELAY = "2"
IMAGE_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif",
)
IMAGE_FILTER = f"extension in {tuple(extension[1:] for extension in IMAGE_EXTENSIONS)}"
SECTION_SEPARATOR = "=" * 60
DESTINATION_SEPARATOR = "-" * 60
QUIT_WORDS = frozenset(("q", "quit", "exit"))
RESERVED_FOLDER_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)
INVALID_FOLDER_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
ACCESS_RESTRICTION = re.compile(
    r"HTTP\s*(403|429)\b|"
    r"\b403 Forbidden\b|"
    r"\b429 Too Many Requests\b|"
    r"Cloudflare challenge|"
    r"Access denied",
    re.IGNORECASE,
)


def _help_colors_enabled(stream):
    """Use colors only on a compatible terminal, never redirected help."""
    if ('NO_COLOR' in os.environ or os.environ.get('PYTHON_COLORS') == '0'
            or os.environ.get('TERM', '').lower() == 'dumb'):
        return False
    try:
        if not stream.isatty():
            return False
        if os.name != 'nt':
            return True
        import ctypes
        from ctypes import wintypes
        import msvcrt
        console = ctypes.WinDLL('kernel32', use_last_error=True)
        console.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        console.GetConsoleMode.restype = wintypes.BOOL
        console.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        console.SetConsoleMode.restype = wintypes.BOOL
        handle = wintypes.HANDLE(msvcrt.get_osfhandle(stream.fileno()))
        mode = wintypes.DWORD()
        return bool(console.GetConsoleMode(handle, ctypes.byref(mode))
                    and console.SetConsoleMode(handle, mode.value | 0x0004))
    except (AttributeError, ImportError, OSError, ValueError):
        return False


def _color_help(text, command):
    """Highlight after layout so ANSI sequences cannot alter alignment."""
    reset, heading, option, program, address = '\x1b[0m', '\x1b[1;36m', '\x1b[32m', '\x1b[1;32m', '\x1b[94m'
    result = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip('\r\n')
        ending = line[len(body):]
        if body and not body[0].isspace() and body.endswith(':'):
            body = heading + body + reset
        elif not body.lstrip().startswith('#'):
            body = re.sub(r'(?<![\w-])(?:--[A-Za-z][A-Za-z0-9-]*|-[A-Za-z])(?![\w-])',
                          lambda match: option + match.group() + reset, body)
            body = re.sub(r'''https?://[^\s"'<>]+''', lambda match: address + match.group() + reset, body)
            body = re.sub(r'^(\s*)(' + re.escape(command) + r')(?=\s|$)',
                          lambda match: match.group(1) + program + match.group(2) + reset, body)
            if body.startswith('usage: '):
                tail = body[len('usage: '):]
                if tail == command or tail.startswith(command + ' '):
                    tail = program + command + reset + tail[len(command):]
                body = heading + 'usage:' + reset + ' ' + tail
        result.append(body + ending)
    return ''.join(result)


class ColorHelpParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        if sys.version_info >= (3, 14):
            kwargs['color'] = False  # Avoid nesting Python's native help colors.
        super().__init__(*args, **kwargs)

    def print_help(self, file=None):
        output = sys.stdout if file is None else file
        text = self.format_help()
        if _help_colors_enabled(output):
            text = _color_help(text, self.prog)
        self._print_message(text, output)


def log(level, message):
    print(f"[{level}] {message}", flush=True)


def _print_banner(title, *, leading_newline=False):
    prefix = '\n' if leading_newline else ''
    print(prefix + SECTION_SEPARATOR)
    print(f' {title}')
    print(SECTION_SEPARATOR)


def get_desktop():
    """Find the user's Desktop, including Windows and XDG redirects."""
    home = Path.home()
    if sys.platform == 'win32':
        try:
            import winreg

            registry_path = (
                r'Software\Microsoft\Windows'
                r'\CurrentVersion\Explorer\User Shell Folders'
            )
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_path) as key:
                desktop_path, _ = winreg.QueryValueEx(key, 'Desktop')
            return Path(os.path.expandvars(desktop_path)).expanduser()
        except (OSError, ValueError):
            pass

    if sys.platform.startswith('linux'):
        configuration = home / '.config' / 'user-dirs.dirs'
        if configuration.is_file():
            lines = configuration.read_text(
                encoding='utf-8', errors='replace').splitlines()
            for line in lines:
                if line.startswith('XDG_DESKTOP_DIR='):
                    value = line.split('=', 1)[1].strip().strip('"')
                    value = value.replace('$HOME', str(home))
                    return Path(os.path.expandvars(value)).expanduser()
    return home / 'Desktop'


def _is_valid_gallery_url(url):
    try:
        parsed_url = urlparse(url)
        valid = (
            parsed_url.scheme in ('http', 'https')
            and bool(parsed_url.hostname)
            and '.' in parsed_url.hostname.strip('.')
            and not any(character.isspace() for character in url)
        )
        _ = parsed_url.port
        return valid
    except ValueError:
        return False


def get_gallery_url(given=None):
    """Validate a supplied URL or prompt until a valid URL is entered."""
    url = (given or '').strip()
    while True:
        if not url:
            url = input('[INPUT] Enter gallery URL (Q to quit): ').strip()
        if url.lower() in QUIT_WORDS:
            return None
        if _is_valid_gallery_url(url):
            log('OK', f'Valid URL format: {url}')
            return url
        print('\n[ERROR] Invalid gallery URL!')
        print('[INFO] Include http:// or https://')
        print('[INFO] Example: https://example.com/foo/')
        print('[INFO] Please try again.')
        url = ''


def valid_folder_name(name):
    """Accept portable Windows folder names without changing valid names."""
    if not name or name in ('.', '..'):
        return False
    return (
        name == name.strip(' .')
        and len(name) <= 255
        and not INVALID_FOLDER_CHARACTERS.search(name)
        and name.split('.')[0].upper() not in RESERVED_FOLDER_NAMES
    )


def _prepare_output_directory(destination):
    """Create or reuse a directory, reporting a recoverable input error."""
    if destination.is_symlink():
        log('ERROR', 'Folder is a symbolic link. Choose another.')
        return False
    if destination.exists():
        if not destination.is_dir():
            log('ERROR', 'A file already uses that name.')
            return False
        log('INFO', 'Folder already exists.')
        return True
    try:
        destination.mkdir(parents=True, exist_ok=True)
        log('OK', 'New folder created.')
        return True
    except OSError as error:
        log('ERROR', f'Cannot create folder: {error}')
        return False


def get_output_folder(desktop):
    """Prompt for a destination directory beneath the detected Desktop."""
    _print_banner('DOWNLOAD DESTINATION', leading_newline=True)
    print('[INFO] Files will be saved on your Desktop:')
    print(f'       {desktop}')
    while True:
        name = input('\n[INPUT] Enter folder name (Q to quit): ').strip()
        if name.lower() in QUIT_WORDS:
            return None
        if not valid_folder_name(name):
            log('ERROR', 'Invalid folder name. Please try again.')
            continue
        destination = desktop / name
        if not _prepare_output_directory(destination):
            continue
        print('\n' + DESTINATION_SEPARATOR)
        log('OK', f'Destination: {destination}')
        log('INFO', 'Existing images will be skipped.')
        print(DESTINATION_SEPARATOR)
        return destination


def get_image_files(directory):
    """Return relative paths for existing images, including subdirectories."""
    image_extensions = frozenset(IMAGE_EXTENSIONS)
    return {
        path.relative_to(directory)
        for path in directory.rglob('*')
        if path.is_file() and path.suffix.lower() in image_extensions
    }


def build_download_command(gallery_url, output_directory):
    """Build the existing gallery-dl invocation without starting a process."""
    command = [
        sys.executable,
        '-u',
        '-m',
        'gallery_dl',
        '--directory', str(output_directory),
        '--filter', IMAGE_FILTER,
        '--retries', '0',
        '--sleep', REQUEST_DELAY,
        '--sleep-request', REQUEST_DELAY,
        '--no-colors',
    ]
    hostname = (urlparse(gallery_url).hostname or '').lower()
    if hostname in ('fapello.com', 'www.fapello.com'):
        command.extend(['--filename', '{model}_{id:04d}.{extension}'])
    command.append(gallery_url)
    return command


def _print_download_start(gallery_url, output_directory):
    print('\n' + SECTION_SEPARATOR)
    log('INFO', 'Starting gallery download...')
    log('INFO', f'Gallery : {gallery_url}')
    log('INFO', f'Saving to: {output_directory}')
    log('INFO', 'Press CTRL+C to stop.')
    print(SECTION_SEPARATOR + '\n')


def _display_download_line(line, output_path_prefix):
    clean_line = line.strip()
    if clean_line.startswith('# '):
        log('SKIP', clean_line[2:])
    elif (clean_line.casefold().startswith(output_path_prefix)
          and clean_line.lower().endswith(IMAGE_EXTENSIONS)):
        log('DOWNLOADED', clean_line)
    else:
        print(line, end='', flush=True)


def _print_access_restriction():
    print('\n' + SECTION_SEPARATOR)
    log('STOP', 'Access denied or rate limited.')
    log('INFO', 'Stopping further requests.')
    print(SECTION_SEPARATOR)


def _wait_for_process(process, timeout):
    """Wait for a bounded interval, then kill and reap the child if needed."""
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait()


def _cleanup_download_process(process):
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
        _wait_for_process(process, timeout=5)
    if process.stdout is not None:
        process.stdout.close()


def run_download_process(command, output_directory):
    """Relay child output and always clean up its process and output pipe."""
    blocked = False
    exit_code = 1
    process = None
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,
        )
        output_path_prefix = str(output_directory).casefold()
        for line in process.stdout:
            _display_download_line(line, output_path_prefix)
            if not ACCESS_RESTRICTION.search(line):
                continue
            blocked = True
            _print_access_restriction()
            process.terminate()
            break
        exit_code = _wait_for_process(process, timeout=10)
    except KeyboardInterrupt:
        log('STOP', 'Interrupted by user.')
        exit_code = 130
    except Exception as error:
        log('ERROR', str(error))
    finally:
        _cleanup_download_process(process)
    return blocked, exit_code


def _print_download_summary(output_directory, before_count, after_count,
                            new_count, blocked, exit_code):
    _print_banner('DOWNLOAD SUMMARY', leading_newline=True)
    print(f'[INFO] Images before   : {before_count}')
    print(f'[INFO] Images after    : {after_count}')
    print(f'[INFO] New images      : {new_count}')
    print(f'[INFO] Access blocked  : {blocked}')
    print(f'[INFO] Exit code       : {exit_code}')
    print(f'[INFO] Save location   : {output_directory}')
    print(SECTION_SEPARATOR)
    if blocked:
        log('WARN', 'Stopped due to access restrictions.')
    elif exit_code == 0:
        log('DONE', 'Gallery download completed.')
    else:
        log('WARN', 'Download process ended with an error.')


def build_parser():
    parser = ColorHelpParser(
        prog="download",
        description=(
            "Download images from galleries supported by gallery-dl. "
            "You will be prompted for a destination folder on your Desktop."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  # Prompt for the gallery URL and destination folder:
  download

  # Use a gallery URL and then choose a Desktop folder:
  download "https://example.com/foo/"

  # Display usage, arguments, options, and these examples:
  download --help
  download -h

During a run:
  Enter Q at an input prompt to cancel, or press Ctrl+C to stop downloading.
  Existing images are skipped; use the same destination folder to rerun.
  Supported image formats: JPG, JPEG, PNG, WebP, GIF, BMP, AVIF.
  Requests use two-second intervals and stop on detected access restrictions.
""",
    )
    parser.add_argument(
        "url", nargs="?", metavar="URL",
        help="Gallery URL; leave it out to enter the URL interactively.",
    )
    return parser


def main(given_url=None):
    _print_banner('GALLERY IMAGE DOWNLOADER')
    gallery_url = get_gallery_url(given_url)
    if gallery_url is None:
        log('EXIT', 'Cancelled by user.')
        return
    desktop = get_desktop()
    output_directory = get_output_folder(desktop)
    if output_directory is None:
        log('EXIT', 'Cancelled by user.')
        return

    before = get_image_files(output_directory)
    command = build_download_command(gallery_url, output_directory)
    _print_download_start(gallery_url, output_directory)
    blocked, exit_code = run_download_process(command, output_directory)
    after = get_image_files(output_directory)
    new_count = sum(image not in before for image in after)
    _print_download_summary(
        output_directory, len(before), len(after), new_count, blocked, exit_code)


if __name__ == "__main__":
    # Help and argument errors exit before any prompts or download activity.
    args = build_parser().parse_args()
    try:
        main(args.url)

    except (KeyboardInterrupt, EOFError):
        print("\n[EXIT] Cancelled.")

    finally:
        if sys.stdin.isatty():
            try:
                input("\n[FINISHED] Press ENTER to exit...")
            except (KeyboardInterrupt, EOFError):
                pass
