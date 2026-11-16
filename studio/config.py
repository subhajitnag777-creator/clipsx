"""All settings come from environment variables (or a .env file next to the project), so the same code runs
on a laptop and on a server. Nothing here is specific to one machine."""
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv():
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


_ALIASES = {
    "PORT": ("CLIPSX_PORT", "PEAKCUT_PORT"),
    "HOST": ("CLIPSX_HOST", "PEAKCUT_HOST"),
    "APP_URL": ("CLIPSX_PUBLIC_URL", "PEAKCUT_PUBLIC_URL", "PUBLIC_URL"),
    "PUBLIC_URL": ("APP_URL", "CLIPSX_PUBLIC_URL", "PEAKCUT_PUBLIC_URL"),
    "ADMIN_EMAIL": ("CLIPSX_OWNER_EMAIL", "PEAKCUT_OWNER_EMAIL", "OWNER_EMAIL"),
    "CLIPSX_OWNER_EMAIL": ("ADMIN_EMAIL", "PEAKCUT_OWNER_EMAIL", "OWNER_EMAIL"),
    "PEAKCUT_OWNER_EMAIL": ("ADMIN_EMAIL", "CLIPSX_OWNER_EMAIL", "OWNER_EMAIL"),
    "DATABASE_URL": ("CLIPSX_DATABASE_URL", "PEAKCUT_DATABASE_URL"),
    "SMTP_HOST": ("CLIPSX_SMTP_HOST", "PEAKCUT_SMTP_HOST"),
    "PEAKCUT_SMTP_HOST": ("SMTP_HOST", "CLIPSX_SMTP_HOST"),
    "SMTP_PORT": ("CLIPSX_SMTP_PORT", "PEAKCUT_SMTP_PORT"),
    "PEAKCUT_SMTP_PORT": ("SMTP_PORT", "CLIPSX_SMTP_PORT"),
    "SMTP_USER": ("CLIPSX_SMTP_USER", "PEAKCUT_SMTP_USER"),
    "PEAKCUT_SMTP_USER": ("SMTP_USER", "CLIPSX_SMTP_USER"),
    "SMTP_PASSWORD": ("CLIPSX_SMTP_PASSWORD", "PEAKCUT_SMTP_PASSWORD"),
    "PEAKCUT_SMTP_PASSWORD": ("SMTP_PASSWORD", "CLIPSX_SMTP_PASSWORD"),
    "SMTP_FROM": ("MAIL_FROM", "CLIPSX_MAIL_FROM", "PEAKCUT_MAIL_FROM"),
    "MAIL_FROM": ("SMTP_FROM", "CLIPSX_MAIL_FROM", "PEAKCUT_MAIL_FROM"),
    "PEAKCUT_MAIL_FROM": ("SMTP_FROM", "MAIL_FROM", "CLIPSX_MAIL_FROM"),
    "VERIFY_EMAIL": ("CLIPSX_VERIFY_EMAIL", "PEAKCUT_VERIFY_EMAIL"),
    "PEAKCUT_VERIFY_EMAIL": ("VERIFY_EMAIL", "CLIPSX_VERIFY_EMAIL"),
    "SESSION_DAYS": ("CLIPSX_SESSION_DAYS", "PEAKCUT_SESSION_DAYS"),
    "PEAKCUT_SESSION_DAYS": ("SESSION_DAYS", "CLIPSX_SESSION_DAYS"),
    "SESSION_SECRET": ("JWT_SECRET", "CLIPSX_SESSION_SECRET", "PEAKCUT_SESSION_SECRET"),
    "JWT_SECRET": ("SESSION_SECRET", "CLIPSX_SESSION_SECRET"),
    "SESSION_COOKIE_SECURE": ("CLIPSX_SESSION_COOKIE_SECURE", "PEAKCUT_SESSION_COOKIE_SECURE"),
    "TURNSTILE_SITE_KEY": ("CLIPSX_TURNSTILE_SITE_KEY", "PEAKCUT_TURNSTILE_SITE_KEY"),
    "TURNSTILE_SECRET_KEY": ("CLIPSX_TURNSTILE_SECRET_KEY", "PEAKCUT_TURNSTILE_SECRET_KEY"),
    "TURNSTILE_ENABLED": ("CLIPSX_TURNSTILE_ENABLED", "PEAKCUT_TURNSTILE_ENABLED"),
    "ACCOUNTS": ("CLIPSX_ACCOUNTS", "PEAKCUT_ACCOUNTS"),
    "PEAKCUT_ACCOUNTS": ("CLIPSX_ACCOUNTS", "ACCOUNTS"),
    "CLIPSX_ACCOUNTS": ("PEAKCUT_ACCOUNTS", "ACCOUNTS"),
    "PEAKCUT_IG_APP_ID": ("CLIPSX_IG_APP_ID", "IG_APP_ID", "INSTAGRAM_APP_ID"),
    "CLIPSX_IG_APP_ID": ("PEAKCUT_IG_APP_ID", "IG_APP_ID", "INSTAGRAM_APP_ID"),
    "PEAKCUT_IG_APP_SECRET": ("CLIPSX_IG_APP_SECRET", "IG_APP_SECRET", "INSTAGRAM_APP_SECRET"),
    "CLIPSX_IG_APP_SECRET": ("PEAKCUT_IG_APP_SECRET", "IG_APP_SECRET", "INSTAGRAM_APP_SECRET"),
    "PEAKCUT_TIKTOK_CLIENT_KEY": ("CLIPSX_TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_KEY"),
    "CLIPSX_TIKTOK_CLIENT_KEY": ("PEAKCUT_TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_KEY"),
    "PEAKCUT_TIKTOK_CLIENT_SECRET": ("CLIPSX_TIKTOK_CLIENT_SECRET", "TIKTOK_CLIENT_SECRET"),
    "CLIPSX_TIKTOK_CLIENT_SECRET": ("PEAKCUT_TIKTOK_CLIENT_SECRET", "TIKTOK_CLIENT_SECRET"),
}


def env(name: str, default: str = None) -> str:
    """Read an environment variable, checking direct name, aliases, and cross-prefix variants."""
    val = os.environ.get(name)
    if val is not None:
        return val
    for alt in _ALIASES.get(name, ()):
        val = os.environ.get(alt)
        if val is not None:
            return val
    if name.startswith("PEAKCUT_"):
        suffix = name[len("PEAKCUT_"):]
        val = os.environ.get(f"CLIPSX_{suffix}") or os.environ.get(f"CLIPS_X_{suffix}") or os.environ.get(suffix)
        if val is not None:
            return val
    elif name.startswith("CLIPSX_"):
        suffix = name[len("CLIPSX_"):]
        val = os.environ.get(f"CLIPS_X_{suffix}") or os.environ.get(f"PEAKCUT_{suffix}") or os.environ.get(suffix)
        if val is not None:
            return val
    elif name.startswith("CLIPS_X_"):
        suffix = name[len("CLIPS_X_"):]
        val = os.environ.get(f"CLIPSX_{suffix}") or os.environ.get(f"PEAKCUT_{suffix}") or os.environ.get(suffix)
        if val is not None:
            return val
    return default


_kept: dict = {}


def _keep(key, make, seconds=60):
    """Settings read from files (keys, the Google client) are looked at once a minute, not on every request."""
    import time
    got = _kept.get(key)
    if not got or time.time() - got[0] > seconds:
        got = _kept[key] = (time.time(), make())
    return got[1]


def _secret(var: str, file_var: str, pattern: str = r"\S{16,}") -> str:
    """A secret given directly (VAR) or as a path to a file holding it (VAR_FILE)."""
    return _keep(("secret", var, file_var), lambda: _read_secret(var, file_var, pattern))


def _read_secret(var: str, file_var: str, pattern: str) -> str:
    if env(var):
        return env(var).strip()
    path = env(file_var)
    if path and Path(path).exists():
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        m = re.search(pattern, text)
        return m.group(0) if m else text.strip().strip('"')
    return ""


# ---------------------------------------------------------------- where things live
# Everything PeakCut keeps is in one folder. Which one: PEAKCUT_DATA in .env if it is set; otherwise the folder the
# owner chose in Settings, Storage (kept in storage.json); otherwise "data" inside PeakCut's own folder.
STORAGE_FILE = Path(env("PEAKCUT_STORAGE_FILE") or ROOT / "storage.json")


def _move_folder(old: Path, new: Path) -> bool:
    """Move everything from the old folder into the new one. Done at start, before anything is open. True when
    nothing is left behind; anything that could not be moved stays where it was and is tried again next start."""
    import shutil
    if not old.is_dir() or old.resolve() == new.resolve():
        return True
    items = list(old.iterdir())
    if items:
        print(f"\n  Moving PeakCut's folder to {new} ({len(items)} things). This is done once and can take a while...", flush=True)
    done = True
    for item in items:
        target = new / item.name
        try:
            if target.exists() and item.is_dir():
                for sub in item.iterdir():           # the folder is already there (made empty, or half moved): fill it
                    if not (target / sub.name).exists():
                        shutil.move(str(sub), str(target / sub.name))
                if not any(item.iterdir()):
                    item.rmdir()
                else:
                    done = False
            elif not target.exists():
                shutil.move(str(item), str(target))
            else:
                done = False
        except OSError as e:
            print(f"  Could not move {item.name}: {e}", flush=True)
            done = False
    if done:
        try:
            old.rmdir()
        except OSError:
            pass
        print("  Moved.\n", flush=True)
    return done


def _data_folder():
    if env("PEAKCUT_DATA"):
        return Path(env("PEAKCUT_DATA")), "env"
    try:
        chosen = json.loads(STORAGE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        chosen = {}
    if not chosen.get("path"):
        return ROOT / "data", "default"
    new = Path(chosen["path"])
    try:
        new.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise SystemExit(f"\n  PeakCut's folder is set to {new}, and that can't be reached right now.\n"
                         f"  Connect that drive and start PeakCut again, or delete {STORAGE_FILE} to go back to the\n"
                         f"  folder inside PeakCut (your videos and clips stay where they are).\n")
    if chosen.get("move_from"):
        if _move_folder(Path(chosen["move_from"]), new):
            STORAGE_FILE.write_text(json.dumps({"path": str(new)}, indent=1), encoding="utf-8")
    return new, "chosen"


DATA_DIR, DATA_FROM = _data_folder()
USERS_DIR = DATA_DIR / "users"          # users/<user id>/{creators,jobs,accounts}
MODELS_DIR = Path(env("PEAKCUT_MODELS") or DATA_DIR / "models")
TMP_DIR = DATA_DIR / "tmp"
FONTS_DIR = DATA_DIR / "fonts"          # caption fonts, copied from studio/fonts so every server renders the same
# YouTube already has a word-by-word transcript of most videos. With this on, that is what the AI reads to find the
# clips (seconds instead of transcribing hours), and our own model is run only on the clips themselves.
YT_TRANSCRIPT = env("PEAKCUT_YT_TRANSCRIPT", "1") != "0"
# the compact model for processors; a machine with a graphics card sets PEAKCUT_ASR_MODEL to the full-precision one
ASR_MODEL_NAME = env("PEAKCUT_ASR_MODEL", "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8")
ASR_MODEL_DIR = MODELS_DIR / ASR_MODEL_NAME
DATABASE_URL = env("DATABASE_URL") or (
    f"sqlite:///{(DATA_DIR / 'peakcut.db').as_posix()}" if (DATA_DIR / "peakcut.db").exists()
    else f"sqlite:///{(DATA_DIR / 'clipsx.db').as_posix()}"
)

for d in (USERS_DIR, MODELS_DIR, TMP_DIR, FONTS_DIR):
    d.mkdir(parents=True, exist_ok=True)


def user_dir(uid: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_]{6,40}", uid or ""):
        raise ValueError("bad user id")
    return USERS_DIR / uid


# ---------------------------------------------------------------- the site
HOST = env("PEAKCUT_HOST", "127.0.0.1")
PORT = int(env("PEAKCUT_PORT") or "8765")
PUBLIC_URL = (env("PEAKCUT_PUBLIC_URL") or f"http://127.0.0.1:{PORT}").rstrip("/")   # e.g. https://peakcut.com
HTTPS = PUBLIC_URL.startswith("https://")
SESSION_DAYS = int(env("PEAKCUT_SESSION_DAYS", "30"))
# Accounts are off by default: Clips X opens straight into the dashboard, with no sign-in, which is what you want
# on your own computer. On a server that other people can reach, set CLIPSX_ACCOUNTS=1: everyone then signs up
# and signs in, and each person only sees their own videos.
ACCOUNTS = env("PEAKCUT_ACCOUNTS", "0") == "1"
OWNER_EMAIL = (env("CLIPSX_OWNER_EMAIL") or env("PEAKCUT_OWNER_EMAIL") or "").strip().lower()
# The two buttons along the top of the dashboard: empty by default so no third-party links are displayed.
REPO_URL = env("CLIPSX_REPO_URL", env("PEAKCUT_REPO_URL", "")).strip()
FOLLOW_URL = env("CLIPSX_FOLLOW_URL", env("PEAKCUT_FOLLOW_URL", "")).strip()

# ---------------------------------------------------------------- limits (per user, and for the whole server)
# Your own Clips X has no limits unless you set them: 0 (the default) means "none" for every limit below. The
# machine still protects itself: new work waits while the processor, memory or disk are nearly full (load.py).
_NONE = 10 ** 7                      # what "no limit" becomes: far beyond anything real, and still a plain number


def _limit(name: str, default: str = "0"):
    v = float(env(name) or default)
    return _NONE if v <= 0 else v


MAX_UPLOAD_MB = int(_limit("PEAKCUT_MAX_UPLOAD_MB"))              # the largest video file someone may upload
# A big file is sent in pieces of this size and joined here, because web servers and CDNs in front of the app
# refuse very large single requests (Cloudflare stops at 100 MB).
UPLOAD_PART_MB = max(5, int(env("PEAKCUT_UPLOAD_PART_MB", "40")))
# The most videos that may ever run at once. How many actually run is decided by how busy the machine is (load.py).
JOB_WORKERS = int(env("PEAKCUT_JOB_WORKERS") or max(2, os.cpu_count() or 4))
MAX_ACTIVE_JOBS_PER_USER = int(_limit("PEAKCUT_MAX_JOBS_PER_USER", "5"))    # videos sent and worked on at once
MAX_LIVE_TOTAL = int(env("PEAKCUT_MAX_LIVE") or max(4, 2 * (os.cpu_count() or 4)))   # ceiling; real load decides below it
MAX_LIVE_PER_USER = int(_limit("PEAKCUT_MAX_LIVE_PER_USER"))     # streams one person records at once
MAX_VIDEO_HOURS = _limit("PEAKCUT_MAX_VIDEO_HOURS")              # longest video (or chosen part of one) that is processed
MAX_LIVE_HOURS = _limit("PEAKCUT_MAX_LIVE_HOURS")                # a recording stops by itself after this long
MAX_USER_GB = _limit("PEAKCUT_MAX_USER_GB")                      # disk space one account may fill
MAX_CREATORS = int(_limit("PEAKCUT_MAX_CREATORS"))               # creators one account may add
ALLOWED_SITES = tuple(s.strip().lower() for s in env(
    "PEAKCUT_ALLOWED_SITES", "youtube.com,youtu.be,twitch.tv,kick.com").split(",") if s.strip())

# ---------------------------------------------------------------- AI (bring your own key: see studio/ai.py)
# These are the starting values. Whatever is saved from the dashboard (Settings, AI) is used instead.
AI_PROVIDER = env("CLIPSX_AI_PROVIDER", env("PEAKCUT_AI_PROVIDER", "")).strip().lower()            # gemini, openai, xai, groq, openrouter, anthropic, ollama, custom
AI_MODELS = [m.strip() for m in env("PEAKCUT_AI_MODELS", "").split(",") if m.strip()]   # tried in this order
AI_BASE_URL = env("PEAKCUT_AI_BASE_URL", "").rstrip("/")                      # only for "custom", or to override a provider's address


def ai_key() -> str:
    return _secret("PEAKCUT_AI_KEY", "PEAKCUT_AI_KEY_FILE", r"\S{8,}")


def ai_ready() -> bool:
    from . import ai
    return ai.ready()


# ---------------------------------------------------------------- account emails (see mailer.py)
SMTP_HOST = env("PEAKCUT_SMTP_HOST", "")
SMTP_PORT = int(env("PEAKCUT_SMTP_PORT", "587"))
SMTP_USER = env("PEAKCUT_SMTP_USER", "")
MAIL_FROM = env("PEAKCUT_MAIL_FROM", "")
CONTACT_EMAIL = env("PEAKCUT_CONTACT_EMAIL", "")
LEGAL_NAME = env("CLIPSX_LEGAL_NAME", env("PEAKCUT_LEGAL_NAME", "Clips X"))            # the business that runs Clips X, for the legal pages
LEGAL_COUNTRY = env("PEAKCUT_LEGAL_COUNTRY", "")      # whose law applies, for the terms
# Set to 1 on a public site with email set up: password sign-ups must then confirm their address before clipping.
VERIFY_EMAIL = env("PEAKCUT_VERIFY_EMAIL", "0") == "1"


def smtp_password() -> str:
    return _secret("PEAKCUT_SMTP_PASSWORD", "PEAKCUT_SMTP_PASSWORD_FILE", r"\S{4,}")


# ---------------------------------------------------------------- Cloudflare & Bot Protection
CLOUDFLARE_ACCOUNT_ID = env("CLOUDFLARE_ACCOUNT_ID", "").strip()
CLOUDFLARE_ZONE_ID = env("CLOUDFLARE_ZONE_ID", "").strip()
CLOUDFLARE_API_TOKEN = env("CLOUDFLARE_API_TOKEN", "").strip()
TURNSTILE_SITE_KEY = env("TURNSTILE_SITE_KEY", "").strip()
TURNSTILE_SECRET_KEY = env("TURNSTILE_SECRET_KEY", "").strip()
TURNSTILE_ENABLED = env("TURNSTILE_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")

# ---------------------------------------------------------------- session & cookie security
SESSION_SECRET = env("SESSION_SECRET", env("JWT_SECRET", "")).strip()
_cookie_sec = env("SESSION_COOKIE_SECURE")
SESSION_COOKIE_SECURE = (_cookie_sec.strip().lower() in ("1", "true", "yes", "on")) if _cookie_sec is not None else HTTPS

# ---------------------------------------------------------------- rate limiting (configurable via .env)
LOGIN_RATE_LIMIT_MAX = int(env("LOGIN_RATE_LIMIT_MAX", "5"))
LOGIN_RATE_LIMIT_WINDOW = int(env("LOGIN_RATE_LIMIT_WINDOW_MINUTES", "15")) * 60
REGISTER_RATE_LIMIT_MAX = int(env("REGISTER_RATE_LIMIT_MAX", "3"))
REGISTER_RATE_LIMIT_WINDOW = int(env("REGISTER_RATE_LIMIT_WINDOW_MINUTES", "60")) * 60
PASSWORD_RESET_RATE_LIMIT_MAX = int(env("PASSWORD_RESET_RATE_LIMIT_MAX", "3"))
PASSWORD_RESET_RATE_LIMIT_WINDOW = int(env("PASSWORD_RESET_RATE_LIMIT_WINDOW_MINUTES", "60")) * 60

# ---------------------------------------------------------------- Google OAuth
GOOGLE_CALLBACK_URL = env("GOOGLE_CALLBACK_URL", f"{PUBLIC_URL}/auth/google/callback").strip()


# ---------------------------------------------------------------- Google (sign in with Google, and connecting YouTube)
def google_client() -> tuple:
    """(client id, client secret). Either GOOGLE_CLIENT_ID/SECRET, or GOOGLE_CLIENT_FILE = the JSON Google lets you download."""
    return _keep("google", _read_google_client)


def _read_google_client() -> tuple:
    if env("GOOGLE_CLIENT_ID") and env("GOOGLE_CLIENT_SECRET"):
        return env("GOOGLE_CLIENT_ID").strip(), env("GOOGLE_CLIENT_SECRET").strip()
    path = env("GOOGLE_CLIENT_FILE")
    if path and Path(path).exists():
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            web = data.get("web") or data.get("installed") or {}
            return web.get("client_id", ""), web.get("client_secret", "")
        except ValueError:
            pass
    return "", ""


def validate_config() -> list:
    """Check configuration health on startup without ever leaking secrets in logs."""
    notices = []
    if TURNSTILE_ENABLED and not TURNSTILE_SECRET_KEY:
        notices.append("Turnstile is enabled but TURNSTILE_SECRET_KEY is empty.")
    if ACCOUNTS and not OWNER_EMAIL:
        notices.append("Accounts enabled but no ADMIN_EMAIL / CLIPSX_OWNER_EMAIL set.")
    return notices


# ---------------------------------------------------------------- video
MAX_SOURCE_HEIGHT = 1080
OUT_W, OUT_H, OUT_FPS = 1080, 1920, 30
