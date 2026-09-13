import os
import sys
import time
import fcntl
import shutil
import logging
import subprocess
import threading
import urllib.request
import urllib.error
import zipfile
import tarfile
from pathlib import Path

import streamlit as st


# ============================================================
# SPMA - FULL SELF-CONTAINED STREAMLIT VERSION
# ============================================================

BASE_DIR = Path("/mount/src/spma")


# ============================================================
# FIXED VERSIONS
# ============================================================

SPOTDL_VERSION = "4.4.11"
YTDLP_VERSION = "2026.06.09"
YTDLP_EJS_VERSION = "0.8.0"
BGUTIL_VERSION = "2.0.0"
DENO_VERSION = "2.9.6"
FFMPEG_VERSION = "7.0.2"


SPOTDL_GIT = (
    "git+https://github.com/TzurSoffer/"
    "spotify-downloader"
    "@29cb0b0669d5c107331b0912fdef73967b47493e"
)


# ============================================================
# LOCAL PATHS
# ============================================================

BIN_DIR = BASE_DIR / ".bin"

SPOTDL_VENV = BASE_DIR / ".spotdl_venv"

SPOTDL_PYTHON = (
    SPOTDL_VENV / "bin" / "python"
)

SPOTDL_BIN = (
    SPOTDL_VENV / "bin" / "spotdl"
)

BGUTIL_DIR = (
    BASE_DIR / ".bgutil-ytdlp-pot-provider"
)

BGUTIL_SERVER_DIR = (
    BGUTIL_DIR / "server"
)

BGUTIL_NODE_MODULES = (
    BGUTIL_SERVER_DIR / "node_modules"
)

BGUTIL_MAIN_TS = (
    BGUTIL_SERVER_DIR / "src" / "main.ts"
)

DOWNLOAD_DIR = (
    BASE_DIR / "downloads"
)

CACHE_DIR = (
    BASE_DIR / ".spma_cache"
)

YOUTUBE_TEST_DIR = (
    BASE_DIR / ".youtube_test"
)

DENO_BIN = (
    BIN_DIR / "deno"
)

FFMPEG_BIN = (
    BIN_DIR / "ffmpeg"
)

FFPROBE_BIN = (
    BIN_DIR / "ffprobe"
)


# ============================================================
# BGUTIL SERVER
# ============================================================

BGUTIL_HOST = "127.0.0.1"

BGUTIL_PORT = 4416

BGUTIL_URL = (
    f"http://{BGUTIL_HOST}:{BGUTIL_PORT}"
)


# ============================================================
# TELEGRAM LOCK
# ============================================================

BOT_LOCK_FILE = (
    "/tmp/spma_telegram_bot.lock"
)

BOT_LOCK_FD = None

TELEGRAM_UPDATER = None

BGUTIL_PROCESS = None


# ============================================================
# YOUTUBE / YT-DLP
# ============================================================

YOUTUBE_CLIENT_ARGS = (
    "youtube:player_client=mweb;fetch_pot=always"
)

YOUTUBE_POT_ARGS = (
    "youtubepot-bgutilhttp:"
    f"base_url={BGUTIL_URL}"
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s - "
        "%(levelname)s - "
        "%(message)s"
    ),
)

logger = logging.getLogger("SPMA")


# ============================================================
# STREAMLIT SECRETS
# ============================================================

def get_secret(
    name: str,
    default: str = "",
) -> str:

    try:

        value = st.secrets.get(
            name,
            default,
        )

        if value is None:
            return default

        return str(value).strip()

    except Exception:

        return os.environ.get(
            name,
            default,
        ).strip()


TELEGRAM_TOKEN = get_secret(
    "TELEGRAM_TOKEN"
)

SPOTIFY_CLIENT_ID = get_secret(
    "SPOTIFY_CLIENT_ID"
)

SPOTIFY_CLIENT_SECRET = get_secret(
    "SPOTIFY_CLIENT_SECRET"
)


# ============================================================
# DIRECTORY SETUP
# ============================================================

def create_directories():

    directories = [
        BASE_DIR,
        BIN_DIR,
        DOWNLOAD_DIR,
        CACHE_DIR,
        YOUTUBE_TEST_DIR,
    ]

    for directory in directories:

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )


# ============================================================
# ENVIRONMENT
# ============================================================

def configure_environment():

    create_directories()

    paths = [
        str(BIN_DIR),
        str(SPOTDL_VENV / "bin"),
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ]

    current_path = os.environ.get(
        "PATH",
        "",
    )

    for item in current_path.split(":"):

        if item and item not in paths:
            paths.append(item)

    os.environ["PATH"] = ":".join(paths)

    # --------------------------------------------------------
    # Spotify
    # --------------------------------------------------------

    if SPOTIFY_CLIENT_ID:

        os.environ[
            "SPOTIPY_CLIENT_ID"
        ] = SPOTIFY_CLIENT_ID

        os.environ[
            "SPOTIFY_CLIENT_ID"
        ] = SPOTIFY_CLIENT_ID

    if SPOTIFY_CLIENT_SECRET:

        os.environ[
            "SPOTIPY_CLIENT_SECRET"
        ] = SPOTIFY_CLIENT_SECRET

        os.environ[
            "SPOTIFY_CLIENT_SECRET"
        ] = SPOTIFY_CLIENT_SECRET

    # --------------------------------------------------------
    # FFmpeg
    # --------------------------------------------------------

    if FFMPEG_BIN.exists():

        os.environ[
            "FFMPEG_BINARY"
        ] = str(FFMPEG_BIN)

    if FFPROBE_BIN.exists():

        os.environ[
            "FFPROBE_BINARY"
        ] = str(FFPROBE_BIN)

    # --------------------------------------------------------
    # Deno
    # --------------------------------------------------------

    if DENO_BIN.exists():

        os.environ[
            "DENO_BINARY"
        ] = str(DENO_BIN)

    logger.info(
        "Environment configured."
    )


# ============================================================
# COMMAND RUNNER
# ============================================================

def run_command(
    command,
    timeout=None,
    cwd=None,
    env=None,
):

    logger.info(
        "Running: %s",
        " ".join(
            map(str, command)
        ),
    )

    try:

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )

        if result.stdout:

            output = result.stdout

            if len(output) > 20000:

                output = output[-20000:]

            logger.info(
                "\n%s",
                output,
            )

        return result

    except subprocess.TimeoutExpired:

        logger.error(
            "Command timed out."
        )

        return None

    except Exception as exc:

        logger.exception(
            "Command failed: %s",
            exc,
        )

        return None


# ============================================================
# DOWNLOAD FILE
# ============================================================

def download_file(
    url: str,
    destination: Path,
    timeout: int = 600,
):

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_file = Path(
        str(destination) + ".tmp"
    )

    if temp_file.exists():

        try:
            temp_file.unlink()
        except Exception:
            pass

    logger.info(
        "Downloading: %s",
        url,
    )

    try:

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "(X11; Linux x86_64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/140.0.0.0 "
                    "Safari/537.36"
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:

            total = response.headers.get(
                "Content-Length"
            )

            if total:
                total = int(total)

            downloaded = 0

            with open(
                temp_file,
                "wb",
            ) as output:

                while True:

                    chunk = response.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    output.write(chunk)

                    downloaded += len(chunk)

                    if total:

                        percent = (
                            downloaded
                            * 100
                            / total
                        )

                        logger.info(
                            "Download: %.1f%%",
                            percent,
                        )

        temp_file.replace(
            destination
        )

        logger.info(
            "Download complete: %s",
            destination,
        )

        return True

    except Exception as exc:

        logger.warning(
            "Python download failed: %s",
            exc,
        )

        try:

            if temp_file.exists():
                temp_file.unlink()

        except Exception:
            pass

    # --------------------------------------------------------
    # Fallback to curl
    # --------------------------------------------------------

    logger.info(
        "Trying curl fallback..."
    )

    result = run_command(
        [
            "curl",
            "-L",
            "--fail",
            "--retry",
            "3",
            "--retry-delay",
            "2",
            "--connect-timeout",
            "20",
            "--max-time",
            str(timeout),
            "-A",
            (
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/140.0.0.0 "
                "Safari/537.36"
            ),
            "-o",
            str(temp_file),
            url,
        ],
        timeout=timeout + 60,
    )

    if (
        result
        and result.returncode == 0
        and temp_file.exists()
        and temp_file.stat().st_size > 0
    ):

        try:

            temp_file.replace(
                destination
            )

            logger.info(
                "Download complete with curl: %s",
                destination,
            )

            return True

        except Exception as exc:

            logger.exception(
                "Could not move downloaded file: %s",
                exc,
            )

    try:

        if temp_file.exists():
            temp_file.unlink()

    except Exception:
        pass

    logger.error(
        "Download failed completely: %s",
        url,
    )

    return False


# ============================================================
# INSTALL DENO
# ============================================================

def install_deno():

    if (
        DENO_BIN.exists()
        and os.access(
            DENO_BIN,
            os.X_OK,
        )
    ):

        result = run_command(
            [
                str(DENO_BIN),
                "--version",
            ],
            timeout=30,
        )

        if (
            result
            and result.returncode == 0
        ):

            logger.info(
                "Deno already installed."
            )

            return True

    logger.info(
        "Installing Deno %s...",
        DENO_VERSION,
    )

    archive = (
        CACHE_DIR
        / f"deno-{DENO_VERSION}.zip"
    )

    # --------------------------------------------------------
    # First source: GitHub Release
    # This avoids the 403 encountered from dl.deno.land.
    # --------------------------------------------------------

    urls = [
        (
            "https://github.com/denoland/deno/"
            "releases/download/"
            f"v{DENO_VERSION}/"
            "deno-x86_64-unknown-linux-gnu.zip"
        ),
        (
            "https://dl.deno.land/release/"
            f"v{DENO_VERSION}/"
            "deno-x86_64-unknown-linux-gnu.zip"
        ),
    ]

    downloaded = False

    for url in urls:

        logger.info(
            "Trying Deno source: %s",
            url,
        )

        if download_file(
            url,
            archive,
        ):

            downloaded = True
            break

    if not downloaded:

        logger.error(
            "Unable to download Deno %s.",
            DENO_VERSION,
        )

        return False

    extract_dir = (
        CACHE_DIR
        / f"deno-{DENO_VERSION}"
    )

    extract_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:

        extracted = (
            extract_dir / "deno"
        )

        if not extracted.exists():

            with zipfile.ZipFile(
                archive,
                "r",
            ) as zf:

                zf.extractall(
                    extract_dir
                )

        if not extracted.exists():

            logger.error(
                "Deno binary not found."
            )

            return False

        shutil.copy2(
            extracted,
            DENO_BIN,
        )

        os.chmod(
            DENO_BIN,
            0o755,
        )

    except Exception as exc:

        logger.exception(
            "Deno extraction failed: %s",
            exc,
        )

        return False

    result = run_command(
        [
            str(DENO_BIN),
            "--version",
        ],
        timeout=30,
    )

    if (
        result
        and result.returncode == 0
    ):

        logger.info(
            "Deno %s: OK",
            DENO_VERSION,
        )

        return True

    logger.error(
        "Deno verification failed."
    )

    return False


# ============================================================
# INSTALL FFMPEG
# ============================================================

def install_ffmpeg():

    if (
        FFMPEG_BIN.exists()
        and FFPROBE_BIN.exists()
        and os.access(
            FFMPEG_BIN,
            os.X_OK,
        )
    ):

        result = run_command(
            [
                str(FFMPEG_BIN),
                "-version",
            ],
            timeout=30,
        )

        if (
            result
            and result.returncode == 0
        ):

            logger.info(
                "FFmpeg already installed."
            )

            return True

    logger.info(
        "Installing FFmpeg %s...",
        FFMPEG_VERSION,
    )

    url = (
        "https://www.johnvansickle.com/"
        "ffmpeg/releases/"
        "ffmpeg-7.0.2-amd64-static.tar.xz"
    )

    archive = (
        CACHE_DIR
        / "ffmpeg-7.0.2-amd64-static.tar.xz"
    )

    if not archive.exists():

        if not download_file(
            url,
            archive,
        ):
            return False

    extract_dir = (
        CACHE_DIR
        / "ffmpeg-7.0.2-amd64-static"
    )

    extract_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:

        extracted_ffmpeg = (
            extract_dir / "ffmpeg"
        )

        extracted_ffprobe = (
            extract_dir / "ffprobe"
        )

        if (
            not extracted_ffmpeg.exists()
            or not extracted_ffprobe.exists()
        ):

            with tarfile.open(
                archive,
                "r:xz",
            ) as tar:

                tar.extractall(
                    CACHE_DIR
                )

        if not extracted_ffmpeg.exists():

            logger.error(
                "FFmpeg binary not found."
            )

            return False

        if not extracted_ffprobe.exists():

            logger.error(
                "FFprobe binary not found."
            )

            return False

        shutil.copy2(
            extracted_ffmpeg,
            FFMPEG_BIN,
        )

        shutil.copy2(
            extracted_ffprobe,
            FFPROBE_BIN,
        )

        os.chmod(
            FFMPEG_BIN,
            0o755,
        )

        os.chmod(
            FFPROBE_BIN,
            0o755,
        )

    except Exception as exc:

        logger.exception(
            "FFmpeg extraction failed: %s",
            exc,
        )

        return False

    result = run_command(
        [
            str(FFMPEG_BIN),
            "-version",
        ],
        timeout=30,
    )

    if (
        result
        and result.returncode == 0
    ):

        logger.info(
            "FFmpeg %s: OK",
            FFMPEG_VERSION,
        )

        return True

    logger.error(
        "FFmpeg verification failed."
    )

    return False


# ============================================================
# INSTALL SPOTDL
# ============================================================

def install_spotdl():

    if not SPOTDL_PYTHON.exists():

        logger.info(
            "Creating spotDL virtual environment..."
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

        if (
            result is None
            or result.returncode != 0
        ):

            logger.error(
                "Unable to create spotDL venv."
            )

            return False

    result = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "wheel",
            "setuptools",
        ],
        timeout=300,
    )

    if (
        result is None
        or result.returncode != 0
    ):

        return False

    logger.info(
        "Installing spotDL %s...",
        SPOTDL_VERSION,
    )

    result = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "install",
            "--upgrade",
            SPOTDL_GIT,
        ],
        timeout=900,
    )

    if (
        result is None
        or result.returncode != 0
    ):

        logger.error(
            "spotDL installation failed."
        )

        return False

    logger.info(
        "Pinning yt-dlp %s...",
        YTDLP_VERSION,
    )

    result = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "install",
            "--upgrade",
            f"yt-dlp=={YTDLP_VERSION}",
        ],
        timeout=300,
    )

    if (
        result is None
        or result.returncode != 0
    ):

        return False

    logger.info(
        "Installing yt-dlp-ejs %s...",
        YTDLP_EJS_VERSION,
    )

    result = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "install",
            "--upgrade",
            f"yt-dlp-ejs=={YTDLP_EJS_VERSION}",
        ],
        timeout=300,
    )

    if (
        result is None
        or result.returncode != 0
    ):

        return False

    logger.info(
        "Installing bgutil plugin %s...",
        BGUTIL_VERSION,
    )

    result = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "install",
            "--upgrade",
            (
                "bgutil-ytdlp-pot-provider=="
                f"{BGUTIL_VERSION}"
            ),
        ],
        timeout=300,
    )

    if (
        result is None
        or result.returncode != 0
    ):

        logger.error(
            "bgutil plugin installation failed."
        )

        return False

    result = run_command(
        [
            str(SPOTDL_BIN),
            "--version",
        ],
        timeout=30,
    )

    if (
        result
        and result.returncode == 0
    ):

        logger.info(
            "spotDL %s: OK",
            SPOTDL_VERSION,
        )

    else:

        logger.error(
            "spotDL verification failed."
        )

        return False

    return True


# ============================================================
# INSTALL BGUTIL SOURCE
# ============================================================

def install_bgutil():

    if (
        BGUTIL_SERVER_DIR.exists()
        and BGUTIL_MAIN_TS.exists()
    ):

        logger.info(
            "bgutil source already exists."
        )

        return True

    if BGUTIL_DIR.exists():

        logger.warning(
            "Incomplete bgutil directory found. "
            "Removing it..."
        )

        try:

            shutil.rmtree(
                BGUTIL_DIR
            )

        except Exception as exc:

            logger.exception(
                "Unable to remove old bgutil: %s",
                exc,
            )

            return False

    logger.info(
        "Cloning bgutil %s...",
        BGUTIL_VERSION,
    )

    result = run_command(
        [
            "git",
            "clone",
            "--single-branch",
            "--branch",
            BGUTIL_VERSION,
            (
                "https://github.com/"
                "Brainicism/"
                "bgutil-ytdlp-pot-provider.git"
            ),
            str(BGUTIL_DIR),
        ],
        timeout=300,
    )

    if (
        result is None
        or result.returncode != 0
    ):

        logger.error(
            "bgutil clone failed."
        )

        return False

    if not BGUTIL_MAIN_TS.exists():

        logger.error(
            "bgutil main.ts not found: %s",
            BGUTIL_MAIN_TS,
        )

        return False

    logger.info(
        "bgutil source: OK"
    )

    return True


# ============================================================
# INSTALL BGUTIL SERVER DEPENDENCIES
# ============================================================

def install_bgutil_dependencies():

    if not BGUTIL_SERVER_DIR.exists():

        logger.error(
            "bgutil server directory missing."
        )

        return False

    if (
        BGUTIL_NODE_MODULES.exists()
        and (
            BGUTIL_NODE_MODULES
            / ".deno"
        ).exists()
    ):

        logger.info(
            "bgutil dependencies already installed."
        )

        return True

    logger.info(
        "Installing bgutil dependencies..."
    )

    result = run_command(
        [
            str(DENO_BIN),
            "install",
            "--allow-scripts=npm:canvas",
            "--frozen",
        ],
        timeout=900,
        cwd=str(BGUTIL_SERVER_DIR),
    )

    if (
        result is None
        or result.returncode != 0
    ):

        logger.error(
            "bgutil dependency installation failed."
        )

        return False

    if not BGUTIL_NODE_MODULES.exists():

        logger.error(
            "bgutil node_modules was not created."
        )

        return False

    logger.info(
        "bgutil dependencies: OK"
    )

    return True


# ============================================================
# BGUTIL SERVER CHECK
# ============================================================

def is_bgutil_server_running():

    try:

        with urllib.request.urlopen(
            BGUTIL_URL + "/ping",
            timeout=3,
        ) as response:

            if response.status == 200:
                return True

    except urllib.error.HTTPError as exc:

        if exc.code == 200:
            return True

    except Exception:
        pass

    return False


# ============================================================
# START BGUTIL SERVER
# ============================================================

def start_bgutil_server():

    global BGUTIL_PROCESS

    if is_bgutil_server_running():

        logger.info(
            "bgutil PO Token server: already running."
        )

        return True

    if not BGUTIL_MAIN_TS.exists():

        logger.error(
            "bgutil main.ts missing: %s",
            BGUTIL_MAIN_TS,
        )

        return False

    if not BGUTIL_NODE_MODULES.exists():

        logger.error(
            "bgutil node_modules missing: %s",
            BGUTIL_NODE_MODULES,
        )

        return False

    logger.info(
        "Starting bgutil PO Token server..."
    )

    command = [
        str(DENO_BIN),
        "run",
        "--allow-env",
        "--allow-net",
        "--allow-ffi=.",
        "--allow-read=.",
        "../src/main.ts",
        "--port",
        str(BGUTIL_PORT),
    ]

    try:

        BGUTIL_PROCESS = subprocess.Popen(
            command,
            cwd=str(BGUTIL_NODE_MODULES),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=os.environ.copy(),
            bufsize=1,
        )

    except Exception as exc:

        logger.exception(
            "Could not start bgutil: %s",
            exc,
        )

        return False

    def bgutil_logger():

        try:

            for line in BGUTIL_PROCESS.stdout:

                line = line.rstrip()

                if line:

                    logger.info(
                        "[bgutil] %s",
                        line,
                    )

        except Exception:
            pass

    threading.Thread(
        target=bgutil_logger,
        daemon=True,
    ).start()

    for _ in range(60):

        if is_bgutil_server_running():

            logger.info(
                "bgutil PO Token server: OK"
            )

            return True

        if (
            BGUTIL_PROCESS.poll()
            is not None
        ):

            logger.error(
                "bgutil process exited with code %s",
                BGUTIL_PROCESS.returncode,
            )

            return False

        time.sleep(1)

    logger.error(
        "bgutil server did not become ready."
    )

    return False


# ============================================================
# VERIFY YT-DLP
# ============================================================

def check_ytdlp():

    result = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "yt_dlp",
            "--version",
        ],
        timeout=30,
    )

    if (
        result
        and result.returncode == 0
    ):

        logger.info(
            "yt-dlp %s: OK",
            YTDLP_VERSION,
        )

        return True

    logger.error(
        "yt-dlp verification failed."
    )

    return False


# ============================================================
# VERIFY BGUTIL PLUGIN
# ============================================================

def check_bgutil_plugin():

    test_url = (
        "https://www.youtube.com/watch"
        "?v=0loPj-nIG7c"
    )

    logger.info(
        "Checking yt-dlp bgutil plugin..."
    )

    command = [
        str(SPOTDL_PYTHON),
        "-m",
        "yt_dlp",

        "--no-update",

        "--no-playlist",

        "--socket-timeout",
        "20",

        "--extractor-retries",
        "2",

        "--extractor-args",
        YOUTUBE_CLIENT_ARGS,

        "--extractor-args",
        YOUTUBE_POT_ARGS,

        "--js-runtimes",
        f"deno:{DENO_BIN}",

        "--print",
        "title",

        "--skip-download",

        "--verbose",

        test_url,
    ]

    result = run_command(
        command,
        timeout=180,
    )

    if (
        result
        and result.returncode == 0
    ):

        logger.info(
            "YouTube mweb + bgutil test: SUCCESS"
        )

        return True

    logger.warning(
        "YouTube mweb + bgutil test: FAILED"
    )

    return False


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

        logger.info(
            "Telegram bot lock acquired."
        )

        return True

    except BlockingIOError:

        logger.warning(
            "Telegram bot already running."
        )

        return False

    except Exception as exc:

        logger.exception(
            "Telegram lock error: %s",
            exc,
        )

        return False


# ============================================================
# TELEGRAM / START
# ============================================================

def telegram_start(
    update,
    context,
):

    try:

        update.message.reply_text(
            "سلام 👋\n\n"
            "لینک آهنگ Spotify را بفرست "
            "تا آن را به MP3 با کیفیت "
            "320kbps تبدیل و ارسال کنم."
        )

    except Exception:

        logger.exception(
            "Telegram /start error."
        )


# ============================================================
# TELEGRAM / HELP
# ============================================================

def telegram_help(
    update,
    context,
):

    try:

        update.message.reply_text(
            "لینک آهنگ Spotify را ارسال کن."
        )

    except Exception:

        logger.exception(
            "Telegram /help error."
        )


# ============================================================
# FIND AUDIO FILE
# ============================================================

def find_audio_file(
    output_dir: Path,
):

    extensions = {
        ".mp3",
        ".m4a",
        ".opus",
        ".webm",
        ".wav",
        ".flac",
        ".ogg",
    }

    files = []

    if not output_dir.exists():
        return None

    for path in output_dir.rglob("*"):

        if not path.is_file():
            continue

        if path.suffix.lower() not in extensions:
            continue

        try:

            if path.stat().st_size <= 0:
                continue

        except Exception:

            continue

        files.append(path)

    if not files:
        return None

    files.sort(
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    return files[0]


# ============================================================
# DOWNLOAD SONG
# ============================================================

def download_song(
    spotify_url: str,
    output_dir: Path,
):

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Clean old files
    # --------------------------------------------------------

    for item in output_dir.iterdir():

        try:

            if item.is_file():
                item.unlink()

            elif item.is_dir():
                shutil.rmtree(item)

        except Exception:
            pass

    # --------------------------------------------------------
    # yt-dlp arguments
    # --------------------------------------------------------

    yt_dlp_args = (
        "--no-update "
        "--socket-timeout 20 "
        "--retries 2 "
        "--fragment-retries 2 "
        "--extractor-retries 2 "
        "--retry-sleep 1 "
        f'--js-runtimes "deno:{DENO_BIN}" '
        f'--extractor-args "{YOUTUBE_CLIENT_ARGS}" '
        f'--extractor-args "{YOUTUBE_POT_ARGS}"'
    )

    # --------------------------------------------------------
    # Output template
    # --------------------------------------------------------

    output_template = (
        str(output_dir)
        + "/{artist} - {title}.{output-ext}"
    )

    # --------------------------------------------------------
    # spotDL command
    # --------------------------------------------------------

    command = [
        str(SPOTDL_BIN),

        "--output",
        output_template,

        "--format",
        "mp3",

        "--bitrate",
        "320k",

        "--threads",
        "4",

        "--no-cache",

        # IMPORTANT:
        # spotDL 4.4.11 requires a value.
        "--overwrite",
        "force",

        "--yt-dlp-args",
        yt_dlp_args,

        spotify_url,
    ]

    logger.info(
        "Starting spotDL download..."
    )

    logger.info(
        "Spotify URL: %s",
        spotify_url,
    )

    result = run_command(
        command,
        timeout=600,
    )

    if result is None:

        logger.error(
            "spotDL process returned no result."
        )

        return None

    if result.returncode != 0:

        logger.error(
            "spotDL exited with code %s",
            result.returncode,
        )

    audio_file = find_audio_file(
        output_dir
    )

    if audio_file is None:

        logger.warning(
            "No audio file found after download."
        )

        return None

    logger.info(
        "Audio file found: %s",
        audio_file,
    )

    logger.info(
        "Audio size: %d bytes",
        audio_file.stat().st_size,
    )

    return audio_file


# ============================================================
# TELEGRAM MESSAGE
# ============================================================

def telegram_message(
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
        "open.spotify.com/track/"
        not in text
    ):

        try:

            message.reply_text(
                "لطفاً لینک آهنگ Spotify را ارسال کن."
            )

        except Exception:
            pass

        return

    chat_id = (
        message.chat_id
    )

    message_id = (
        message.message_id
    )

    logger.info(
        "New Spotify request: "
        "chat=%s message=%s",
        chat_id,
        message_id,
    )

    status_message = None

    try:

        status_message = (
            message.reply_text(
                "⏳ در حال دانلود آهنگ..."
            )
        )

    except Exception:
        pass

    output_dir = (
        DOWNLOAD_DIR
        / str(chat_id)
        / str(message_id)
    )

    try:

        audio_file = download_song(
            text,
            output_dir,
        )

        if audio_file is None:

            if status_message:

                try:

                    status_message.edit_text(
                        "❌ دانلود انجام نشد یا فایل صوتی پیدا نشد."
                    )

                except Exception:
                    pass

            return

        if status_message:

            try:

                status_message.edit_text(
                    "📤 دانلود تمام شد؛ در حال ارسال..."
                )

            except Exception:
                pass

        logger.info(
            "Sending audio to Telegram..."
        )

        with open(
            audio_file,
            "rb",
        ) as audio:

            message.reply_audio(
                audio=audio,
                filename=audio_file.name,
                title=audio_file.stem,
                read_timeout=180,
                write_timeout=180,
                connect_timeout=60,
            )

        logger.info(
            "Audio sent successfully."
        )

        if status_message:

            try:
                status_message.delete()
            except Exception:
                pass

        try:

            shutil.rmtree(
                output_dir
            )

        except Exception:
            pass

    except Exception as exc:

        logger.exception(
            "Telegram processing error: %s",
            exc,
        )

        if status_message:

            try:

                status_message.edit_text(
                    "❌ هنگام دانلود یا ارسال آهنگ خطایی رخ داد."
                )

            except Exception:
                pass


# ============================================================
# START TELEGRAM BOT
# ============================================================

def start_telegram_bot():

    global TELEGRAM_UPDATER

    if not TELEGRAM_TOKEN:

        logger.warning(
            "TELEGRAM_TOKEN missing. "
            "Add TELEGRAM_TOKEN to Streamlit Secrets."
        )

        return None

    if not acquire_bot_lock():
        return None

    try:

        from telegram.ext import (
            Updater,
            CommandHandler,
            MessageHandler,
            Filters,
        )

    except Exception as exc:

        logger.exception(
            "python-telegram-bot import failed: %s",
            exc,
        )

        return None

    try:

        updater = Updater(
            token=TELEGRAM_TOKEN,
            use_context=True,
        )

        dispatcher = (
            updater.dispatcher
        )

        dispatcher.add_handler(
            CommandHandler(
                "start",
                telegram_start,
            )
        )

        dispatcher.add_handler(
            CommandHandler(
                "help",
                telegram_help,
            )
        )

        dispatcher.add_handler(
            MessageHandler(
                Filters.text
                & ~Filters.command,
                telegram_message,
            )
        )

        updater.start_polling(
            drop_pending_updates=True,
        )

        TELEGRAM_UPDATER = updater

        logger.info(
            "Telegram bot started."
        )

        return updater

    except Exception as exc:

        logger.exception(
            "Unable to start Telegram bot: %s",
            exc,
        )

        return None


# ============================================================
# INITIALIZATION
# ============================================================

def initialize():

    logger.info(
        "========================================"
    )

    logger.info(
        "SPMA initialization started"
    )

    logger.info(
        "========================================"
    )

    # --------------------------------------------------------
    # 1. Environment
    # --------------------------------------------------------

    configure_environment()

    # --------------------------------------------------------
    # 2. Deno
    # --------------------------------------------------------

    deno_ok = install_deno()

    if not deno_ok:

        logger.error(
            "Deno installation FAILED."
        )

    # --------------------------------------------------------
    # 3. FFmpeg
    # --------------------------------------------------------

    ffmpeg_ok = install_ffmpeg()

    if not ffmpeg_ok:

        logger.error(
            "FFmpeg installation FAILED."
        )

    # --------------------------------------------------------
    # 4. spotDL
    # --------------------------------------------------------

    spotdl_ok = install_spotdl()

    if not spotdl_ok:

        logger.error(
            "spotDL installation FAILED."
        )

    # --------------------------------------------------------
    # 5. bgutil source
    # --------------------------------------------------------

    bgutil_source_ok = (
        install_bgutil()
    )

    if not bgutil_source_ok:

        logger.error(
            "bgutil source installation FAILED."
        )

    # --------------------------------------------------------
    # 6. bgutil dependencies
    # --------------------------------------------------------

    bgutil_dependencies_ok = False

    if bgutil_source_ok and deno_ok:

        bgutil_dependencies_ok = (
            install_bgutil_dependencies()
        )

    # --------------------------------------------------------
    # 7. Refresh environment
    # --------------------------------------------------------

    configure_environment()

    # --------------------------------------------------------
    # 8. Component checks
    # --------------------------------------------------------

    if SPOTDL_BIN.exists():

        logger.info(
            "spotDL: OK"
        )

    else:

        logger.error(
            "spotDL: FAILED"
        )

    if SPOTDL_PYTHON.exists():

        logger.info(
            "spotDL Python: OK"
        )

    else:

        logger.error(
            "spotDL Python: FAILED"
        )

    if FFMPEG_BIN.exists():

        logger.info(
            "FFmpeg: OK"
        )

    else:

        logger.error(
            "FFmpeg: FAILED"
        )

    if DENO_BIN.exists():

        logger.info(
            "Deno: OK"
        )

    else:

        logger.error(
            "Deno: FAILED"
        )

    # --------------------------------------------------------
    # 9. yt-dlp
    # --------------------------------------------------------

    ytdlp_ok = False

    if SPOTDL_PYTHON.exists():

        ytdlp_ok = check_ytdlp()

    # --------------------------------------------------------
    # 10. bgutil server
    # --------------------------------------------------------

    bgutil_ok = False

    if (
        bgutil_source_ok
        and bgutil_dependencies_ok
        and deno_ok
    ):

        bgutil_ok = (
            start_bgutil_server()
        )

    if bgutil_ok:

        logger.info(
            "bgutil PO Token: OK"
        )

    else:

        logger.warning(
            "bgutil PO Token: FAILED"
        )

    # --------------------------------------------------------
    # 11. YouTube verification
    # --------------------------------------------------------

    if (
        ytdlp_ok
        and bgutil_ok
        and deno_ok
    ):

        check_bgutil_plugin()

    # --------------------------------------------------------
    # 12. Telegram
    # --------------------------------------------------------

    start_telegram_bot()

    # --------------------------------------------------------
    # Finished
    # ----------------------------
