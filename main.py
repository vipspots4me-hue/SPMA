import os
import sys
import time
import fcntl
import shutil
import subprocess
import urllib.request
import zipfile
import tarfile
from pathlib import Path

import streamlit as st


# ============================================================
# PATHS
# ============================================================

APP_DIR = Path("/mount/src/spma")

SPOTDL_VENV = APP_DIR / ".spotdl_venv"
SPOTDL_PYTHON = SPOTDL_VENV / "bin" / "python"
SPOTDL_CMD = SPOTDL_VENV / "bin" / "spotdl"

LOCAL_BIN = APP_DIR / ".bin"
DENO_BIN = LOCAL_BIN / "deno"

FFMPEG_DIR = Path.home() / ".config" / "spotdl"
FFMPEG_BIN = FFMPEG_DIR / "ffmpeg"

BOT_LOCK_FILE = "/tmp/spma_telegram_bot.lock"

TEST_URL = "https://www.youtube.com/watch?v=0loPj-nIG7c"

# ============================================================
# EXACT VERSIONS
# ============================================================

SPOTDL_REPO = (
    "git+https://github.com/TzurSoffer/"
    "spotify-downloader@29cb0b0669d5c107331b0912fdef73967b47493e"
)

YTDLP_VERSION = "2026.06.09"

BGUTIL_VERSION = "2.0.0"

# ============================================================
# BGUTIL
# ============================================================

BGUTIL_DIR = (
    APP_DIR
    / ".bgutil-ytdlp-pot-provider"
)

BGUTIL_SERVER_DIR = (
    BGUTIL_DIR
    / "server"
)

BGUTIL_PORT = 4416

BGUTIL_URL = (
    f"http://127.0.0.1:{BGUTIL_PORT}"
)

# IMPORTANT:
# This is the extractor argument expected by
# bgutil-ytdlp-pot-provider.
YOUTUBE_EXTRACTOR_ARGS = (
    "youtubepot-bgutilhttp:"
    "base_url=http://127.0.0.1:4416"
)

# ============================================================
# GLOBALS
# ============================================================

BOT_LOCK_FD = None
BGUTIL_PROCESS = None

_INITIALIZED = False
_BOT_STARTED = False


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(message, flush=True)


# ============================================================
# COMMAND RUNNER
# ============================================================

def run_command(
    cmd,
    timeout=300,
    env=None,
    cwd=None,
):
    log("")
    log("COMMAND:")
    log(
        " ".join(
            str(x)
            for x in cmd
        )
    )

    try:
        result = subprocess.run(
            [
                str(x)
                for x in cmd
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=(
                str(cwd)
                if cwd
                else None
            ),
            timeout=timeout,
        )

        if result.stdout:
            print(
                result.stdout,
                flush=True,
            )

        log(
            f"Exit code: "
            f"{result.returncode}"
        )

        return (
            result.returncode,
            result.stdout or "",
        )

    except subprocess.TimeoutExpired as e:

        log(
            f"COMMAND TIMEOUT "
            f"after {timeout} seconds"
        )

        if e.stdout:
            try:
                print(
                    e.stdout,
                    flush=True,
                )
            except Exception:
                pass

        return 124, ""

    except Exception as e:

        log(
            "COMMAND ERROR: "
            f"{repr(e)}"
        )

        return 1, ""


# ============================================================
# ENVIRONMENT
# ============================================================

def build_environment():

    env = os.environ.copy()

    current_path = env.get(
        "PATH",
        "",
    )

    extra_paths = [
        str(LOCAL_BIN),
        str(SPOTDL_VENV / "bin"),
        str(FFMPEG_DIR),
    ]

    env["PATH"] = (
        ":".join(
            extra_paths
            + [current_path]
        )
    )

    env["DENO_NO_PROMPT"] = "1"
    env["DENO_NO_UPDATE_CHECK"] = "1"

    return env


# ============================================================
# PIP
# ============================================================

def pip_install(
    python_bin,
    packages,
    extra_args=None,
):

    if extra_args is None:
        extra_args = []

    cmd = [
        str(python_bin),
        "-m",
        "pip",
        "install",
        "--upgrade",
    ]

    cmd.extend(extra_args)
    cmd.extend(packages)

    return run_command(
        cmd,
        timeout=900,
        env=build_environment(),
    )


# ============================================================
# DOWNLOAD FILE
# ============================================================

def download_file(
    url,
    destination,
    timeout=300,
):

    destination = Path(
        destination
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    log("")
    log(
        f"Downloading:\n{url}"
    )

    try:

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent":
                    "Mozilla/5.0",
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:

            with open(
                destination,
                "wb",
            ) as f:

                shutil.copyfileobj(
                    response,
                    f,
                    length=1024 * 1024,
                )

        log(
            f"Downloaded: "
            f"{destination}"
        )

        return True

    except Exception as e:

        log(
            "Download failed: "
            f"{repr(e)}"
        )

        try:
            destination.unlink()
        except Exception:
            pass

        return False


# ============================================================
# DENO
# ============================================================

def ensure_deno():

    LOCAL_BIN.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Already installed
    # --------------------------------------------------------

    if DENO_BIN.exists():

        try:
            DENO_BIN.chmod(0o755)
        except Exception:
            pass

        code, _ = run_command(
            [
                str(DENO_BIN),
                "--version",
            ],
            timeout=30,
            env=build_environment(),
        )

        if code == 0:

            log("Deno: OK")

            return True

    # --------------------------------------------------------
    # Direct ZIP installation
    #
    # This avoids the install.sh requirement for unzip.
    # --------------------------------------------------------

    log(
        "Deno not found. "
        "Installing Deno from ZIP..."
    )

    deno_version = "2.9.6"

    zip_url = (
        "https://dl.deno.land/release/"
        f"v{deno_version}/"
        "deno-x86_64-unknown-linux-gnu.zip"
    )

    zip_path = (
        LOCAL_BIN
        / "deno.zip"
    )

    if not download_file(
        zip_url,
        zip_path,
        timeout=300,
    ):

        log(
            "Deno ZIP download failed."
        )

        return False

    try:

        with zipfile.ZipFile(
            zip_path,
            "r",
        ) as z:

            names = z.namelist()

            deno_member = None

            for name in names:

                if (
                    name == "deno"
                    or name.endswith(
                        "/deno"
                    )
                ):

                    deno_member = name
                    break

            if not deno_member:

                raise RuntimeError(
                    "deno executable "
                    "not found in ZIP"
                )

            with z.open(
                deno_member
            ) as source:

                with open(
                    DENO_BIN,
                    "wb",
                ) as target:

                    shutil.copyfileobj(
                        source,
                        target,
                    )

        DENO_BIN.chmod(
            0o755
        )

    except Exception as e:

        log(
            "Deno ZIP extraction "
            f"failed: {repr(e)}"
        )

        return False

    try:
        zip_path.unlink()
    except Exception:
        pass

    # --------------------------------------------------------
    # Verify
    # --------------------------------------------------------

    code, _ = run_command(
        [
            str(DENO_BIN),
            "--version",
        ],
        timeout=30,
        env=build_environment(),
    )

    if code == 0:

        log("Deno: OK")

        return True

    log(
        "Deno: FAILED"
    )

    return False


# ============================================================
# FFMPEG
# ============================================================

def ensure_ffmpeg():

    FFMPEG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Already available
    # --------------------------------------------------------

    if FFMPEG_BIN.exists():

        try:
            FFMPEG_BIN.chmod(0o755)
        except Exception:
            pass

        code, _ = run_command(
            [
                str(FFMPEG_BIN),
                "-version",
            ],
            timeout=30,
            env=build_environment(),
        )

        if code == 0:

            log("FFmpeg: OK")

            return True

    # --------------------------------------------------------
    # Check system PATH
    # --------------------------------------------------------

    system_ffmpeg = shutil.which(
        "ffmpeg"
    )

    if system_ffmpeg:

        try:

            if (
                Path(system_ffmpeg).resolve()
                != FFMPEG_BIN.resolve()
            ):

                shutil.copy2(
                    system_ffmpeg,
                    FFMPEG_BIN,
                )

            FFMPEG_BIN.chmod(
                0o755
            )

        except Exception:
            pass

        if FFMPEG_BIN.exists():

            log("FFmpeg: OK")

            return True

    # --------------------------------------------------------
    # Static FFmpeg build
    # --------------------------------------------------------

    log(
        "FFmpeg not found. "
        "Installing static FFmpeg..."
    )

    archive = (
        APP_DIR
        / ".cache"
        / "ffmpeg-release-amd64-static.tar.xz"
    )

    archive.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ffmpeg_url = (
        "https://johnvansickle.com/"
        "ffmpeg/releases/"
        "ffmpeg-release-amd64-static.tar.xz"
    )

    if not download_file(
        ffmpeg_url,
        archive,
        timeout=600,
    ):

        log(
            "FFmpeg download failed."
        )

        return False

    extract_dir = (
        APP_DIR
        / ".cache"
        / "ffmpeg-extracted"
    )

    if extract_dir.exists():

        shutil.rmtree(
            extract_dir,
            ignore_errors=True,
        )

    extract_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:

        with tarfile.open(
            archive,
            mode="r:xz",
        ) as tar:

            tar.extractall(
                extract_dir
            )

    except Exception as e:

        log(
            "FFmpeg extraction failed: "
            f"{repr(e)}"
        )

        return False

    # Find ffmpeg binary
    found_ffmpeg = None

    for p in extract_dir.rglob(
        "ffmpeg"
    ):

        if p.is_file():

            found_ffmpeg = p
            break

    if not found_ffmpeg:

        log(
            "FFmpeg binary not found "
            "after extraction."
        )

        return False

    try:

        shutil.copy2(
            found_ffmpeg,
            FFMPEG_BIN,
        )

        FFMPEG_BIN.chmod(
            0o755
        )

    except Exception as e:

        log(
            "Could not install FFmpeg: "
            f"{repr(e)}"
        )

        return False

    # --------------------------------------------------------
    # Verify
    # --------------------------------------------------------

    code, _ = run_command(
        [
            str(FFMPEG_BIN),
            "-version",
        ],
        timeout=30,
        env=build_environment(),
    )

    if code == 0:

        log("FFmpeg: OK")

        return True

    log(
        "FFmpeg: FAILED"
    )

    return False


# ============================================================
# SPOTDL
# ============================================================

def ensure_spotdl():

    if not SPOTDL_VENV.exists():

        log(
            "Creating spotDL virtual "
            "environment..."
        )

        code, _ = run_command(
            [
                sys.executable,
                "-m",
                "venv",
                str(SPOTDL_VENV),
            ],
            timeout=300,
            env=build_environment(),
        )

        if code != 0:

            log(
                "Failed to create "
                "spotDL venv."
            )

            return False

    if not SPOTDL_PYTHON.exists():

        log(
            "spotDL Python not found."
        )

        return False

    # --------------------------------------------------------
    # pip tools
    # --------------------------------------------------------

    log(
        "Updating pip/setuptools/wheel..."
    )

    code, _ = pip_install(
        SPOTDL_PYTHON,
        [
            "pip",
            "setuptools",
            "wheel",
        ],
    )

    if code != 0:
        return False

    # --------------------------------------------------------
    # EXACT SPOTDL FORK
    # --------------------------------------------------------

    log("")
    log("=" * 60)
    log(
        "INSTALLING EXACT SPOTDL FORK"
    )
    log("=" * 60)

    log(
        SPOTDL_REPO
    )

    code, _ = pip_install(
        SPOTDL_PYTHON,
        [
            SPOTDL_REPO,
        ],
    )

    if code != 0:

        log(
            "spotDL installation failed."
        )

        return False

    # --------------------------------------------------------
    # EXACT YT-DLP
    # --------------------------------------------------------

    log("")
    log("=" * 60)
    log(
        f"INSTALLING EXACT YT-DLP "
        f"VERSION {YTDLP_VERSION}"
    )
    log("=" * 60)

    code, _ = pip_install(
        SPOTDL_PYTHON,
        [
            f"yt-dlp=={YTDLP_VERSION}",
            "yt-dlp-ejs==0.8.0",
        ],
    )

    if code != 0:

        log(
            "yt-dlp installation failed."
        )

        return False

    # --------------------------------------------------------
    # BGUTIL PLUGIN
    # --------------------------------------------------------

    log("")
    log("=" * 60)
    log(
        "INSTALLING BGUTIL PO TOKEN "
        "PROVIDER PLUGIN"
    )
    log("=" * 60)

    code, _ = pip_install(
        SPOTDL_PYTHON,
        [
            "bgutil-ytdlp-pot-provider==2.0.0",
        ],
    )

    if code != 0:

        log(
            "bgutil plugin installation "
            "failed."
        )

        return False

    # --------------------------------------------------------
    # VERSIONS
    # --------------------------------------------------------

    log("")
    log("=" * 60)
    log(
        "INSTALLED VERSIONS"
    )
    log("=" * 60)

    run_command(
        [
            str(SPOTDL_CMD),
            "--version",
        ],
        timeout=60,
        env=build_environment(),
    )

    run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "yt_dlp",
            "--version",
        ],
        timeout=60,
        env=build_environment(),
    )

    run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "show",
            "yt-dlp",
        ],
        timeout=60,
        env=build_environment(),
    )

    run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "show",
            "yt-dlp-ejs",
        ],
        timeout=60,
        env=build_environment(),
    )

    run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "show",
            "bgutil-ytdlp-pot-provider",
        ],
        timeout=60,
        env=build_environment(),
    )

    log(
        "spotDL: OK"
    )

    return True


# ============================================================
# BGUTIL REPOSITORY
# ============================================================

def ensure_bgutil_repository():

    if not DENO_BIN.exists():

        log(
            "Cannot setup bgutil: "
            "Deno is missing."
        )

        return False

    # --------------------------------------------------------
    # Clone repository
    # --------------------------------------------------------

    if not BGUTIL_SERVER_DIR.exists():

        if BGUTIL_DIR.exists():

            shutil.rmtree(
                BGUTIL_DIR,
                ignore_errors=True,
            )

        log(
            "Cloning bgutil "
            f"version {BGUTIL_VERSION}..."
        )

        code, _ = run_command(
            [
                "git",
                "clone",
                "--single-branch",
                "--branch",
                BGUTIL_VERSION,
                "https://github.com/"
                "Brainicism/"
                "bgutil-ytdlp-pot-provider.git",
                str(BGUTIL_DIR),
            ],
            timeout=300,
            env=build_environment(),
        )

        if code != 0:

            log(
                "Failed to clone "
                "bgutil repository."
            )

            return False

    return True


# ============================================================
# BGUTIL SERVER HEALTH CHECK
# ============================================================

def is_bgutil_server_running():

    try:

        import urllib.request

        request = urllib.request.Request(
            f"{BGUTIL_URL}/",
            method="GET",
        )

        with urllib.request.urlopen(
            request,
            timeout=3,
        ) as response:

            # Any HTTP response means
            # the server is listening.
            return True

    except urllib.error.HTTPError:

        # Server is alive but endpoint
        # may return 404.
        return True

    except Exception:

        return False


# ============================================================
# START BGUTIL
# ============================================================

def start_bgutil_server():

    global BGUTIL_PROCESS

    if is_bgutil_server_running():

        log(
            "bgutil PO Token server "
            "already running."
        )

        return True

    if not ensure_bgutil_repository():

        return False

    server_dir = (
        BGUTIL_SERVER_DIR
    )

    log("")
    log("=" * 60)
    log(
        "SETTING UP BGUTIL SERVER"
    )
    log("=" * 60)

    # --------------------------------------------------------
    # Install server dependencies
    #
    # Correct command from bgutil 2.0.0 docs:
    #
    # deno install
    # --allow-scripts=npm:canvas
    # --frozen
    # --------------------------------------------------------

    log(
        "Installing bgutil server "
        "dependencies..."
    )

    code, _ = run_command(
        [
            str(DENO_BIN),
            "install",
            "--allow-scripts=npm:canvas",
            "--frozen",
        ],
        timeout=900,
        env=build_environment(),
        cwd=server_dir,
    )

    if code != 0:

        log(
            "bgutil Deno dependency "
            "installation failed."
        )

        return False

    # --------------------------------------------------------
    # Verify node_modules
    # --------------------------------------------------------

    node_modules = (
        server_dir
        / "node_modules"
    )

    if not node_modules.exists():

        log(
            "bgutil node_modules "
            "was not created."
        )

        return False

    # --------------------------------------------------------
    # Correct server command
    #
    # According to bgutil 2.0.0:
    #
    # cd node_modules
    # deno run ...
    # ../src/main.ts
    # --------------------------------------------------------

    main_ts = (
        server_dir
        / "src"
        / "main.ts"
    )

    if not main_ts.exists():

        log(
            "bgutil src/main.ts "
            "not found."
        )

        return False

    log(
        "Starting bgutil HTTP server..."
    )

    server_cmd = [
        str(DENO_BIN),

        "run",

        "--allow-env",

        "--allow-net",

        "--allow-ffi=.",

        "--allow-read=.",

        "../src/main.ts",

        "--host",
        "127.0.0.1",

        "--port",
        str(BGUTIL_PORT),
    ]

    try:

        BGUTIL_PROCESS = (
            subprocess.Popen(
                server_cmd,
                cwd=str(
                    node_modules
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=build_environment(),
                start_new_session=True,
            )
        )

    except Exception as e:

        log(
            "Failed to start bgutil: "
            f"{repr(e)}"
        )

        return False

    # --------------------------------------------------------
    # Wait
    # --------------------------------------------------------

    for _ in range(45):

        time.sleep(1)

        if is_bgutil_server_running():

            log(
                "bgutil PO Token server: OK"
            )

            return True

        if (
            BGUTIL_PROCESS.poll()
            is not None
        ):

            log(
                "bgutil exited early. "
                f"Exit code: "
                f"{BGUTIL_PROCESS.returncode}"
            )

            try:

                output = (
                    BGUTIL_PROCESS
                    .stdout
                    .read()
                )

                if output:
                    print(
                        output,
                        flush=True,
                    )

            except Exception:
                pass

            return False

    log(
        "bgutil server did not "
        "become ready."
    )

    return False


# ============================================================
# YT-DLP BASE COMMAND
# ============================================================

def youtube_base_command():

    cmd = [
        str(SPOTDL_PYTHON),
        "-m",
        "yt_dlp",

        "--no-playlist",

        "--socket-timeout",
        "20",

        "--retries",
        "2",

        "--fragment-retries",
        "2",

        "--extractor-retries",
        "2",

        "--retry-sleep",
        "1",

        "--extractor-args",
        YOUTUBE_EXTRACTOR_ARGS,
    ]

    if DENO_BIN.exists():

        cmd.extend(
            [
                "--js-runtimes",
                f"deno:{DENO_BIN}",
            ]
        )

    return cmd


# ============================================================
# YOUTUBE METADATA TEST
# ============================================================

def test_youtube_metadata():

    log("")
    log("=" * 60)
    log(
        "TESTING YOUTUBE METADATA"
    )
    log("=" * 60)

    if not is_bgutil_server_running():

        log(
            "bgutil server is not running."
        )

        return False

    cmd = youtube_base_command()

    cmd.extend(
        [
            "--print",
            "title",

            "--skip-download",

            "--verbose",

            TEST_URL,
        ]
    )

    code, _ = run_command(
        cmd,
        timeout=120,
        env=build_environment(),
    )

    if code == 0:

        log(
            "METADATA TEST SUCCESS"
        )

        return True

    log(
        "METADATA TEST FAILED"
    )

    return False


# ============================================================
# YOUTUBE AUDIO TEST
# ============================================================

def test_youtube_audio():

    log("")
    log("=" * 60)
    log(
        "TESTING YOUTUBE AUDIO"
    )
    log("=" * 60)

    test_dir = (
        APP_DIR
        / ".youtube_test"
    )

    test_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Remove previous files.
    for item in test_dir.iterdir():

        try:

            if item.is_file():
                item.unlink()

        except Exception:
            pass

    cmd = youtube_base_command()

    cmd.extend(
        [
            "-f",
            "bestaudio/best",

            "-o",
            str(
                test_dir
                / "%(id)s.%(ext)s"
            ),

            "--verbose",

            TEST_URL,
        ]
    )

    code, _ = run_command(
        cmd,
        timeout=180,
        env=build_environment(),
    )

    if code != 0:

        log(
            "AUDIO TEST FAILED"
        )

        return False

    files = [
        p
        for p in test_dir.iterdir()
        if p.is_file()
    ]

    if not files:

        log(
            "Audio command succeeded "
            "but no file was produced."
        )

        return False

    log(
        "AUDIO TEST SUCCESS"
    )

    for p in files:

        log(
            f"Downloaded test file: "
            f"{p}"
        )

    return True


# ============================================================
# TELEGRAM LOCK
# ============================================================

def acquire_bot_lock():

    global BOT_LOCK_FD

    try:

        BOT_LOCK_FD = open(
            BOT_LOCK_FILE,
            "w",
        )

        fcntl.flock(
            BOT_LOCK_FD,
            fcntl.LOCK_EX
            | fcntl.LOCK_NB,
        )

        log(
            "Telegram bot lock acquired."
        )

        return True

    except BlockingIOError:

        log(
            "Telegram bot already running."
        )

        return False

    except Exception as e:

        log(
            "Bot lock error: "
            f"{repr(e)}"
        )

        return False


# ============================================================
# SECRETS
# ============================================================

def get_secret(name):

    value = None

    try:

        value = st.secrets.get(
            name
        )

    except Exception:
        pass

    if not value:

        value = os.environ.get(
            name
        )

    if value:

        return str(
            value
        ).strip()

    return None


# ============================================================
# FIND AUDIO
# ============================================================

def find_downloaded_audio(
    download_dir,
):

    audio_extensions = {
        ".mp3",
        ".m4a",
        ".opus",
        ".webm",
        ".aac",
        ".wav",
        ".flac",
        ".ogg",
    }

    files = []

    if download_dir.exists():

        for p in (
            download_dir.rglob("*")
        ):

            if (
                p.is_file()
                and p.suffix.lower()
                in audio_extensions
            ):

                files.append(p)

    if not files:

        return None

    files.sort(
        key=lambda x:
            x.stat().st_mtime,
        reverse=True,
    )

    return files[0]


# ============================================================
# TELEGRAM DOWNLOAD
# ============================================================

def telegram_download(
    update,
    context,
):

    message = (
        update.effective_message
    )

    if message is None:
        return

    text = (
        message.text or ""
    ).strip()

    if not text:
        return

    if (
        "spotify.com/"
        not in text
    ):

        message.reply_text(
            "لینک Spotify را ارسال کن."
        )

        return

    client_id = get_secret(
        "SPOTIFY_CLIENT_ID"
    )

    client_secret = get_secret(
        "SPOTIFY_CLIENT_SECRET"
    )

    if (
        not client_id
        or not client_secret
    ):

        message.reply_text(
            "Spotify API credentials "
            "تنظیم نشده است."
        )

        return

    work_dir = (
        APP_DIR
        / "downloads"
        / str(
            message.chat_id
        )
    )

    work_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    for p in work_dir.iterdir():

        try:

            if p.is_file():
                p.unlink()

        except Exception:
            pass

    status_message = (
        message.reply_text(
            "⏳ در حال دانلود..."
        )
    )

    cmd = [
        str(SPOTDL_CMD),

        "download",

        text,

        "--no-cache",

        "--client-id",
        client_id,

        "--client-secret",
        client_secret,

        "--threads",
        "8",

        "--format",
        "mp3",

        "--bitrate",
        "320k",

        "--output",
        str(
            work_dir
            / "{artist} - {title}.{output-ext}"
        ),
    ]

    # IMPORTANT:
    # No web_safari.
    # No web_embedded.
    # No android_vr.
    #
    # bgutil supplies the PO token.

    yt_args = (
        f'--js-runtimes '
        f'"deno:{DENO_BIN}" '
        f'--extractor-args '
        f'"{YOUTUBE_EXTRACTOR_ARGS}" '
        f'--retries 2 '
        f'--fragment-retries 2 '
        f'--socket-timeout 20'
    )

    cmd.extend(
        [
            "--yt-dlp-args",
            yt_args,
        ]
    )

    code, output = run_command(
        cmd,
        timeout=900,
        env=build_environment(),
    )

    audio_file = (
        find_downloaded_audio(
            work_dir
        )
    )

    if (
        code != 0
        or audio_file is None
    ):

        log(
            "SPOTIFY DOWNLOAD FAILED"
        )

        log(
            output[-10000:]
        )

        try:

            status_message.edit_text(
                "❌ دانلود انجام نشد.\n"
                "YouTube/spotDL خطا داد."
            )

        except Exception:
            pass

        return

    try:

        status_message.edit_text(
            "📤 فایل آماده شد، "
            "در حال ارسال..."
        )

    except Exception:
        pass

    try:

        with open(
            audio_file,
            "rb",
        ) as audio:

            message.reply_audio(
                audio=audio,
                title=audio_file.stem,
            )

        try:
            status_message.delete()
        except Exception:
            pass

    except Exception as e:

        log(
            "Telegram send error: "
            f"{repr(e)}"
        )

        try:

            status_message.edit_text(
                "❌ ارسال فایل به "
                "Telegram انجام نشد."
            )

        except Exception:
            pass

    finally:

        try:
            audio_file.unlink()
        except Exception:
            pass


# ============================================================
# TELEGRAM BOT
# ============================================================

def start_telegram_bot():

    global _BOT_STARTED

    if _BOT_STARTED:

        log(
            "Telegram bot already "
            "initialized."
        )

        return True

    token = get_secret(
        "TELEGRAM_TOKEN"
    )

    if not token:

        log(
            "TELEGRAM_TOKEN missing."
        )

        log(
            "Add TELEGRAM_TOKEN "
            "to Streamlit Secrets."
        )

        return False

    if not acquire_bot_lock():

        return False

    try:

        from telegram.ext import (
            Updater,
            CommandHandler,
            MessageHandler,
            Filters,
        )

    except Exception as e:

        log(
            "python-telegram-bot "
            f"import failed: {repr(e)}"
        )

        return False

    try:

        updater = Updater(
            token=token,
            use_context=True,
        )

        dispatcher = (
            updater.dispatcher
        )

        dispatcher.add_handler(
            CommandHandler(
                "start",
                lambda update, context:
                    update.effective_message.reply_text(
                        "🎵 لینک Spotify را ارسال کن."
                    ),
            )
        )

        dispatcher.add_handler(
            MessageHandler(
                Filters.text
                & ~Filters.command,
                telegram_download,
            )
        )

        updater.start_polling(
            drop_pending_updates=True,
        )

        _BOT_STARTED = True

        log(
            "Telegram bot polling started."
        )

        return True

    except Exception as e:

        log(
            "Telegram bot start failed: "
            f"{repr(e)}"
        )

        return False


# ============================================================
# INITIALIZATION
# ============================================================

def initialize():

    global _INITIALIZED

    if _INITIALIZED:
        return

    _INITIALIZED = True

    log("")
    log("=" * 60)
    log(
        "              SPMA INITIALIZATION"
    )
    log("=" * 60)

    # --------------------------------------------------------
    # DENO
    # --------------------------------------------------------

    deno_ok = (
        ensure_deno()
    )

    # --------------------------------------------------------
    # FFMPEG
    # --------------------------------------------------------

    ffmpeg_ok = (
        ensure_ffmpeg()
    )

    # --------------------------------------------------------
    # SPOTDL
    # --------------------------------------------------------

    spotdl_ok = (
        ensure_spotdl()
    )

    # --------------------------------------------------------
    # BGUTIL
    # --------------------------------------------------------

    bgutil_ok = False

    if (
        deno_ok
        and spotdl_ok
    ):

        bgutil_ok = (
            start_bgutil_server()
        )

    # --------------------------------------------------------
    # YOUTUBE
    # --------------------------------------------------------

    metadata_ok = False
    audio_ok = False

    if (
        bgutil_ok
        and spotdl_ok
    ):

        metadata_ok = (
            test_youtube_metadata()
        )

        if metadata_ok:

            audio_ok = (
                test_youtube_audio()
            )

        else:

            log(
                "Metadata test failed."
            )

            log(
                "Skipping audio test."
            )

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    telegram_ok = (
        start_telegram_bot()
    )

    # --------------------------------------------------------
    # FINAL SUMMARY
    # --------------------------------------------------------

    log("")
    log("=" * 60)
    log(
        "                 FINAL SUMMARY"
    )
    log("=" * 60)

    log(
        "spotDL: "
        + (
            "OK"
            if spotdl_ok
            else "FAILED"
        )
    )

    log(
        "FFmpeg: "
        + (
            "OK"
            if ffmpeg_ok
            else "FAILED"
        )
    )

    log(
        "Deno: "
        + (
            "OK"
            if deno_ok
            else "FAILED"
        )
    )

    log(
        "bgutil PO Token: "
        + (
            "OK"
            if bgutil_ok
            else "FAILED"
        )
    )

    log(
        "YouTube metadata: "
        + (
            "OK"
            if metadata_ok
            else "FAILED"
        )
    )

    log(
        "YouTube audio: "
        + (
            "OK"
            if audio_ok
            else "FAILED"
        )
    )

    log(
        "Telegram: "
        + (
            "OK"
            if telegram_ok
            else "FAILED"
        )
    )

    log("=" * 60)


# ============================================================
# STREAMLIT
# ============================================================

st.set_page_config(
    page_title="SPMA",
    page_icon="🎵",
)

st.title("🎵 SPMA")

if not globals().get(
    "_SPMA_INITIALIZED",
    False,
):

    globals()[
        "_SPMA_INITIALIZED"
    ] = True

    try:

        initialize()

    except Exception as e:

        log("")
        log(
            "INITIALIZATION ERROR:"
        )
        log(
            repr(e)
        )

while True:

    time.sleep(3600)
