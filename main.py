import os
import sys
import time
import shutil
import signal
import threading
import subprocess
import platform
import urllib.request
import tarfile
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
# GENERAL HELPERS
# ============================================================

def run_command(
    cmd,
    timeout=300,
    env=None,
    cwd=None,
):
    """
    Run command and return CompletedProcess.
    """

    print("\n$ " + " ".join(map(str, cmd)))

    try:
        result = subprocess.run(
            [str(x) for x in cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            env=env,
            cwd=cwd,
        )

        print(result.stdout)

        print("Exit code:", result.returncode)

        return result

    except subprocess.TimeoutExpired as e:
        print("COMMAND TIMEOUT")

        output = ""

        if e.stdout:
            output += str(e.stdout)

        if e.stderr:
            output += str(e.stderr)

        print(output)

        return subprocess.CompletedProcess(
            cmd,
            124,
            output,
        )

    except Exception as e:
        print("COMMAND ERROR:", repr(e))

        return subprocess.CompletedProcess(
            cmd,
            1,
            str(e),
        )


# ============================================================
# CPU INFO
# ============================================================

def cpu_info():
    print("\n========== CPU INFO ==========")

    try:
        nproc = shutil.which("nproc")

        if nproc:
            result = run_command(
                [nproc],
                timeout=10,
            )

        else:
            print("nproc not found.")

    except Exception as e:
        print("nproc error:", repr(e))

    try:
        lscpu = shutil.which("lscpu")

        if lscpu:
            result = run_command(
                [
                    lscpu
                ],
                timeout=10,
            )

        else:
            print("lscpu not found.")

    except Exception as e:
        print("lscpu error:", repr(e))


# ============================================================
# ROOT TEST
# ============================================================

def root_test():
    print("\n========== ROOT TEST ==========")

    try:
        print("Current user:", os.getenv("USER"))

        print(
            "UID:",
            os.getuid() if hasattr(os, "getuid") else "N/A"
        )

        sudo = shutil.which("sudo")

        if sudo:
            print("sudo:", sudo)

            result = run_command(
                [
                    sudo,
                    "-n",
                    "id",
                ],
                timeout=10,
            )

        else:
            print("sudo not found.")

    except Exception as e:
        print("Root test error:", repr(e))


# ============================================================
# ENVIRONMENT
# ============================================================

def build_environment():
    env = os.environ.copy()

    current_path = env.get("PATH", "")

    paths = [
        str(SPOTDL_VENV / "bin"),
        str(LOCAL_BIN),
        str(FFMPEG_DIR),
    ]

    env["PATH"] = ":".join(paths + [current_path])

    return env


# ============================================================
# DENO
# ============================================================

def setup_deno():
    """
    Install Deno locally if it does not exist.

    No root privileges required.
    """

    print("\n========== DENO SETUP ==========")

    if DENO_BIN.exists():
        try:
            result = run_command(
                [
                    DENO_BIN,
                    "--version",
                ],
                timeout=20,
            )

            if result.returncode == 0:
                print("Deno already installed.")

                return True

        except Exception as e:
            print("Existing Deno test failed:", repr(e))

    print("Deno not found.")

    system = platform.system().lower()
    machine = platform.machine().lower()

    if system != "linux":
        print("Unsupported OS for automatic Deno installation:", system)
        return False

    if machine in ("x86_64", "amd64"):
        deno_arch = "x86_64"

    elif machine in ("aarch64", "arm64"):
        deno_arch = "aarch64"

    else:
        print("Unsupported CPU architecture:", machine)
        return False

    # Current stable Deno release endpoint.
    download_url = (
        "https://github.com/denoland/deno/releases/latest/download/"
        f"deno-{deno_arch}-unknown-linux-gnu.zip"
    )

    zip_path = LOCAL_BIN / "deno.zip"

    try:
        print("Downloading Deno from:")
        print(download_url)

        urllib.request.urlretrieve(
            download_url,
            zip_path,
        )

        print("Deno archive downloaded.")

        # Python stdlib zip extraction
        import zipfile

        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(LOCAL_BIN)

        if not DENO_BIN.exists():
            print("Deno binary was not found after extraction.")

            return False

        mode = DENO_BIN.stat().st_mode

        DENO_BIN.chmod(
            mode
            | stat.S_IXUSR
            | stat.S_IXGRP
            | stat.S_IXOTH
        )

        try:
            zip_path.unlink()
        except Exception:
            pass

        result = run_command(
            [
                DENO_BIN,
                "--version",
            ],
            timeout=20,
        )

        if result.returncode == 0:
            print("Deno installation successful.")

            return True

        print("Deno installation test failed.")

        return False

    except Exception as e:
        print("Deno installation error:", repr(e))

        return False


# ============================================================
# SPOTDL
# ============================================================

def setup_spotdl():
    print("\n========== SPOTDL SETUP ==========")

    if not SPOTDL_PYTHON.exists():

        print("Creating isolated spotDL environment...")

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

    print("Installing spotDL...")

    install_cmd = [
        str(SPOTDL_PYTHON),
        "-m",
        "pip",
        "install",
        "--upgrade",
        "pip",
        "setuptools",
        "wheel",
    ]

    result = run_command(
        install_cmd,
        timeout=300,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Failed to upgrade pip/setuptools."
        )

    # --------------------------------------------------------
    # yt-dlp
    # --------------------------------------------------------

    print("\n========== YT-DLP INSTALL ==========")

    result = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "install",
            "--force-reinstall",
            "yt-dlp==2026.06.09",
        ],
        timeout=300,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Failed to install yt-dlp."
        )

    # --------------------------------------------------------
    # spotDL
    # --------------------------------------------------------

    print("\n========== SPOTDL INSTALL ==========")

    result = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "install",
            "--force-reinstall",
            "git+https://github.com/TzurSoffer/"
            "spotify-downloader@"
            "29cb0b0669d5c107331b0912fdef73967b47493e",
        ],
        timeout=600,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Failed to install spotDL."
        )

    # --------------------------------------------------------
    # Versions
    # --------------------------------------------------------

    print("\n========== SPOTDL VERSION ==========")

    run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "spotdl",
            "--version",
        ],
        timeout=30,
    )

    print("\n========== YT-DLP VERSION ==========")

    run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "yt_dlp",
            "--version",
        ],
        timeout=30,
    )

    print("\nspotDL isolated environment ready.")


# ============================================================
# FFMPEG
# ============================================================

def setup_ffmpeg():
    print("\n========== FFMPEG SETUP ==========")

    FFMPEG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if FFMPEG_BIN.exists():
        print("FFmpeg already exists:")
        print(FFMPEG_BIN)

    else:
        print("FFmpeg not found.")
        print("Asking spotDL to download FFmpeg...")

        env = build_environment()

        result = run_command(
            [
                str(SPOTDL_PYTHON),
                "-m",
                "spotdl",
                "--download-ffmpeg",
            ],
            timeout=600,
            env=env,
        )

        if result.returncode != 0:
            print(
                "spotDL FFmpeg download command failed."
            )

    # Search possible FFmpeg locations.

    possible_paths = [
        FFMPEG_BIN,
        Path.home() / ".config/spotdl/ffmpeg",
        SPOTDL_VENV / "bin/ffmpeg",
    ]

    found = None

    for path in possible_paths:

        if path.exists() and os.access(path, os.X_OK):
            found = path
            break

    if found is None:

        found_from_path = shutil.which(
            "ffmpeg",
            path=build_environment()["PATH"],
        )

        if found_from_path:
            found = Path(found_from_path)

    if found is None:
        print("FFmpeg could not be found.")

        return False

    print("FFmpeg available at:")
    print(found)

    try:
        found.chmod(
            found.stat().st_mode
            | stat.S_IXUSR
            | stat.S_IXGRP
            | stat.S_IXOTH
        )
    except Exception:
        pass

    env = build_environment()

    env["PATH"] = (
        str(found.parent)
        + ":"
        + env["PATH"]
    )

    result = run_command(
        [
            str(found),
            "-version",
        ],
        timeout=30,
        env=env,
    )

    return result.returncode == 0


# ============================================================
# YOUTUBE / YT-DLP TEST
# ============================================================

def test_youtube():
    """
    First test metadata.
    Then perform a REAL audio-only download.

    We intentionally do NOT use:
        -f 18

    because the previous test returned HTTP 403.

    We also do NOT use:
        youtube:player_client=web_embedded

    because that client override caused metadata/download
    problems with the tracks used by spotDL.
    """

    print("\n========== YOUTUBE TEST ==========")

    env = build_environment()

    # --------------------------------------------------------
    # Deno
    # --------------------------------------------------------

    deno_available = False

    if DENO_BIN.exists():
        deno_available = True

        env["PATH"] = (
            str(LOCAL_BIN)
            + ":"
            + env["PATH"]
        )

    print(
        "Deno available:",
        deno_available
    )

    # --------------------------------------------------------
    # Metadata test
    # --------------------------------------------------------

    print("\n========== YT-DLP METADATA TEST ==========")

    metadata_cmd = [
        str(SPOTDL_PYTHON),
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--skip-download",
    ]

    if deno_available:
        metadata_cmd.extend(
            [
                "--js-runtimes",
                f"deno:{DENO_BIN}",
            ]
        )

    metadata_cmd.append(TEST_URL)

    result = run_command(
        metadata_cmd,
        timeout=180,
        env=env,
    )

    if result.returncode != 0:

        print(
            "YT-DLP METADATA TEST: FAILED"
        )

        return False

    print(
        "YT-DLP METADATA TEST: SUCCESS"
    )

    # --------------------------------------------------------
    # Actual audio download
    # --------------------------------------------------------

    print(
        "\n========== YT-DLP AUDIO DOWNLOAD TEST =========="
    )

    test_dir = Path("/tmp/yt_test")

    try:
        if test_dir.exists():
            shutil.rmtree(test_dir)
    except Exception:
        pass

    test_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    audio_cmd = [
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

    if deno_available:
        audio_cmd.extend(
            [
                "--js-runtimes",
                f"deno:{DENO_BIN}",
            ]
        )

    audio_cmd.append(TEST_URL)

    result = run_command(
        audio_cmd,
        timeout=300,
        env=env,
    )

    if result.returncode != 0:

        print(
            "YT-DLP AUDIO DOWNLOAD TEST: FAILED"
        )

        print(
            "\nThe metadata extractor works, "
            "but the actual YouTube media request failed."
        )

        return False

    # --------------------------------------------------------
    # Verify file
    # --------------------------------------------------------

    files = list(
        test_dir.glob("*")
    )

    files = [
        x for x in files
        if x.is_file()
    ]

    if not files:

        print(
            "YT-DLP AUDIO DOWNLOAD TEST: "
            "NO FILE FOUND"
        )

        return False

    print("\nDownloaded file:")

    for file in files:

        print(
            file,
            file.stat().st_size,
            "bytes"
        )

    print(
        "\nYT-DLP AUDIO DOWNLOAD TEST: SUCCESS"
    )

    return True


# ============================================================
# TELEGRAM BOT
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
            "Telegram bot process lock acquired."
        )

        return True

    except BlockingIOError:

        print(
            "Telegram bot is already running "
            "in this container."
        )

        return False

    except Exception as e:

        print(
            "Bot lock error:",
            repr(e)
        )

        return False


def start_bot():
    """
    Telegram bot using python-telegram-bot 13.14.
    """

    print("\n========== TELEGRAM BOT ==========")

    token = os.getenv(
        "TELEGRAM_TOKEN"
    )

    if not token:

        print(
            "TELEGRAM_TOKEN is not set."
        )

        return

    client_id = os.getenv(
        "SPOTIFY_CLIENT_ID"
    )

    client_secret = os.getenv(
        "SPOTIFY_CLIENT_SECRET"
    )

    if not client_id or not client_secret:

        print(
            "Spotify credentials are not set."
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
            repr(e)
        )

        return

    # --------------------------------------------------------
    # /start
    # --------------------------------------------------------

    def start(update, context):

        update.message.reply_text(
            "سلام 👋\n\n"
            "لینک آهنگ Spotify را بفرستید "
            "تا به MP3 تبدیل و ارسال شود."
        )

    # --------------------------------------------------------
    # Download function
    # --------------------------------------------------------

    def download_spotify(
        spotify_url,
        output_dir,
    ):

        output_dir = Path(output_dir)

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        env = build_environment()

        # Important:
        #
        # NO:
        # --yt-dlp-args
        # youtube:player_client=web_embedded
        #
        # spotDL uses its own yt-dlp integration.

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

        # If Deno exists, pass it to spotDL's yt-dlp.
        #
        # spotDL forwards this argument to yt-dlp.

        if DENO_BIN.exists():

            cmd.extend(
                [
                    "--yt-dlp-args",
                    f'--js-runtimes "deno:{DENO_BIN}"',
                ]
            )

        result = run_command(
            cmd,
            timeout=900,
            env=env,
            cwd=output_dir,
        )

        return result

    # --------------------------------------------------------
    # Message handler
    # --------------------------------------------------------

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

        if not text:
            return

        # ----------------------------------------------------
        # Check Spotify URL
        # ----------------------------------------------------

        if (
            "open.spotify.com/track/" not in text
            and "spotify.com/track/" not in text
        ):

            update.message.reply_text(
                "لطفاً لینک آهنگ Spotify را ارسال کنید."
            )

            return

        update.message.reply_text(
            "⏳ در حال دریافت اطلاعات آهنگ و دانلود..."
        )

        work_dir = Path(
            "/tmp/spma_downloads"
        )

        work_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Separate directory for this request.
        request_dir = (
            work_dir
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
                    "❌ دانلود انجام نشد.\n\n"
                    "خروجی خطا در لاگ سرور ثبت شده است."
                )

                return

            # ------------------------------------------------
            # Search downloaded audio
            # ------------------------------------------------

            audio_files = []

            for ext in (
                "*.mp3",
                "*.m4a",
                "*.opus",
                "*.webm",
                "*.ogg",
                "*.wav",
            ):

                audio_files.extend(
                    request_dir.glob(ext)
                )

            audio_files = [
                x for x in audio_files
                if x.is_file()
                and x.stat().st_size > 0
            ]

            if not audio_files:

                update.message.reply_text(
                    "❌ دانلود ظاهراً انجام شد "
                    "ولی فایل صوتی پیدا نشد."
                )

                return

            # Use newest/largest suitable file.
            audio_file = max(
                audio_files,
                key=lambda x: x.stat().st_mtime,
            )

            print(
                "Audio file found:",
                audio_file,
                audio_file.stat().st_size,
                "bytes"
            )

            # ------------------------------------------------
            # Send audio
            # ------------------------------------------------

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
                "Telegram download error:",
                repr(e)
            )

            try:

                update.message.reply_text(
                    "❌ خطا هنگام پردازش آهنگ."
                )

            except Exception:
                pass

        finally:

            # ------------------------------------------------
            # Cleanup
            # ------------------------------------------------

            try:

                if request_dir.exists():

                    shutil.rmtree(
                        request_dir,
                        ignore_errors=True,
                    )

            except Exception:
                pass

    # --------------------------------------------------------
    # Create updater
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
                Filters.text
                & ~Filters.command,
                handle_message,
            )
        )

        print(
            "Starting Telegram polling..."
        )

        updater.start_polling(
            drop_pending_updates=True,
        )

        print(
            "Telegram bot polling started."
        )

        # Do NOT use updater.idle()
        #
        # Streamlit can throw:
        # ValueError: signal only works in main thread

        while True:

            time.sleep(3600)

    except Exception as e:

        print(
            "Telegram bot startup error:",
            repr(e)
        )


def start_bot_thread():

    global BOT_THREAD

    # --------------------------------------------------------
    # Prevent duplicate thread in current Python process
    # --------------------------------------------------------

    if globals().get(
        "_BOT_STARTED",
        False,
    ):

        print(
            "Telegram bot already started."
        )

        return

    # --------------------------------------------------------
    # Process-wide file lock
    # --------------------------------------------------------

    if not acquire_bot_lock():

        print(
            "Not starting another Telegram bot."
        )

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
        "Telegram bot thread started."
    )


# ============================================================
# INITIALIZATION
# ============================================================

@st.cache_resource(
    show_spinner=False
)
def initialize_spma():

    print(
        "\n\n"
        "========================================"
    )

    print(
        "       SPMA INITIALIZATION"
    )

    print(
        "========================================"
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

    setup_spotdl()

    # --------------------------------------------------------
    # FFmpeg
    # --------------------------------------------------------

    ffmpeg_ok = setup_ffmpeg()

    # --------------------------------------------------------
    # Deno
    # --------------------------------------------------------

    deno_ok = setup_deno()

    # --------------------------------------------------------
    # YouTube test
    # --------------------------------------------------------

    youtube_ok = test_youtube()

    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------

    start_bot_thread()

    return {
        "ffmpeg": ffmpeg_ok,
        "deno": deno_ok,
        "youtube": youtube_ok,
        "spotdl": SPOTDL_CMD.exists(),
    }


# ============================================================
# STREAMLIT UI
# ============================================================

st.set_page_config(
    page_title="SPMA",
    page_icon="🎵",
    layout="centered",
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


# ============================================================
# INITIALIZE
# ============================================================

try:

    status = initialize_spma()

    st.success(
        "SPMA initialization completed."
    )

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    col1, col2 = st.columns(2)

    with col1:

        st.write(
            "spotDL:",
            "✅"
            if status["spotdl"]
            else "❌"
        )

        st.write(
            "FFmpeg:",
            "✅"
            if status["ffmpeg"]
            else "❌"
        )

    with col2:

        st.write(
            "Deno:",
            "✅"
            if status["deno"]
            else "⚠️"
        )

        st.write(
            "YouTube:",
            "✅"
            if status["youtube"]
            else "❌"
        )

except Exception as e:

    st.error(
        "Initialization failed."
    )

    st.exception(e)
