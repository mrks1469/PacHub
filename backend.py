"""
PacHub — backend.py
All pacman / system data functions: package queries, AUR search,
update checks, orphan detection, system info, and demo data.
"""

import subprocess
import threading
from gi.repository import GLib


# ─── Demo data (used when pacman is unavailable) ──────────────────────────────

DEMO_PACKAGES = [
    ("base","3-1","core","Minimal package set to define a basic Arch Linux installation"),
    ("linux","6.7.4.arch1-1","core","The Linux kernel and modules"),
    ("linux-firmware","20240312.bf4e0cc-1","core","Firmware files for Linux"),
    ("glibc","2.39-1","core","GNU C Library"),
    ("bash","5.2.026-2","core","The GNU Bourne Again shell"),
    ("coreutils","9.4-2","core","Basic file, shell and text manipulation utilities"),
    ("systemd","255.4-1","core","System and service manager"),
    ("dbus","1.14.10-2","core","Freedesktop.org message bus system"),
    ("gtk4","4.14.1-1","extra","GObject-based multi-platform UI toolkit"),
    ("libadwaita","1.5.0-1","extra","Building blocks for modern GNOME applications"),
    ("python","3.11.8-1","core","High-level scripting language"),
    ("git","2.44.0-1","extra","The fast distributed version control system"),
    ("vim","9.1.0104-1","extra","Vi Improved, a highly configurable text editor"),
    ("nano","7.2-3","core","Pico editor clone with enhancements"),
    ("curl","8.6.0-1","core","URL retrieval utility and library"),
    ("wget","1.21.4-1","extra","Network utility to retrieve files from the web"),
    ("openssh","9.6p1-1","core","SSH connectivity tools"),
    ("pacman","6.0.2-8","core","A library-based package manager"),
    ("mesa","23.3.5-1","extra","Open-source implementation of OpenGL"),
    ("alsa-utils","1.2.11-1","extra","ALSA utilities"),
    ("pipewire","1.0.3-3","extra","Low-latency audio/video router and processor"),
    ("networkmanager","1.46.0-1","extra","Network connection manager and user applications"),
    ("firefox","123.0.1-1","extra","Standalone web browser from Mozilla"),
    ("chromium","122.0.6261.128-1","extra","Open-source web browser project from Google"),
    ("gimp","2.10.36-2","extra","GNU Image Manipulation Program"),
    ("vlc","3.0.20-4","extra","Multi-platform MPEG and DVD player"),
    ("htop","3.3.0-2","extra","Interactive process viewer"),
    ("python-pip","24.0-1","extra","The PyPA recommended tool for installing Python packages"),
    ("docker","25.0.3-1","extra","Pack, ship and run applications as containers"),
    ("nodejs","21.6.1-1","extra","Evented I/O for V8 Javascript"),
    ("npm","10.5.0-1","extra","The package manager for JavaScript"),
    ("rust","1.76.0-1","extra","Systems programming language focused on safety"),
    ("go","2:1.22.0-1","extra","Core compiler tools for the Go programming language"),
    ("cmake","3.28.3-1","extra","A cross-platform open-source make system"),
    ("flatpak","1.15.6-1","extra","Linux application sandboxing and distribution"),
    ("lib32-glibc","2.39-1","multilib","GNU C Library (32-bit)"),
    ("lib32-mesa","23.3.5-1","multilib","Open-source implementation of OpenGL (32-bit)"),
    ("neofetch","7.1.0-2","aur","A fast, highly customizable system info script"),
    ("yay","12.3.5-1","aur","Yet another yogurt — AUR helper written in Go"),
    ("paru","2.0.1-1","aur","Feature packed AUR helper"),
    ("timeshift","24.01.1-1","aur","A system restore utility for Linux"),
    ("visual-studio-code-bin","1.87.0-1","aur","Visual Studio Code editor from Microsoft"),
    ("google-chrome","122.0.6261.128-1","aur","The popular web browser from Google"),
]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def run_command(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
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
                cmd, shell=True,
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
    _, code = run_command("which pacman 2>/dev/null")
    return code != 0


# ─── Package queries ──────────────────────────────────────────────────────────

def get_packages():
    out, code = run_command("pacman -Q 2>/dev/null")
    if not out or code != 0:
        return [{"name": n, "version": v, "repo": r, "status": "installed",
                 "description": d, "foreign": r == "aur"} for n, v, r, d in DEMO_PACKAGES]

    all_pkgs = {}
    for line in out.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            all_pkgs[parts[0]] = {"name": parts[0], "version": parts[1],
                                   "repo": "local", "status": "installed",
                                   "description": "", "foreign": False}

    foreign_out, _ = run_command("pacman -Qm 2>/dev/null")
    for line in (foreign_out or "").splitlines():
        parts = line.strip().split(None, 1)
        if parts and parts[0] in all_pkgs:
            all_pkgs[parts[0]]["foreign"] = True
            all_pkgs[parts[0]]["repo"] = "aur"

    sl_out, _ = run_command("pacman -Sl 2>/dev/null")
    if sl_out:
        for line in sl_out.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                repo, pkgname = parts[0], parts[1]
                if pkgname in all_pkgs and not all_pkgs[pkgname]["foreign"]:
                    all_pkgs[pkgname]["repo"] = repo

    return list(all_pkgs.values())


def get_package_info(pkg_name):
    out, code = run_command(f"pacman -Qi '{pkg_name}' 2>/dev/null")
    if out and code == 0:
        return out
    out2, code2 = run_command(f"pacman -Si --noconfirm '{pkg_name}' 2>/dev/null")
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
    out, code = run_command(f"pacman -Ql '{pkg_name}' 2>/dev/null")
    if out and code == 0:
        return out.splitlines()
    return [f"{pkg_name} /usr/bin/{pkg_name}", f"{pkg_name} /usr/share/man/man1/{pkg_name}.1"]


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

    out, code = run_command(f"pacman -Ss '{query}' 2>/dev/null")
    if out and code == 0:
        for p in parse_pacman_ss(out):
            if p["name"] not in seen:
                seen.add(p["name"])
                packages.append(p)

    aur_helper = None
    for h in ("yay", "paru"):
        _, c = run_command(f"which {h} 2>/dev/null")
        if c == 0:
            aur_helper = h
            break
    if aur_helper:
        aur_out, aur_code = run_command(f"{aur_helper} -Ss --aur '{query}' 2>/dev/null", timeout=30)
        if aur_out and aur_code == 0:
            for p in parse_pacman_ss(aur_out):
                if p["name"] not in seen:
                    p["foreign"] = True
                    if p["repo"].lower() not in ("core", "extra", "multilib", "community"):
                        p["repo"] = "aur"
                    seen.add(p["name"])
                    packages.append(p)

    return packages
