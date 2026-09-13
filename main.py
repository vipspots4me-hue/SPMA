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

SPOTDL_REPO = (
    "git+https://github.com/TzurSoffer/"
    "spotify-downloader@29cb0b0669d5c107331b0912fdef73967b47493e"
)


# ============================================================
# GLOBALS
# ============================================================

BOT_LOCK_FD = None
BOT_THREAD = None


# ============================================================
# COMMAND RUNNER
# ============================================================

def run_command(cmd, timeout=300, env=None):
    """
    Run command and print stdout/stderr in real time.
    Returns:
        returncode, output
    """

    print("\n$ " + " ".join(map(str, cmd)), flush=True)

    try:
        process = subprocess.Popen(
            [str(x) for x in cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )

        output_lines = []

        for line in process.stdout:
            print(line, end="", flush=True)
            output_lines.append(line)

        process.wait(timeout=timeout)

        output = "".join(output_lines)

        print(
            f"Exit code: {process.returncode}",
            flush=True,
        )

        return process.returncode, output

    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except Exception:
            pass

        print("COMMAND TIMEOUT", flush=True)
        return 124, ""

    except Exception as e:
        print(
            "COMMAND ERROR:",
            repr(e),
            flush=True,
        )
        return 1, str(e)


# ============================================================
# ENVIRONMENT
# ============================================================

def build_environment():
    env = os.environ.copy()

    paths = [
        str(SPOTDL_VENV / "bin"),
        str(LOCAL_BIN),
        str(FFMPEG_DIR),
    ]

    old_path = env.get("PATH", "")

    env["PATH"] = ":".join(paths + [old_path])

    return env


# ============================================================
# CPU INFO
# ============================================================

def cpu_info():

    print("\n========== CPU INFO ==========", flush=True)

    run_command(
        ["nproc"],
        timeout=30,
    )

    run_command(
        [
            "bash",
            "-c",
            "lscpu | grep -E "
            "'Architecture|Model name|CPU\\(s\\)|Thread|Core|Socket|Virtualization'"
        ],
        timeout=30,
    )


# ============================================================
# ROOT TEST
# ============================================================

def root_test():

    print("\n========== ROOT TEST ==========", flush=True)

    code, _ = run_command(
        ["sudo", "-n", "id"],
        timeout=30,
    )

    if code == 0:
        print("SUDO WITHOUT PASSWORD: AVAILABLE", flush=True)
        return True

    print(
        "SUDO WITHOUT PASSWORD: NOT AVAILABLE",
        flush=True,
    )

    return False


# ============================================================
# SPOTDL SETUP
# ============================================================

def setup_spotdl():

    print("\n========== SPOTDL SETUP ==========", flush=True)

    SPOTDL_VENV.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Create virtual environment
    # --------------------------------------------------------

    if not SPOTDL_PYTHON.exists():

        print(
            "Creating isolated spotDL virtual environment...",
            flush=True,
        )

        code, _ = run_command(
            [
                sys.executable,
                "-m",
                "venv",
                str(SPOTDL_VENV),
            ],
            timeout=180,
        )

        if code != 0:
            print(
                "FAILED TO CREATE SPOTDL VENV",
                flush=True,
            )
            return False

    else:

        print(
            "spotDL virtual environment already exists.",
            flush=True,
        )

    # --------------------------------------------------------
    # Install spotDL if missing
    # --------------------------------------------------------

    if not SPOTDL_CMD.exists():

        print(
            "Installing spotDL...",
            flush=True,
        )

        code, _ = run_command(
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

        if code != 0:
            return False

        code, _ = run_command(
            [
                str(SPOTDL_PYTHON),
                "-m",
                "pip",
                "install",
                SPOTDL_REPO,
            ],
            timeout=600,
        )

        if code != 0:
            print(
                "FAILED TO INSTALL SPOTDL",
                flush=True,
            )
            return False

    else:

        print(
            "spotDL already installed.",
            flush=True,
        )

    # --------------------------------------------------------
    # IMPORTANT:
    # DO NOT PIN OLD YT-DLP
    # --------------------------------------------------------

    print(
        "\nUpdating yt-dlp and yt-dlp-ejs to latest versions...",
        flush=True,
    )

    code, _ = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "yt-dlp",
            "yt-dlp-ejs",
        ],
        timeout=600,
    )

    if code != 0:
        print(
            "FAILED TO UPDATE YT-DLP",
            flush=True,
        )
        return False

    # --------------------------------------------------------
    # Verify spotDL
    # --------------------------------------------------------

    print(
        "\n========== SPOTDL VERSION ==========",
        flush=True,
    )

    run_command(
        [
            str(SPOTDL_CMD),
            "--version",
        ],
        timeout=60,
    )

    # --------------------------------------------------------
    # Verify yt-dlp
    # --------------------------------------------------------

    print(
        "\n========== YT-DLP VERSION ==========",
        flush=True,
    )

    code, _ = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "yt_dlp",
            "--version",
        ],
        timeout=60,
    )

    if code != 0:
        print(
            "YT-DLP VERIFICATION FAILED",
            flush=True,
        )
        return False

    # --------------------------------------------------------
    # Verify yt-dlp-ejs
    # --------------------------------------------------------

    print(
        "\n========== YT-DLP-EJS ==========",
        flush=True,
    )

    code, _ = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "show",
            "yt-dlp-ejs",
        ],
        timeout=60,
    )

    if code != 0:
        print(
            "YT-DLP-EJS CHECK FAILED",
            flush=True,
        )

    return True


# ============================================================
# DENO SETUP
# ============================================================

def setup_deno():

    print("\n========== DENO SETUP ==========", flush=True)

    LOCAL_BIN.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Already installed
    # --------------------------------------------------------

    if DENO_BIN.exists():

        try:
            DENO_BIN.chmod(
                DENO_BIN.stat().st_mode
                | stat.S_IXUSR
                | stat.S_IXGRP
                | stat.S_IXOTH
            )
        except Exception:
            pass

        code, _ = run_command(
            [
                str(DENO_BIN),
                "--version",
            ],
            timeout=60,
            env=build_environment(),
        )

        if code == 0:
            print(
                "Deno already available.",
                flush=True,
            )
            return True

    # --------------------------------------------------------
    # Download Deno
    # --------------------------------------------------------

    print(
        "Downloading Deno...",
        flush=True,
    )

    deno_zip = LOCAL_BIN / "deno.zip"

    url = (
        "https://github.com/denoland/deno/releases/latest/"
        "download/deno-x86_64-unknown-linux-gnu.zip"
    )

    try:

        urllib.request.urlretrieve(
            url,
            deno_zip,
        )

        print(
            "Deno archive downloaded.",
            flush=True,
        )

    except Exception as e:

        print(
            "Deno download failed:",
            repr(e),
            flush=True,
        )

        return False

    # --------------------------------------------------------
    # Extract
    # --------------------------------------------------------

    try:

        with zipfile.ZipFile(
            deno_zip,
            "r",
        ) as z:

            z.extractall(
                LOCAL_BIN
            )

    except Exception as e:

        print(
            "Deno extraction failed:",
            repr(e),
            flush=True,
        )

        return False

    # --------------------------------------------------------
    # Permissions
    # --------------------------------------------------------

    try:

        DENO_BIN.chmod(
            DENO_BIN.stat().st_mode
            | stat.S_IXUSR
            | stat.S_IXGRP
            | stat.S_IXOTH
        )

    except Exception as e:

        print(
            "Deno chmod failed:",
            repr(e),
            flush=True,
        )

    # --------------------------------------------------------
    # Cleanup
    # --------------------------------------------------------

    try:
        deno_zip.unlink(
            missing_ok=True
        )
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
        timeout=60,
        env=build_environment(),
    )

    if code != 0:
        print(
            "DENO TEST FAILED",
            flush=True,
        )
        return False

    print(
        "Deno setup successful.",
        flush=True,
    )

    return True


# ============================================================
# FFMPEG SETUP
# ============================================================

def setup_ffmpeg():

    print("\n========== FFMPEG SETUP ==========", flush=True)

    FFMPEG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if FFMPEG_BIN.exists():

        try:

            FFMPEG_BIN.chmod(
                FFMPEG_BIN.stat().st_mode
                | stat.S_IXUSR
                | stat.S_IXGRP
                | stat.S_IXOTH
            )

        except Exception:
            pass

        code, _ = run_command(
            [
                str(FFMPEG_BIN),
                "-version",
            ],
            timeout=60,
            env=build_environment(),
        )

        if code == 0:

            print(
                "FFmpeg already available.",
                flush=True,
            )

            return True

    # --------------------------------------------------------
    # Download through spotDL
    # --------------------------------------------------------

    print(
        "FFmpeg not found. Downloading through spotDL...",
        flush=True,
    )

    code, _ = run_command(
        [
            str(SPOTDL_CMD),
            "--download-ffmpeg",
        ],
        timeout=600,
        env=build_environment(),
    )

    if code != 0:
        print(
            "FFmpeg download failed.",
            flush=True,
        )
        return False

    # --------------------------------------------------------
    # Verify
    # --------------------------------------------------------

    if not FFMPEG_BIN.exists():

        print(
            "FFmpeg binary still not found.",
            flush=True,
        )

        return False

    try:

        FFMPEG_BIN.chmod(
            FFMPEG_BIN.stat().st_mode
            | stat.S_IXUSR
            | stat.S_IXGRP
            | stat.S_IXOTH
        )

    except Exception:
        pass

    code, _ = run_command(
        [
            str(FFMPEG_BIN),
            "-version",
        ],
        timeout=60,
        env=build_environment(),
    )

    return code == 0


# ============================================================
# YOUTUBE METADATA TEST
# ============================================================

def test_youtube_metadata():

    print(
        "\n========== YT-DLP METADATA TEST ==========",
        flush=True,
    )

    cmd = [
        str(SPOTDL_PYTHON),
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--dump-single-json",
        "--skip-download",
    ]

    if DENO_BIN.exists():

        cmd.extend(
            [
                "--js-runtimes",
                f"deno:{DENO_BIN}",
            ]
        )

    cmd.append(
        TEST_URL
    )

    code, output = run_command(
        cmd,
        timeout=180,
        env=build_environment(),
    )

    if code == 0:

        print(
            "METADATA TEST SUCCESS",
            flush=True,
        )

        return True

    print(
        "METADATA TEST FAILED",
        flush=True,
    )

    return False


# ============================================================
# YOUTUBE AUDIO TEST
# ============================================================

def test_youtube_audio():

    print(
        "\n========== YT-DLP AUDIO TEST ==========",
        flush=True,
    )

    test_dir = Path("/tmp/spma_yt_test")

    try:

        shutil.rmtree(
            test_dir,
            ignore_errors=True,
        )

        test_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    except Exception:
        pass

    output_template = (
        str(test_dir)
        + "/%(id)s.%(ext)s"
    )

    cmd = [
        str(SPOTDL_PYTHON),
        "-m",
        "yt_dlp",

        "--no-playlist",

        # Let yt-dlp choose the best available audio.
        "-f",
        "ba/b",

        "-o",
        output_template,
    ]

    # --------------------------------------------------------
    # Deno / EJS
    # --------------------------------------------------------

    if DENO_BIN.exists():

        cmd.extend(
            [
                "--js-runtimes",
                f"deno:{DENO_BIN}",
            ]
        )

    # --------------------------------------------------------
    # IMPORTANT:
    # NO web_embedded
    # NO forced player_client
    # --------------------------------------------------------

    cmd.append(
        TEST_URL
    )

    code, _ = run_command(
        cmd,
        timeout=300,
        env=build_environment(),
    )

    if code != 0:

        print(
            "AUDIO TEST FAILED",
            flush=True,
        )

        return False

    files = list(
        test_dir.glob("*")
    )

    if files:

        print(
            "AUDIO TEST SUCCESS",
            flush=True,
        )

        print(
            "Downloaded:",
            files[0],
            flush=True,
        )

        return True

    print(
        "AUDIO TEST FAILED: no output file.",
        flush=True,
    )

    return False


# ============================================================
# YOUTUBE FULL TEST
# ============================================================

def test_youtube():

    print(
        "\n"
        "##################################################\n"
        "#               YOUTUBE TESTS                    #\n"
        "##################################################",
        flush=True,
    )

    metadata_ok = test_youtube_metadata()

    audio_ok = test_youtube_audio()

    print(
        "\n========== YOUTUBE TEST SUMMARY ==========",
        flush=True,
    )

    print(
        "Metadata:",
        "OK" if metadata_ok else "FAILED",
        flush=True,
    )

    print(
        "Audio:",
        "OK" if audio_ok else "FAILED",
        flush=True,
    )

    return metadata_ok, audio_ok


# ============================================================
# TELEGRAM BOT LOCK
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

    token = os.environ.get(
        "TELEGRAM_TOKEN"
    )

    client_id = os.environ.get(
        "SPOTIFY_CLIENT_ID"
    )

    client_secret = os.environ.get(
        "SPOTIFY_CLIENT_SECRET"
    )

    if not token:

        print(
            "TELEGRAM_TOKEN missing.",
            flush=True,
        )

        return False

    if not client_id:

        print(
            "SPOTIFY_CLIENT_ID missing.",
            flush=True,
        )

        return False

    if not client_secret:

        print(
            "SPOTIFY_CLIENT_SECRET missing.",
            flush=True,
        )

        return False

    # --------------------------------------------------------
    # Import PTB 13.14
    # --------------------------------------------------------

    try:

        from telegram.ext import (
            Updater,
            CommandHandler,
            MessageHandler,
            Filters,
        )

    except Exception as e:

        print(
            "Telegram import failed:",
            repr(e),
            flush=True,
        )

        return False

    # --------------------------------------------------------
    # Handlers
    # --------------------------------------------------------

    def start(update, context):

        try:

            update.message.reply_text(
                "🎵 Send me a Spotify track link."
            )

        except Exception as e:

            print(
                "Start handler error:",
                repr(e),
                flush=True,
            )

    def download_track(update, context):

        message = update.message

        if not message:
            return

        text = (
            message.text or ""
        ).strip()

        if "spotify.com" not in text:

            try:

                message.reply_text(
                    "Please send a Spotify track URL."
                )

            except Exception:
                pass

            return

        try:

            message.reply_text(
                "⏳ Downloading..."
            )

        except Exception:
            pass

        # ----------------------------------------------------
        # Temporary download directory
        # ----------------------------------------------------

        download_dir = (
            Path("/tmp/spma_downloads")
        )

        download_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # ----------------------------------------------------
        # SpotDL command
        # ----------------------------------------------------

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
        ]

        # ----------------------------------------------------
        # Deno / EJS
        # ----------------------------------------------------

        if DENO_BIN.exists():

            cmd.extend(
                [
                    "--yt-dlp-args",
                    f'--js-runtimes "deno:{DENO_BIN}"',
                ]
            )

        # ----------------------------------------------------
        # Run spotDL
        # ----------------------------------------------------

        print(
            "\n========== SPOTIFY DOWNLOAD ==========",
            flush=True,
        )

        print(
            "Spotify URL:",
            text,
            flush=True,
        )

        code, output = run_command(
            cmd,
            timeout=900,
            env=build_environment(),
        )

        # ----------------------------------------------------
        # Find generated audio
        # ----------------------------------------------------

        audio_files = []

        for extension in [
            "*.mp3",
            "*.m4a",
            "*.opus",
            "*.ogg",
            "*.wav",
            "*.flac",
        ]:

            audio_files.extend(
                download_dir.rglob(
                    extension
                )
            )

        # SpotDL may save somewhere else depending
        # on its config, so also inspect current directory.
        if not audio_files:

            for extension in [
                "*.mp3",
                "*.m4a",
                "*.opus",
                "*.ogg",
                "*.wav",
                "*.flac",
            ]:

                audio_files.extend(
                    Path(".").glob(
                        extension
                    )
                )

        if code != 0 or not audio_files:

            print(
                "No audio file found after download.",
                flush=True,
            )

            try:

                message.reply_text(
                    "❌ Download failed.\n\n"
                    "YouTube/yt-dlp may have rejected "
                    "the media request."
                )

            except Exception:
                pass

            return

        audio_file = audio_files[-1]

        print(
            "Audio found:",
            audio_file,
            flush=True,
        )

        # ----------------------------------------------------
        # Send audio
        # ----------------------------------------------------

        try:

            with open(
                audio_file,
                "rb",
            ) as audio:

                message.reply_audio(
                    audio=audio,
                    filename=audio_file.name,
                )

        except Exception as e:

            print(
                "Telegram send error:",
                repr(e),
                flush=True,
            )

            try:

                message.reply_text(
                    "❌ Could not send the audio."
                )

            except Exception:
                pass

        # ----------------------------------------------------
        # Cleanup
        # ----------------------------------------------------

        try:

            audio_file.unlink(
                missing_ok=True
            )

        except Exception:
            pass

    # --------------------------------------------------------
    # Updater
    # --------------------------------------------------------

    try:

        updater = Updater(
            token=token,
            use_context=True,
        )

        dispatcher = updater.dispatcher

        dispatcher.add_handler(
            CommandHandler(
                "start",
                start,
            )
        )

        dispatcher.add_handler(
            MessageHandler(
                Filters.text & ~Filters.command,
                download_track,
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
            "Telegram bot started successfully.",
            flush=True,
        )

        # IMPORTANT:
        # Do NOT use updater.idle() on Streamlit.
        while True:

            time.sleep(
                3600
            )

    except Exception as e:

        print(
            "Telegram bot error:",
            repr(e),
            flush=True,
        )

        return False


# ============================================================
# BOT THREAD
# ============================================================

def start_bot_thread():

    global BOT_THREAD

    if BOT_THREAD is not None:

        print(
            "Telegram bot thread already exists.",
            flush=True,
        )

        return

    if not acquire_bot_lock():

        return

    BOT_THREAD = threading.Thread(
        target=start_bot,
        daemon=True,
        name="spma-telegram-bot",
    )

    BOT_THREAD.start()

    print(
        "Telegram bot thread started.",
        flush=True,
    )


# ============================================================
# INITIALIZATION
# ============================================================

def initialize():

    print(
        "\n"
        "==================================================\n"
        "              SPMA INITIALIZATION                 \n"
        "==================================================",
        flush=True,
    )

    # --------------------------------------------------------
    # CPU
    # --------------------------------------------------------

    cpu_info()

    # --------------------------------------------------------
    # Root
    # --------------------------------------------------------

    root_test()

    # --------------------------------------------------------
    # spotDL
    # --------------------------------------------------------

    spotdl_ok = setup_spotdl()

    if not spotdl_ok:

        print(
            "spotDL setup FAILED.",
            flush=True,
        )

        return False

    # --------------------------------------------------------
    # FFmpeg
    # --------------------------------------------------------

    ffmpeg_ok = setup_ffmpeg()

    if not ffmpeg_ok:

        print(
            "FFmpeg setup FAILED.",
            flush=True,
        )

    # --------------------------------------------------------
    # Deno
    # --------------------------------------------------------

    deno_ok = setup_deno()

    if not deno_ok:

        print(
            "Deno setup FAILED.",
            flush=True,
        )

    # --------------------------------------------------------
    # YouTube tests
    # --------------------------------------------------------

    metadata_ok, audio_ok = test_youtube()

    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------

    start_bot_thread()

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print(
        "\n"
        "==================================================\n"
        "                FINAL SUMMARY                     \n"
        "==================================================",
        flush=True,
    )

    print(
        "spotDL:",
        "OK" if spotdl_ok else "FAILED",
        flush=True,
    )

    print(
        "FFmpeg:",
        "OK" if ffmpeg_ok else "FAILED",
        flush=True,
    )

    print(
        "Deno:",
        "OK" if deno_ok else "FAILED",
        flush=True,
    )

    print(
        "YouTube metadata:",
        "OK" if metadata_ok else "FAILED",
        flush=True,
    )

    print(
        "YouTube audio:",
        "OK" if audio_ok else "FAILED",
        flush=True,
    )

    return True


# ============================================================
# STREAMLIT
# ============================================================

st.set_page_config(
    page_title="SPMA",
    page_icon="🎵",
)

st.title("🎵 SPMA")

st.write(
    "Spotify downloader service is running."
)

# ------------------------------------------------------------
# Initialize once per Streamlit process
# ------------------------------------------------------------

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

        print(
            "\n========== INITIALIZATION ERROR ==========",
            flush=True,
        )

        print(
            repr(e),
            flush=True,
        )


# ------------------------------------------------------------
# Keep Streamlit process alive
# ------------------------------------------------------------

while True:

    time.sleep(
        3600
    )
