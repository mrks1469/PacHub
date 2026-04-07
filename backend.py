"""
PacHub — backend.py
All pacman / system data functions: package queries, AUR search,
update checks, orphan detection, system info, and demo data.

Caching strategy
----------------
~/.cache/pachub/
  installed.json   — pacman -Q + -Qm output, invalidated when pacman -Q changes
  syncdb.json      — pacman -Sl output, TTL 6 h (changes only after pacman -Sy)
  packages.json    — merged full package list (served instantly on next launch)
"""

import json
import os
import re
import shutil
import subprocess
import threading
import time
import hashlib
from pathlib import Path
from gi.repository import GLib


# ─── Cache paths ──────────────────────────────────────────────────────────────

CACHE_DIR      = Path.home() / ".cache" / "pachub"
PKG_CACHE      = CACHE_DIR / "packages.json"
SYNCDB_CACHE   = CACHE_DIR / "syncdb.json"
INSTALLED_CACHE= CACHE_DIR / "installed.json"
SYNCDB_TTL     = 6 * 3600   # 6 hours
SAFE_PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9._+@-]+$")

def _ensure_cache_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _read_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None

def _write_json(path, data):
    try:
        _ensure_cache_dir()
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, separators=(",", ":"))
        tmp.replace(path)
    except Exception:
        pass

def _file_age(path):
    """Return seconds since file was last modified, or infinity."""
    try:
        return time.time() - path.stat().st_mtime
    except Exception:
        return float("inf")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def run_command(cmd, timeout=30):
    try:
        r = subprocess.run(
            cmd,
            shell=isinstance(cmd, str),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return r.stdout.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", 1
    except Exception as e:
        return str(e), 1


def run_command_stream(cmd, on_line, on_done, timeout=180):
    """Run a non-interactive command, streaming output line by line."""
    def worker():
        try:
            proc = subprocess.Popen(
                cmd,
                shell=isinstance(cmd, str),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True, bufsize=1
            )
            for line in proc.stdout:
                GLib.idle_add(on_line, line.rstrip())
            proc.wait()
            GLib.idle_add(on_done, proc.returncode)
        except Exception as e:
            GLib.idle_add(on_line, f"Error: {e}")
            GLib.idle_add(on_done, 1)
    threading.Thread(target=worker, daemon=True).start()


def _is_demo():
    return shutil.which("pacman") is None


def is_safe_package_name(name):
    return bool(name and SAFE_PACKAGE_NAME_RE.fullmatch(name))


def find_installed_helper(*helpers):
    for helper in helpers:
        if shutil.which(helper):
            return helper
    return None


# ─── Popular AUR packages to always show in the list ─────────────────────────
POPULAR_AUR_PACKAGES = [
    ("yay",                    "12.3.5-1",   "Yet another yogurt - AUR helper written in Go"),
    ("paru",                   "2.0.4-1",    "Feature packed AUR helper"),
    ("google-chrome",          "124.0-1",    "The popular web browser by Google"),
    ("visual-studio-code-bin", "1.89.0-1",   "Visual Studio Code editor from Microsoft"),
    ("discord",                "0.0.57-1",   "All-in-one voice and text chat for gamers"),
    ("spotify",                "1.2.25-1",   "A proprietary music streaming service"),
    ("1password",              "8.10.30-1",  "Password manager and secure digital wallet"),
    ("zoom",                   "6.0.2-1",    "Video conferencing, web conferencing, webinars"),
    ("slack-desktop",          "4.38.125-1", "Messaging app for teams"),
    ("telegram-desktop-bin",   "5.1.6-1",    "Official Telegram Desktop client"),
    ("obs-studio-browser",     "30.1.2-1",   "Free and open source streaming/recording software"),
    ("timeshift",              "24.01.1-1",  "System restore utility for Linux"),
    ("ventoy-bin",             "1.0.99-1",   "Tool to create bootable USB drives"),
    ("onlyoffice-bin",         "8.0.1-1",    "Free office suite compatible with MS Office"),
    ("bottles",                "51.14-1",    "Run Windows software on Linux using Wine"),
    ("protonup-qt",            "2.9.0-1",    "Install and manage Proton-GE and Luxtorpeda"),
    ("heroic-games-launcher",  "2.14.0-1",   "Open source Epic, GOG and Amazon Games launcher"),
    ("lutris",                 "0.5.17-1",   "Open gaming platform for Linux"),
    ("mangohud",               "0.7.1-1",    "Vulkan/OpenGL overlay for monitoring FPS and temps"),
    ("nerd-fonts-complete",    "3.2.1-1",    "Iconic font aggregator and collection"),
    ("ttf-ms-fonts",           "0.1-9",      "Core Microsoft fonts"),
    ("pamac-aur",              "11.6.0-1",   "A Package Manager with AUR support"),
    ("pikaur",                 "1.28-1",     "Lightweight AUR package manager"),
    ("sublime-text-4",         "4.0.4180-1", "Sophisticated text editor for code and prose"),
    ("jetbrains-toolbox",      "2.3.2-1",    "JetBrains IDE manager"),
    ("postman-bin",            "11.0.9-1",   "API development environment"),
    ("insomnia",               "9.2.0-1",    "Open-source API client"),
    ("dbeaver",                "24.0.5-1",   "Universal database tool and SQL client"),
    ("wine",                   "9.8-1",      "A compatibility layer for running Windows programs"),
    ("steam",                  "1.0.0.79-2", "Valve's digital software delivery system"),
]


# ─── Installed-package fingerprint ────────────────────────────────────────────

def _installed_fingerprint():
    """Fast fingerprint of installed packages using local DB mtime + count."""
    local_db = Path("/var/lib/pacman/local")
    out, code = run_command("pacman -Q 2>/dev/null")
    if code != 0:
        return None
    # Combine package count + local db mtime for a fast, reliable fingerprint
    try:
        mtime = str(int(local_db.stat().st_mtime))
    except Exception:
        mtime = "0"
    pkg_count = str(out.count("\n"))
    fingerprint = hashlib.md5(f"{mtime}:{pkg_count}".encode()).hexdigest()
    return fingerprint, out


# ─── Sync-DB cache (pacman -Sl) ───────────────────────────────────────────────

def _load_syncdb_cache():
    """Return cached pacman -Sl data if it's fresh enough."""
    if _file_age(SYNCDB_CACHE) < SYNCDB_TTL:
        data = _read_json(SYNCDB_CACHE)
        if data:
            return data
    return None

def _parse_db_file(db_path):
    """Parse one pacman .db tarball and return {pkgname: (repo, version, desc)}."""
    import tarfile
    repo = db_path.stem  # filename without .db = repo name
    result = {}
    try:
        with tarfile.open(db_path, "r:*") as tar:
            members = {m.name: m for m in tar.getmembers()}
            desc_members = [m for name, m in members.items() if name.endswith("/desc")]
            for member in desc_members:
                f = tar.extractfile(member)
                if not f:
                    continue
                content = f.read().decode("utf-8", errors="replace")
                name = version = desc = None
                lines = content.splitlines()
                i = 0
                while i < len(lines):
                    tag = lines[i]
                    if tag in ("%NAME%", "%VERSION%", "%DESC%") and i + 1 < len(lines):
                        val = lines[i + 1].strip()
                        if tag == "%NAME%":
                            name = val
                        elif tag == "%VERSION%":
                            version = val
                        elif tag == "%DESC%":
                            desc = val
                    i += 1
                if name:
                    result[name] = (repo, version or "", desc or "")
    except Exception:
        pass
    return result


def _build_syncdb(installed_set):
    """Build sync DB from local pacman .db files (fast, no subprocess needed)."""
    from concurrent.futures import ThreadPoolExecutor
    sync_dir = Path("/var/lib/pacman/sync")
    pkgs = {}

    if sync_dir.exists():
        db_files = list(sync_dir.glob("*.db"))
        with ThreadPoolExecutor(max_workers=min(4, len(db_files) or 1)) as ex:
            futures = [ex.submit(_parse_db_file, db) for db in db_files]
            for future in futures:
                for name, (repo, version, desc) in future.result().items():
                    pkgs[name] = {"repo": repo, "version": version, "description": desc}

    # Fallback: if no .db files found, use pacman -Sl (slower)
    if not pkgs:
        sl_out, sl_code = run_command("pacman -Sl 2>/dev/null", timeout=60)
        if sl_out and sl_code == 0:
            for line in sl_out.splitlines():
                parts = line.strip().split()
                if len(parts) >= 3:
                    repo, pkgname, version = parts[0], parts[1], parts[2]
                    pkgs[pkgname] = {"repo": repo, "version": version, "description": ""}

    _write_json(SYNCDB_CACHE, pkgs)
    return pkgs


# ─── Main package list ────────────────────────────────────────────────────────

def _merge_into_list(installed_pkgs, syncdb, aur_set):
    """Combine installed + syncdb + popular AUR into the final package list."""
    all_pkgs = dict(installed_pkgs)

    for pkgname, info in syncdb.items():
        desc = info.get("description", "")
        if pkgname in all_pkgs:
            if not all_pkgs[pkgname]["foreign"]:
                all_pkgs[pkgname]["repo"] = info["repo"]
            # Always fill description from syncdb if missing
            if not all_pkgs[pkgname].get("description"):
                all_pkgs[pkgname]["description"] = desc
        else:
            all_pkgs[pkgname] = {
                "name": pkgname,
                "version": info["version"],
                "repo": info["repo"],
                "status": "available",
                "description": desc,
                "foreign": False,
            }

    for name, version, desc in POPULAR_AUR_PACKAGES:
        if name not in all_pkgs:
            all_pkgs[name] = {
                "name": name, "version": version, "repo": "aur",
                "status": "available", "description": desc, "foreign": True,
            }

    return list(all_pkgs.values())


def get_packages():
    """
    Return package list as fast as possible.

    Launch path:
      1. If packages.json cache exists AND installed fingerprint matches → return cache instantly.
      2. Otherwise build from scratch (pacman -Q + cached/fresh pacman -Sl) and save cache.
    """
    if _is_demo():
        demo = []
        for name, version, desc in POPULAR_AUR_PACKAGES:
            demo.append({"name": name, "version": version, "repo": "aur",
                          "status": "available", "description": desc, "foreign": True})
        return demo

    # ── Fast path: fingerprint check ─────────────────────────────────────────
    result = _installed_fingerprint()
    if result is None:
        return []
    fingerprint, raw_Q = result

    cached = _read_json(PKG_CACHE)
    if cached and cached.get("fingerprint") == fingerprint:
        return cached["packages"]

    # ── Slow path: rebuild ────────────────────────────────────────────────────
    # Step 1 — installed packages
    installed_pkgs = {}
    for line in raw_Q.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            installed_pkgs[parts[0]] = {
                "name": parts[0], "version": parts[1],
                "repo": "local", "status": "installed",
                "description": "", "foreign": False,
            }

    # Step 2 — mark AUR/foreign
    foreign_out, _ = run_command("pacman -Qm 2>/dev/null")
    for line in (foreign_out or "").splitlines():
        parts = line.strip().split(None, 1)
        if parts and parts[0] in installed_pkgs:
            installed_pkgs[parts[0]]["foreign"] = True
            installed_pkgs[parts[0]]["repo"] = "aur"

    # Step 3 — sync DB (use cache if fresh, else rebuild)
    syncdb = _load_syncdb_cache()
    if syncdb is None:
        syncdb = _build_syncdb(set(installed_pkgs))

    # Step 4 — merge
    packages = _merge_into_list(installed_pkgs, syncdb, set())

    # Step 5 — save cache
    _write_json(PKG_CACHE, {"fingerprint": fingerprint, "packages": packages})

    return packages


def invalidate_cache():
    """Call this after install/remove/upgrade so next load rebuilds."""
    try:
        PKG_CACHE.unlink(missing_ok=True)
    except Exception:
        pass


def invalidate_syncdb_cache():
    """Call this after pacman -Sy so the sync DB is re-fetched."""
    try:
        SYNCDB_CACHE.unlink(missing_ok=True)
    except Exception:
        pass


# ─── Package info / files ─────────────────────────────────────────────────────

def get_package_info(pkg_name):
    if not is_safe_package_name(pkg_name):
        return "Invalid package name."
    out, code = run_command(["pacman", "-Qi", pkg_name])
    if out and code == 0:
        return out
    out2, code2 = run_command(["pacman", "-Si", "--noconfirm", pkg_name])
    if out2 and code2 == 0:
        return out2
    return (f"Name           : {pkg_name}\nVersion        : 1.0.0-1\n"
            f"Description    : Demo package (not on Arch Linux)\n"
            f"Architecture   : x86_64\nURL            : https://example.com/{pkg_name}\n"
            f"Licenses       : GPL\nGroups         : None\nProvides       : None\n"
            f"Depends On     : glibc\nOptional Deps  : None\nConflicts With : None\n"
            f"Replaces       : None\nInstalled Size : 1.20 MiB\nPackager       : Arch Linux\n"
            f"Build Date     : Thu 01 Jan 2026\nInstall Date   : Thu 01 Jan 2026\n"
            f"Install Reason : Explicitly installed\nValidated By   : Signature\n")


def get_package_files(pkg_name):
    if not is_safe_package_name(pkg_name):
        return ["Invalid package name."]
    out, code = run_command(["pacman", "-Ql", pkg_name])
    if out and code == 0:
        return out.splitlines()
    return [f"{pkg_name} /usr/bin/{pkg_name}", f"{pkg_name} /usr/share/man/man1/{pkg_name}.1"]


# ─── Updates / orphans / sysinfo ─────────────────────────────────────────────

def check_updates():
    out, code = run_command("checkupdates 2>/dev/null || pacman -Qu 2>/dev/null", timeout=60)
    updates = []
    if out and code == 0:
        for line in out.splitlines():
            parts = line.strip().split()
            if len(parts) >= 4:
                updates.append({"name": parts[0], "old": parts[1], "new": parts[3]})
    return updates


def get_orphans():
    out, _ = run_command("pacman -Qdt 2>/dev/null")
    orphans = []
    if out:
        for line in out.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                orphans.append({"name": parts[0], "version": parts[1]})
    if not orphans and _is_demo():
        orphans = [
            {"name": "lib32-libpng12", "version": "1.2.56-2"},
            {"name": "perl-encode-locale", "version": "1.05-7"},
            {"name": "python2", "version": "2.7.18-3"},
        ]
    return orphans


def get_system_info():
    info = {}
    out, _ = run_command("uname -r 2>/dev/null"); info["Kernel"] = out or "Unknown"
    out, _ = run_command("uname -m 2>/dev/null"); info["Architecture"] = out or "x86_64"
    out, _ = run_command("cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'")
    info["OS"] = out or "Arch Linux"
    out, _ = run_command("pacman --version 2>/dev/null | head -1"); info["Pacman"] = out or "6.0.x"
    out, _ = run_command("df -h / 2>/dev/null | awk 'NR==2{print $3\"/\"$2\" (\"$5\" used)\"}'")
    info["Disk (/)"] = out or "N/A"
    out, _ = run_command("free -h 2>/dev/null | awk 'NR==2{print $3\"/\"$2}'")
    info["RAM"] = out or "N/A"
    out, _ = run_command("pacman -Q 2>/dev/null | wc -l"); info["Installed Packages"] = out or "N/A"
    out, _ = run_command("pacman -Qm 2>/dev/null | wc -l"); info["Foreign (AUR) Packages"] = out or "0"
    out, _ = run_command("du -sh /var/cache/pacman/pkg 2>/dev/null | cut -f1")
    info["Package Cache Size"] = out or "N/A"
    return info


# ─── Search ───────────────────────────────────────────────────────────────────

def search_packages_cmd(query):
    def parse_pacman_ss(out):
        pkgs = []
        lines = out.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if '/' in line and not line.startswith(' '):
                parts = line.split()
                if parts:
                    repo_pkg = parts[0]
                    version = parts[1] if len(parts) > 1 else "unknown"
                    repo, name = repo_pkg.split('/', 1) if '/' in repo_pkg else ('', repo_pkg)
                    desc = lines[i + 1].strip() if i + 1 < len(lines) else ""
                    pkgs.append({"name": name, "version": version, "repo": repo,
                                 "description": desc, "status": "available",
                                 "foreign": repo.lower() == "aur"})
                    i += 2
                    continue
            i += 1
        return pkgs

    packages = []
    seen = set()

    out, code = run_command(["pacman", "-Ss", query])
    if out and code == 0:
        for p in parse_pacman_ss(out):
            if p["name"] not in seen:
                seen.add(p["name"])
                packages.append(p)

    aur_helper = find_installed_helper("yay", "paru")
    if aur_helper:
        aur_out, aur_code = run_command([aur_helper, "-Ss", "--aur", query], timeout=30)
        if aur_out and aur_code == 0:
            for p in parse_pacman_ss(aur_out):
                if p["name"] not in seen:
                    p["foreign"] = True
                    if p["repo"].lower() not in ("core", "extra", "multilib", "community"):
                        p["repo"] = "aur"
                    seen.add(p["name"])
                    packages.append(p)

    return packages
