from __future__ import annotations

APP_NAME = "IR/Raman Phase Finder"
APP_VERSION = "1.0"
AUTHOR = "Artem B. Kuznetsov"
INSTITUTE = "Institute of Geology and Mineralogy SB RAS"
COPYRIGHT = f"© 2026 {AUTHOR}"
LICENSE = "MIT License"
GITHUB_URL = "https://github.com/ABKuznetsov/IR_Raman_analysis_Toolkit"

APP_DESCRIPTION = (
    "Open-source software for preliminary phase identification from Raman and "
    "FTIR vibrational spectra using open spectral databases, user reference "
    "libraries, peak/line indexing, and spectrum matching."
)


def about_plain_text() -> str:
    return (
        f"{APP_NAME}\n"
        f"Version {APP_VERSION}\n\n"
        f"{APP_DESCRIPTION}\n\n"
        f"{COPYRIGHT}\n"
        f"{INSTITUTE}\n\n"
        f"{LICENSE}\n"
        f"{GITHUB_URL}"
    )


def about_html() -> str:
    return f"""
    <div style="font-family: sans-serif;">
      <h2 style="margin-bottom: 4px;">{APP_NAME}</h2>
      <p style="margin-top: 0;"><b>Version {APP_VERSION}</b></p>
      <p>{APP_DESCRIPTION}</p>
      <p>
        {COPYRIGHT}<br>
        {INSTITUTE}
      </p>
      <p><b>{LICENSE}</b></p>
      <p>
        GitHub:<br>
        <a href="{GITHUB_URL}">{GITHUB_URL}</a>
      </p>
    </div>
    """
