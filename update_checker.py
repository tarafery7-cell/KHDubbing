
import json
import re
import threading
import urllib.request
import webbrowser
import tkinter as tk
from tkinter import messagebox

APP_VERSION = "1.0.0"

GITHUB_API = (
    "https://api.github.com/repos/"
    "tarafery7-cell/KHDubbing/releases/latest"
)

RELEASES_URL = (
    "https://github.com/tarafery7-cell/"
    "KHDubbing/releases/latest"
)


def version_tuple(version):
    # Supports versions such as v1.0.1 or 1.0.1
    numbers = re.findall(r"\d+", version)
    return tuple(map(int, numbers))


def check_update():
    try:
        request = urllib.request.Request(
            GITHUB_API,
            headers={"User-Agent": "KH-Dubbing-Update-Checker"}
        )

        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))

        latest_version = data.get("tag_name", "").strip()

        if not latest_version:
            return

        if version_tuple(latest_version) > version_tuple(APP_VERSION):
            download_url = data.get("html_url", RELEASES_URL)

            def show_popup():
                root = tk.Tk()
                root.withdraw()

                answer = messagebox.askyesno(
                    "KH Dubbing - Update",
                    f"មាន Update ថ្មី!\n\n"
                    f"Version បច្ចុប្បន្ន: {APP_VERSION}\n"
                    f"Version ថ្មី: {latest_version}\n\n"
                    "តើអ្នកចង់ចូលទៅទាញយកឥឡូវនេះទេ?"
                )

                if answer:
                    webbrowser.open(download_url)

                root.destroy()

            show_popup()

    except Exception:
        # No internet or GitHub unavailable:
        # continue opening the application normally.
        pass


def start_update_checker():
    threading.Thread(
        target=check_update,
        daemon=True
    ).start()
