# -*- coding: utf-8 -*-
"""
KH Dubbing (Khmer)  --  rebuilt source
Rebuilt from the decompiled main.pyc (v1.4.0 behaviour).

Features
  * Khmer / English TTS through edge-tts (voice presets, speed slider)
  * "Smart Pause" text clean-up + long-text chunking
  * SRT import and timeline-accurate audio (Auto Sync fits each line to its timecode)
  * Translate button: Gemini / OpenAI (context-aware, story summary + glossary, model list loaded from the API key)
    or free Google Translate (MyMemory fallback). SRT-aware (timecodes untouched)
  * Video display (auto-fit screen) + Dub video: Khmer voice mixed onto the loaded video with ffmpeg
  * Optional cloud voice clone (Hugging Face Gradio Space, e.g. Plachta/Seed-VC)
  * Update check via version.json on GitHub (non-blocking)

NOT included on purpose: the machine-ID license / trial / Firebase system and the
embedded Hugging Face tokens. See `LICENSE_HOOK` below if you want to re-add your own.
"""
import os
import sys
import io

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"
for _s in (sys.stdout, sys.stderr):
    if _s is not None:
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
try:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
except Exception:
    pass

import re
import json
import time
import shutil
import asyncio
import hashlib
import tempfile
import queue
import threading
import subprocess
import webbrowser
import urllib.request
import urllib.parse
import urllib.error
from concurrent.futures import ThreadPoolExecutor

import customtkinter as ctk
from tkinter import filedialog, messagebox
import edge_tts

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
APP_VERSION = "1"
GITHUB_REPO = ""
GITHUB_VERSION_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/version.json"
GITHUB_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
CONTACT_URL = ""

FONT_MAIN = "Khmer OS Battambang"
FONT_TITLE = FONT_MAIN
CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

DEFAULT_CLOUD_SERVER = "Plachta/Seed-VC"

# Auto-Sync limits. The old code could squeeze a line up to 2.8x (sounds rushed).
# Now the speed-up is capped (adjustable in the sidebar) and a line may run a little
# past its slot instead of being squeezed harder.
MAX_SPEEDUP = 1.25      # default max speed-up factor (sidebar slider: 1.00x - 2.00x)
SYNC_OVERRUN = 1.0      # seconds a line may run past its slot before it is cut
_SYNC_LOCK = threading.Lock()
SYNC_REPORT = {"late": 0, "total": 0}

KHMER_VOICE_PRESETS = {
    "🌸 កញ្ញា ស្រីមុំ (ធម្មជាតិ)": {
        "voice_id": "km-KH-SreymomNeural", "pitch": "+0Hz", "rate_offset": 0,
        "desc": "សំឡេងស្តង់ដារ ធម្មជាតិ ច្បាស់ល្អ និងងាយស្តាប់",
        "sample": "សួស្តី! ខ្ញុំជាស្រីមុំ សំឡេងបែបធម្មជាតិ និងច្បាស់ល្អ។"},
    "💖 កញ្ញា សុជាតា (ស្រទន់ មួយៗ)": {
        "voice_id": "km-KH-SreymomNeural", "pitch": "+0Hz", "rate_offset": -4,
        "desc": "សំឡេងស្រទន់ មួយៗ ផ្អែមពិរោះ ស័ក្តិសមសម្រាប់កំណាព្យ ឬសាររំជួលចិត្ត",
        "sample": "សួស្តី! ខ្ញុំជាសុជាតា សំឡេងស្រទន់ ផ្អែមពិរោះរណ្តំចិត្ត។"},
    "✨ កញ្ញា រស្មី (អានព័ត៌មាន)": {
        "voice_id": "km-KH-SreymomNeural", "pitch": "+0Hz", "rate_offset": 6,
        "desc": "សំឡេងច្បាស់ៗ រហ័សរហួន ស័ក្តិសមសម្រាប់ព័ត៌មានទាន់ហេតុការណ៍",
        "sample": "ជម្រាបសួរទស្សនិកជន! នេះជាព័ត៌មានទាន់ហេតុការណ៍ប្រចាំថ្ងៃ។"},
    "🎀 កញ្ញា ទេវី (រស់រវើក)": {
        "voice_id": "km-KH-SreymomNeural", "pitch": "+0Hz", "rate_offset": 3,
        "desc": "សំឡេងរស់រវើក រហ័ស គួរឱ្យទាក់ទាញ សម្រាប់វីដេអូកម្សាន្ត ឬ TikTok",
        "sample": "សួស្តីអ្នកទាំងអស់គ្នា! ថ្ងៃនេះខ្ញុំមានរឿងសប្បាយៗចែករំលែកជូន។"},
    "📖 អ្នកគ្រូ សោភា (និទានរឿង)": {
        "voice_id": "km-KH-SreymomNeural", "pitch": "+0Hz", "rate_offset": -7,
        "desc": "សំឡេងរម្យទម មួយៗ ស័ក្តិសមសម្រាប់រឿងនិទាន ធម៌អប់រំ និងមេរៀន",
        "sample": "កាលពីព្រេងនាយ មានកុមារម្នាក់រស់នៅជាមួយឪពុកម្តាយយ៉ាងមានសេចក្តីសុខ។"},
    "🎙️ លោក ពិសិដ្ឋ (ធម្មជាតិ)": {
        "voice_id": "km-KH-PisethNeural", "pitch": "+0Hz", "rate_offset": 0,
        "desc": "សំឡេងស្តង់ដារ ធម្មជាតិ ច្បាស់ល្អ និងងាយស្តាប់",
        "sample": "សួស្តី! ខ្ញុំជាពិសិដ្ឋ សំឡេងបែបធម្មជាតិ និងច្បាស់ល្អ។"},
    "🌟 លោក វឌ្ឍនា (អានព័ត៌មាន)": {
        "voice_id": "km-KH-PisethNeural", "pitch": "+0Hz", "rate_offset": 6,
        "desc": "សំឡេងរឹងមាំ ម៉ឺងម៉ាត់ ច្បាស់ៗ កម្រិតពិធីករព័ត៌មានទូរទស្សន៍",
        "sample": "សូមស្វាគមន៍មកកាន់ការផ្សាយព័ត៌មានជាតិ និងអន្តរជាតិ។"},
    "📻 លោក វិបុល (មួយៗ និទានរឿង)": {
        "voice_id": "km-KH-PisethNeural", "pitch": "+0Hz", "rate_offset": -5,
        "desc": "សំឡេងមួយៗ ធ្ងន់ច្បាស់ បែបភាពយន្ត និទានរឿង ឬរឿងព្រឺព្រួច",
        "sample": "នៅក្នុងរាត្រីដ៏ស្ងប់ស្ងាត់មួយ ដំណើររឿងដ៏អស្ចារ្យបានចាប់ផ្តើមឡើង។"},
    "⚡ យុវជន រិទ្ធី (ស្វាហាប់)": {
        "voice_id": "km-KH-PisethNeural", "pitch": "+0Hz", "rate_offset": 4,
        "desc": "សំឡេងយុវវ័យ ក្លៀវក្លា ស័ក្តិសមសម្រាប់បច្ចេកវិទ្យា និងកីឡា",
        "sample": "សួស្តីបងប្អូន! ថ្ងៃនេះយើងមកជួបគ្នាជាមួយគន្លឹះបច្ចេកវិទ្យាថ្មីៗ។"},
    "👴 លោកតា សុវណ្ណ (ចាស់ទុំ)": {
        "voice_id": "km-KH-PisethNeural", "pitch": "+0Hz", "rate_offset": -8,
        "desc": "សំឡេងចាស់ទុំ មានបទពិសោធន៍ សម្រាប់រឿងព្រេង ឬទស្សនវិជ្ជាជីវិត",
        "sample": "ចៅៗអើយ ការខិតខំរៀនសូត្រជាទ្រព្យដ៏មានតម្លៃបំផុតក្នុងឆាកជីវិត។"},
    "🇺🇸 Aria (English Female)": {
        "voice_id": "en-US-AriaNeural", "pitch": "+0Hz", "rate_offset": 0,
        "desc": "Clear and natural American English female voice",
        "sample": "Hello! I am Aria, a high quality English female voice."},
    "🇺🇸 Guy (English Male)": {
        "voice_id": "en-US-GuyNeural", "pitch": "+0Hz", "rate_offset": 0,
        "desc": "Deep and clear American English male voice",
        "sample": "Hello! I am Guy, a natural English male voice."},
}
DEFAULT_VOICE_CHOICE = "🌸 កញ្ញា ស្រីមុំ (ធម្មជាតិ)"

# --------------------------------------------------------------------------- #
# Design system (modern dark UI)  --  change colours here, everything follows
# --------------------------------------------------------------------------- #
T = {
    "bg": "#0A0E17",        # window background
    "sidebar": "#0E1420",   # sidebar background
    "surface": "#131A29",   # cards / editor
    "surface2": "#1B2436",  # inputs, secondary buttons
    "hover": "#26324A",
    "border": "#243049",
    "text": "#E8ECF4",
    "muted": "#8A96AD",
    "accent": "#6366F1", "accent_h": "#4F46E5",
    "ok": "#10B981", "ok_h": "#059669",
    "warn": "#F59E0B",
    "danger": "#F87171", "danger_bg": "#2B1820",
    "info": "#38BDF8",
}
FONT_CANDIDATES = ("Noto Sans Khmer", "Kantumruy Pro", "Khmer UI", "Leelawadee UI", "Khmer OS Battambang")


def load_bundled_fonts():
    """Register the fonts shipped in ./fonts for this process only (Windows). Nothing is installed."""
    if os.name != "nt":
        return
    try:
        import ctypes
        d = resource_path("fonts")
        if os.path.isdir(d):
            for fn in os.listdir(d):
                if fn.lower().endswith((".ttf", ".otf")):
                    ctypes.windll.gdi32.AddFontResourceExW(os.path.join(d, fn), 0x10, 0)   # FR_PRIVATE
    except Exception:
        pass


def pick_font():
    """Use the most modern Khmer-capable font that is installed (needs a Tk root)."""
    global FONT_MAIN, FONT_TITLE
    try:
        import tkinter.font as tkfont
        have = set(tkfont.families())
        for name in FONT_CANDIDATES:
            if name in have:
                FONT_MAIN = FONT_TITLE = name
                return
    except Exception:
        pass


def F(size=13, weight="normal"):
    return ctk.CTkFont(family=FONT_MAIN, size=size + 1, weight=weight)   # Khmer reads small -> +1


_BTN_STYLES = {
    "primary":   dict(fg_color=T["accent"], hover_color=T["accent_h"], text_color="#FFFFFF"),
    "success":   dict(fg_color=T["ok"], hover_color=T["ok_h"], text_color="#FFFFFF"),
    "secondary": dict(fg_color=T["surface2"], hover_color=T["hover"], text_color=T["text"],
                      border_width=1, border_color=T["border"]),
    "ghost":     dict(fg_color="transparent", hover_color=T["surface2"], text_color=T["muted"]),
    "danger":    dict(fg_color="transparent", hover_color=T["danger_bg"], text_color=T["danger"]),
}


def mkbtn(master, text, kind="secondary", size=12, weight="bold", **kw):
    opts = dict(_BTN_STYLES[kind])
    opts.update(kw)
    opts.setdefault("corner_radius", 10)
    opts.setdefault("height", 34)
    opts.setdefault("font", F(size, weight))
    return ctk.CTkButton(master, text=text, **opts)


def mkcard(master, **kw):
    opts = dict(fg_color=T["surface"], corner_radius=14, border_width=1, border_color=T["border"])
    opts.update(kw)
    return ctk.CTkFrame(master, **opts)


def section_title(master, text):
    return ctk.CTkLabel(master, text=text, font=F(11, "bold"), text_color=T["muted"], anchor="w")


def menu_style(**kw):
    d = dict(fg_color=T["surface2"], button_color=T["surface2"], button_hover_color=T["hover"],
             text_color=T["text"], dropdown_fg_color=T["surface"], dropdown_hover_color=T["surface2"],
             dropdown_text_color=T["text"], corner_radius=10, height=34, font=F(12), dropdown_font=F(12))
    d.update(kw)
    return d


def slider_style(**kw):
    d = dict(fg_color=T["border"], progress_color=T["accent"], button_color="#FFFFFF",
             button_hover_color="#E5E7EB", height=16)
    d.update(kw)
    return d


def entry_style(**kw):
    d = dict(fg_color=T["surface2"], border_color=T["border"], border_width=1, corner_radius=8,
             text_color=T["text"], font=F(12))
    d.update(kw)
    return d


SRT_TIME_RE = re.compile(
    r"(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})")

# Put your own license check here if you want one (return True to allow use).
# Example: LICENSE_HOOK = lambda: my_license_module.is_valid()
LICENSE_HOOK = None


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


# --------------------------------------------------------------------------- #
# Voice parameters
# --------------------------------------------------------------------------- #
def resolve_voice_params(voice_name, user_rate_str):
    """-> (voice_id, pitch, effective_rate_str, rate_offset)"""
    if voice_name in KHMER_VOICE_PRESETS:
        p = KHMER_VOICE_PRESETS[voice_name]
        voice_id, pitch, rate_offset = p["voice_id"], p.get("pitch", "+0Hz"), p.get("rate_offset", 0)
    else:
        voice_id = None
        for p in KHMER_VOICE_PRESETS.values():
            if p["voice_id"] in str(voice_name):
                voice_id = p["voice_id"]
                break
        if not voice_id:
            name = str(voice_name)
            voice_id = name.split(" - ")[-1].strip() if " - " in name else (name.strip() or "km-KH-SreymomNeural")
        pitch, rate_offset = "+0Hz", 0
    try:
        user_val = int(str(user_rate_str).replace("%", "").replace("+", ""))
    except Exception:
        user_val = 0
    total = user_val + rate_offset
    return voice_id, pitch, (f"+{total}%" if total >= 0 else f"{total}%"), rate_offset


def fmt_rate(v):
    v = int(v)
    return f"+{v}%" if v >= 0 else f"{v}%"


def sync_note():
    """Khmer warning text when some SRT lines were still longer than their slot (else '')."""
    n, t = SYNC_REPORT["late"], SYNC_REPORT["total"]
    if n <= 0:
        return ""
    return (f"\n\n⚠️ {n}/{t} បន្ទាត់ វែងជាងចន្លោះ Timecode ទោះបង្កើនល្បឿនដល់កម្រិតកំណត់ហើយ "
            "(សំឡេងអាចយឺតបន្តិច)។ ដើម្បីដោះស្រាយ៖ បង្កើនល្បឿនអតិបរមា (Auto Sync) "
            "ឬកាត់បន្ថយអត្ថបទបកប្រែឱ្យខ្លីជាងមុន។")


def parse_clock(s):
    """'90' / '1:30' / '01:02:03.5' -> seconds (float); '' -> None; invalid -> ValueError."""
    s = (s or "").strip().replace(",", ".")
    if not s:
        return None
    parts = s.split(":")
    if len(parts) > 3:
        raise ValueError(s)
    total = 0.0
    for p in parts:
        total = total * 60.0 + float(p)
    if total < 0:
        raise ValueError(s)
    return total


def fmt_clock(t):
    t = round(max(0.0, float(t)), 1)
    h, m, s = int(t // 3600), int((t % 3600) // 60), t % 60
    return f"{h}:{m:02d}:{s:04.1f}" if h else f"{m:02d}:{s:04.1f}"


# --------------------------------------------------------------------------- #
# ffmpeg helpers
# --------------------------------------------------------------------------- #
def ffmpeg_exe():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_ffmpeg(args, capture=False):
    cmd = [ffmpeg_exe(), "-y"] + args
    if capture:
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              encoding="utf-8", errors="ignore", creationflags=CREATE_NO_WINDOW)
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          creationflags=CREATE_NO_WINDOW)


def audio_duration(path):
    try:
        res = subprocess.run([ffmpeg_exe(), "-i", path], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, encoding="utf-8", errors="ignore", creationflags=CREATE_NO_WINDOW)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
        if m:
            h, mi, s = map(float, m.groups())
            return h * 3600 + mi * 60 + s
    except Exception:
        pass
    return 0.0


def _out_codec(out_path):
    return ["-c:a", "libmp3lame", "-b:a", "192k"] if out_path.lower().endswith(".mp3") else []


def standardize_clip(src, dst, max_len=None):
    args = ["-i", src, "-ar", "44100", "-ac", "2"]
    if max_len and max_len > 0:
        args += ["-t", f"{max_len:.3f}"]
    run_ffmpeg(args + _out_codec(dst) + [dst])


def adjust_tempo(src, dst, factor, max_len=None):
    factor = max(0.35, min(2.8, factor))
    if factor > 2.0:
        flt = f"atempo=2.0,atempo={factor / 2.0:.3f}"
    elif factor < 0.5:
        flt = f"atempo=0.5,atempo={factor / 0.5:.3f}"
    else:
        flt = f"atempo={factor:.3f}"
    args = ["-i", src, "-filter:a", flt, "-ar", "44100", "-ac", "2"]
    if max_len and max_len > 0:
        args += ["-t", f"{max_len:.3f}"]
    run_ffmpeg(args + _out_codec(dst) + [dst])


def make_silence(path, seconds):
    run_ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-ar", "44100", "-ac", "2",
                "-t", f"{seconds:.3f}", path])
    return os.path.exists(path) and os.path.getsize(path) > 100


def write_concat_list(list_path, files):
    with open(list_path, "w", encoding="utf-8") as f:
        for item in files:
            f.write("file '" + item.replace("\\", "/").replace("'", "'\\''") + "'\n")


def combine_timeline(clips, out_path, workdir, max_duration=None):
    """clips: [(start_seconds, wav_path)] -> one mp3 with silence gaps preserved."""
    clips = sorted(clips, key=lambda x: x[0])
    files, current = [], 0.0
    for idx, (start, path) in enumerate(clips):
        if not os.path.exists(path):
            continue
        dur = audio_duration(path)
        if dur <= 0.01:
            continue
        gap = start - current
        if gap > 0.01:
            sil = os.path.join(workdir, f"sil_{idx}.wav")
            if make_silence(sil, gap):
                files.append(sil)
                current += gap
        files.append(path)
        current += dur
    if max_duration and max_duration > current + 0.02:
        sil = os.path.join(workdir, "sil_end.wav")
        if make_silence(sil, max_duration - current):
            files.append(sil)
    if not files:
        raise RuntimeError("No audio clips to combine")
    lst = os.path.join(workdir, "timeline.txt")
    write_concat_list(lst, files)
    args = ["-f", "concat", "-safe", "0", "-i", lst]
    if max_duration and max_duration > 0:
        args += ["-t", f"{max_duration:.3f}"]
    args += ["-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", out_path]
    res = run_ffmpeg(args)
    if res.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", lst, "-ar", "44100", "-ac", "2",
                    "-c:a", "libmp3lame", "-b:a", "192k", out_path])


def play_audio(path):
    """Play a short audio file without blocking the UI."""
    try:
        if os.name == "nt":
            import winsound
            if path.lower().endswith(".wav"):
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                os.startfile(path)
        else:
            webbrowser.open("file://" + path)
    except Exception:
        webbrowser.open("file://" + path)


# --------------------------------------------------------------------------- #
# Video helpers (dubbing + built-in video display; no extra dependency, ffmpeg only)
# --------------------------------------------------------------------------- #
def video_info(path):
    """-> {'duration', 'w', 'h', 'has_audio'} read from `ffmpeg -i` (rotation aware)."""
    info = {"duration": 0.0, "w": 0, "h": 0, "has_audio": False}
    try:
        res = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", path], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore",
                             creationflags=CREATE_NO_WINDOW)
        err = res.stderr
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", err)
        if m:
            h, mi, s = map(float, m.groups())
            info["duration"] = h * 3600 + mi * 60 + s
        vl = re.search(r"Stream #[^\n]*Video:[^\n]*", err)
        if vl:
            m = re.search(r"\b(\d{2,5})x(\d{2,5})\b", vl.group(0))
            if m:
                info["w"], info["h"] = int(m.group(1)), int(m.group(2))
            r = re.search(r"rotation of (-?[\d.]+) degrees", err)
            if r and int(abs(float(r.group(1)))) % 180 == 90:
                info["w"], info["h"] = info["h"], info["w"]
        info["has_audio"] = bool(re.search(r"Stream #[^\n]*Audio:", err))
    except Exception:
        pass
    return info


def mux_dub(video, dub_audio, out_path, orig_volume=0.0, trim_start=0.0, trim_end=None):
    """Put the dub audio on the video (video stream copied when possible).
    orig_volume 0 = replace the original sound; >0 = keep the original underneath at that level (0-1).
    trim_start / trim_end (seconds, on the ORIGINAL timeline; end=None -> to the end) cut the result:
    the dub audio is cut at the same points, so SRT timecodes stay in sync.
    The audio is padded with silence / cut so the result has exactly the output length."""
    info = video_info(video)
    full = info["duration"]
    ts = max(0.0, float(trim_start or 0.0))
    te = float(trim_end) if trim_end else full
    if full > 0:
        te = min(te, full)
    if te and te - ts < 0.2:
        raise RuntimeError("ចន្លោះ Trim ខ្លីពេក ឬមិនត្រឹមត្រូវ!")
    dur = (te - ts) if te else 0.0
    cut_start = ts > 0.001
    seek = ["-ss", f"{ts:.3f}"] if cut_start else []
    vol = max(0.0, min(1.0, float(orig_volume)))
    if info["has_audio"] and vol > 0.001:
        fc = (f"[0:a:0]volume={vol:.3f},apad[o];[1:a:0]apad[d];"
              "[o][d]amix=inputs=2:duration=longest:dropout_transition=0,volume=2,alimiter=limit=0.95[a]")
    else:
        fc = "[1:a:0]apad[a]"
    base = seek + ["-i", video] + seek + ["-i", dub_audio, "-filter_complex", fc,
                                       "-map", "0:v:0", "-map", "[a]"]
    tail = ["-c:a", "aac", "-b:a", "192k", "-ar", "44100"]
    if dur > 0:
        tail += ["-t", f"{dur:.3f}"]
    else:
        tail += ["-shortest"]
    if out_path.lower().endswith((".mp4", ".mov", ".m4v")):
        tail += ["-movflags", "+faststart"]
    encode = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
    # a cut that does not start at 0 must re-encode (stream copy can only cut on keyframes -> A/V drift)
    vcodecs = [encode] if cut_start else [["-c:v", "copy"], encode]
    err = ""
    for vcodec in vcodecs:
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
        except Exception:
            pass
        res = run_ffmpeg(base + vcodec + tail + [out_path], capture=True)
        if res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            return out_path
        err = (res.stderr or "")[-400:]
    raise RuntimeError("មិនអាចបញ្ចូលសំឡេងទៅក្នុងវីដេអូបានទេ:\n" + err)


def trim_video(video, out_path, start=0.0, end=None):
    """Save only [start, end] of `video` (seconds; end=None -> to the end), original sound kept."""
    full = video_info(video)["duration"]
    ts = max(0.0, float(start or 0.0))
    te = float(end) if end else full
    if full > 0:
        te = min(te, full)
    if te and te - ts < 0.2:
        raise RuntimeError("ចន្លោះ Trim ខ្លីពេក ឬមិនត្រឹមត្រូវ!")
    dur = (te - ts) if te else 0.0
    seek = ["-ss", f"{ts:.3f}"] if ts > 0.001 else []
    tail = ["-t", f"{dur:.3f}"] if dur > 0 else []
    if out_path.lower().endswith((".mp4", ".mov", ".m4v")):
        tail += ["-movflags", "+faststart"]
    attempts = []
    if not seek:                      # cutting only the end: no re-encode needed
        attempts.append(["-c", "copy"])
    attempts.append(["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                     "-c:a", "aac", "-b:a", "192k"])
    err = ""
    for codec in attempts:
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
        except Exception:
            pass
        res = run_ffmpeg(seek + ["-i", video, "-map", "0:v:0", "-map", "0:a:0?"] + codec + tail + [out_path],
                         capture=True)
        if res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            return out_path
        err = (res.stderr or "")[-400:]
    raise RuntimeError("មិនអាចកាត់វីដេអូបានទេ:\n" + err)


def grab_frame(path, t, w, h):
    """One RGB frame at time t scaled to w x h (bytes) or None."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0, t):.3f}", "-i", path,
           "-an", "-sn", "-frames:v", "1", "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             creationflags=CREATE_NO_WINDOW, timeout=30)
    except Exception:
        return None
    return res.stdout[:w * h * 3] if len(res.stdout) >= w * h * 3 else None


class FrameStream:
    """Decode a video with ffmpeg into raw RGB frames at a fixed fps, starting at `start` seconds.
    Frames arrive in self.q as (index, bytes); FrameStream.END marks the end."""
    END = object()

    def __init__(self, path, start, w, h, fps):
        self.w, self.h, self.fps = w, h, fps
        self.q = queue.Queue(maxsize=20)
        self._stop = threading.Event()
        cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0, start):.3f}",
               "-i", path, "-an", "-sn", "-vf", f"fps={fps},scale={w}:{h}",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     creationflags=CREATE_NO_WINDOW)
        threading.Thread(target=self._reader, daemon=True).start()

    def _put(self, item):
        while not self._stop.is_set():
            try:
                self.q.put(item, timeout=0.2)
                return
            except queue.Full:
                pass

    def _reader(self):
        size, idx = self.w * self.h * 3, 0
        try:
            while not self._stop.is_set():
                buf = self.proc.stdout.read(size)
                if len(buf) < size:
                    break
                self._put((idx, buf))
                idx += 1
        except Exception:
            pass
        self._put(FrameStream.END)

    def stop(self):
        self._stop.set()
        try:
            self.proc.kill()
        except Exception:
            pass


class MciAudio:
    """Tiny audio player (Windows MCI, nothing to install). No-op elsewhere."""
    ALIAS = "ttv_video_audio"

    def __init__(self, alias=None):
        self.ok = os.name == "nt"
        self.loaded = False
        if alias:
            self.ALIAS = alias

    def _send(self, cmd):
        if not self.ok:
            return -1
        try:
            import ctypes
            return ctypes.windll.winmm.mciSendStringW(cmd, None, 0, 0)
        except Exception:
            return -1

    def _query(self, cmd):
        if not self.ok:
            return ""
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(128)
            if ctypes.windll.winmm.mciSendStringW(cmd, buf, 128, 0) == 0:
                return buf.value
        except Exception:
            pass
        return ""

    def load(self, path):
        self.close()
        ok = self._send(f'open "{path}" type mpegvideo alias {self.ALIAS}') == 0
        if not ok:
            ok = self._send(f'open "{path}" alias {self.ALIAS}') == 0
        if ok:
            self._send(f"set {self.ALIAS} time format milliseconds")
            self.loaded = True
        return self.loaded

    def play(self, pos=0.0):
        if self.loaded:
            self._send(f"play {self.ALIAS} from {int(max(0.0, pos) * 1000)}")

    def position(self):
        """Current position in seconds (0.0 when unknown)."""
        if not self.loaded:
            return 0.0
        try:
            return int(self._query(f"status {self.ALIAS} position")) / 1000.0
        except Exception:
            return 0.0

    def stop(self):
        if self.loaded:
            self._send(f"stop {self.ALIAS}")

    def close(self):
        if self.loaded:
            self._send(f"stop {self.ALIAS}")
            self._send(f"close {self.ALIAS}")
            self.loaded = False


class VideoPanel(ctk.CTkFrame):
    """Video display that automatically fits its frame (keeps the aspect ratio, follows window resizes).
    Play / pause / seek; sound comes from the video's own audio track through MciAudio."""
    FPS = 15
    MAX_SIDE = 1280

    def __init__(self, master, on_close=None, on_export=None, on_import=None):
        import tkinter as tk
        super().__init__(master, fg_color=T["surface"], corner_radius=14, border_width=1, border_color=T["border"])
        self._close_cb = on_close
        self._export_cb = on_export
        self._import_cb = on_import
        self.path = ""
        self.duration = 0.0
        self.vw = self.vh = 0
        self.pos = 0.0
        self.playing = False
        self.audio = MciAudio()
        self._audio_ok = False
        self._stream = None
        self._pending = None
        self._t0 = 0.0
        self._start_pos = 0.0
        self._disp = (480, 270)
        self._photo = None
        self._tick_job = self._resize_job = self._seek_job = None
        self._grab_seq = 0
        self._load_id = 0
        self._tmp = tempfile.mkdtemp(prefix="ttv_vid_")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        wrap = ctk.CTkFrame(self, fg_color="#000000", corner_radius=10)
        wrap.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 6))
        self.screen = tk.Frame(wrap, bg="#000000", width=320, height=180)
        self.screen.pack(fill="both", expand=True, padx=3, pady=3)
        self.img_lbl = tk.Label(self.screen, bg="#000000", bd=0, highlightthickness=0)
        self.img_lbl.place(relx=0.5, rely=0.5, anchor="center")
        self.screen.bind("<Configure>", self._on_resize)

        # empty state: shown until a video is loaded (the video zone is always visible)
        self._ph = ctk.CTkFrame(wrap, fg_color="#0B0F1A", corner_radius=10)
        _inner = ctk.CTkFrame(self._ph, fg_color="transparent")
        _inner.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(_inner, text="🎬", font=ctk.CTkFont(size=42)).pack()
        ctk.CTkLabel(_inner, text="មិនទាន់មានវីដេអូ", font=F(14, "bold"), text_color=T["text"]).pack(pady=(6, 2))
        ctk.CTkLabel(_inner, text="នាំចូលវីដេអូ ដើម្បីមើល កាត់ និង Dub", font=F(11),
                     text_color=T["muted"]).pack(pady=(0, 12))
        mkbtn(_inner, "នាំចូលវីដេអូ", "primary", width=160, height=38,
              command=lambda: self._import_cb() if self._import_cb else None).pack()

        ctl = ctk.CTkFrame(self, fg_color="transparent")
        ctl.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        ctl.grid_columnconfigure(1, weight=1)
        self.play_btn = ctk.CTkButton(ctl, text="▶", width=36, height=36, corner_radius=18, fg_color=T["accent"],
                                      hover_color=T["accent_h"], font=ctk.CTkFont(size=13), command=self.toggle)
        self.play_btn.grid(row=0, column=0)
        self.slider = ctk.CTkSlider(ctl, from_=0, to=1, command=self._on_slider, **slider_style())
        self.slider.grid(row=0, column=1, sticky="ew", padx=8)
        self.slider.set(0)
        self.time_lbl = ctk.CTkLabel(ctl, text="00:00 / 00:00", text_color=T["muted"], font=ctk.CTkFont(size=12))
        self.time_lbl.grid(row=0, column=2)
        ctk.CTkButton(ctl, text="✕", width=30, height=30, corner_radius=8, fg_color="transparent",
                      text_color=T["muted"], hover_color=T["danger_bg"],
                      command=self._close_panel).grid(row=0, column=3, padx=(8, 0))

        # ---- trim bar: cut the start / end of the video --------------------
        trim = ctk.CTkFrame(self, fg_color=T["surface2"], corner_radius=12)
        trim.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.trim_start_var = ctk.StringVar(value="")
        self.trim_end_var = ctk.StringVar(value="")
        lf = F(12, "bold")
        ctk.CTkLabel(trim, text="កាត់វីដេអូ (Trim)", font=lf).grid(row=0, column=0, padx=(8, 6), pady=(6, 2))
        ctk.CTkLabel(trim, text="ពី", font=lf).grid(row=0, column=1, padx=(4, 2), pady=(6, 2))
        self.trim_start_entry = ctk.CTkEntry(trim, width=74, height=28, textvariable=self.trim_start_var, **entry_style(fg_color=T["surface"]))
        self.trim_start_entry.grid(row=0, column=2, pady=(6, 2))
        ctk.CTkButton(trim, text="◎", width=28, height=28, corner_radius=8, fg_color=T["surface"], hover_color=T["accent"],
                      command=lambda: self._set_trim_from_pos("start")).grid(row=0, column=3, padx=(3, 8), pady=(6, 2))
        ctk.CTkLabel(trim, text="ដល់", font=lf).grid(row=0, column=4, padx=(0, 2), pady=(6, 2))
        self.trim_end_entry = ctk.CTkEntry(trim, width=74, height=28, textvariable=self.trim_end_var, **entry_style(fg_color=T["surface"]))
        self.trim_end_entry.grid(row=0, column=5, pady=(6, 2))
        ctk.CTkButton(trim, text="◎", width=28, height=28, corner_radius=8, fg_color=T["surface"], hover_color=T["accent"],
                      command=lambda: self._set_trim_from_pos("end")).grid(row=0, column=6, padx=(3, 8), pady=(6, 2))
        self.trim_info = ctk.CTkLabel(trim, text="", anchor="w", font=ctk.CTkFont(family=FONT_MAIN, size=11))
        self.trim_info.grid(row=1, column=0, columnspan=7, padx=(10, 8), pady=(0, 6), sticky="w")
        ctk.CTkButton(trim, text="↺ Reset", width=60, height=26, corner_radius=8, fg_color=T["surface"], hover_color=T["hover"],
                      font=ctk.CTkFont(family=FONT_MAIN, size=11),
                      command=self.reset_trim).grid(row=2, column=0, columnspan=5, padx=(10, 6), pady=(0, 10), sticky="e")
        ctk.CTkButton(trim, text="រក្សាទុកផ្នែកដែលកាត់", width=130, height=26, corner_radius=8, fg_color=T["accent"],
                      hover_color=T["accent_h"], font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
                      command=self._do_export).grid(row=2, column=5, columnspan=2, padx=(0, 10), pady=(0, 10), sticky="e")
        for ent in (self.trim_start_entry, self.trim_end_entry):
            ent.bind("<KeyRelease>", lambda e: self._update_trim_info())
            ent.bind("<FocusOut>", lambda e: self._update_trim_info())
        self._update_trim_info()
        self._show_placeholder()

    # ---- helpers ------------------------------------------------------- #
    def _show_placeholder(self):
        self._ph.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._ph.tkraise()

    def seek_to(self, t):
        """Jump to `t` seconds (used by the SRT line editor)."""
        if not self.path:
            return
        t = max(0.0, float(t))
        if self.duration:
            t = min(t, self.duration)
        self.pos = t
        self.slider.set(t)
        self._update_time()
        self._apply_seek()

    def clear(self):
        """Back to the empty state (no video loaded)."""
        self.pause()
        self.audio.close()
        self._audio_ok = False
        self._load_id += 1
        self._grab_seq += 1
        self.path = ""
        self.duration = 0.0
        self.vw = self.vh = 0
        self.pos = 0.0
        self._photo = None
        try:
            self.img_lbl.configure(image="")
        except Exception:
            pass
        self.slider.configure(from_=0, to=1)
        self.slider.set(0)
        self._update_time()
        self.reset_trim()
        self._show_placeholder()

    @staticmethod
    def _fmt(t):
        t = int(max(0, t))
        return f"{t // 60:02d}:{t % 60:02d}"

    def _update_time(self):
        self.time_lbl.configure(text=f"{self._fmt(self.pos)} / {self._fmt(self.duration)}")

    # ---- trim ------------------------------------------------------------ #
    def _set_trim_from_pos(self, which):
        if not self.path:
            return
        (self.trim_start_var if which == "start" else self.trim_end_var).set(fmt_clock(self.pos))
        self._update_trim_info()

    def reset_trim(self):
        self.trim_start_var.set("")
        self.trim_end_var.set("")
        self._update_trim_info()

    def get_trim(self):
        """-> (start, end) seconds; end=None means 'to the end of the video'.
        Raises ValueError (Khmer message) when the values are invalid."""
        try:
            s = parse_clock(self.trim_start_var.get())
            e = parse_clock(self.trim_end_var.get())
        except ValueError:
            raise ValueError("ពេលវេលា Trim មិនត្រឹមត្រូវ! សូមវាយជាទម្រង់ 1:30 ឬ 01:30.5")
        s = s or 0.0
        d = self.duration
        if d > 0:
            if s >= d - 0.2:
                raise ValueError("ចំណុចចាប់ផ្តើម Trim លើសប្រវែងវីដេអូ!")
            if e is not None and e >= d - 0.05:
                e = None
        if e is not None and e - s < 0.2:
            raise ValueError("ចំណុចបញ្ចប់ត្រូវនៅក្រោយចំណុចចាប់ផ្តើម!")
        return s, e

    def _trim_bounds(self):
        try:
            return self.get_trim()
        except ValueError:
            return 0.0, None

    def _update_trim_info(self):
        if not self.path:
            self.trim_info.configure(text="ទទេ = ពីដើម / ដល់ចុង (ចុច ◎ យកទីតាំងបច្ចុប្បន្ន)", text_color=T["muted"])
            return
        try:
            s, e = self.get_trim()
        except ValueError:
            self.trim_info.configure(text="❌ ពេលវេលាមិនត្រឹមត្រូវ", text_color="#F87171")
            return
        if s <= 0.001 and e is None:
            self.trim_info.configure(text="មិនទាន់កាត់ (ទទេ = ពីដើម / ដល់ចុង)", text_color=T["muted"])
        else:
            end = e if e is not None else self.duration
            self.trim_info.configure(text=f"✅ ប្រវែងថ្មី {fmt_clock(max(0.0, end - s))}", text_color="#34D399")

    def _do_export(self):
        if self._export_cb:
            self._export_cb()

    def _calc_disp(self):
        """Largest size that fits the screen area while keeping the video's aspect ratio."""
        aw = max(80, self.screen.winfo_width() - 4)
        ah = max(60, self.screen.winfo_height() - 4)
        if not (self.vw and self.vh):
            return aw, ah
        s = min(aw / self.vw, ah / self.vh)
        if max(self.vw, self.vh) * s > self.MAX_SIDE:
            s = self.MAX_SIDE / max(self.vw, self.vh)
        return max(2, int(self.vw * s)), max(2, int(self.vh * s))

    def _paint_frame(self, buf, w, h):
        try:
            from PIL import Image, ImageTk
            img = Image.frombytes("RGB", (w, h), buf[:w * h * 3])
            self._photo = ImageTk.PhotoImage(img)
            self.img_lbl.configure(image=self._photo)
        except Exception:
            pass

    def _show_frame_at(self, t):
        self._grab_seq += 1
        seq, w, h, path = self._grab_seq, self._disp[0], self._disp[1], self.path

        def work():
            buf = grab_frame(path, t, w, h)
            if buf:
                self.after(0, lambda: seq == self._grab_seq and not self.playing and self._paint_frame(buf, w, h))
        threading.Thread(target=work, daemon=True).start()

    # ---- load ----------------------------------------------------------- #
    def load(self, path):
        self.pause()
        info = video_info(path)
        if info["w"] <= 0 or info["h"] <= 0:
            raise RuntimeError("មិនអាចអានវីដេអូនេះបានទេ (ទ្រង់ទ្រាយមិនគាំទ្រ?)")
        self.path, self.duration = path, info["duration"]
        self.vw, self.vh = info["w"], info["h"]
        self.pos = 0.0
        self.slider.configure(from_=0, to=max(self.duration, 0.1))
        self.slider.set(0)
        self._update_time()
        self.reset_trim()
        self.update_idletasks()
        self._disp = self._calc_disp()
        self._show_frame_at(0.0)
        self._ph.place_forget()
        self.audio.close()
        self._audio_ok = False
        self._load_id += 1
        if info["has_audio"] and self.audio.ok:
            threading.Thread(target=self._extract_audio, args=(path, self._load_id), daemon=True).start()

    def _extract_audio(self, path, lid):
        out = os.path.join(self._tmp, f"a{lid}.mp3")
        res = run_ffmpeg(["-i", path, "-vn", "-ac", "2", "-ar", "44100", "-c:a", "libmp3lame",
                          "-b:a", "128k", out])
        if res.returncode != 0 or not os.path.exists(out):
            return

        def ready():
            if lid != self._load_id:
                return
            if self.audio.load(out):
                self._audio_ok = True
                if self.playing:
                    self.audio.play(self.pos)
        self.after(0, ready)

    # ---- playback ------------------------------------------------------- #
    def toggle(self):
        if not self.path:
            return
        self.pause() if self.playing else self.play()

    def _begin_stream(self, start):
        if self._stream:
            self._stream.stop()
        w, h = self._disp
        self._stream = FrameStream(self.path, start, w, h, self.FPS)
        self._pending = None
        self._start_pos = start
        self._t0 = time.perf_counter()

    def play(self):
        if not self.path:
            return
        if self.duration and self.pos >= self.duration - 0.2:
            self.pos = 0.0
        ts, te = self._trim_bounds()
        if self.pos < ts or (te is not None and self.pos >= te - 0.05):
            self.pos = ts            # preview only the part that will be kept
        self.playing = True
        self.play_btn.configure(text="⏸")
        self._begin_stream(self.pos)
        if self._audio_ok:
            self.audio.play(self.pos)
        if self._tick_job:
            self.after_cancel(self._tick_job)
        self._tick()

    def pause(self):
        self.playing = False
        try:
            self.play_btn.configure(text="▶")
        except Exception:
            pass
        if self._tick_job:
            try:
                self.after_cancel(self._tick_job)
            except Exception:
                pass
            self._tick_job = None
        if self._stream:
            self._stream.stop()
            self._stream = None
        self._pending = None
        self.audio.stop()

    def _tick(self):
        self._tick_job = None
        if not self.playing or not self._stream:
            return
        st = self._stream
        target = int((time.perf_counter() - self._t0) * self.FPS)
        shown, ended = None, False
        while True:
            if self._pending is None:
                try:
                    self._pending = st.q.get_nowait()
                except queue.Empty:
                    break
            if self._pending is FrameStream.END:
                ended = True
                break
            idx, buf = self._pending
            if idx <= target:
                shown = (idx, buf)
                self._pending = None
            else:
                break
        if shown:
            self._paint_frame(shown[1], st.w, st.h)
            self.pos = self._start_pos + shown[0] / self.FPS
            self.slider.set(self.pos)
            self._update_time()
            _ts, _te = self._trim_bounds()
            if _te is not None and self.pos >= _te:      # reached the trim end -> stop
                self.pause()
                self.pos = _te
                self.slider.set(self.pos)
                self._update_time()
                return
        if ended:
            self.pause()
            self.pos = self.duration
            self.slider.set(self.pos)
            self._update_time()
        else:
            self._tick_job = self.after(10, self._tick)

    def _on_slider(self, v):
        self.pos = float(v)
        self._update_time()
        if self._seek_job:
            self.after_cancel(self._seek_job)
        self._seek_job = self.after(160, self._apply_seek)

    def _apply_seek(self):
        self._seek_job = None
        if not self.path:
            return
        if self.playing:
            self._begin_stream(self.pos)
            if self._audio_ok:
                self.audio.play(self.pos)
        else:
            self._show_frame_at(self.pos)

    # ---- auto screen (resize) -------------------------------------------- #
    def _on_resize(self, _e=None):
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(220, self._apply_resize)

    def _apply_resize(self):
        self._resize_job = None
        if not self.path:
            return
        new = self._calc_disp()
        if abs(new[0] - self._disp[0]) < 4 and abs(new[1] - self._disp[1]) < 4:
            return
        self._disp = new
        if self.playing:
            self._begin_stream(self.pos)      # audio keeps running
        else:
            self._show_frame_at(self.pos)

    # ---- close ------------------------------------------------------------ #
    def _close_panel(self):
        self.clear()
        if self._close_cb:
            self._close_cb()

    def shutdown(self):
        try:
            self.pause()
            self.audio.close()
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# SRT block helpers + line-by-line editor + audio preview panel
# --------------------------------------------------------------------------- #
def split_srt_blocks(text):
    """SRT text -> [(head_lines, text)]. head = index + timecode lines (kept untouched)."""
    out = []
    for b in re.split(r"\n\s*\n+", (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()):
        lines = [l.rstrip() for l in b.split("\n") if l.strip()]
        if not lines:
            continue
        ti = next((i for i, l in enumerate(lines) if SRT_TIME_RE.search(l)), None)
        if ti is None:
            out.append(([], "\n".join(lines)))
        else:
            out.append((lines[:ti + 1], "\n".join(lines[ti + 1:])))
    return out


def join_srt_blocks(blocks):
    parts = []
    for head, txt in blocks:
        lines = list(head) + ([txt.strip()] if txt and txt.strip() else [])
        if lines:
            parts.append("\n".join(lines))
    return "\n\n".join(parts) + "\n"


class SrtLineEditor(ctk.CTkFrame):
    """Cue list (# / time / source / translation). Pick a cue, fix the translation, save."""

    def __init__(self, master, on_seek=None):
        import tkinter as tk
        from tkinter import ttk
        super().__init__(master, fg_color=T["surface"], corner_radius=14, border_width=1, border_color=T["border"])
        self._on_seek = on_seek
        self.blocks = []      # [[head_lines, text], ...]
        self.orig = []        # source text per cue ([] when unknown)
        self._sel = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("TTV.Treeview", background=T["surface"], fieldbackground=T["surface"], foreground=T["text"],
                     bordercolor=T["surface"], lightcolor=T["surface"], darkcolor=T["surface"],
                     rowheight=30, borderwidth=0, font=(FONT_MAIN, 11))
        st.configure("TTV.Treeview.Heading", background=T["surface2"], foreground=T["muted"], relief="flat",
                     borderwidth=0, font=(FONT_MAIN, 10, "bold"))
        st.map("TTV.Treeview", background=[("selected", T["accent"])], foreground=[("selected", "#FFFFFF")])
        st.map("TTV.Treeview.Heading", background=[("active", T["hover"])])

        self.tree = ttk.Treeview(self, columns=("n", "time", "orig", "text"), show="headings",
                                 selectmode="browse", style="TTV.Treeview")
        for col, title, w, stretch in (("n", "#", 46, False), ("time", "ម៉ោង", 104, False),
                                       ("orig", "ដើម (Source)", 220, True),
                                       ("text", "បកប្រែ (កែបាន)", 260, True)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=w, minwidth=40, stretch=stretch, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=(10, 6))
        sb = ctk.CTkScrollbar(self, command=self.tree.yview, button_color=T["border"],
                              button_hover_color=T["hover"])
        sb.grid(row=0, column=1, sticky="ns", padx=(2, 8), pady=(10, 6))
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        ed = ctk.CTkFrame(self, fg_color="transparent")
        ed.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        ed.grid_columnconfigure(0, weight=1)
        self.info_lbl = ctk.CTkLabel(ed, text="", font=F(11), text_color=T["muted"], anchor="w",
                                     justify="left", wraplength=520)
        self.info_lbl.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        self.orig_lbl = ctk.CTkLabel(ed, text="", font=F(12), text_color=T["info"], anchor="w",
                                     justify="left", wraplength=520)
        self.orig_lbl.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self.edit_box = ctk.CTkTextbox(ed, height=88, wrap="word", font=F(15), fg_color=T["surface2"],
                                       text_color=T["text"], border_width=1, border_color=T["border"],
                                       corner_radius=10)
        self.edit_box.grid(row=2, column=0, sticky="ew")
        btn = ctk.CTkFrame(ed, fg_color="transparent")
        btn.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        mkbtn(btn, "↑ មុន", "secondary", width=70, command=lambda: self.step(-1)).pack(side="left")
        mkbtn(btn, "↓ បន្ទាប់", "secondary", width=84, command=lambda: self.step(1)).pack(side="left", padx=(6, 0))
        mkbtn(btn, "មើលក្នុងវីដេអូ", "secondary", width=120, command=self._seek).pack(side="left", padx=(10, 0))
        mkbtn(btn, "រក្សាទុកបន្ទាត់ (Ctrl+Enter)", "primary", width=200,
              command=lambda: self.commit(go_next=True)).pack(side="right")
        self.edit_box.bind("<Control-Return>", lambda e: (self.commit(go_next=True), "break")[1])
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, _e=None):
        w = max(240, self.winfo_width() - 60)
        self.info_lbl.configure(wraplength=w)
        self.orig_lbl.configure(wraplength=w)

    @staticmethod
    def _flat(s):
        return " ".join((s or "").split())

    @staticmethod
    def _time_of(head):
        for l in head:
            m = SRT_TIME_RE.search(l)
            if m:
                return m.group(1)
        return ""

    def load(self, srt_text, orig_text=""):
        self.blocks = [[h, t] for h, t in split_srt_blocks(srt_text)]
        ob = [t for _h, t in split_srt_blocks(orig_text)] if orig_text else []
        self.orig = ob if len(ob) == len(self.blocks) else []
        self._sel = None
        self.tree.delete(*self.tree.get_children())
        for i, (h, t) in enumerate(self.blocks):
            num = h[0].strip() if h and h[0].strip().isdigit() else str(i + 1)
            self.tree.insert("", "end", iid=str(i),
                             values=(num, self._time_of(h), self._flat(self.orig[i]) if self.orig else "",
                                     self._flat(t)))
        self.edit_box.delete("1.0", "end")
        self.orig_lbl.configure(text="")
        extra = "" if self.orig else "  (មិនមានអត្ថបទដើមសម្រាប់ប្រៀបធៀប)"
        self.info_lbl.configure(text=f"{len(self.blocks)} បន្ទាត់ — ចុចលើបន្ទាត់ណាមួយ ដើម្បីកែ{extra}")
        if self.blocks:
            self.select(0)

    def select(self, i):
        if not (0 <= i < len(self.blocks)):
            return
        self._commit_current()
        iid = str(i)
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)
        self._load_row(i)

    def _on_select(self, _e=None):
        sel = self.tree.selection()
        if not sel:
            return
        i = int(sel[0])
        if i == self._sel:
            return
        self._commit_current()
        self._load_row(i)

    def _load_row(self, i):
        self._sel = i
        h, t = self.blocks[i]
        self.edit_box.delete("1.0", "end")
        self.edit_box.insert("1.0", t)
        o = self.orig[i] if self.orig else ""
        self.orig_lbl.configure(text=("ដើម: " + self._flat(o)) if o else "")
        self.info_lbl.configure(text=f"បន្ទាត់ {i + 1}/{len(self.blocks)}   ·   {self._time_of(h)}")

    def _commit_current(self):
        i = self._sel
        if i is None or not (0 <= i < len(self.blocks)):
            return
        new = self.edit_box.get("1.0", "end-1c").strip()
        if new != self.blocks[i][1].strip():
            self.blocks[i][1] = new
            try:
                self.tree.set(str(i), "text", self._flat(new))
            except Exception:
                pass

    def commit(self, go_next=False):
        self._commit_current()
        if go_next:
            self.step(1)

    def step(self, d):
        if self._sel is None:
            return
        self.select(min(max(self._sel + d, 0), len(self.blocks) - 1))

    def _seek(self):
        if self._sel is None or not self._on_seek:
            return
        t = self._time_of(self.blocks[self._sel][0])
        if t:
            self._on_seek(parse_srt_time(t))

    def get_text(self):
        self._commit_current()
        return join_srt_blocks(self.blocks)


class AudioPanel(ctk.CTkFrame):
    """Listen to the generated voice (play / pause / seek) before exporting it."""

    def __init__(self, master):
        super().__init__(master, fg_color=T["surface"], corner_radius=14, border_width=1, border_color=T["border"])
        self.audio = MciAudio("ttv_voice_audio")
        self.path = ""
        self.duration = 0.0
        self.pos = 0.0
        self.playing = False
        self._t0 = 0.0
        self._start = 0.0
        self._job = self._seek_job = None
        self._state = None
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text="សំឡេងដែលបានបង្កើត  ·  ស្តាប់មុន Export", font=F(12, "bold"),
                     text_color=T["text"], anchor="w").grid(row=0, column=0, columnspan=3, sticky="w",
                                                            padx=14, pady=(10, 0))
        self.status_lbl = ctk.CTkLabel(self, text="", font=F(11), text_color=T["muted"], anchor="w",
                                       justify="left")
        self.status_lbl.grid(row=1, column=0, columnspan=3, sticky="w", padx=14, pady=(0, 4))
        self.play_btn = ctk.CTkButton(self, text="▶", width=36, height=36, corner_radius=18, fg_color=T["accent"],
                                      hover_color=T["accent_h"], font=ctk.CTkFont(size=13), command=self.toggle,
                                      state="disabled")
        self.play_btn.grid(row=2, column=0, padx=(14, 0), pady=(0, 12))
        self.slider = ctk.CTkSlider(self, from_=0, to=1, command=self._on_slider, **slider_style())
        self.slider.grid(row=2, column=1, sticky="ew", padx=8, pady=(0, 12))
        self.slider.set(0)
        self.time_lbl = ctk.CTkLabel(self, text="00:00 / 00:00", text_color=T["muted"], font=ctk.CTkFont(size=12))
        self.time_lbl.grid(row=2, column=2, padx=(0, 14), pady=(0, 12))
        self.set_state("none")

    @staticmethod
    def _fmt(t):
        t = int(max(0, t))
        return f"{t // 60:02d}:{t % 60:02d}"

    def _update_time(self):
        self.time_lbl.configure(text=f"{self._fmt(self.pos)} / {self._fmt(self.duration)}")

    def set_state(self, state):
        """'none' (no audio yet) | 'fresh' | 'stale' (text/settings changed since it was generated)."""
        if state == self._state:
            return
        self._state = state
        if state == "none":
            self.status_lbl.configure(text="មិនទាន់មានសំឡេង — ចុច «បង្កើតសំឡេង» ខាងក្រោម រួចស្តាប់នៅទីនេះ",
                                      text_color=T["muted"])
        elif state == "fresh":
            self.status_lbl.configure(text=f"✅ សំឡេងរួចរាល់ ({self._fmt(self.duration)}) — ស្តាប់ ហើយបើពេញចិត្តចុច «រក្សាទុក MP3» ឬ «Dub វីដេអូ»",
                                      text_color="#34D399")
        else:
            self.status_lbl.configure(text="⚠️ អត្ថបទ ឬការកំណត់បានប្តូរ ក្រោយបង្កើតសំឡេង — ចុច «បង្កើតសំឡេង» ម្តងទៀត",
                                      text_color=T["warn"])

    def load(self, path):
        self.pause()
        self.audio.close()
        self.path = path
        try:
            self.duration = float(audio_duration(path) or 0.0)
        except Exception:
            self.duration = 0.0
        self.pos = 0.0
        self.slider.configure(from_=0, to=max(self.duration, 0.1))
        self.slider.set(0)
        self._update_time()
        self.audio.load(path)
        self.play_btn.configure(state="normal")
        self._state = None
        self.set_state("fresh")

    def clear(self):
        self.pause()
        self.audio.close()
        self.path = ""
        self.duration = self.pos = 0.0
        self.slider.set(0)
        self._update_time()
        self.play_btn.configure(state="disabled")
        self.set_state("none")

    def toggle(self):
        if self.path:
            self.pause() if self.playing else self.play()

    def play(self):
        if not self.path:
            return
        if not self.audio.loaded:          # no built-in player (non-Windows): use the default app
            play_audio(self.path)
            return
        if self.duration and self.pos >= self.duration - 0.2:
            self.pos = 0.0
        self.audio.play(self.pos)
        self.playing = True
        self._start, self._t0 = self.pos, time.perf_counter()
        self.play_btn.configure(text="⏸")
        self._tick()

    def pause(self):
        if self.playing:
            p = self.audio.position()
            if p > 0:
                self.pos = min(p, self.duration or p)
        self.playing = False
        try:
            self.play_btn.configure(text="▶")
        except Exception:
            pass
        if self._job:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        self.audio.stop()

    def _tick(self):
        self._job = None
        if not self.playing:
            return
        elapsed = self._start + (time.perf_counter() - self._t0)
        p = self.audio.position()
        self.pos = min(p if p > 0 else elapsed, self.duration or elapsed)
        self.slider.set(self.pos)
        self._update_time()
        if self.duration and elapsed >= self.duration + 0.3:
            self.pause()
            self.pos = 0.0
            self.slider.set(0)
            self._update_time()
            return
        self._job = self.after(150, self._tick)

    def _on_slider(self, v):
        self.pos = float(v)
        self._update_time()
        if self._seek_job:
            self.after_cancel(self._seek_job)
        self._seek_job = self.after(160, self._apply_seek)

    def _apply_seek(self):
        self._seek_job = None
        if self.playing and self.audio.loaded:
            self.audio.play(self.pos)
            self._start, self._t0 = self.pos, time.perf_counter()

    def shutdown(self):
        try:
            self.pause()
            self.audio.close()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #
def optimize_text_for_reading(text):
    """'Smart Pause' clean-up: strip markup/noise, fix punctuation spacing, merge lines."""
    if not text:
        return ""
    text = text.replace("\ufeff", "").replace("\u00ad", "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]", " ", text)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"^[#*>\-•\s]+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[\*_~`]", "", text)
    text = re.sub(r"[។]{2,}", "។", text)
    text = re.sub(r"\.{4,}", "...", text)
    text = re.sub(r"[!]{2,}", "!", text)
    text = re.sub(r"[\?]{2,}", "?", text)
    text = re.sub(r"[ៗ]{2,}", "ៗ", text)
    text = re.sub(r"([។៕!\?:,;])([^\s\d\n\.,!?:;])", r"\1 \2", text)
    paragraphs = []
    for p in text.split("\n\n"):
        lines = [l.strip() for l in p.split("\n") if l.strip()]
        if not lines:
            continue
        merged = lines[0]
        for l in lines[1:]:
            merged += ("\n" if re.search(r"[។៕!\?\.:]$", merged) else " ") + l
        paragraphs.append(merged)
    text = "\n\n".join(paragraphs)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def split_khmer_text(text, max_len=1000):
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_len:
        return [text]

    chunks, current = [], ""

    def push(piece, sep):
        nonlocal current
        if not current:
            current = piece
        elif len(current) + len(piece) + len(sep) <= max_len:
            current += sep + piece
        else:
            chunks.append(current.strip())
            current = piece

    for para in [p.strip() for p in re.split(r"\n+", text) if p.strip()]:
        if len(para) <= max_len:
            push(para, "\n")
            continue
        if current:
            chunks.append(current.strip())
            current = ""
        parts = re.split(r"([។៕!\?\.]+)", para)
        sentences = [(parts[i] + parts[i + 1]).strip() for i in range(0, len(parts) - 1, 2)]
        if len(parts) % 2 == 1 and parts[-1].strip():
            sentences.append(parts[-1].strip())
        for s in [x for x in sentences if x]:
            if len(s) <= max_len:
                push(s, " ")
                continue
            if current:
                chunks.append(current.strip())
                current = ""
            tmp = ""
            for w in [w.strip() for w in re.split(r"([ ,;:\t\u200b]+)", s) if w.strip()]:
                if not tmp:
                    tmp = w
                elif len(tmp) + len(w) + 1 <= max_len:
                    tmp += " " + w
                else:
                    chunks.append(tmp.strip())
                    tmp = w
            current = tmp
    if current:
        chunks.append(current.strip())
    return [c for c in chunks if c.strip()]


def parse_srt_time(t):
    try:
        parts = re.sub(r"[\.,]", ",", t.strip()).split(":")
        sec = parts[-1].split(",")
        s = int(sec[0]) + (int(sec[1]) / 1000.0 if len(sec) > 1 else 0)
        m = int(parts[-2]) if len(parts) >= 2 else 0
        h = int(parts[-3]) if len(parts) >= 3 else 0
        return h * 3600.0 + m * 60.0 + s
    except Exception:
        return 0.0


def parse_srt(text):
    entries = []
    for block in [b.strip() for b in re.split(r"\n\s*\n+", text.strip()) if b.strip()]:
        match, parts = None, []
        for line in [l.strip() for l in block.split("\n") if l.strip()]:
            m = SRT_TIME_RE.search(line)
            if m:
                match = m
            elif not line.isdigit():
                parts.append(line)
        if not (match and parts):
            continue
        st, et = parse_srt_time(match.group(1)), parse_srt_time(match.group(2))
        t = " ".join(parts)
        t = re.sub(r"<[^>]+>", "", t)
        t = re.sub(r"\{[^}]+\}", "", t).strip()
        t = re.sub(r"\[.*?\]", "", t)
        t = re.sub(r"\(.*?\)", "", t)
        t = re.sub(r"[♪♫#*_~]+", "", t).strip()
        if re.search(r"[\w\u1780-\u17ff\u19e0-\u19ff]", t) and et > st:
            entries.append({"start_time": st, "end_time": et, "target_duration": et - st, "text": t})
    for i, e in enumerate(entries):
        if i + 1 < len(entries):
            gap = entries[i + 1]["start_time"] - e["start_time"]
            e["hard_limit"] = max(0.1, min(e["target_duration"] * 1.15, gap - 0.04))
        else:
            e["hard_limit"] = e["target_duration"]
    return entries


# --------------------------------------------------------------------------- #
# Free translation (no API key)
# --------------------------------------------------------------------------- #
TRANSLATE_LANGS = {
    "ខ្មែរ (Khmer)": "km",
    "English": "en",
    "中文 (Chinese)": "zh-CN",
    "ไทย (Thai)": "th",
    "Tiếng Việt": "vi",
}
DEFAULT_TRANSLATE_LANG = "ខ្មែរ (Khmer)"


def _guess_source_lang(text):
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh-CN"
    if re.search(r"[\u1780-\u17ff]", text):
        return "km"
    if re.search(r"[\u0e00-\u0e7f]", text):
        return "th"
    return "en"


def _google_translate(text, target, timeout=15):
    """Free Google Translate web endpoint (gtx client). POST so long text is fine."""
    data = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": target,
                                   "dt": "t", "q": text}).encode("utf-8")
    req = urllib.request.Request("https://translate.googleapis.com/translate_a/single", data=data,
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        j = json.loads(resp.read().decode("utf-8"))
    out = "".join(seg[0] for seg in (j[0] or []) if seg and seg[0])
    if not out.strip():
        raise RuntimeError("empty translation")
    return out


def _mymemory_translate(text, target, timeout=15):
    """Fallback: MyMemory free API (about 500 chars per request)."""
    src_lang = _guess_source_lang(text)
    if src_lang == target:
        return text
    parts, cur = [], ""
    for piece in re.split(r"(?<=[\.\!\?។])\s*", text):
        if len(cur) + len(piece) > 450 and cur:
            parts.append(cur)
            cur = ""
        cur += piece + " "
    if cur.strip():
        parts.append(cur)
    result = []
    for p in parts:
        p = p.strip()[:480]
        if not p:
            continue
        url = ("https://api.mymemory.translated.net/get?q=" + urllib.parse.quote(p) +
               f"&langpair={src_lang}|{target}")
        d = _http_json(url, timeout=timeout)
        t = (d.get("responseData") or {}).get("translatedText", "")
        if not t or "MYMEMORY WARNING" in t.upper():
            raise RuntimeError("mymemory failed")
        result.append(t)
    return " ".join(result)


def translate_text(text, target, attempts=3):
    """Translate text to `target` language code. Raises RuntimeError if all providers fail."""
    text = text.strip()
    if not text:
        return text
    last = None
    for i in range(attempts):
        try:
            return _google_translate(text, target)
        except Exception as e:
            last = e
            time.sleep(0.6 * (i + 1))
    try:
        return _mymemory_translate(text, target)
    except Exception as e:
        last = e
    raise RuntimeError(f"Translate failed: {last}")


AI_KEY_PROVIDERS = ("gemini", "openai", "openrouter", "custom")
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

AI_PROVIDERS = {
    "Gemini (Google AI Studio)": "gemini",
    "OpenAI": "openai",
    "OpenRouter": "openrouter",
    "CodeCraft / Custom (OpenAI-compatible)": "custom",
    "Google Translate (ឥតគិតថ្លៃ / គ្មានបរិបទ)": "google",
}
LANG_NAMES = {"km": "Khmer", "en": "English", "zh-CN": "Simplified Chinese",
              "th": "Thai", "vi": "Vietnamese"}


class ApiError(Exception):
    def __init__(self, status, msg):
        super().__init__(f"HTTP {status}: {msg}")
        self.status = status
        self.msg = msg


class FatalApiError(RuntimeError):
    """Bad key / bad model / bad request: retrying or falling back silently would hide the problem."""


def _api_request(url, payload=None, headers=None, timeout=90):
    h = {"User-Agent": "TTV-App", "Content-Type": "application/json"}
    h.update(headers or {})
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=h, method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8", "replace"))
            err = body.get("error", body)
            msg = err.get("message") if isinstance(err, dict) else str(err)
        except Exception:
            msg = str(e.reason)
        raise ApiError(e.code, str(msg)[:300])


def _norm_base(url):
    url = (url or "").strip().rstrip("/")
    return url[:-len("/chat/completions")] if url.endswith("/chat/completions") else url


def list_ai_models(provider, key, base_url=""):
    """Ask the provider which chat/text models this API key can use."""
    key = key.strip()
    if provider == "gemini":
        d = _api_request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
                         headers={"x-goog-api-key": key}, timeout=20)
        bad = ("embedding", "tts", "image", "live", "audio", "robotics", "computer-use", "native")
        names = []
        for m in d.get("models", []):
            n = str(m.get("name", "")).replace("models/", "")
            if n.startswith("gemini") and "generateContent" in m.get("supportedGenerationMethods", []) \
                    and not any(x in n for x in bad):
                names.append(n)
        return sorted(set(names), reverse=True)
    if provider == "openai":
        d = _api_request("https://api.openai.com/v1/models",
                         headers={"Authorization": f"Bearer {key}"}, timeout=20)
        bad = ("audio", "realtime", "image", "tts", "transcribe", "search", "embedding",
               "moderation", "instruct", "codex", "diarize")
        ids = [m.get("id", "") for m in d.get("data", [])]
        return sorted({i for i in ids if re.match(r"^(gpt-|o\d|chatgpt-)", i)
                       and not any(x in i for x in bad)}, reverse=True)
    if provider in ("openrouter", "custom"):
        base = OPENROUTER_BASE if provider == "openrouter" else _norm_base(base_url)
        if not base:
            raise RuntimeError("សូមបញ្ចូល Base URL ជាមុនសិន")
        d = _api_request(base + "/models", headers={"Authorization": f"Bearer {key}"}, timeout=25)
        ids = []
        for m in d.get("data", []):
            mid = str(m.get("id", ""))
            outs = (m.get("architecture") or {}).get("output_modalities")
            if mid and (not outs or "text" in outs):
                ids.append(mid)
        return sorted(set(ids))
    return []


def pick_default_model(provider, models, saved=""):
    if saved and saved in models:
        return saved
    for m in models:
        if (provider == "gemini" and "flash" in m) or (provider == "openai" and m.startswith("gpt") and "mini" in m) \
                or (provider == "openrouter" and m.startswith("google/gemini") and "flash" in m and ":free" not in m):
            return m
    return models[0] if models else ""


def _ai_system_prompt(target, summary, glossary):
    lang = LANG_NAMES.get(target, target)
    p = (f"You are a professional subtitle translator for a TV drama / story series. "
         f"Translate the subtitle lines into natural, spoken {lang} that sounds good when read aloud by a voice actor.\n"
         "Rules:\n"
         "- Understand the story context: who speaks to whom, tone, relationships, slang and idioms; "
         "translate the meaning, not word by word.\n"
         "- Use 'context_before', 'previous_translations' and 'context_after' ONLY to understand the scene. "
         "Do not translate or output them.\n"
         "- Keep every line's id. Return exactly one translation per input line. Never merge, split, skip or add lines.\n"
         "- Keep each translation concise (similar spoken length to the source) so it fits the same time slot.\n"
         "- Keep character names consistent. Follow the glossary exactly when a term appears in it.\n"
         "- Do not add notes, explanations or quotation marks.\n"
         '- Output ONLY valid JSON: {"lines":[{"id":1,"text":"..."}]}\n')
    if summary.strip():
        p += "\nSTORY SUMMARY / CHARACTERS:\n" + summary.strip() + "\n"
    if glossary.strip():
        p += "\nGLOSSARY (source = target):\n" + glossary.strip() + "\n"
    return p


def _ai_call(provider, key, model, system, user, base_url=""):
    if provider == "gemini":
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               + urllib.parse.quote(model, safe="") + ":generateContent")
        payload = {"systemInstruction": {"parts": [{"text": system}]},
                   "contents": [{"role": "user", "parts": [{"text": user}]}],
                   "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"}}
        d = _api_request(url, payload, {"x-goog-api-key": key})
        cands = d.get("candidates") or []
        if not cands:
            raise RuntimeError("Gemini returned no candidates (blocked?)")
        parts = (cands[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if provider in ("openrouter", "custom"):
        base = OPENROUTER_BASE if provider == "openrouter" else _norm_base(base_url)
        if not base:
            raise ApiError(400, "Base URL is empty")
        hdr = {"Authorization": f"Bearer {key}"}
        if provider == "openrouter":
            hdr.update({"HTTP-Referer": "https://t.me/Trakula168", "X-Title": "TTV Text To Voice"})
        # no response_format here: many routed models reject it; the prompt already demands JSON
        payload = {"model": model, "temperature": 0.3,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        d = _api_request(base + "/chat/completions", payload, hdr, timeout=120)
        if d.get("error"):
            e = d["error"]
            raise ApiError(int(e.get("code", 500)) if str(e.get("code", "")).isdigit() else 500,
                           str(e.get("message", e))[:300] if isinstance(e, dict) else str(e)[:300])
        return d["choices"][0]["message"].get("content") or ""
    payload = {"model": model,
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
               "response_format": {"type": "json_object"}}
    d = _api_request("https://api.openai.com/v1/chat/completions", payload,
                     {"Authorization": f"Bearer {key}"})
    return d["choices"][0]["message"].get("content") or ""


def _parse_ai_lines(raw):
    raw = raw.strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, flags=re.S) or re.search(r"\[.*\]", raw, flags=re.S)
        if not m:
            raise
        data = json.loads(m.group(0))
    items = data.get("lines", data) if isinstance(data, dict) else data
    out = {}
    for it in items:
        try:
            t = str(it.get("text", "")).strip()
            if t:
                out[int(it["id"])] = t
        except Exception:
            continue
    return out


def _ai_batch(cfg, system, user):
    """One batch call with retry. 400/401/403/404 -> FatalApiError."""
    delays = [4, 10, 20]
    last = None
    for attempt in range(len(delays) + 1):
        try:
            return _parse_ai_lines(_ai_call(cfg["provider"], cfg["key"], cfg["model"], system, user, cfg.get("base_url", "")))
        except ApiError as e:
            if e.status in (400, 401, 403, 404):
                raise FatalApiError(str(e))
            last = e
        except Exception as e:
            last = e
        if attempt < len(delays):
            time.sleep(delays[attempt])
    raise last


def translate_lines(lines, target, cfg, progress=None):
    """Translate a list of strings (empty / symbol-only ones are kept as is).
    cfg: provider ('gemini' | 'openai' | 'google'), key, model, batch, summary, glossary.
    Returns (results, failed, fallback): failed = lines left untranslated,
    fallback = lines the AI could not do that Google Translate did instead."""
    results = list(lines)
    idx = [i for i, t in enumerate(lines) if re.search(r"[\w\u1780-\u17ff]", t)]
    total = max(1, len(idx))
    state = {"done": 0, "failed": 0, "fallback": 0}

    def google_one(i):
        try:
            results[i] = translate_text(lines[i], target)
            return True
        except Exception:
            return False

    def google_many(ids, is_fallback):
        with ThreadPoolExecutor(max_workers=4) as ex:
            for ok in ex.map(google_one, ids):
                state["done"] += 1
                if not ok:
                    state["failed"] += 1
                elif is_fallback:
                    state["fallback"] += 1
                if progress:
                    progress(int(state["done"] / total * 100))

    if cfg.get("provider", "google") == "google" or not cfg.get("key") or not cfg.get("model"):
        google_many(idx, False)
        return results, state["failed"], 0

    try:
        bs = max(5, min(60, int(cfg.get("batch") or 25)))
    except Exception:
        bs = 25
    system = _ai_system_prompt(target, cfg.get("summary", ""), cfg.get("glossary", ""))
    use_ai, quota_fail = True, 0
    for b in range(0, len(idx), bs):
        ids = idx[b:b + bs]
        if not use_ai:
            google_many(ids, True)
            continue
        first, last_i = ids[0], ids[-1]
        user = json.dumps({
            "context_before": [l for l in lines[max(0, first - 4):first] if l.strip()],
            "previous_translations": [l for l in results[max(0, first - 4):first] if l.strip()],
            "context_after": [l for l in lines[last_i + 1:last_i + 4] if l.strip()],
            "lines": [{"id": k + 1, "text": lines[i]} for k, i in enumerate(ids)],
        }, ensure_ascii=False)
        try:
            got = _ai_batch(cfg, system, user)
            quota_fail = 0
        except FatalApiError:
            raise
        except Exception as e:
            got = {}
            if isinstance(e, ApiError) and e.status == 429:
                quota_fail += 1
                if quota_fail >= 2:      # quota exhausted -> finish the rest with Google Translate
                    use_ai = False
        missing = []
        for k, i in enumerate(ids):
            t = got.get(k + 1)
            if t:
                results[i] = t
                state["done"] += 1
            else:
                missing.append(i)
        if progress:
            progress(int(state["done"] / total * 100))
        if missing:
            google_many(missing, True)
    return results, state["failed"], state["fallback"]


def translate_plain(text, target, cfg, progress=None):
    """Translate free text line by line (line breaks kept). Returns (text, failed, fallback)."""
    lines = text.split("\n")
    res, failed, fb = translate_lines(lines, target, cfg, progress)
    return "\n".join(res), failed, fb


def translate_srt(text, target, cfg, progress=None):
    """Translate only the subtitle text of an SRT; indexes and timecodes stay untouched.
    Returns (srt_text, failed, fallback)."""
    blocks = [b for b in re.split(r"\n\s*\n+", text.strip()) if b.strip()]
    parsed = []  # (header_lines, text_to_translate)
    for b in blocks:
        lines = [l for l in b.split("\n") if l.strip()]
        ti = next((i for i, l in enumerate(lines) if SRT_TIME_RE.search(l)), None)
        if ti is None:
            parsed.append((lines, ""))
            continue
        parsed.append((lines[:ti + 1], " ".join(l.strip() for l in lines[ti + 1:])))
    res, failed, fb = translate_lines([t for _, t in parsed], target, cfg, progress)
    out = ["\n".join(h + ([r] if r else [])) for (h, _), r in zip(parsed, res)]
    return "\n\n".join(out) + "\n", failed, fb


# --------------------------------------------------------------------------- #
# TTS engine
# --------------------------------------------------------------------------- #
async def tts_save(text, voice_id, rate, pitch, out_path, attempts=3, timeout=25.0, sem=None):
    for attempt in range(attempts):
        try:
            if sem:
                async with sem:
                    await asyncio.wait_for(
                        edge_tts.Communicate(text, voice_id, rate=rate, pitch=pitch).save(out_path), timeout)
            else:
                await asyncio.wait_for(
                    edge_tts.Communicate(text, voice_id, rate=rate, pitch=pitch).save(out_path), timeout)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
                return True
        except Exception:
            pass
        await asyncio.sleep(0.8 * (attempt + 1))
    return False


def generate_tts(text, voice_name, rate_str, out_path, workdir, smart_read=True,
                 auto_sync=True, progress=None, max_speedup=None):
    """Create audio for plain text or SRT text. Returns out_path."""
    progress = progress or (lambda p, m: None)
    with _SYNC_LOCK:
        SYNC_REPORT.update(late=0, total=0)
    cap = float(max_speedup) if max_speedup else MAX_SPEEDUP
    voice_id, pitch, eff_rate, rate_offset = resolve_voice_params(voice_name, rate_str)
    text = text.replace("\ufeff", "").replace("\u00ad", "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    if SRT_TIME_RE.search(text):
        return _generate_srt(text, voice_id, pitch, eff_rate, rate_offset, rate_str,
                             out_path, workdir, auto_sync, progress, cap)

    if smart_read:
        text = optimize_text_for_reading(text)
    chunks = split_khmer_text(text, 1000) or ([text.strip()] if text.strip() else [])
    if not chunks:
        raise RuntimeError("អត្ថបទទំនេរ មិនអាចបង្កើតសំឡេងបានទេ!")

    if len(chunks) == 1:
        progress(30, "១. កំពុងបង្កើតសំឡេង (TTS)...")
        ok = asyncio.run(tts_save(chunks[0], voice_id, eff_rate, pitch, out_path, attempts=4, timeout=60))
        if not ok:
            raise RuntimeError("មិនអាចបង្កើតសំឡេងបានទេ! សូមពិនិត្យមើលការតភ្ជាប់អ៊ីនធឺណិត ឬសាកល្បងម្ដងទៀត។")
        progress(100, "១. បង្កើតសំឡេងរួចរាល់")
        return out_path

    total = len(chunks)
    progress(10, f"១. កំពុងរៀបចំអត្ថបទ ({total} ផ្នែក)...")
    files = [os.path.join(workdir, f"chunk_{i}.mp3") for i in range(total)]
    done = 0

    async def run_all():
        nonlocal done
        sem = asyncio.Semaphore(2)

        async def one(i):
            nonlocal done
            ok = await tts_save(chunks[i], voice_id, eff_rate, pitch, files[i], attempts=4, timeout=25, sem=sem)
            done += 1
            progress(int(10 + done / total * 75), f"១. កំពុងបង្កើតសំឡេង ({done}/{total})...")
            return ok

        return await asyncio.gather(*[one(i) for i in range(total)])

    results = asyncio.run(run_all())
    failed = [i for i, ok in enumerate(results) if not ok]
    if failed:
        progress(85, f"១. កំពុងទាញយកឡើងវិញនូវផ្នែកដែលខកខាន ({len(failed)} ផ្នែក)...")

        async def retry():
            for i in failed:
                if await tts_save(chunks[i], voice_id, eff_rate, pitch, files[i], attempts=3, timeout=25):
                    results[i] = True
        asyncio.run(retry())
        still = [i for i, ok in enumerate(results) if not ok]
        if still:
            raise RuntimeError(f"មិនអាចបង្កើតសំឡេងបានគ្រប់គ្រាន់ទេ (បរាជ័យផ្នែកទី {still[0] + 1}/{total})។")

    progress(92, "១. កំពុងភ្ជាប់សំឡេង (Audio Stitching)...")
    lst = os.path.join(workdir, "concat.txt")
    write_concat_list(lst, files)
    ok = False
    res = run_ffmpeg(["-f", "concat", "-safe", "0", "-i", lst, "-c:a", "libmp3lame", "-b:a", "192k", out_path])
    if res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        ok = True
    else:
        res = run_ffmpeg(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out_path])
        ok = res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1000
    if not ok:  # last resort: raw MP3 byte concatenation
        with open(out_path, "wb") as out:
            for f in files:
                with open(f, "rb") as src:
                    out.write(src.read())
    progress(100, "១. បង្កើតសំឡេងរួចរាល់")
    return out_path


def _generate_srt(text, voice_id, pitch, eff_rate, rate_offset, user_rate_str,
                  out_path, workdir, auto_sync, progress, max_speedup=MAX_SPEEDUP):
    entries = parse_srt(text)
    total = len(entries)
    if not entries:
        raise RuntimeError("រកមិនឃើញទិន្នន័យអត្ថបទក្នុងឯកសារ SRT ឡើយ!")
    try:
        user_speed = int(str(user_rate_str).replace("%", "").replace("+", ""))
    except Exception:
        user_speed = 0

    clips = [None] * total
    done = 0

    async def process(idx, e, sem):
        nonlocal done
        hard = e["hard_limit"]
        rate = eff_rate          # the voice keeps the speed chosen by the user (no blind pre-speed-up)
        raw = os.path.join(workdir, f"raw_{idx}.mp3")
        ok = await tts_save(e["text"], voice_id, rate, pitch, raw, attempts=3, timeout=15, sem=sem)
        if not ok:  # one more slow retry
            await asyncio.sleep(1.0)
            ok = await tts_save(e["text"], voice_id, rate, pitch, raw, attempts=2, timeout=12, sem=sem)
        if ok:
            final = os.path.join(workdir, f"std_{idx}.wav")

            def build():
                if auto_sync:
                    actual = audio_duration(raw)
                    with _SYNC_LOCK:
                        SYNC_REPORT["total"] += 1
                    if actual > hard:
                        need = actual / max(0.1, hard - 0.03)
                        factor = max(1.0, min(max_speedup, need))      # capped -> never rushed
                        if factor > 1.01:
                            adjust_tempo(raw, final, factor, max_len=hard + SYNC_OVERRUN)
                        else:
                            standardize_clip(raw, final, max_len=hard + SYNC_OVERRUN)
                        if actual / factor > hard + 0.05:
                            with _SYNC_LOCK:
                                SYNC_REPORT["late"] += 1
                    else:
                        standardize_clip(raw, final, max_len=hard)
                else:
                    standardize_clip(raw, final)
                if not (os.path.exists(final) and os.path.getsize(final) > 100):
                    standardize_clip(raw, final)
            await asyncio.to_thread(build)
            if os.path.exists(final):
                clips[idx] = (e["start_time"], final)
        done += 1
        progress(int(done / total * 85), f"១. កំពុងបង្កើតសំឡេង SRT ({done}/{total})...")

    async def run_all():
        sem = asyncio.Semaphore(3)
        await asyncio.gather(*[process(i, e, sem) for i, e in enumerate(entries)])

    asyncio.run(run_all())
    valid = [c for c in clips if c and os.path.exists(c[1])]
    if not valid:
        raise RuntimeError("មិនអាចទាញយកសំឡេងពីបន្ទាត់ SRT បានឡើយ សូមពិនិត្យមើលអ៊ីនធឺណិត ឬឯកសារ SRT!")
    progress(88, "១. កំពុងភ្ជាប់សំឡេងតាម Timecode...")
    max_end = max(e["end_time"] for e in entries)
    combine_timeline(valid, out_path, workdir, max_duration=max_end if max_end > 0 else None)
    progress(100, "១. បង្កើតសំឡេង SRT រួចរាល់")
    return out_path


# --------------------------------------------------------------------------- #
# Cloud voice clone (Hugging Face Gradio Space)
# --------------------------------------------------------------------------- #
_HF_TOKEN_LOCK = threading.Lock()
_HF_TOKEN_CURSOR = 0


def parse_hf_tokens(value):
    """Accept a list or a string (newline / comma / space separated); return unique, non-empty tokens."""
    if value is None:
        return []
    if isinstance(value, str):
        value = re.split(r"[\s,;]+", value)
    out, seen = [], set()
    for t in value:
        t = str(t).strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _is_quota_error(msg):
    m = str(msg).lower()
    return any(k in m for k in ("zerogpu", "429", "quota", "rate limit", "too many requests",
                                "401", "unauthorized", "invalid token", "expired"))


def run_cloud_voice_clone(input_path, output_path, server="", ref_audio="", hf_token="", text_prompt=""):
    """Convert `input_path` to the voice of `ref_audio` using a public Gradio Space.
    `hf_token` may be a single token or a list of tokens. When one token hits the quota
    (ZeroGPU / 429 / 401) the next token is tried automatically. The starting token rotates
    on every call so the load is spread across all tokens.
    The Space's API can change; adjust the predict() calls below if it does."""
    global _HF_TOKEN_CURSOR
    from gradio_client import Client, handle_file
    if not ref_audio or not os.path.exists(ref_audio):
        raise RuntimeError("សូម Upload សំឡេងគំរូ ១០ វិនាទី (Sample Audio) ជាមុនសិន!")
    tokens = parse_hf_tokens(hf_token) or parse_hf_tokens(os.environ.get("HF_TOKEN", ""))
    if tokens:
        with _HF_TOKEN_LOCK:
            k = _HF_TOKEN_CURSOR % len(tokens)
            _HF_TOKEN_CURSOR += 1
        tokens = tokens[k:] + tokens[:k]
    else:
        tokens = [None]  # anonymous (very limited quota)
    servers = [server.strip().rstrip("/")] if server and server.strip() else [
        DEFAULT_CLOUD_SERVER, "mrfakename/E2-F5-TTS"]
    ref = handle_file(ref_audio)
    src = handle_file(input_path) if input_path and os.path.exists(input_path) else None
    last_error, result = None, None

    for token in tokens:
        for srv in servers:
            try:
                try:
                    client = Client(srv, token=token)
                except TypeError:
                    client = Client(srv, hf_token=token)
                attempts = []
                if src:
                    attempts = [
                        lambda: client.predict(src, ref, 10, 1.0, 0.7, False, False, 0, api_name="/predict"),
                        lambda: client.predict(src, ref, api_name="/predict"),
                        lambda: client.predict(src, ref),
                    ]
                elif text_prompt:
                    t = text_prompt.strip()
                    attempts = [
                        lambda: client.predict(ref_audio=ref, ref_text="", gen_text=t, remove_silence=False,
                                               api_name="/predict"),
                        lambda: client.predict(ref, "", t, api_name="/predict"),
                    ]
                quota_hit = False
                for attempt in attempts:
                    try:
                        res = attempt()
                        if res:
                            result = res
                            break
                    except Exception as ex:
                        last_error = ex
                        if _is_quota_error(ex):
                            quota_hit = True
                            break  # this token is exhausted -> go to next token
                if result or quota_hit:
                    break
            except Exception as ex:
                last_error = ex
                if _is_quota_error(ex):
                    break
        if result:
            break

    if not result:
        msg = str(last_error) if last_error else "Unknown Error"
        if _is_quota_error(msg):
            msg = (f"Token ទាំង {len(tokens) if tokens != [None] else 0} ដល់កម្រិតកំណត់កូតា (ZeroGPU)។\n"
                   "បន្ថែម Token ថ្មីៗ (ឥតគិតថ្លៃ) នៅ https://huggingface.co/settings/tokens "
                   "ក្នុងប្រអប់ 🔑 Token ឬរង់ចាំកូតាកើតឡើងវិញ។")
        raise RuntimeError(f"ការ Clone សំឡេងតាម Server បរាជ័យ:\n{msg}")

    def as_path(x):
        if isinstance(x, str) and os.path.exists(x):
            return x
        if isinstance(x, dict):
            p = x.get("path") or x.get("name")
            if p and os.path.exists(p):
                return p
        return None

    out = as_path(result)
    if not out and isinstance(result, (list, tuple)):
        for item in reversed(result):
            out = as_path(item)
            if out:
                break
    if not out or os.path.getsize(out) < 100:
        raise RuntimeError("Server មិនបានបញ្ជូនឯកសារសំឡេងត្រឡប់មកវិញឡើយ!")
    shutil.copy2(out, output_path)


# --------------------------------------------------------------------------- #
# Update check
# --------------------------------------------------------------------------- #
def is_newer_version(current, latest):
    def parse(v):
        return [int(x) for x in re.findall(r"\d+", str(v))]
    try:
        return parse(latest) > parse(current)
    except Exception:
        return False


def _http_json(url, timeout=5):
    req = urllib.request.Request(url, headers={"User-Agent": "TTV-App"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_github_update_info():
    """-> (has_update, latest_version, download_url, notes)"""
    default_url = f"https://github.com/{GITHUB_REPO}/releases"
    try:
        d = _http_json(GITHUB_VERSION_URL)
        latest = str(d.get("version", "")).lstrip("v").strip()
        if latest and is_newer_version(APP_VERSION, latest):
            return True, latest, d.get("download_url", default_url), d.get("release_notes", "មានកំណែអាប់ដេតថ្មី!")
    except Exception:
        pass
    try:
        d = _http_json(GITHUB_RELEASE_API)
        latest = str(d.get("tag_name", "")).lstrip("v").strip()
        assets = d.get("assets", [])
        url = assets[0]["browser_download_url"] if assets else d.get("html_url", default_url)
        if latest and is_newer_version(APP_VERSION, latest):
            return True, latest, url, d.get("body", "មានកំណែអាប់ដេតថ្មី!")
    except Exception:
        pass
    return False, "", "", ""


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #
class App(ctk.CTk):
    BTN_TEXT = "បង្កើតសំឡេង"
    SRT_MODE_TEXT = "📄 អត្ថបទ"
    SRT_MODE_LINES = "📝 កែម្តងមួយបន្ទាត់"
    DUB_TEXT = "Dub វីដេអូ"
    TR_TEXT = "បកប្រែ"
    LISTEN_TEXT = "▶  ស្តាប់"

    def __init__(self):
        load_bundled_fonts()
        super().__init__()
        pick_font()
        self.configure(fg_color=T["bg"])
        self.ref_audio_path = ""
        self.video_path = ""
        self._srt_mode = "text"          # "text" | "lines"
        self._orig_text = ""             # source SRT before the last translation (for the line editor)
        self._voice = None               # {"path":..., "key":...} last generated voice (listen before export)
        self._voice_n = 0
        self._voice_dir = tempfile.mkdtemp(prefix="ttv_voice_")
        self.title(f"KH Dubbing v{APP_VERSION}")
        self.geometry("1280x800")
        self.minsize(1100, 680)
        icon = resource_path("app_icon.ico")
        if os.path.exists(icon):
            try:
                self.iconbitmap(icon)
            except Exception:
                pass
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.load_translate_config()
        self._build_sidebar()
        self._build_main()
        self.load_cloud_clone_config()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(150, self._maximize)          # open full screen
        threading.Thread(target=self.auto_check_update_silent, daemon=True).start()

    def _maximize(self):
        """Open the tool full screen (maximised window) on any PC."""
        try:
            self.state("zoomed")                 # Windows
            # CustomTkinter re-shows the window shortly after start-up: re-apply once if it was undone
            self.after(700, lambda: self.state("zoomed") if self.state() != "zoomed" else None)
            return
        except Exception:
            pass
        try:
            self.attributes("-zoomed", True)     # Linux
            return
        except Exception:
            pass
        try:
            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
        except Exception:
            pass

    # ---- layout -------------------------------------------------------- #
    def _build_sidebar(self):
        sb = self.sidebar_frame = ctk.CTkFrame(self, width=308, corner_radius=0, fg_color=T["sidebar"])
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_columnconfigure(0, weight=1)
        sb.grid_rowconfigure(1, weight=1)

        # ---- brand ----
        brand = ctk.CTkFrame(sb, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(22, 14))
        logo = resource_path("logo.jpg")
        if os.path.exists(logo):
            from PIL import Image
            img = Image.open(logo)
            self.ctk_logo = ctk.CTkImage(light_image=img, dark_image=img, size=(220, 110))
            ctk.CTkLabel(brand, image=self.ctk_logo, text="").pack(anchor="w")
        else:
            ctk.CTkLabel(brand, text="T", width=42, height=42, corner_radius=12, fg_color=T["accent"],
                         text_color="#FFFFFF", font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold")
                         ).pack(side="left")
            tb = ctk.CTkFrame(brand, fg_color="transparent")
            tb.pack(side="left", padx=(12, 0))
            ctk.CTkLabel(tb, text="TTV", text_color=T["text"], anchor="w",
                         font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold")).pack(anchor="w")
            ctk.CTkLabel(tb, text="Text To Voice  ·  Khmer", text_color=T["muted"], anchor="w",
                         font=ctk.CTkFont(family="Segoe UI", size=11)).pack(anchor="w")

        body = ctk.CTkScrollableFrame(sb, fg_color="transparent", corner_radius=0,
                                      scrollbar_button_color=T["border"], scrollbar_button_hover_color=T["hover"])
        body.grid(row=1, column=0, sticky="nsew", padx=(10, 4))
        body.grid_columnconfigure(0, weight=1)

        # ---- voice card ----
        vc = mkcard(body)
        vc.grid(row=0, column=0, sticky="ew", padx=6, pady=(0, 10))
        vc.grid_columnconfigure(0, weight=1)
        section_title(vc, "សំឡេងអាន  ·  VOICE").grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 6))
        self.voice_optionemenu = ctk.CTkOptionMenu(vc, values=list(KHMER_VOICE_PRESETS.keys()),
                                                   command=self.on_voice_change, **menu_style())
        self.voice_optionemenu.set(DEFAULT_VOICE_CHOICE)
        self.voice_optionemenu.grid(row=1, column=0, sticky="ew", padx=(14, 6))
        self.voice_preview_btn = mkbtn(vc, self.LISTEN_TEXT, "primary", size=11, width=76,
                                       command=self.preview_selected_voice)
        self.voice_preview_btn.grid(row=1, column=1, padx=(0, 14))
        self.voice_desc_label = ctk.CTkLabel(
            vc, text=KHMER_VOICE_PRESETS[DEFAULT_VOICE_CHOICE]["desc"], text_color=T["muted"], font=F(11),
            wraplength=236, justify="left", anchor="w")
        self.voice_desc_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=14, pady=(8, 14))

        # ---- cloud clone card ----
        card = self.cloud_clone_card = mkcard(body)
        card.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 10))
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 12))
        self.cloud_clone_enable_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(head, text="Clone សំឡេង  (Upload 10s)", variable=self.cloud_clone_enable_var,
                      command=self.on_toggle_cloud_clone, text_color=T["text"], progress_color=T["accent"],
                      button_color="#FFFFFF", fg_color=T["border"], font=F(12, "bold")).pack(side="left")
        self.cloud_clone_inner = ctk.CTkFrame(card, fg_color="transparent")
        mkbtn(self.cloud_clone_inner, "Upload សំឡេង ១០ វិនាទី (Sample Audio)", "primary", size=11,
              command=self.select_ref_audio).pack(fill="x", pady=(2, 6))
        rrow = ctk.CTkFrame(self.cloud_clone_inner, fg_color="transparent")
        rrow.pack(fill="x", pady=(0, 6))
        self.cloud_ref_file_lbl = ctk.CTkLabel(
            rrow, text="⚪ (សូម Upload សំឡេង 10s)", text_color=T["muted"], wraplength=160, justify="left",
            anchor="w", font=F(10))
        self.cloud_ref_file_lbl.pack(side="left", fill="x", expand=True)
        mkbtn(rrow, self.LISTEN_TEXT, "secondary", size=10, width=70, height=28,
              command=self.preview_ref_audio).pack(side="right")
        ctk.CTkLabel(self.cloud_clone_inner, text="Hugging Face Token  (១ បន្ទាត់ = ១ Token)",
                     text_color=T["muted"], anchor="w", font=F(10, "bold")).pack(fill="x", pady=(4, 3))
        self.hf_token_box = ctk.CTkTextbox(self.cloud_clone_inner, height=70, wrap="none", corner_radius=8,
                                           fg_color=T["surface2"], border_width=1, border_color=T["border"],
                                           text_color=T["text"], font=ctk.CTkFont(family="Consolas", size=10))
        self.hf_token_box.pack(fill="x", pady=(0, 2))
        self.hf_token_box.insert("1.0", "\n".join(getattr(self, "hf_tokens", [])))
        self.hf_token_box.bind("<FocusOut>", lambda e: self.on_tokens_changed())
        self.hf_token_count_lbl = ctk.CTkLabel(self.cloud_clone_inner, text="", text_color=T["muted"], anchor="w",
                                               font=F(9))
        self.hf_token_count_lbl.pack(fill="x", pady=(0, 4))
        self.update_token_count_label()
        self.cloud_preview_btn = mkbtn(self.cloud_clone_inner, "ស្តាប់សំឡេង Clone សាកល្បង", "success", size=10,
                                       height=30, command=self.preview_cloud_clone)
        self.cloud_preview_btn.pack(fill="x", pady=(2, 8))

        # ---- speed card ----
        sc = mkcard(body)
        sc.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 10))
        sc.grid_columnconfigure(0, weight=1)
        section_title(sc, "ល្បឿន  ·  SPEED").grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))
        self.speed_label = ctk.CTkLabel(sc, text="ល្បឿនអាន (Speed): 0%", font=F(12, "bold"),
                                        text_color=T["text"], anchor="w")
        self.speed_label.grid(row=1, column=0, padx=14, sticky="w")
        self.speed_slider = ctk.CTkSlider(sc, from_=-50, to=50, command=self.update_speed_label, **slider_style())
        self.speed_slider.set(0)
        self.speed_slider.grid(row=2, column=0, padx=14, pady=(6, 10), sticky="ew")
        ctk.CTkFrame(sc, height=1, fg_color=T["border"]).grid(row=3, column=0, sticky="ew", padx=14)
        self.max_speed_label = ctk.CTkLabel(sc, text="", anchor="w", justify="left", wraplength=236,
                                            text_color=T["text"], font=F(12, "bold"))
        self.max_speed_label.grid(row=4, column=0, padx=14, pady=(10, 0), sticky="w")
        self.max_speed_slider = ctk.CTkSlider(sc, from_=1.0, to=2.0, number_of_steps=20,
                                              command=self.update_max_speed_label, **slider_style())
        self.max_speed_slider.set(MAX_SPEEDUP)
        self.max_speed_slider.grid(row=5, column=0, padx=14, pady=(6, 14), sticky="ew")
        self.max_speedup = MAX_SPEEDUP
        self.update_max_speed_label(MAX_SPEEDUP)

        # ---- footer ----
        foot = ctk.CTkFrame(sb, fg_color="transparent")
        foot.grid(row=2, column=0, sticky="ew", padx=16, pady=(6, 14))
        foot.grid_columnconfigure(0, weight=1)
        cp = ctk.CTkLabel(foot, text="KH Dubbing", text_color=T["muted"], cursor="hand2",
                          font=F(10))
        cp.grid(row=0, column=0, pady=(0, 6))
        cp.bind("<Button-1>", lambda e: webbrowser.open(CONTACT_URL))
        cp.bind("<Enter>", lambda e: cp.configure(text_color=T["info"]))
        cp.bind("<Leave>", lambda e: cp.configure(text_color=T["muted"]))
        mkbtn(foot, f"ពិនិត្យអាប់ដេត  (v{APP_VERSION})", "secondary", size=11, height=32,
              command=self.manual_check_update).grid(row=1, column=0, sticky="ew")

    def _build_main(self):
        main = self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=22)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)

        # two separate zones, both ready before any video is imported:
        #   LEFT  = SRT / text (+ audio preview below it)      RIGHT = video
        work = self.work_frame = ctk.CTkFrame(main, fg_color="transparent")
        work.grid(row=0, column=0, sticky="nsew", pady=(20, 0))
        work.grid_rowconfigure(0, weight=1)
        work.grid_columnconfigure(0, weight=1, uniform="zone")
        work.grid_columnconfigure(1, weight=1, uniform="zone")

        # ================= LEFT: SRT zone =================
        left = self.srt_zone = ctk.CTkFrame(work, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(left, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        head.grid_columnconfigure(0, weight=1)
        titles = ctk.CTkFrame(head, fg_color="transparent")
        titles.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(titles, text="SRT / អត្ថបទ", font=F(20, "bold"), text_color=T["text"], anchor="w").pack(anchor="w")
        ctk.CTkLabel(titles, text="វាយ បិទភ្ជាប់ ឬនាំចូល SRT រួចបកប្រែ និងកែ", font=F(11), text_color=T["muted"],
                     anchor="w").pack(anchor="w")
        self.srt_mode_btn = ctk.CTkSegmentedButton(
            head, values=[self.SRT_MODE_TEXT, self.SRT_MODE_LINES], command=self._on_srt_mode, font=F(12),
            height=32, fg_color=T["surface2"], selected_color=T["accent"], selected_hover_color=T["accent_h"],
            unselected_color=T["surface2"], unselected_hover_color=T["hover"], text_color=T["text"])
        self.srt_mode_btn.grid(row=0, column=1, sticky="e")
        self.srt_mode_btn.set(self.SRT_MODE_TEXT)

        tools = ctk.CTkFrame(left, fg_color="transparent")
        tools.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        mkbtn(tools, "បិទភ្ជាប់", "secondary", width=84, command=self.paste_clipboard_text).pack(side="left", padx=(0, 6))
        mkbtn(tools, "នាំចូល SRT", "secondary", width=96, command=self.import_srt).pack(side="left", padx=3)
        mkbtn(tools, "សម្អាត", "danger", width=72, command=self.clear_text).pack(side="left", padx=3)
        self.translate_btn = mkbtn(tools, self.TR_TEXT, "primary", width=92, command=self.start_translate)
        self.translate_btn.pack(side="right")
        mkbtn(tools, "⚙", "secondary", width=36, size=15, command=self.open_translate_settings).pack(side="right", padx=(0, 6))

        self.srt_stack = ctk.CTkFrame(left, fg_color="transparent")
        self.srt_stack.grid(row=2, column=0, sticky="nsew")
        self.srt_stack.grid_rowconfigure(0, weight=1)
        self.srt_stack.grid_columnconfigure(0, weight=1)
        self.textbox = ctk.CTkTextbox(self.srt_stack, wrap="word", font=F(15), fg_color=T["surface"],
                                      text_color=T["text"], border_width=1, border_color=T["border"],
                                      corner_radius=14, scrollbar_button_color=T["border"],
                                      scrollbar_button_hover_color=T["hover"])
        self.textbox.grid(row=0, column=0, sticky="nsew")
        try:   # inner padding + calmer line spacing for Khmer
            self.textbox._textbox.configure(padx=16, pady=14, spacing1=2, spacing3=4,
                                            insertbackground=T["accent"], selectbackground=T["accent"])
            self.textbox.bind("<FocusIn>", lambda e: self.textbox.configure(border_color=T["accent"]))
            self.textbox.bind("<FocusOut>", lambda e: self.textbox.configure(border_color=T["border"]))
        except Exception:
            pass
        self.line_editor = SrtLineEditor(self.srt_stack, on_seek=self._seek_video)
        self.line_editor.grid(row=0, column=0, sticky="nsew")
        self.line_editor.grid_remove()
        self.setup_textbox_khmer_editing()
        self.setup_textbox_khmer_editing(self.line_editor.edit_box)

        # audio preview sits right behind (below) the SRT
        self.audio_panel = AudioPanel(left)
        self.audio_panel.grid(row=3, column=0, sticky="ew", pady=(10, 0))

        # ================= RIGHT: video zone =================
        right = self.video_zone = ctk.CTkFrame(work, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        vh = ctk.CTkFrame(right, fg_color="transparent")
        vh.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        vh.grid_columnconfigure(0, weight=1)
        vt = ctk.CTkFrame(vh, fg_color="transparent")
        vt.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(vt, text="វីដេអូ", font=F(20, "bold"), text_color=T["text"], anchor="w").pack(anchor="w")
        ctk.CTkLabel(vt, text="មើល កាត់ និង Dub ជាសំឡេងខ្មែរ", font=F(11), text_color=T["muted"],
                     anchor="w").pack(anchor="w")
        mkbtn(vh, "នាំចូលវីដេអូ", "secondary", width=130, command=self.import_video).grid(row=0, column=1, sticky="e")
        self.video_panel = VideoPanel(right, on_close=self.close_video, on_export=self.export_trim,
                                      on_import=self.import_video)
        self.video_panel.grid(row=1, column=0, sticky="nsew")

        # ---- options card ----
        oc = mkcard(main)
        oc.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        oc.grid_columnconfigure(0, weight=1)
        r1 = ctk.CTkFrame(oc, fg_color="transparent")
        r1.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))
        cb = dict(checkbox_width=20, checkbox_height=20, corner_radius=6, border_width=2, fg_color=T["accent"],
                  hover_color=T["accent_h"], border_color=T["hover"], text_color=T["text"], font=F(12))
        self.smart_read_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(r1, text="អានឆ្លាតវៃ (Smart Pause)", variable=self.smart_read_var, **cb
                        ).pack(side="left", padx=(0, 18))
        self.auto_sync_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(r1, text="តម្រូវល្បឿនតាម Timecode (Auto Sync)", variable=self.auto_sync_var, **cb
                        ).pack(side="left")
        self.translate_lang_var = ctk.StringVar(value=DEFAULT_TRANSLATE_LANG)
        ctk.CTkOptionMenu(r1, values=list(TRANSLATE_LANGS.keys()), variable=self.translate_lang_var,
                          **menu_style(width=150, height=30)).pack(side="right")
        ctk.CTkLabel(r1, text="បកប្រែទៅ", font=F(12), text_color=T["muted"]).pack(side="right", padx=(0, 8))

        ctk.CTkFrame(oc, height=1, fg_color=T["border"]).grid(row=1, column=0, sticky="ew", padx=16)
        r2 = ctk.CTkFrame(oc, fg_color="transparent")
        r2.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 12))
        self.orig_vol_label = ctk.CTkLabel(r2, text="", font=F(12), text_color=T["text"], width=280, anchor="w")
        self.orig_vol_label.pack(side="left")
        self.char_lbl = ctk.CTkLabel(r2, text="0 តួអក្សរ", font=F(11), text_color=T["muted"], anchor="e")
        self.char_lbl.pack(side="right", padx=(12, 0))
        self.orig_vol_slider = ctk.CTkSlider(r2, from_=0, to=100, number_of_steps=20,
                                             command=self.update_orig_vol_label, **slider_style())
        self.orig_vol_slider.set(0)
        self.orig_vol_slider.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.update_orig_vol_label(0)

        # ---- action bar ----
        ab = ctk.CTkFrame(main, fg_color="transparent")
        ab.grid(row=2, column=0, sticky="ew", pady=(14, 20))
        ab.grid_columnconfigure(0, weight=1)
        self.progress_label = ctk.CTkLabel(ab, text="", font=F(12), text_color=T["muted"], anchor="w")
        self.progress_label.grid(row=0, column=0, sticky="ew")
        self.progressbar = ctk.CTkProgressBar(ab, height=6, corner_radius=3, fg_color=T["border"],
                                              progress_color=T["accent"])
        self.progressbar.grid(row=1, column=0, sticky="ew", pady=(4, 14))
        self.progressbar.set(0)
        btns = ctk.CTkFrame(ab, fg_color="transparent")
        btns.grid(row=2, column=0, sticky="ew")
        for c in range(3):
            btns.grid_columnconfigure(c, weight=1, uniform="act")
        self.save_mp3_btn = mkbtn(btns, self.BTN_TEXT, "primary", height=50, size=15, corner_radius=12,
                                  command=self.start_voice_generation)
        self.save_mp3_btn.grid(row=0, column=0, sticky="ew")
        self.export_mp3_btn = mkbtn(btns, "រក្សាទុក MP3", "secondary", height=50, size=15, corner_radius=12,
                                    command=self.export_voice_mp3)
        self.export_mp3_btn.grid(row=0, column=1, padx=(10, 0), sticky="ew")
        self.dub_btn = mkbtn(btns, self.DUB_TEXT, "success", height=50, size=15, corner_radius=12,
                             command=self.start_dub)
        self.dub_btn.grid(row=0, column=2, padx=(10, 0), sticky="ew")

        self._char_n = -1
        self._tick_chars()

    # ---- SRT view mode: plain text <-> line-by-line editor ---------------- #
    def _current_text(self):
        """The text to translate / voice / dub (always includes edits made in the line editor)."""
        if self._srt_mode == "lines":
            try:
                return self.line_editor.get_text()
            except Exception:
                pass
        return self.textbox.get("1.0", "end-1c")

    def _on_srt_mode(self, value):
        self._set_srt_mode("lines" if value == self.SRT_MODE_LINES else "text")

    def _ensure_text_mode(self):
        self._set_srt_mode("text")

    def _set_srt_mode(self, mode):
        if mode == self._srt_mode:
            return
        if mode == "lines":
            text = self.textbox.get("1.0", "end-1c")
            if not text.strip():
                messagebox.showinfo("SRT", "សូមនាំចូល SRT ឬបិទភ្ជាប់អត្ថបទជាមុនសិន!")
                self.srt_mode_btn.set(self.SRT_MODE_TEXT)
                return
            if not SRT_TIME_RE.search(text):
                messagebox.showinfo("SRT", "ការកែម្តងមួយបន្ទាត់ ត្រូវការ SRT ដែលមាន Timecode "
                                           "(ឧ. 00:00:01,000 --> 00:00:03,000)។")
                self.srt_mode_btn.set(self.SRT_MODE_TEXT)
                return
            self.line_editor.load(text, self._orig_text)
            self.textbox.grid_remove()
            self.line_editor.grid()
            self._srt_mode = "lines"
            self.srt_mode_btn.set(self.SRT_MODE_LINES)
        else:
            text = self.line_editor.get_text()
            self.line_editor.grid_remove()
            self.textbox.grid()
            self._srt_mode = "text"
            self.srt_mode_btn.set(self.SRT_MODE_TEXT)
            if self.textbox.get("1.0", "end-1c").strip() != text.strip():
                inner = self.textbox._textbox
                try:
                    inner.edit_separator()
                except Exception:
                    pass
                self.textbox.delete("1.0", "end")
                self.textbox.insert("1.0", text)
                try:
                    inner.edit_separator()
                except Exception:
                    pass

    def _seek_video(self, t):
        if self.video_path:
            try:
                self.video_panel.seek_to(t)
            except Exception:
                pass

    # ---- generated voice: is it still up to date? -------------------------- #
    def _voice_key(self, text=None):
        text = self._current_text() if text is None else text
        cloud = bool(self.cloud_clone_enable_var.get())
        parts = [text.strip(), self.voice_optionemenu.get(), fmt_rate(self.speed_slider.get()),
                 str(self.smart_read_var.get()), str(self.auto_sync_var.get()),
                 str(round(self.max_speed_slider.get(), 2)), str(cloud),
                 self.ref_audio_path if cloud else ""]
        return hashlib.md5("\u241f".join(parts).encode("utf-8")).hexdigest()

    def _refresh_voice_state(self, text):
        v = self._voice
        if not v:
            self.audio_panel.set_state("none")
        elif v["key"] == self._voice_key(text):
            self.audio_panel.set_state("fresh")
        else:
            self.audio_panel.set_state("stale")

    def _tick_chars(self):
        """Live character counter + 'voice is out of date' check (polled, so paste / import / translate / edits are all covered)."""
        text = None
        try:
            text = self._current_text()
            n = len(text)
            if n != self._char_n:
                self._char_n = n
                self.char_lbl.configure(text=f"{n:,} តួអក្សរ")
        except Exception:
            pass
        try:
            if text is not None:
                self._refresh_voice_state(text)
        except Exception:
            pass
        try:
            self.after(500, self._tick_chars)
        except Exception:
            pass

    # ---- small UI helpers ---------------------------------------------- #
    def update_progress(self, pct, text=""):
        val = max(0, min(100, int(pct)))
        label = f"{text} {val}%" if text and not text.endswith("%") else text
        self.after(0, lambda: (self.progressbar.set(val / 100.0), self.progress_label.configure(text=label)))

    def update_speed_label(self, value):
        v = int(value)
        self.speed_label.configure(text=f"ល្បឿនអាន (Speed): {'+' if v > 0 else ''}{v}%")

    def update_max_speed_label(self, value):
        v = float(value)
        hint = "មិនបង្កើនល្បឿន" if v <= 1.001 else "សំឡេងកាន់តែញាប់ បើតម្លៃកាន់តែខ្ពស់"
        self.max_speed_label.configure(text=f"ល្បឿនបង្កើនអតិបរមា (Auto Sync): {v:.2f}x\n{hint}")

    def on_voice_change(self, choice):
        p = KHMER_VOICE_PRESETS.get(choice)
        if p:
            self.voice_desc_label.configure(text=p.get("desc", ""))
            if hasattr(self, "translate_lang_var"):
                vid = p.get("voice_id", "")
                for name, code in TRANSLATE_LANGS.items():
                    if vid.lower().startswith(code.split("-")[0].lower() + "-"):
                        self.translate_lang_var.set(name)
                        break

    # ---- text box ------------------------------------------------------- #
    def clear_text(self):
        self._ensure_text_mode()
        self.textbox.delete("1.0", "end")
        self._orig_text = ""
        self.update_progress(0, "")

    def paste_clipboard_text(self, tb=None):
        try:
            clip = self.clipboard_get()
        except Exception:
            return
        if clip:
            inner = (tb if tb is not None else self.textbox)._textbox
            try:
                inner.delete("sel.first", "sel.last")
            except Exception:
                pass
            inner.insert("insert", clip)
            inner.see("insert")

    def import_srt(self):
        self._ensure_text_mode()
        path = filedialog.askopenfilename(title="ជ្រើសរើសឯកសារ SRT",
                                          filetypes=[("SRT Files", "*.srt"), ("All Files", "*.*")])
        if not path:
            return
        try:
            content = None
            for enc in ("utf-8-sig", "utf-8", "utf-16", "utf-16-le", "utf-16-be", "cp1252", "latin-1"):
                try:
                    with open(path, "r", encoding=enc) as f:
                        content = f.read()
                    break
                except Exception:
                    continue
            if content is None:
                raise RuntimeError("មិនអាចកំណត់ប្រភេទ Encoding នៃឯកសារបានឡើយ!")
            content = content.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
            self.textbox.delete("1.0", "end")
            self.textbox.insert("1.0", content)
            self._orig_text = ""
        except Exception as e:
            messagebox.showerror("Error", f"មិនអាចអានឯកសារបានទេ:\n{e}")

    # ---- translate settings (AI provider / key / model / story context) -- #
    def _translate_config_path(self):
        base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
            else os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, "translate_config.json")

    def load_translate_config(self):
        self.tr_cfg = {"provider": "gemini", "keys": {}, "models": {}, "batch": 25,
                       "summary": "", "glossary": ""}
        try:
            with open(self._translate_config_path(), "r", encoding="utf-8") as f:
                self.tr_cfg.update(json.load(f))
        except Exception:
            pass
        self._tr_models_cache = {}
        self._tr_win = None

    def save_translate_config(self):
        try:
            with open(self._translate_config_path(), "w", encoding="utf-8") as f:
                json.dump(self.tr_cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _effective_translate_cfg(self):
        prov = self.tr_cfg.get("provider", "gemini")
        return {"provider": prov, "key": self.tr_cfg.get("keys", {}).get(prov, "").strip(),
                "model": self.tr_cfg.get("models", {}).get(prov, ""),
                "batch": self.tr_cfg.get("batch", 25), "summary": self.tr_cfg.get("summary", ""),
                "glossary": self.tr_cfg.get("glossary", ""),
                "base_url": self.tr_cfg.get("base_urls", {}).get(prov, "")}

    def open_translate_settings(self):
        if self._tr_win is not None:
            try:
                if self._tr_win.winfo_exists():
                    self._tr_win.deiconify()
                    self._tr_win.lift()
                    self._tr_win.focus_force()
                    return
            except Exception:
                pass
        F = lambda s=13, w="normal": ctk.CTkFont(family=FONT_MAIN, size=s, weight=w)
        win = ctk.CTkToplevel(self)
        win.configure(fg_color=T["bg"])
        self._tr_win = win
        win.title("ការកំណត់ការបកប្រែ (AI Translate)")
        try:
            _sh = win.winfo_screenheight()
        except Exception:
            _sh = 768
        _h = max(420, min(860, _sh - 120))
        win.geometry(f"580x{_h}+{max(0, (win.winfo_screenwidth() - 580) // 2)}+20")
        win.minsize(540, 420)
        win.transient(self)
        # Footer (Save button) is pinned at the bottom; form scrolls above it.
        footer = ctk.CTkFrame(win, fg_color="transparent")
        footer.pack(side="bottom", fill="x")
        body = ctk.CTkScrollableFrame(win, fg_color="transparent")
        body.pack(side="top", fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)

        prov_names = list(AI_PROVIDERS.keys())
        cur = self.tr_cfg.get("provider", "gemini")
        prov_var = ctk.StringVar(value=next((n for n, c in AI_PROVIDERS.items() if c == cur), prov_names[0]))
        model_var = ctk.StringVar(value="")
        prev = {"code": cur}

        def ckey(c, k):
            return (c, k, url_entry.get().strip() if c == "custom" else "")

        def code():
            return AI_PROVIDERS.get(prov_var.get(), "gemini")

        def is_ai():
            return code() in AI_KEY_PROVIDERS

        def save_widgets_for(c):
            self.tr_cfg.setdefault("keys", {})[c] = key_entry.get().strip()
            if c == "custom":
                self.tr_cfg.setdefault("base_urls", {})[c] = url_entry.get().strip()
            m = model_var.get()
            if m and not m.startswith(("(", "-")):
                self.tr_cfg.setdefault("models", {})[c] = m

        def set_models(models, saved=""):
            if models:
                model_menu.configure(values=models)
                model_var.set(pick_default_model(code(), models, saved))
            else:
                model_menu.configure(values=["(ដាក់ API Key ជាមុនសិន)"])
                model_var.set("(ដាក់ API Key ជាមុនសិន)")

        def load_models(_=None):
            if not is_ai():
                return
            c, k = code(), key_entry.get().strip()
            if not k:
                status.configure(text="⚠️ សូមដាក់ API Key ជាមុនសិន", text_color="#F59E0B")
                return
            if ckey(c, k) in self._tr_models_cache and model_var.get() in self._tr_models_cache[ckey(c, k)]:
                return
            status.configure(text="កំពុងទាញបញ្ជីម៉ូដែល...", text_color="#38BDF8")
            load_btn.configure(state="disabled")

            def work():
                try:
                    models = list_ai_models(c, k, url_entry.get().strip())
                    err = "" if models else "គ្មានម៉ូដែលសមស្របសម្រាប់ Key នេះ"
                except ApiError as e:
                    models, err = [], f"Key មិនត្រឹមត្រូវ ឬគ្មានសិទ្ធិ ({e})"
                except Exception as e:
                    models, err = [], f"មិនអាចភ្ជាប់បាន: {e}"

                def apply():
                    try:
                        load_btn.configure(state="normal" if is_ai() else "disabled")
                        if c != code() or k != key_entry.get().strip() or ckey(c, k) != ckey(c, key_entry.get().strip()):
                            return  # provider/key changed meanwhile
                        if models:
                            self._tr_models_cache[ckey(c, k)] = models
                            set_models(models, self.tr_cfg.get("models", {}).get(c, ""))
                            status.configure(text=f"✅ មាន {len(models)} ម៉ូដែល សូមជ្រើសរើសក្នុងបញ្ជី",
                                             text_color="#22C55E")
                        else:
                            status.configure(text="❌ " + err, text_color="#EF4444")
                    except Exception:
                        pass
                self.after(0, apply)
            threading.Thread(target=work, daemon=True).start()

        def refresh_provider():
            ai = is_ai()
            if code() == "custom":
                url_lbl.grid()
                url_entry.grid()
                url_entry.delete(0, "end")
                url_entry.insert(0, self.tr_cfg.get("base_urls", {}).get("custom", ""))
            else:
                url_lbl.grid_remove()
                url_entry.grid_remove()
            key_entry.configure(state="normal")
            key_entry.delete(0, "end")
            key_entry.insert(0, self.tr_cfg.get("keys", {}).get(code(), ""))
            st = "normal" if ai else "disabled"
            key_entry.configure(state=st)
            model_menu.configure(state=st)
            load_btn.configure(state=st)
            if not ai:
                model_menu.configure(values=["-"])
                model_var.set("-")
                status.configure(text="ប្រើ Google Translate ឥតគិតថ្លៃ (បកប្រែម្តងមួយបន្ទាត់ មិនយល់បរិបទ)។",
                                 text_color=T["muted"])
                return
            k = key_entry.get().strip()
            saved = self.tr_cfg.get("models", {}).get(code(), "")
            cached = self._tr_models_cache.get(ckey(code(), k))
            if cached:
                set_models(cached, saved)
                status.configure(text=f"✅ មាន {len(cached)} ម៉ូដែល", text_color="#22C55E")
            else:
                set_models([saved] if saved else [], saved)
                status.configure(text="ដាក់ API Key រួចចុច Enter ឬ «ផ្ទុកម៉ូដែល» ដើម្បីទាញបញ្ជីម៉ូដែល។",
                                 text_color=T["muted"])
                if k:
                    load_models()

        def on_provider(_choice):
            save_widgets_for(prev["code"])
            prev["code"] = code()
            refresh_provider()

        ctk.CTkLabel(body, text="ជ្រើសរើសសេវាបកប្រែ (Provider):", font=F(13, "bold"), anchor="w"
                     ).grid(row=0, column=0, padx=18, pady=(16, 2), sticky="w")
        ctk.CTkOptionMenu(body, values=prov_names, variable=prov_var, command=on_provider, **menu_style()).grid(row=1, column=0, padx=18, pady=(0, 10), sticky="ew")

        ctk.CTkLabel(body, text="API Key:", font=F(13, "bold"), anchor="w"
                     ).grid(row=2, column=0, padx=18, pady=(0, 2), sticky="w")
        kf = ctk.CTkFrame(body, fg_color="transparent")
        kf.grid(row=3, column=0, padx=18, pady=(0, 10), sticky="ew")
        kf.grid_columnconfigure(0, weight=1)
        key_entry = ctk.CTkEntry(kf, show="•", placeholder_text="បិទភ្ជាប់ API Key នៅទីនេះ", height=34, **entry_style(font=F(13)))
        key_entry.grid(row=0, column=0, sticky="ew")
        load_btn = mkbtn(kf, "↻  ផ្ទុកម៉ូដែល", "secondary", width=120, command=load_models)
        load_btn.grid(row=0, column=1, padx=(8, 0))
        key_entry.bind("<Return>", load_models)
        key_entry.bind("<FocusOut>", load_models)
        key_entry.bind("<<Paste>>", lambda e: self.after(300, load_models))

        url_lbl = ctk.CTkLabel(body, text="Base URL (OpenAI-compatible, ឧ. https://api.example.com/v1):",
                               font=F(13, "bold"), anchor="w")
        url_lbl.grid(row=4, column=0, padx=18, pady=(0, 2), sticky="w")
        url_entry = ctk.CTkEntry(body, height=34, placeholder_text="https://.../v1", **entry_style(font=F(13)))
        url_entry.grid(row=5, column=0, padx=18, pady=(0, 10), sticky="ew")
        url_entry.bind("<Return>", load_models)
        url_entry.bind("<FocusOut>", load_models)

        ctk.CTkLabel(body, text="ម៉ូដែល (Model) — ជ្រើសរើសពីបញ្ជី:", font=F(13, "bold"), anchor="w"
                     ).grid(row=6, column=0, padx=18, pady=(0, 2), sticky="w")
        model_menu = ctk.CTkOptionMenu(body, values=["(ដាក់ API Key ជាមុនសិន)"], variable=model_var, **menu_style())
        model_menu.grid(row=7, column=0, padx=18, pady=(0, 6), sticky="ew")
        status = ctk.CTkLabel(body, text="", font=F(12), anchor="w", justify="left", wraplength=500)
        status.grid(row=8, column=0, padx=18, pady=(0, 8), sticky="w")

        bf = ctk.CTkFrame(body, fg_color="transparent")
        bf.grid(row=9, column=0, padx=18, pady=(0, 8), sticky="ew")
        ctk.CTkLabel(bf, text="ចំនួនបន្ទាត់ក្នុងមួយសំណើ (Batch 5-60):", font=F(12)).pack(side="left")
        batch_entry = ctk.CTkEntry(bf, width=70, height=30, **entry_style(font=F(13)))
        batch_entry.pack(side="left", padx=8)
        batch_entry.insert(0, str(self.tr_cfg.get("batch", 25)))

        ctk.CTkLabel(body, text="សេចក្ដីសង្ខេបរឿង / ប្រវត្តិតួអង្គ (ជួយឱ្យយល់បរិបទ):", font=F(13, "bold"),
                     anchor="w").grid(row=10, column=0, padx=18, pady=(6, 2), sticky="w")
        summary_box = ctk.CTkTextbox(body, height=100, font=F(13), border_width=1, border_color=T["border"], fg_color=T["surface"], corner_radius=10, text_color=T["text"])
        summary_box.grid(row=11, column=0, padx=18, pady=(0, 8), sticky="nsew")
        summary_box.insert("1.0", self.tr_cfg.get("summary", ""))
        ctk.CTkLabel(body, text="វចនានុក្រមឈ្មោះ/ពាក្យពិសេស (មួយបន្ទាត់: ដើម = ខ្មែរ  ឧ. 李明 = លី មីង):",
                     font=F(13, "bold"), anchor="w").grid(row=12, column=0, padx=18, pady=(0, 2), sticky="w")
        gloss_box = ctk.CTkTextbox(body, height=120, font=F(13), border_width=1, border_color=T["border"], fg_color=T["surface"], corner_radius=10, text_color=T["text"])
        gloss_box.grid(row=13, column=0, padx=18, pady=(0, 8), sticky="nsew")
        gloss_box.insert("1.0", self.tr_cfg.get("glossary", ""))

        def save_and_close():
            self.tr_cfg["provider"] = code()
            save_widgets_for(code())
            try:
                self.tr_cfg["batch"] = max(5, min(60, int(batch_entry.get())))
            except Exception:
                self.tr_cfg["batch"] = 25
            self.tr_cfg["summary"] = summary_box.get("1.0", "end-1c")
            self.tr_cfg["glossary"] = gloss_box.get("1.0", "end-1c")
            self.save_translate_config()
            self._tr_win = None
            win.destroy()

        mkbtn(footer, "រក្សាទុក និងបិទ", "primary", height=44, size=14, corner_radius=12,
              command=save_and_close).pack(fill="x", padx=18, pady=(8, 14))
        win.protocol("WM_DELETE_WINDOW", save_and_close)
        refresh_provider()
        win.after(150, lambda: (win.lift(), win.focus_force()))

    # ---- translate ------------------------------------------------------ #
    def start_translate(self):
        self._ensure_text_mode()
        text = self.textbox.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showerror("Error", "សូមបញ្ចូលអត្ថបទ ឬនាំចូល SRT ជាមុនសិន!")
            return
        cfg = self._effective_translate_cfg()
        if cfg["provider"] in AI_KEY_PROVIDERS and (not cfg["key"] or not cfg["model"]):
            messagebox.showinfo("ការកំណត់ការបកប្រែ",
                                "សូមដាក់ API Key និងជ្រើសរើសម៉ូដែលជាមុនសិន\n"
                                "(ឬជ្រើស Google Translate ឥតគិតថ្លៃ)។")
            self.open_translate_settings()
            return
        target = TRANSLATE_LANGS.get(self.translate_lang_var.get(), "km")
        self.translate_btn.configure(state="disabled", text="កំពុងបកប្រែ...")
        self.save_mp3_btn.configure(state="disabled")
        self.update_progress(0, "កំពុងបកប្រែ (Translating)...")
        threading.Thread(target=self._translate_task, args=(text, target, cfg), daemon=True).start()

    def _translate_task(self, text, target, cfg):
        try:
            prog = lambda p: self.update_progress(p, "កំពុងបកប្រែ (Translating)...")
            if SRT_TIME_RE.search(text):
                result, failed, fb = translate_srt(text, target, cfg, progress=prog)
            else:
                result, failed, fb = translate_plain(text, target, cfg, progress=prog)

            def apply():
                inner = self.textbox._textbox
                try:
                    inner.edit_separator()
                except Exception:
                    pass
                self.textbox.delete("1.0", "end")
                self.textbox.insert("1.0", result)
                try:
                    inner.edit_separator()
                except Exception:
                    pass
                self._orig_text = text           # keep the source for side-by-side checking
                if SRT_TIME_RE.search(result):   # open the line editor so the result can be checked / fixed
                    try:
                        self._set_srt_mode("lines")
                    except Exception:
                        pass
                notes = []
                if fb:
                    notes.append(f"{fb} បន្ទាត់ AI មិនអាចបកប្រែបាន (quota/កំហុស) ទើបប្រើ Google Translate ជំនួស។")
                if failed:
                    notes.append(f"{failed} បន្ទាត់មិនអាចបកប្រែបាន (រក្សាអត្ថបទដើម)។")
                if notes:
                    messagebox.showwarning("បកប្រែមិនពេញលេញ", "\n".join(notes) + "\nសូមពិនិត្យអ៊ីនធឺណិត/quota។")
            self.after(0, apply)
            self.update_progress(100, "បកប្រែរួចរាល់! (Ctrl+Z ដើម្បីត្រឡប់ទៅដើមវិញ)")
        except Exception as e:
            self.after(0, lambda e=e: messagebox.showerror("Error", f"មិនអាចបកប្រែបានទេ:\n{e}"))
            self.update_progress(0, "")
        finally:
            self.after(0, lambda: (self.translate_btn.configure(state="normal", text=self.TR_TEXT),
                                   self.save_mp3_btn.configure(state="normal")))

    def setup_textbox_khmer_editing(self, tb=None):
        """Undo/redo, select-all, context menu and reliable Unicode (Khmer) key input on Windows."""
        import tkinter as tk
        main_box = tb is None
        tb = tb if tb is not None else self.textbox
        try:
            inner = tb._textbox
            inner.configure(font=(FONT_MAIN, 13), undo=True, maxundo=50, spacing1=4, spacing2=5,
                            spacing3=4, padx=8, pady=6, insertwidth=2, insertbackground="#38BDF8")

            def select_all(e=None):
                inner.tag_add("sel", "1.0", "end")
                inner.mark_set("insert", "end")
                return "break"

            def undo(e=None):
                try:
                    inner.edit_undo()
                except Exception:
                    pass
                return "break"

            def redo(e=None):
                try:
                    inner.edit_redo()
                except Exception:
                    pass
                return "break"

            def paste(e=None):
                self.paste_clipboard_text(tb)
                return "break"

            if os.name == "nt":
                import ctypes
                user32 = ctypes.windll.user32
                kstate = (ctypes.c_ubyte * 256)()
                buf = ctypes.create_unicode_buffer(10)
                skip = {"BackSpace", "Delete", "Return", "Tab", "Escape", "Left", "Right", "Up", "Down",
                        "Home", "End", "Prior", "Next"}

                def insert_text(s):
                    try:
                        inner.delete("sel.first", "sel.last")
                    except Exception:
                        pass
                    inner.insert("insert", s)
                    inner.see("insert")

                def on_key(event):
                    try:
                        if event.state & 4 or event.keysym in skip:
                            return None
                        ch = event.char
                        if ch and ch != "?" and len(ch) == 1 and ord(ch) >= 32:
                            insert_text(ch)
                            return "break"
                        if event.keycode > 0:
                            user32.GetKeyboardState(kstate)
                            kstate[16] = 128 if event.state & 1 else 0
                            res = user32.ToUnicode(event.keycode, 0, kstate, buf, 10, 0)
                            if res > 0 and buf.value:
                                insert_text(buf.value)
                                return "break"
                    except Exception:
                        pass
                    return None

                inner.bind("<Key>", on_key)

            for w in (tb, inner):
                for k, fn in (("a", select_all), ("z", undo), ("y", redo), ("v", paste)):
                    w.bind(f"<Control-{k}>", fn)
                    w.bind(f"<Control-{k.upper()}>", fn)

            menu = tk.Menu(self, tearoff=0, font=(FONT_MAIN, 11), bg="#1E293B", fg="#F8FAFC",
                           activebackground="#2563EB", activeforeground="#FFFFFF", bd=1, relief="flat")
            menu.add_command(label="✂️ កាត់ (Cut)", command=lambda: inner.event_generate("<<Cut>>"))
            menu.add_command(label="📋 ចម្លង (Copy)", command=lambda: inner.event_generate("<<Copy>>"))
            menu.add_command(label="📥 បិទភ្ជាប់ (Paste)", command=lambda: self.paste_clipboard_text(tb))
            menu.add_command(label="❌ លុប (Delete)",
                             command=lambda: inner.delete("sel.first", "sel.last"))
            menu.add_separator()
            menu.add_command(label="🔘 ជ្រើសទាំងអស់ (Select All)", command=select_all)
            menu.add_command(label="↩️ ត្រឡប់ក្រោយ (Undo)", command=undo)
            menu.add_command(label="↪️ ធ្វើឡើងវិញ (Redo)", command=redo)
            menu.add_separator()
            menu.add_command(label="🗑️ សម្អាតទាំងអស់ (Clear All)",
                             command=self.clear_text if main_box else (lambda: tb.delete("1.0", "end")))

            def popup(event):
                try:
                    menu.tk_popup(event.x_root, event.y_root)
                finally:
                    menu.grab_release()

            inner.bind("<Button-3>", popup)
            tb.bind("<Button-3>", popup)
        except Exception as e:
            print(f"[Khmer Textbox] Setup error: {e}")

    # ---- voice preview --------------------------------------------------- #
    def preview_selected_voice(self):
        if self.cloud_clone_enable_var.get():
            self.preview_cloud_clone()
            return
        choice = self.voice_optionemenu.get()
        preset = KHMER_VOICE_PRESETS.get(choice)
        if not preset:
            return
        self.voice_preview_btn.configure(state="disabled", text="⏳...")

        def worker():
            try:
                cache = os.path.join(tempfile.gettempdir(), "ttv_voice_previews")
                os.makedirs(cache, exist_ok=True)
                key = hashlib.md5(f"{choice}_{preset['voice_id']}_{preset['pitch']}_{preset['rate_offset']}"
                                  .encode("utf-8")).hexdigest()
                wav, mp3 = os.path.join(cache, key + ".wav"), os.path.join(cache, key + ".mp3")
                if not os.path.exists(wav):
                    ok = asyncio.run(tts_save(preset["sample"], preset["voice_id"],
                                              fmt_rate(preset["rate_offset"]), preset["pitch"], mp3, attempts=3))
                    if not ok:
                        raise RuntimeError("មិនអាចទាញយកសំឡេងគំរូបានទេ")
                    run_ffmpeg(["-i", mp3, "-ac", "1", "-ar", "24000", wav])
                play_audio(wav if os.path.exists(wav) else mp3)
            except Exception as e:
                print("Voice preview error:", e)
            finally:
                self.after(0, lambda: self.voice_preview_btn.configure(state="normal", text=self.LISTEN_TEXT))

        threading.Thread(target=worker, daemon=True).start()

    # ---- cloud clone UI --------------------------------------------------- #
    def _cloud_config_path(self):
        base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
            else os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, "cloud_clone_config.json")

    def load_cloud_clone_config(self):
        self.hf_tokens = []
        try:
            with open(self._cloud_config_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            # new key "hf_tokens" (list); old key "hf_token" (single) still supported
            self.hf_tokens = parse_hf_tokens(data.get("hf_tokens", [])) or parse_hf_tokens(data.get("hf_token", ""))
            # UI is already built at this point -> fill the token box before anything triggers a save
            self.hf_token_box.delete("1.0", "end")
            self.hf_token_box.insert("1.0", "\n".join(self.hf_tokens))
            self.update_token_count_label()
            ref = data.get("ref_audio_path", "")
            if ref and os.path.exists(ref):
                self.ref_audio_path = ref
                name = os.path.basename(ref)
                name = name[:21] + "..." if len(name) > 24 else name
                self.cloud_ref_file_lbl.configure(text=f"✅ {name}", text_color="#38BDF8")
            if data.get("enabled"):
                self.cloud_clone_enable_var.set(True)
                self.on_toggle_cloud_clone()
        except Exception:
            pass

    def save_cloud_clone_config(self):
        try:
            data = {"server_url": DEFAULT_CLOUD_SERVER, "ref_audio_path": self.ref_audio_path,
                    "hf_tokens": self.get_hf_tokens(), "enabled": self.cloud_clone_enable_var.get()}
            with open(self._cloud_config_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_hf_tokens(self):
        box = getattr(self, "hf_token_box", None)
        if box is not None:
            try:
                self.hf_tokens = parse_hf_tokens(box.get("1.0", "end"))
            except Exception:
                pass
        return list(getattr(self, "hf_tokens", []))

    def update_token_count_label(self):
        n = len(self.get_hf_tokens())
        txt = f"✅ មាន {n} Token (ប្តូរស្វ័យប្រវត្តិពេលដល់កូតា)" if n else "⚪ មិនទាន់មាន Token (កូតាតិចណាស់)"
        try:
            self.hf_token_count_lbl.configure(text=txt, text_color="#38BDF8" if n else T["muted"])
        except Exception:
            pass

    def on_tokens_changed(self):
        self.update_token_count_label()
        self.save_cloud_clone_config()

    def on_toggle_cloud_clone(self):
        if self.cloud_clone_enable_var.get():
            self.cloud_clone_inner.pack(fill="x", padx=10, pady=(0, 8))
        else:
            self.cloud_clone_inner.pack_forget()
        self.save_cloud_clone_config()

    def select_ref_audio(self):
        f = filedialog.askopenfilename(
            title="ជ្រើសរើសឯកសារសំឡេងគំរូ (៥-១០ វិនាទី)",
            filetypes=[("Audio Files", "*.wav *.mp3 *.ogg *.m4a *.flac"), ("All Files", "*.*")])
        if f:
            self.ref_audio_path = f
            name = os.path.basename(f)
            name = name[:25] + "..." if len(name) > 28 else name
            self.cloud_ref_file_lbl.configure(text=f"🎙️ {name}", text_color="#38BDF8")
            self.save_cloud_clone_config()

    def preview_ref_audio(self):
        ref = self.ref_audio_path
        if not ref or not os.path.exists(ref):
            messagebox.showwarning("សំឡេងគំរូ", "សូមជ្រើសរើសឯកសារសំឡេងគំរូជាមុនសិន!")
            return

        def play():
            try:
                if ref.lower().endswith(".wav"):
                    play_audio(ref)
                else:
                    tmp = os.path.join(tempfile.gettempdir(), "ttv_ref_preview.wav")
                    run_ffmpeg(["-i", ref, tmp])
                    if os.path.exists(tmp):
                        play_audio(tmp)
            except Exception as e:
                self.after(0, lambda e=e: messagebox.showerror("Error", f"មិនអាចចាក់សំឡេងបានទេ:\n{e}"))

        threading.Thread(target=play, daemon=True).start()

    def preview_cloud_clone(self):
        if not self.check_access():
            return
        ref = self.ref_audio_path
        if not ref or not os.path.exists(ref):
            messagebox.showwarning("សំឡេងគំរូ", "សូមចុច '📤 Upload សំឡេង ១០ វិនាទី' ជាមុនសិន!")
            return
        tokens = self.get_hf_tokens()
        self.update_token_count_label()
        self.save_cloud_clone_config()
        self.cloud_preview_btn.configure(state="disabled", text="⏳ កំពុងដំណើរការ...")

        def worker():
            work = tempfile.mkdtemp(prefix="ttv_cloud_prev_")
            try:
                sample = "សួស្តី! នេះជាការសាកល្បងសំឡេងដែលបាន Clone តាមរយៈសំឡេងគំរូ ១០ វិនាទី។"
                mp3, wav = os.path.join(work, "t.mp3"), os.path.join(work, "t.wav")
                if not asyncio.run(tts_save(sample, "km-KH-PisethNeural", "+0%", "+0Hz", mp3)):
                    raise RuntimeError("មិនអាចបង្កើតសំឡេងគំរូបានទេ")
                standardize_clip(mp3, wav)
                out = os.path.join(work, "cloned.wav")
                run_cloud_voice_clone(wav, out, DEFAULT_CLOUD_SERVER, ref, tokens, sample)
                play = os.path.join(tempfile.gettempdir(), f"ttv_cloned_{int(time.time())}.wav")
                standardize_clip(out, play)
                play_audio(play if os.path.exists(play) else out)
            except Exception as ex:
                self.after(0, lambda ex=ex: messagebox.showerror("Preview Error", f"កំហុសក្នុងការស្តាប់សាកល្បង:\n{ex}"))
            finally:
                shutil.rmtree(work, ignore_errors=True)
                self.after(0, lambda: self.cloud_preview_btn.configure(
                    state="normal", text="✨ ស្តាប់សំឡេង Clone សាកល្បង"))

        threading.Thread(target=worker, daemon=True).start()

    # ---- generation ------------------------------------------------------- #
    def check_access(self):
        if LICENSE_HOOK is None:
            return True
        try:
            return bool(LICENSE_HOOK())
        except Exception:
            return False

    def start_voice_generation(self):
        """Generate the voice into a temporary file so it can be listened to BEFORE exporting."""
        if not self.check_access():
            return
        text = self._current_text().strip()
        if not text:
            messagebox.showerror("Error", "សូមបញ្ចូលអត្ថបទ!")
            return
        if self.cloud_clone_enable_var.get():
            if not self.ref_audio_path or not os.path.exists(self.ref_audio_path):
                messagebox.showwarning("សំឡេងគំរូ", "សូមចុច '📤 Upload សំឡេង ១០ វិនាទី' ជាមុនសិន!")
                return
        voice = self.voice_optionemenu.get()
        rate = fmt_rate(self.speed_slider.get())
        self.max_speedup = round(self.max_speed_slider.get(), 2)
        self.get_hf_tokens()  # refresh self.hf_tokens from the UI (main thread)
        key = self._voice_key(text)
        self.audio_panel.pause()
        self.save_mp3_btn.configure(state="disabled", text="កំពុងដំណើរការ...")
        self.update_progress(0, "កំពុងបង្កើតសំឡេង (Generating voice)...")
        threading.Thread(target=self._voice_task,
                         args=(text, voice, rate, self.smart_read_var.get(), self.auto_sync_var.get(), key),
                         daemon=True).start()

    def _voice_task(self, text, voice, rate, smart_read, auto_sync, key):
        work = tempfile.mkdtemp(prefix="ttv_job_")
        try:
            audio = self._synth_voice(text, voice, rate, smart_read, auto_sync, work, 0, 97)
            self._voice_n += 1
            dst = os.path.join(self._voice_dir, f"voice_{self._voice_n}{os.path.splitext(audio)[1] or '.mp3'}")
            shutil.copy(audio, dst)
            note = sync_note()
            self.update_progress(100, "បង្កើតសំឡេងរួចរាល់! ចុច ▶ ខាងក្រោម SRT ដើម្បីស្តាប់")

            def done():
                old = self._voice
                self._voice = {"path": dst, "key": key}
                self.audio_panel.load(dst)          # closes the old file first
                if old and old["path"] != dst:
                    try:
                        os.remove(old["path"])
                    except Exception:
                        pass
                if note:
                    messagebox.showwarning("Auto Sync", note.strip())

            self.after(0, done)
        except Exception as e:
            self.after(0, lambda e=e: messagebox.showerror("Error", str(e)))
            self.update_progress(0, "")
        finally:
            shutil.rmtree(work, ignore_errors=True)
            self.after(0, lambda: self.save_mp3_btn.configure(state="normal", text=self.BTN_TEXT))

    def export_voice_mp3(self):
        """Save the voice that was generated (and listened to) as an MP3 file."""
        if not self.check_access():
            return
        v = self._voice
        if not v or not os.path.exists(v["path"]):
            messagebox.showinfo("MP3", "សូមចុច «បង្កើតសំឡេង» ជាមុនសិន ហើយស្តាប់មើល បន្ទាប់មកទើបរក្សាទុក MP3។")
            return
        if v["key"] != self._voice_key():
            if not messagebox.askyesno("MP3", "អត្ថបទ ឬការកំណត់បានប្តូរ ក្រោយបង្កើតសំឡេងចុងក្រោយ។\n\n"
                                              "រក្សាទុកសំឡេងដែលបានស្តាប់ (ចាស់) ដែរឬទេ?\n"
                                              "(ចុច No ដើម្បីត្រឡប់ទៅបង្កើតសំឡេងថ្មីវិញ)"):
                return
        save_path = filedialog.asksaveasfilename(defaultextension=".mp3", filetypes=[("MP3 Audio", "*.mp3")],
                                                 title="Save Audio As")
        if not save_path:
            return
        src = v["path"]
        self.export_mp3_btn.configure(state="disabled")
        self.update_progress(30, "កំពុងរក្សាទុកឯកសារ MP3...")

        def work():
            try:
                if src.lower().endswith(".mp3"):
                    shutil.copy(src, save_path)
                else:
                    res = run_ffmpeg(["-i", src, "-c:a", "libmp3lame", "-b:a", "192k", save_path])
                    if res.returncode != 0 or not os.path.exists(save_path):
                        shutil.copy(src, save_path)
                dur = audio_duration(save_path)
                dur_str = f"{int(dur // 60):02d}:{int(dur % 60):02d}"
                self.update_progress(100, "រក្សាទុក MP3 រួចរាល់!")

                def done():
                    if messagebox.askyesno("ជោគជ័យ", f"រក្សាទុក MP3 រួចរាល់! ({dur_str} នាទី)\n\n"
                                                      f"ទីតាំង: {save_path}\n\nតើលោកអ្នកចង់បើកស្តាប់ឯកសារនេះឥឡូវទេ?"):
                        try:
                            os.startfile(save_path) if os.name == "nt" else webbrowser.open("file://" + save_path)
                        except Exception:
                            pass
                self.after(0, done)
            except Exception as e:
                self.after(0, lambda e=e: messagebox.showerror("Error", str(e)))
            finally:
                self.after(0, lambda: (self.export_mp3_btn.configure(state="normal"), self.update_progress(0, "")))
        threading.Thread(target=work, daemon=True).start()

    # ---- video display + dubbing ---------------------------------------- #
    def import_video(self):
        path = filedialog.askopenfilename(
            title="ជ្រើសរើសវីដេអូ",
            filetypes=[("Video", "*.mp4 *.mkv *.mov *.avi *.webm *.flv *.wmv *.m4v *.ts"), ("All Files", "*.*")])
        if not path:
            return False
        return self.load_video(path)

    def load_video(self, path):
        try:
            self._show_video_panel()
            self.video_panel.load(path)
            self.video_path = path
            return True
        except Exception as e:
            self._hide_video_panel()
            messagebox.showerror("Error", f"មិនអាចបើកវីដេអូបានទេ:\n{e}")
            return False

    def _show_video_panel(self):
        pass     # the video zone is always visible (empty state until a video is imported)

    def _hide_video_panel(self):
        self.video_path = ""
        try:
            self.video_panel.clear()
        except Exception:
            pass

    def close_video(self):
        self.video_path = ""

    def update_orig_vol_label(self, value):
        v = int(value)
        self.orig_vol_label.configure(
            text=f"សំឡេងដើម (Original): {v}%" + (" — ជំនួសទាំងស្រុង" if v == 0 else " — រក្សាបន្ថែម"))

    def _synth_voice(self, text, voice, rate, smart_read, auto_sync, work, p0, p1):
        """Khmer voice file for `text` (plain text or SRT); same engine/clone options as Generate MP3."""
        use_cloud = self.cloud_clone_enable_var.get()
        span = p1 - p0
        scale = 0.6 if use_cloud else 1.0
        tmp_audio = os.path.join(work, "tts.mp3")
        generate_tts(text, voice, rate, tmp_audio, work, smart_read, auto_sync,
                     progress=lambda p, m: self.update_progress(p0 + p * span * scale / 100.0, m),
                     max_speedup=getattr(self, "max_speedup", None))
        if not use_cloud:
            return tmp_audio
        self.update_progress(p0 + span * 0.65, "កំពុង Clone សំឡេងតាមរយៈសំឡេងគំរូ (Free Server)...")
        cloud_wav = os.path.join(work, "cloud_out.wav")
        run_cloud_voice_clone(tmp_audio, cloud_wav, DEFAULT_CLOUD_SERVER, self.ref_audio_path,
                              list(self.hf_tokens), text)
        return cloud_wav

    def start_dub(self):
        if not self.check_access():
            return
        if not self.video_path or not os.path.exists(self.video_path):
            if not self.import_video():
                return
        text = self._current_text().strip()
        if not text:
            messagebox.showerror("Error", "សូមបញ្ចូលអត្ថបទ ឬនាំចូល SRT សម្រាប់ Dub!")
            return
        if self.cloud_clone_enable_var.get():
            if not self.ref_audio_path or not os.path.exists(self.ref_audio_path):
                messagebox.showwarning("សំឡេងគំរូ", "សូមចុច '📤 Upload សំឡេង ១០ វិនាទី' ជាមុនសិន!")
                return
        try:
            trim = self.video_panel.get_trim()
        except ValueError as e:
            messagebox.showerror("Trim", str(e))
            return
        base = os.path.splitext(os.path.basename(self.video_path))[0]
        save_path = filedialog.asksaveasfilename(
            defaultextension=".mp4", initialfile=base + "_khmer.mp4",
            filetypes=[("MP4 Video", "*.mp4"), ("MKV Video", "*.mkv")], title="Save Dubbed Video As")
        if not save_path:
            return
        if os.path.abspath(save_path) == os.path.abspath(self.video_path):
            messagebox.showerror("Error", "សូមកុំរក្សាទុកជាន់លើវីដេអូដើម! ជ្រើសឈ្មោះឯកសារផ្សេង។")
            return
        voice = self.voice_optionemenu.get()
        rate = fmt_rate(self.speed_slider.get())
        orig_vol = self.orig_vol_slider.get() / 100.0
        self.max_speedup = round(self.max_speed_slider.get(), 2)
        self.get_hf_tokens()
        ready = None                     # reuse the voice that was already generated + listened to
        v = self._voice
        if v and os.path.exists(v["path"]) and v["key"] == self._voice_key(text):
            ready = v["path"]
        self.video_panel.pause()
        self.audio_panel.pause()
        self.dub_btn.configure(state="disabled", text="កំពុងដំណើរការ...")
        self.save_mp3_btn.configure(state="disabled")
        self.update_progress(0, "កំពុងបង្កើតសំឡេង Dub...")
        threading.Thread(target=self._dub_task,
                         args=(text, voice, rate, save_path, self.video_path, self.smart_read_var.get(),
                               self.auto_sync_var.get(), orig_vol, trim, ready), daemon=True).start()

    def _dub_task(self, text, voice, rate, save_path, video, smart_read, auto_sync, orig_vol,
                  trim=(0.0, None), ready_audio=None):
        work = tempfile.mkdtemp(prefix="ttv_dub_")
        try:
            if ready_audio:
                audio = ready_audio
                self.update_progress(50, "ប្រើសំឡេងដែលបានស្តាប់រួចហើយ...")
            else:
                audio = self._synth_voice(text, voice, rate, smart_read, auto_sync, work, 0, 85)
            self.update_progress(88, "កំពុងបញ្ចូលសំឡេងទៅក្នុងវីដេអូ (Mixing)...")
            mux_dub(video, audio, save_path, orig_vol, trim[0], trim[1])
            a_dur = audio_duration(audio)
            v_dur = video_info(video)["duration"]
            self.update_progress(100, "Dub វីដេអូរួចរាល់!")

            def done():
                self.load_video(save_path)       # preview the dubbed result in the display
                warn = ""
                if v_dur and a_dur > v_dur + 1.0:
                    warn = (f"\n\n⚠️ សំឡេង Dub ({a_dur:.0f} វិនាទី) វែងជាងវីដេអូ ({v_dur:.0f} វិនាទី) "
                            "ផ្នែកដែលលើសត្រូវបានកាត់ចេញ។ សូមប្រើ SRT ដែលមាន Timecode ត្រូវនឹងវីដេអូ "
                            "ឬកាត់បន្ថយអត្ថបទ។")
                messagebox.showinfo("ជោគជ័យ", f"Dub វីដេអូរួចរាល់!\n\nទីតាំង: {save_path}\n\n"
                                              f"ចុច ▶ ក្នុងផ្ទាំងវីដេអូ ដើម្បីមើលលទ្ធផល។{warn}{sync_note()}")
            self.after(0, done)
        except Exception as e:
            self.after(0, lambda e=e: messagebox.showerror("Error", str(e)))
        finally:
            shutil.rmtree(work, ignore_errors=True)
            self.after(0, lambda: (self.dub_btn.configure(state="normal", text=self.DUB_TEXT),
                                   self.save_mp3_btn.configure(state="normal")))
            self.after(0, lambda: self.update_progress(0, ""))

    def export_trim(self):
        """Save only the kept part of the loaded video (no dubbing)."""
        if not self.video_path or not os.path.exists(self.video_path):
            messagebox.showwarning("Trim", "សូមនាំចូលវីដេអូជាមុនសិន!")
            return
        try:
            ts, te = self.video_panel.get_trim()
        except ValueError as e:
            messagebox.showerror("Trim", str(e))
            return
        if ts <= 0.001 and te is None:
            messagebox.showinfo("Trim", "សូមកំណត់ចំណុចចាប់ផ្តើម ឬបញ្ចប់ជាមុនសិន (ប៊ូតុង 📍)។")
            return
        base = os.path.splitext(os.path.basename(self.video_path))[0]
        save_path = filedialog.asksaveasfilename(
            defaultextension=".mp4", initialfile=base + "_trim.mp4",
            filetypes=[("MP4 Video", "*.mp4"), ("MKV Video", "*.mkv")], title="Save Trimmed Video As")
        if not save_path:
            return
        if os.path.abspath(save_path) == os.path.abspath(self.video_path):
            messagebox.showerror("Error", "សូមកុំរក្សាទុកជាន់លើវីដេអូដើម! ជ្រើសឈ្មោះឯកសារផ្សេង។")
            return
        src = self.video_path
        self.video_panel.pause()
        self.update_progress(30, "កំពុងកាត់វីដេអូ (Trim)...")

        def work():
            try:
                trim_video(src, save_path, ts, te)
                self.after(0, lambda: messagebox.showinfo("ជោគជ័យ", f"កាត់វីដេអូរួចរាល់!\n\nទីតាំង: {save_path}"))
            except Exception as e:
                self.after(0, lambda e=e: messagebox.showerror("Error", str(e)))
            finally:
                self.after(0, lambda: self.update_progress(0, ""))
        threading.Thread(target=work, daemon=True).start()

    def _on_close(self):
        try:
            self.video_panel.shutdown()
        except Exception:
            pass
        try:
            self.audio_panel.shutdown()
            shutil.rmtree(self._voice_dir, ignore_errors=True)
        except Exception:
            pass
        self.destroy()

    # ---- updates ---------------------------------------------------------- #
    def auto_check_update_silent(self):
        has, ver, url, notes = check_github_update_info()
        if has:
            self.after(0, lambda: self.open_update_window(ver, url, notes))

    def manual_check_update(self):
        def work():
            has, ver, url, notes = check_github_update_info()
            if has:
                self.after(0, lambda: self.open_update_window(ver, url, notes))
            else:
                self.after(0, lambda: messagebox.showinfo(
                    "អាប់ដេត", f"លោកអ្នកកំពុងប្រើកំណែចុងក្រោយបំផុតហើយ (v{APP_VERSION})"))
        threading.Thread(target=work, daemon=True).start()

    def open_update_window(self, latest, url, notes):
        win = ctk.CTkToplevel(self)
        win.configure(fg_color=T["bg"])
        win.title("មានកំណែថ្មី")
        win.geometry("460x320")
        win.attributes("-topmost", True)
        ctk.CTkLabel(win, text=f"កំណែថ្មី v{latest} ដែលមាន",
                     text_color=T["text"], font=F(17, "bold")).pack(pady=(20, 6))
        ctk.CTkLabel(win, text=f"កំណែបច្ចុប្បន្ន: v{APP_VERSION}", text_color=T["muted"],
                     font=ctk.CTkFont(family=FONT_MAIN, size=12)).pack()
        box = ctk.CTkTextbox(win, height=130, font=F(12), fg_color=T["surface"], border_width=1, border_color=T["border"], corner_radius=10, text_color=T["text"])
        box.pack(fill="x", padx=20, pady=12)
        box.insert("1.0", notes or "")
        box.configure(state="disabled")
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(pady=6)
        mkbtn(row, "ទាញយក", "primary", width=120, height=38,
              command=lambda: (webbrowser.open(url), win.destroy())).pack(side="left", padx=6)
        mkbtn(row, "ពេលក្រោយ", "secondary", width=120, height=38, command=win.destroy).pack(side="left", padx=6)


def main():
    try:
        App().mainloop()
    except Exception:
        import traceback
        err = traceback.format_exc()
        try:
            with open("app_error.log", "w", encoding="utf-8") as f:
                f.write(err)
        except Exception:
            pass
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("TTV Start Error", f"កំហុសក្នុងការបើកកម្មវិធី:\n{err}")
        except Exception:
            pass


if __name__ == "__main__":
    main()
