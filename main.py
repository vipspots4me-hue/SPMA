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

    # --------------------------------------------------------
    # Upgrade pip
    # --------------------------------------------------------

    print("\n========== PIP SETUP ==========")

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
            "Failed to upgrade pip/setuptools."
        )

    # --------------------------------------------------------
    # Install spotDL FIRST
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
    # IMPORTANT:
    # Install the required yt-dlp AFTER spotDL.
    #
    # spotDL installation can upgrade yt-dlp.
    # Therefore this MUST be the final yt-dlp installation.
    # --------------------------------------------------------

    print("\n========== YT-DLP PIN ==========")

    result = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "install",
            "--force-reinstall",
            "yt-dlp==2026.06.09",
            "yt-dlp-ejs==0.8.0",
        ],
        timeout=300,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Failed to install/pin yt-dlp."
        )

    # --------------------------------------------------------
    # Verify spotDL
    # --------------------------------------------------------

    print("\n========== SPOTDL VERSION ==========")

    result = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "spotdl",
            "--version",
        ],
        timeout=30,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "spotDL verification failed."
        )

    # --------------------------------------------------------
    # Verify yt-dlp
    # --------------------------------------------------------

    print("\n========== YT-DLP VERSION ==========")

    result = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "yt_dlp",
            "--version",
        ],
        timeout=30,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "yt-dlp verification failed."
        )

    # --------------------------------------------------------
    # Verify yt-dlp-ejs
    # --------------------------------------------------------

    print("\n========== YT-DLP EJS ==========")

    result = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "show",
            "yt-dlp-ejs",
        ],
        timeout=30,
    )

    print("\nspotDL isolated environment ready.")
