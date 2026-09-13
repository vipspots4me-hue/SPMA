import os
import sys
import time
import fcntl
import shutil
import subprocess
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

# EXACT spotDL fork requested
SPOTDL_REPO = (
    "git+https://github.com/TzurSoffer/"
    "spotify-downloader@29cb0b0669d5c107331b0912fdef73967b47493e"
)

# EXACT yt-dlp version requested
YTDLP_VERSION = "2026.06.09"

# bgutil PO Token provider
BGUTIL_DIR = APP_DIR / ".bgutil-ytdlp-pot-provider"
BGUTIL_SERVER_DIR = BGUTIL_DIR / "server"

BGUTIL_PORT = 4416
BGUTIL_URL = f"http://127.0.0.1:{BGUTIL_PORT}"

# IMPORTANT:
# We are NOT forcing web_safari anymore.
#
# The PO Token provider is passed to yt-dlp instead.
YOUTUBE_EXTRACTOR_ARGS = (
    "youtubepot-bgutilhttp:base_url=http://127.0.0.1:4416"
)


# ============================================================
# GLOBALS
# ============================================================

BOT_LOCK_FD = None
BGUTIL_PROCESS = None

_INITIALIZED = False
_BOT_STARTED = False


# ============================================================
# LOGGING / COMMAND RUNNER
# ============================================================

def log(message):
    print(message, flush=True)


def run_command(
    cmd,
    timeout=300,
    env=None,
    cwd=None,
):
    log("")
    log("COMMAND:")
    log(" ".join(str(x) for x in cmd))

    try:
        result = subprocess.run(
            [str(x) for x in cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=str(cwd) if cwd else None,
            timeout=timeout,
        )

        if result.stdout:
            print(result.stdout, flush=True)

        log(f"Exit code: {result.returncode}")

        return result.returncode, result.stdout or ""

    except subprocess.TimeoutExpired as e:
        log(f"COMMAND TIMEOUT after {timeout} seconds")

        if e.stdout:
            try:
                print(e.stdout, flush=True)
            except Exception:
                pass

        return 124, ""

    except Exception as e:
        log(f"COMMAND ERROR: {repr(e)}")
        return 1, ""


def build_environment():
    env = os.environ.copy()

    current_path = env.get("PATH", "")

    extra_paths = [
        str(LOCAL_BIN),
        str(SPOTDL_VENV / "bin"),
        str(FFMPEG_DIR),
    ]

    env["PATH"] = ":".join(extra_paths + [current_path])

    env["DENO_NO_PROMPT"] = "1"

    return env


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
# DENO
# ============================================================

def ensure_deno():
    LOCAL_BIN.mkdir(
        parents=True,
        exist_ok=True,
    )

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

    log("Deno not found. Installing Deno...")

    install_script = LOCAL_BIN / "install_deno.sh"

    code, _ = run_command(
        [
            "bash",
            "-c",
            (
                "curl -fsSL "
                "https://deno.land/install.sh "
                f"-o {install_script}"
            ),
        ],
        timeout=120,
        env=build_environment(),
    )

    if code != 0:
        log("Failed to download Deno installer.")
        return False

    code, _ = run_command(
        [
            "bash",
            str(install_script),
            "-q",
            "-y",
            "--no-modify-path",
        ],
        timeout=300,
        env=build_environment(),
    )

    installed_deno = (
        Path.home()
        / ".deno"
        / "bin"
        / "deno"
    )

    if installed_deno.exists() and not DENO_BIN.exists():
        try:
            shutil.copy2(
                installed_deno,
                DENO_BIN,
            )
        except Exception as e:
            log(
                "Could not copy Deno: "
                f"{repr(e)}"
            )

    if not DENO_BIN.exists():
        log("Deno installation failed.")
        return False

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

    log("Deno: FAILED")
    return False


# ============================================================
# FFMPEG
# ============================================================

def ensure_ffmpeg():
    FFMPEG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

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

    log("FFmpeg not found.")

    possible = [
        APP_DIR / ".spotdl_venv" / "bin" / "ffmpeg",
        Path.home()
        / ".config"
        / "spotdl"
        / "ffmpeg",
        Path("/usr/bin/ffmpeg"),
        Path("/usr/local/bin/ffmpeg"),
    ]

    for path in possible:
        if not path.exists():
            continue

        try:
            if path.resolve() != FFMPEG_BIN.resolve():
                shutil.copy2(
                    path,
                    FFMPEG_BIN,
                )

            FFMPEG_BIN.chmod(0o755)

        except Exception:
            continue

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

    log("FFmpeg: FAILED")
    return False


# ============================================================
# SPOTDL
# ============================================================

def ensure_spotdl():
    if not SPOTDL_VENV.exists():
        log("Creating spotDL virtual environment...")

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
                "Failed to create spotDL "
                "virtual environment."
            )
            return False

    if not SPOTDL_PYTHON.exists():
        log("spotDL Python not found.")
        return False

    # --------------------------------------------------------
    # pip / setuptools / wheel
    # --------------------------------------------------------

    log("Updating pip/setuptools/wheel...")

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
    log("INSTALLING EXACT SPOTDL FORK")
    log("=" * 60)

    log(SPOTDL_REPO)

    code, _ = pip_install(
        SPOTDL_PYTHON,
        [
            SPOTDL_REPO,
        ],
    )

    if code != 0:
        log("spotDL installation failed.")
        return False

    # --------------------------------------------------------
    # EXACT YT-DLP VERSION
    # --------------------------------------------------------

    log("")
    log("=" * 60)
    log(
        f"INSTALLING EXACT YT-DLP VERSION "
        f"{YTDLP_VERSION}"
    )
    log("=" * 60)

    code, _ = pip_install(
        SPOTDL_PYTHON,
        [
            f"yt-dlp=={YTDLP_VERSION}",
            "yt-dlp-ejs",
        ],
    )

    if code != 0:
        log("yt-dlp installation failed.")
        return False

    # --------------------------------------------------------
    # BGUTIL PO TOKEN PROVIDER
    # --------------------------------------------------------

    log("")
    log("=" * 60)
    log("INSTALLING BGUTIL PO TOKEN PROVIDER")
    log("=" * 60)

    code, _ = pip_install(
        SPOTDL_PYTHON,
        [
            "bgutil-ytdlp-pot-provider",
        ],
    )

    if code != 0:
        log(
            "bgutil-ytdlp-pot-provider "
            "installation failed."
        )
        return False

    # --------------------------------------------------------
    # SHOW VERSIONS
    # --------------------------------------------------------

    log("")
    log("=" * 60)
    log("INSTALLED VERSIONS")
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

    log("spotDL: OK")

    return True


# ============================================================
# BGUTIL PO TOKEN PROVIDER
# ============================================================

def ensure_bgutil_repository():
    """
    Clone the bgutil provider repository if it does not exist.

    The Python plugin installed above talks to this local HTTP
    server.
    """

    if not DENO_BIN.exists():
        log(
            "Cannot setup bgutil: "
            "Deno is missing."
        )
        return False

    if not BGUTIL_DIR.exists():

        log(
            "Cloning bgutil-ytdlp-pot-provider..."
        )

        code, _ = run_command(
            [
                "git",
                "clone",
                "--single-branch",
                "--branch",
                "2.0.0",
                "https://github.com/Brainicism/"
                "bgutil-ytdlp-pot-provider.git",
                str(BGUTIL_DIR),
            ],
            timeout=300,
            env=build_environment(),
        )

        if code != 0:
            log(
                "Failed to clone bgutil "
                "provider."
            )
            return False

    if not BGUTIL_SERVER_DIR.exists():
        log(
            "bgutil server directory "
            "does not exist."
        )
        return False

    return True


def is_bgutil_server_running():
    try:
        import urllib.request

        with urllib.request.urlopen(
            f"{BGUTIL_URL}/",
            timeout=2,
        ) as response:

            return response.status in (
                200,
                404,
            )

    except Exception:
        return False


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

    server_dir = BGUTIL_SERVER_DIR

    log("")
    log("=" * 60)
    log("STARTING BGUTIL PO TOKEN SERVER")
    log("=" * 60)

    # Install Deno dependencies if needed.
    #
    # We use deno install so the server can resolve
    # its npm dependencies.
    log("Installing bgutil server dependencies...")

    code, _ = run_command(
        [
            str(DENO_BIN),
            "install",
            "--allow-scripts",
        ],
        timeout=900,
        env=build_environment(),
        cwd=server_dir,
    )

    if code != 0:
        log(
            "bgutil dependency installation failed."
        )
        return False

    # --------------------------------------------------------
    # Find main.ts
    # --------------------------------------------------------

    main_ts = server_dir / "src" / "main.ts"

    if not main_ts.exists():
        log(
            f"bgutil main.ts not found: "
            f"{main_ts}"
        )
        return False

    server_cmd = [
        str(DENO_BIN),
        "run",

        "--allow-env",
        "--allow-net",
        "--allow-read",
        "--allow-write",

        str(main_ts),

        "--port",
        str(BGUTIL_PORT),

        "--host",
        "127.0.0.1",
    ]

    log(
        " ".join(str(x) for x in server_cmd)
    )

    try:
        BGUTIL_PROCESS = subprocess.Popen(
            server_cmd,
            cwd=str(server_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=build_environment(),
            start_new_session=True,
        )

    except Exception as e:
        log(
            "Failed to start bgutil server: "
            f"{repr(e)}"
        )
        return False

    # --------------------------------------------------------
    # Wait for server
    # --------------------------------------------------------

    for _ in range(30):

        time.sleep(1)

        if is_bgutil_server_running():
            log(
                "bgutil PO Token server: OK"
            )
            return True

        if BGUTIL_PROCESS.poll() is not None:

            log(
                "bgutil server exited early: "
                f"{BGUTIL_PROCESS.returncode}"
            )

            try:
                output = (
                    BGUTIL_PROCESS.stdout.read()
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
        "bgutil PO Token server "
        "did not become ready."
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
    log("TESTING YOUTUBE METADATA")
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

    code, output = run_command(
        cmd,
        timeout=120,
        env=build_environment(),
    )

    if code == 0:
        log("METADATA TEST SUCCESS")
        return True

    log("METADATA TEST FAILED")

    return False


# ============================================================
# YOUTUBE AUDIO TEST
# ============================================================

def test_youtube_audio():

    log("")
    log("=" * 60)
    log("TESTING YOUTUBE AUDIO")
    log("=" * 60)

    test_dir = (
        APP_DIR
        / ".youtube_test"
    )

    test_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Remove old files.
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

    code, output = run_command(
        cmd,
        timeout=180,
        env=build_environment(),
    )

    if code != 0:
        log("AUDIO TEST FAILED")
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

    log("AUDIO TEST SUCCESS")

    for p in files:
        log(
            f"Downloaded test file: {p}"
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
            fcntl.LOCK_EX | fcntl.LOCK_NB,
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
# STREAMLIT SECRETS
# ============================================================

def get_secret(name):

    value = None

    try:
        value = st.secrets.get(name)
    except Exception:
        pass

    if not value:
        value = os.environ.get(name)

    if value:
        return str(value).strip()

    return None


# ============================================================
# FIND DOWNLOADED AUDIO
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

        for p in download_dir.rglob("*"):

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

    if "spotify.com/" not in text:

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

    if not client_id or not client_secret:

        message.reply_text(
            "Spotify API credentials "
            "تنظیم نشده است."
        )

        return

    work_dir = (
        APP_DIR
        / "downloads"
        / str(message.chat_id)
    )

    work_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Remove previous downloads.
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
    #
    # Do NOT use web_safari here.
    #
    # The bgutil provider is responsible for
    # PO tokens.
    yt_args = (
        f'--js-runtimes "deno:{DENO_BIN}" '
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

        log("")
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
# START TELEGRAM BOT
# ============================================================

def start_telegram_bot():

    global _BOT_STARTED

    if _BOT_STARTED:

        log(
            "Telegram bot already "
            "initialized in this process."
        )

        return True

    token = get_secret(
        "TELEGRAM_TOKEN"
    )

    if not token:

        log("")
        log(
            "TELEGRAM_TOKEN missing."
        )

        log(
            "Add TELEGRAM_TOKEN to "
            "Streamlit Secrets."
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
            "python-telegram-bot import "
            f"failed: {repr(e)}"
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
    log("              SPMA INITIALIZATION")
    log("=" * 60)

    # --------------------------------------------------------
    # Deno
    # --------------------------------------------------------

    deno_ok = ensure_deno()

    # --------------------------------------------------------
    # FFmpeg
    # --------------------------------------------------------

    ffmpeg_ok = ensure_ffmpeg()

    # --------------------------------------------------------
    # spotDL + exact yt-dlp + EJS + bgutil plugin
    # --------------------------------------------------------

    spotdl_ok = ensure_spotdl()

    # --------------------------------------------------------
    # bgutil server
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
    # YouTube
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
    # Telegram
    # --------------------------------------------------------

    telegram_ok = (
        start_telegram_bot()
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    log("")
    log("=" * 60)
    log("                 FINAL SUMMARY")
    log("=" * 60)

    log(
        f"spotDL: "
        f"{'OK' if spotdl_ok else 'FAILED'}"
    )

    log(
        f"FFmpeg: "
        f"{'OK' if ffmpeg_ok else 'FAILED'}"
    )

    log(
        f"Deno: "
        f"{'OK' if deno_ok else 'FAILED'}"
    )

    log(
        f"bgutil PO Token: "
        f"{'OK' if bgutil_ok else 'FAILED'}"
    )

    log(
        f"YouTube metadata: "
        f"{'OK' if metadata_ok else 'FAILED'}"
    )

    log(
        f"YouTube audio: "
        f"{'OK' if audio_ok else 'FAILED'}"
    )

    log(
        f"Telegram: "
        f"{'OK' if telegram_ok else 'FAILED'}"
    )

    log("=" * 60)


# ============================================================
# STREAMLIT ENTRYPOINT
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

# Keep Streamlit alive.
#
# Do not use updater.idle() because
# python-telegram-bot 13.x conflicts
# with Streamlit signal handling.

while True:
    time.sleep(3600)
