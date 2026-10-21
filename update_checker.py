
import json
import threading
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import messagebox

GITHUB_API = (
    "https://api.github.com/repos/"
    "tarafery7-cell/KHDubbing/commits?per_page=1"
)

GITHUB_URL = (
    "https://github.com/tarafery7-cell/"
    "KHDubbing/commits"
)

STATE_DIR = Path.home() / "AppData" / "Local" / "KHDubbing"
STATE_FILE = STATE_DIR / "last_seen_commit.txt"


def get_latest_commit():
    request = urllib.request.Request(
        GITHUB_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "KH-Dubbing-Update-Checker"
        }
    )

    with urllib.request.urlopen(request, timeout=8) as response:
        data = json.loads(response.read().decode("utf-8"))

    if not isinstance(data, list) or not data:
        return None

    commit = data[0]

    return {
        "sha": commit["sha"],
        "message": commit["commit"]["message"],
        "url": commit.get("html_url", GITHUB_URL)
    }


def check_update(root):
    def worker():
        try:
            latest = get_latest_commit()

            if not latest:
                return

            STATE_DIR.mkdir(parents=True, exist_ok=True)

            # First run: save the current commit without showing an alert
            if not STATE_FILE.exists():
                STATE_FILE.write_text(
                    latest["sha"],
                    encoding="utf-8"
                )
                return

            previous_sha = STATE_FILE.read_text(
                encoding="utf-8"
            ).strip()

            if previous_sha == latest["sha"]:
                return

            STATE_FILE.write_text(
                latest["sha"],
                encoding="utf-8"
            )

            def show_popup():
                answer = messagebox.askyesno(
                    "KH Dubbing - Update",
                    "មានការកែប្រែថ្មីនៅលើ GitHub!\n\n"
                    f"ព័ត៌មាន៖\n{latest['message'][:800]}\n\n"
                    "តើអ្នកចង់មើលការកែប្រែថ្មីឥឡូវនេះទេ?",
                    parent=root
                )

                if answer:
                    webbrowser.open(latest["url"])

            root.after(0, show_popup)

        except Exception:
            # No internet or GitHub unavailable:
            # continue opening the application normally.
            pass

    threading.Thread(target=worker, daemon=True).start()
