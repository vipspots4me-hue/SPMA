import os
import sys
import time
import shutil
import threading
import subprocess
import platform
import urllib.request
import zipfile
import stat
import fcntl

from pathlib import Path

import streamlit as st


# ============================================================
# CONFIG
# ============================================================

APP_DIR = Path("/mount/src/spma")

SPOTDL_VENV = APP_DIR / ".spotdl_venv"
SPOTDL_PYTHON = SPOTDL_VENV / "bin" / "python"
SPOTDL_CMD = SPOTDL_VENV / "bin" / "spotdl"

LOCAL_BIN = APP_DIR / ".bin"
LOCAL_BIN.mkdir(parents=True, exist_ok=True)

DENO_BIN = LOCAL_BIN / "deno"

FFMPEG_DIR = Path.home() / ".config" / "spotdl"
FFMPEG_BIN = FFMPEG_DIR / "ffmpeg"

BOT_LOCK_FILE = "/tmp/spma_telegram_bot.lock"

TEST_URL = "https://www.youtube.com/watch?v=0loPj-nIG7c"

BOT_LOCK_FD = None
BOT_THREAD = None


# ============================================================
# COMMAND
# ============================================================

def run_command(cmd, timeout=300, env=None, cwd=None):

    cmd = [str(x) for x in cmd]

    print("\n$", " ".join(cmd), flush=True)

    try:

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            env=env,
            cwd=cwd,
        )

        print(result.stdout, flush=True)
        print(
            "Exit code:",
            result.returncode,
            flush=True,
        )

        return result

    except subprocess.TimeoutExpired as e:

        print(
            "COMMAND TIMEOUT:",
            " ".join(cmd),
            flush=True,
        )

        return subprocess.CompletedProcess(
            cmd,
            124,
            str(e),
        )

    except Exception as e:

        print(
            "COMMAND ERROR:",
            repr(e),
            flush=True,
        )

        return subprocess.CompletedProcess(
            cmd,
            1,
            str(e),
        )


# ============================================================
# ENV
# ============================================================

def build_environment():

    env = os.environ.copy()

    paths = [
        str(SPOTDL_VENV / "bin"),
        str(LOCAL_BIN),
        str(FFMPEG_DIR),
    ]

    env["PATH"] = ":".join(
        paths + [env.get("PATH", "")]
    )

    return env


# ============================================================
# CPU
# ============================================================

def cpu_info():

    print(
        "\n========== CPU INFO ==========",
        flush=True,
    )

    nproc = shutil.which("nproc")

    if nproc:

        run_command(
            [nproc],
            timeout=10,
        )

    lscpu = shutil.which("lscpu")

    if lscpu:

        run_command(
            [lscpu],
            timeout=10,
        )


# ============================================================
# ROOT
# ============================================================

def root_test():

    print(
        "\n========== ROOT TEST ==========",
        flush=True,
    )

    print(
        "UID:",
        os.getuid(),
        flush=True,
    )

    sudo = shutil.which("sudo")

    if sudo:

        run_command(
            [
                sudo,
                "-n",
                "id",
            ],
            timeout=10,
        )


# ============================================================
# SPOTDL
# ============================================================

def setup_spotdl():

    print(
        "\n========== SPOTDL SETUP ==========",
        flush=True,
    )

    # --------------------------------------------------------
    # Create venv only once
    # --------------------------------------------------------

    if not SPOTDL_PYTHON.exists():

        print(
            "Creating spotDL virtual environment...",
            flush=True,
        )

        result = run_command(
            [
                sys.executable,
                "-m",
                "venv",
                str(SPOTDL_VENV),
            ],
            timeout=180,
        )

        if result.returncode != 0:

            raise RuntimeError(
                "Could not create spotDL virtual environment."
            )

    else:

        print(
            "spotDL virtual environment already exists.",
            flush=True,
        )

    # --------------------------------------------------------
    # Check spotDL
    # --------------------------------------------------------

    spotdl_exists = SPOTDL_CMD.exists()

    if not spotdl_exists:

        print(
            "Installing spotDL...",
            flush=True,
        )

        result = run_command(
            [
                str(SPOTDL_PYTHON),
                "-m",
                "pip",
                "install",
                "--upgrade",
                "pip",
                "setuptools",
                "wheel",
            ],
            timeout=300,
        )

        if result.returncode != 0:

            raise RuntimeError(
                "pip setup failed."
            )

        result = run_command(
            [
                str(SPOTDL_PYTHON),
                "-m",
                "pip",
                "install",
                "git+https://github.com/TzurSoffer/"
                "spotify-downloader@"
                "29cb0b0669d5c107331b0912fdef73967b47493e",
            ],
            timeout=900,
        )

        if result.returncode != 0:

            raise RuntimeError(
                "spotDL installation failed."
            )

    else:

        print(
            "spotDL already installed.",
            flush=True,
        )

    # --------------------------------------------------------
    # ALWAYS pin yt-dlp AFTER spotDL
    # --------------------------------------------------------

    print(
        "\n========== PINNING YT-DLP ==========",
        flush=True,
    )

    result = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "yt-dlp==2026.06.09",
            "yt-dlp-ejs==0.8.0",
        ],
        timeout=300,
    )

    if result.returncode != 0:

        raise RuntimeError(
            "yt-dlp installation failed."
        )

    # --------------------------------------------------------
    # Verify
    # --------------------------------------------------------

    print(
        "\n========== SPOTDL VERSION ==========",
        flush=True,
    )

    run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "spotdl",
            "--version",
        ],
        timeout=30,
    )

    print(
        "\n========== YT-DLP VERSION ==========",
        flush=True,
    )

    run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "yt_dlp",
            "--version",
        ],
        timeout=30,
    )

    print(
        "\n========== YT-DLP-EJS ==========",
        flush=True,
    )

    run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "show",
            "yt-dlp-ejs",
        ],
        timeout=30,
    )


# ============================================================
# DENO
# ============================================================

def setup_deno():

    print(
        "\n========== DENO SETUP ==========",
        flush=True,
    )

    if DENO_BIN.exists():

        print(
            "Deno already exists:",
            DENO_BIN,
            flush=True,
        )

        result = run_command(
            [
                DENO_BIN,
                "--version",
            ],
            timeout=30,
        )

        return result.returncode == 0

    system = platform.system().lower()
    machine = platform.machine().lower()

    if system != "linux":

        print(
            "Unsupported OS:",
            system,
            flush=True,
        )

        return False

    if machine in ("x86_64", "amd64"):

        arch = "x86_64"

    elif machine in ("aarch64", "arm64"):

        arch = "aarch64"

    else:

        print(
            "Unsupported architecture:",
            machine,
            flush=True,
        )

        return False

    url = (
        "https://github.com/denoland/deno/releases/latest/"
        "download/"
        f"deno-{arch}-unknown-linux-gnu.zip"
    )

    zip_file = LOCAL_BIN / "deno.zip"

    print(
        "Downloading Deno...",
        flush=True,
    )

    print(
        url,
        flush=True,
    )

    try:

        urllib.request.urlretrieve(
            url,
            zip_file,
        )

        with zipfile.ZipFile(
            zip_file,
            "r",
        ) as z:

            z.extractall(
                LOCAL_BIN
            )

        if not DENO_BIN.exists():

            print(
                "Deno binary not found after extraction.",
                flush=True,
            )

            return False

        mode = DENO_BIN.stat().st_mode

        DENO_BIN.chmod(
            mode
            | stat.S_IXUSR
            | stat.S_IXGRP
            | stat.S_IXOTH
        )

        try:
            zip_file.unlink()
        except Exception:
            pass

        result = run_command(
            [
                DENO_BIN,
                "--version",
            ],
            timeout=30,
        )

        return result.returncode == 0

    except Exception as e:

        print(
            "Deno installation error:",
            repr(e),
            flush=True,
        )

        return False


# ============================================================
# FFMPEG
# ============================================================

def setup_ffmpeg():

    print(
        "\n========== FFMPEG SETUP ==========",
        flush=True,
    )

    FFMPEG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not FFMPEG_BIN.exists():

        print(
            "FFmpeg not found.",
            flush=True,
        )

        print(
            "Downloading FFmpeg through spotDL...",
            flush=True,
        )

        result = run_command(
            [
                str(SPOTDL_PYTHON),
                "-m",
                "spotdl",
                "--download-ffmpeg",
            ],
            timeout=600,
            env=build_environment(),
        )

        if result.returncode != 0:

            print(
                "FFmpeg download command failed.",
                flush=True,
            )

    if FFMPEG_BIN.exists():

        print(
            "FFmpeg available:",
            FFMPEG_BIN,
            flush=True,
        )

        result = run_command(
            [
                FFMPEG_BIN,
                "-version",
            ],
            timeout=30,
            env=build_environment(),
        )

        return result.returncode == 0

    ffmpeg = shutil.which(
        "ffmpeg",
        path=build_environment()["PATH"],
    )

    if ffmpeg:

        print(
            "System FFmpeg:",
            ffmpeg,
            flush=True,
        )

        return True

    print(
        "FFmpeg NOT FOUND.",
        flush=True,
    )

    return False


# ============================================================
# YOUTUBE TEST
# ============================================================

def test_youtube():

    print(
        "\n========== YOUTUBE TEST ==========",
        flush=True,
    )

    env = build_environment()

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    print(
        "\n========== YT-DLP METADATA TEST ==========",
        flush=True,
    )

    cmd = [
        str(SPOTDL_PYTHON),
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--skip-download",
    ]

    if DENO_BIN.exists():

        cmd.extend(
            [
                "--js-runtimes",
                f"deno:{DENO_BIN}",
            ]
        )

    cmd.append(TEST_URL)

    result = run_command(
        cmd,
        timeout=180,
        env=env,
    )

    if result.returncode != 0:

        print(
            "METADATA TEST FAILED",
            flush=True,
        )

        return False

    print(
        "METADATA TEST SUCCESS",
        flush=True,
    )

    # --------------------------------------------------------
    # Real audio download
    # --------------------------------------------------------

    print(
        "\n========== YT-DLP AUDIO TEST ==========",
        flush=True,
    )

    test_dir = Path(
        "/tmp/spma_yt_test"
    )

    shutil.rmtree(
        test_dir,
        ignore_errors=True,
    )

    test_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    cmd = [
        str(SPOTDL_PYTHON),
        "-m",
        "yt_dlp",
        "--no-playlist",
        "-f",
        "ba/b",
        "-o",
        str(
            test_dir / "%(id)s.%(ext)s"
        ),
    ]

    if DENO_BIN.exists():

        cmd.extend(
            [
                "--js-runtimes",
                f"deno:{DENO_BIN}",
            ]
        )

    cmd.append(TEST_URL)

    result = run_command(
        cmd,
        timeout=300,
        env=env,
    )

    if result.returncode != 0:

        print(
            "AUDIO TEST FAILED",
            flush=True,
        )

        return False

    files = [
        x for x in test_dir.iterdir()
        if x.is_file()
    ]

    if not files:

        print(
            "AUDIO TEST FAILED: NO FILE",
            flush=True,
        )

        return False

    print(
        "Downloaded:",
        files[0],
        flush=True,
    )

    print(
        "AUDIO TEST SUCCESS",
        flush=True,
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

        print(
            "Telegram bot lock acquired.",
            flush=True,
        )

        return True

    except BlockingIOError:

        print(
            "Telegram bot already running.",
            flush=True,
        )

        return False

    except Exception as e:

        print(
            "Bot lock error:",
            repr(e),
            flush=True,
        )

        return False


# ============================================================
# TELEGRAM BOT
# ============================================================

def start_bot():

    print(
        "\n========== TELEGRAM BOT ==========",
        flush=True,
    )

    token = os.getenv(
        "TELEGRAM_TOKEN"
    )

    client_id = os.getenv(
        "SPOTIFY_CLIENT_ID"
    )

    client_secret = os.getenv(
        "SPOTIFY_CLIENT_SECRET"
    )

    if not token:

        print(
            "TELEGRAM_TOKEN missing.",
            flush=True,
        )

        return

    if not client_id or not client_secret:

        print(
            "Spotify credentials missing.",
            flush=True,
        )

        return

    try:

        from telegram.ext import (
            Updater,
            CommandHandler,
            MessageHandler,
            Filters,
        )

    except Exception as e:

        print(
            "Telegram import error:",
            repr(e),
            flush=True,
        )

        return

    def start(update, context):

        update.message.reply_text(
            "سلام 👋\n\n"
            "لینک آهنگ Spotify را ارسال کنید."
        )

    def download_spotify(
        spotify_url,
        output_dir,
    ):

        output_dir = Path(
            output_dir
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        cmd = [
            str(SPOTDL_CMD),
            "download",
            spotify_url,

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
        ]

        if DENO_BIN.exists():

            cmd.extend(
                [
                    "--yt-dlp-args",
                    f'--js-runtimes "deno:{DENO_BIN}"',
                ]
            )

        return run_command(
            cmd,
            timeout=900,
            env=build_environment(),
            cwd=output_dir,
        )

    def handle_message(
        update,
        context,
    ):

        if not update.message:
            return

        text = (
            update.message.text
            or ""
        ).strip()

        if (
            "open.spotify.com/track/" not in text
            and "spotify.com/track/" not in text
        ):

            update.message.reply_text(
                "لطفاً لینک آهنگ Spotify را ارسال کنید."
            )

            return

        update.message.reply_text(
            "⏳ در حال دانلود..."
        )

        request_dir = (
            Path("/tmp/spma_downloads")
            / str(update.message.chat_id)
            / str(update.message.message_id)
        )

        request_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:

            result = download_spotify(
                text,
                request_dir,
            )

            if result.returncode != 0:

                update.message.reply_text(
                    "❌ دانلود ناموفق بود."
                )

                return

            audio_files = []

            for pattern in (
                "*.mp3",
                "*.m4a",
                "*.opus",
                "*.webm",
                "*.ogg",
                "*.wav",
            ):

                audio_files.extend(
                    request_dir.glob(pattern)
                )

            audio_files = [
                x for x in audio_files
                if x.is_file()
                and x.stat().st_size > 0
            ]

            if not audio_files:

                update.message.reply_text(
                    "❌ فایل صوتی بعد از دانلود پیدا نشد."
                )

                return

            audio_file = max(
                audio_files,
                key=lambda x: x.stat().st_mtime,
            )

            print(
                "Audio:",
                audio_file,
                flush=True,
            )

            with open(
                audio_file,
                "rb",
            ) as f:

                update.message.reply_audio(
                    audio=f,
                    filename=audio_file.name,
                    title=audio_file.stem,
                )

        except Exception as e:

            print(
                "Bot error:",
                repr(e),
                flush=True,
            )

            try:

                update.message.reply_text(
                    "❌ خطا هنگام دانلود."
                )

            except Exception:
                pass

        finally:

            shutil.rmtree(
                request_dir,
                ignore_errors=True,
            )

    try:

        updater = Updater(
            token=token,
            use_context=True,
        )

        updater.dispatcher.add_handler(
            CommandHandler(
                "start",
                start,
            )
        )

        updater.dispatcher.add_handler(
            MessageHandler(
                Filters.text
                & ~Filters.command,
                handle_message,
            )
        )

        print(
            "Starting Telegram polling...",
            flush=True,
        )

        updater.start_polling(
            drop_pending_updates=True,
        )

        print(
            "Telegram polling started.",
            flush=True,
        )

        while True:

            time.sleep(3600)

    except Exception as e:

        print(
            "Telegram startup error:",
            repr(e),
            flush=True,
        )


def start_bot_thread():

    global BOT_THREAD

    if globals().get(
        "_BOT_STARTED",
        False,
    ):

        print(
            "Bot already started.",
            flush=True,
        )

        return

    if not acquire_bot_lock():

        return

    globals()[
        "_BOT_STARTED"
    ] = True

    BOT_THREAD = threading.Thread(
        target=start_bot,
        daemon=True,
        name="telegram-bot",
    )

    BOT_THREAD.start()

    print(
        "Telegram bot thread started.",
        flush=True,
    )


# ============================================================
# MAIN INITIALIZATION
# ============================================================

def initialize():

    print(
        "\n========================================",
        flush=True,
    )

    print(
        "        SPMA INITIALIZATION",
        flush=True,
    )

    print(
        "========================================",
        flush=True,
    )

    cpu_info()

    root_test()

    setup_spotdl()

    ffmpeg_ok = setup_ffmpeg()

    deno_ok = setup_deno()

    youtube_ok = test_youtube()

    start_bot_thread()

    return {
        "spotdl": SPOTDL_CMD.exists(),
        "ffmpeg": ffmpeg_ok,
        "deno": deno_ok,
        "youtube": youtube_ok,
    }


# ============================================================
# STREAMLIT
# ============================================================

st.set_page_config(
    page_title="SPMA Spotify Downloader",
    page_icon="🎵",
)

st.title(
    "🎵 SPMA Spotify Downloader"
)

st.write(
    "Spotify → MP3 320kbps"
)

st.info(
    "Bot در پس‌زمینه اجرا می‌شود. "
    "لینک آهنگ Spotify را در Telegram ارسال کنید."
)


# ------------------------------------------------------------
# RUN INITIALIZATION ONLY ONCE PER PROCESS
# ------------------------------------------------------------

if not globals().get(
    "_SPMA_INITIALIZED",
    False,
):

    globals()[
        "_SPMA_INITIALIZED"
    ] = True

    try:

        status = initialize()

        st.success(
            "SPMA initialization completed."
        )

        col1, col2 = st.columns(2)

        with col1:

            st.write(
                "spotDL:",
                "✅"
                if status["spotdl"]
                else "❌",
            )

            st.write(
                "FFmpeg:",
                "✅"
                if status["ffmpeg"]
                else "❌",
            )

        with col2:

            st.write(
                "Deno:",
                "✅"
                if status["deno"]
                else "❌",
            )

            st.write(
                "YouTube:",
                "✅"
                if status["youtube"]
                else "❌",
            )

    except Exception as e:

        print(
            "INITIALIZATION ERROR:",
            repr(e),
            flush=True,
        )

        st.error(
            "SPMA initialization failed."
        )

        st.exception(e)

else:

    st.success(
        "SPMA is already running."
    )
