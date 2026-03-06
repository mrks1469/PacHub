#!/usr/bin/env python3
"""
PacHub — A powerful Pacman/AUR front end using GTK4 and libadwaita
"""

import gi
import subprocess
import threading
import sys

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, Gio, Gdk, GObject, Pango


# ─── Styles ──────────────────────────────────────────────────────────────────

CSS = """
/* ── Nav rows ── */
.nav-row {
    border-radius: 8px;
    margin: 1px 6px;
}
.nav-row:selected {
    background: alpha(@accent_bg_color, 0.16);
}
.nav-row label {
    font-weight: 600;
    font-size: 0.88rem;
}

/* ── Package rows ── */
.pkg-row { border-radius: 6px; margin: 1px 8px; }
.pkg-row:hover { background: alpha(@card_fg_color, 0.05); }
.pkg-row:selected,
.pkg-row:selected:hover { background: alpha(@accent_bg_color, 0.18); }

/* ── Badges ── */
.badge {
    border-radius: 999px;
    padding: 1px 7px;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.04em;
}
.badge-core     { background: alpha(#3584e4, 0.18); color: #3584e4; }
.badge-extra    { background: alpha(#2ec27e, 0.18); color: #26a269; }
.badge-aur      { background: alpha(#9141ac, 0.18); color: #9141ac; }
.badge-local    { background: alpha(@card_fg_color, 0.10); color: alpha(@card_fg_color, 0.55); }
.badge-multilib { background: alpha(#e5a50a, 0.18); color: #c38600; }
.badge-foreign  { background: alpha(#e66100, 0.18); color: #e66100; }

/* ── Status pills ── */
.status-pill {
    border-radius: 999px;
    padding: 2px 10px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.05em;
}
.status-installed { background: alpha(#2ec27e, 0.15); color: #26a269; }
.status-available { background: alpha(@accent_bg_color, 0.15); color: @accent_color; }
.status-update    { background: alpha(#e5a50a, 0.15); color: #c38600; }
.status-foreign   { background: alpha(#e66100, 0.15); color: #e66100; }

/* ── Terminal ── */
.terminal-view {
    background: #0d1117;
    color: #c9d1d9;
    border-radius: 8px;
    font-family: "Cascadia Code","JetBrains Mono","Fira Code",monospace;
    font-size: 0.85rem;
    padding: 14px 16px;
}

/* ── Detail hero ── */
.pkg-hero {
    background: alpha(@card_fg_color, 0.04);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 4px;
}

/* ── Sidebar section labels (GTK4-valid CSS only) ── */
.sidebar-section {
    font-size: 0.78rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    color: alpha(@window_fg_color, 0.50);
    margin-top: 6px;
    margin-bottom: 4px;
}

/* ── Stat cards ── */
.stat-card {
    background: alpha(@accent_bg_color, 0.08);
    border-radius: 12px;
    padding: 10px 6px;
    border: 1px solid alpha(@accent_bg_color, 0.18);
}
.stat-card-aur {
    background: alpha(#9141ac, 0.08);
    border-radius: 12px;
    padding: 10px 6px;
    border: 1px solid alpha(#9141ac, 0.18);
}
.stat-card-updates {
    background: alpha(#e5a50a, 0.08);
    border-radius: 12px;
    padding: 10px 6px;
    border: 1px solid alpha(#e5a50a, 0.18);
}
.stat-number {
    font-size: 1.45rem;
    font-weight: 900;
}
.stat-label {
    font-size: 0.64rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    color: alpha(@window_fg_color, 0.48);
}

/* ── Count badges ── */
.count-badge {
    border-radius: 999px;
    background: alpha(@card_fg_color, 0.10);
    padding: 0px 7px;
    font-size: 0.70rem;
    font-weight: 700;
    min-width: 20px;
}
.count-update  { background: alpha(#e5a50a, 0.15); color: #c38600; }
.count-foreign { background: alpha(#9141ac, 0.15); color: #9141ac; }

/* ── Misc ── */
.install-btn { border-radius: 8px; font-weight: 600; }
.remove-btn  { border-radius: 8px; font-weight: 600; }
.orphan-row  { border-left: 3px solid alpha(#e66100, 0.6); }

progressbar.success trough progress { background: #2ec27e; }
progressbar.warning trough progress { background: #e5a50a; }
progressbar trough { border-radius: 999px; min-height: 6px; }
progressbar trough progress { border-radius: 999px; }
"""


def load_css():
    p = Gtk.CssProvider()
    p.load_from_data(CSS.encode())
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

# ─── Backend ─────────────────────────────────────────────────────────────────


# ─── Demo data ────────────────────────────────────────────────────────────────
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

# ─── Models ──────────────────────────────────────────────────────────────────

REPO_BADGE_CLASS = {
    "core": "badge-core", "extra": "badge-extra", "aur": "badge-aur",
    "multilib": "badge-multilib", "local": "badge-local", "foreign": "badge-foreign",
}

# Fallback symbolic icons for packages without .desktop files
PKG_ICONS = {
    "linux": "utilities-terminal-symbolic",
    "linux-firmware": "drive-harddisk-symbolic",
    "base": "package-x-generic-symbolic",
    "bash": "utilities-terminal-symbolic",
    "zsh": "utilities-terminal-symbolic",
    "fish": "utilities-terminal-symbolic",
    "git": "preferences-system-details-symbolic",
    "python": "text-x-script-symbolic",
    "python-pip": "text-x-script-symbolic",
    "nodejs": "text-x-script-symbolic",
    "npm": "text-x-script-symbolic",
    "rust": "application-x-executable-symbolic",
    "go": "application-x-executable-symbolic",
    "cmake": "applications-engineering-symbolic",
    "docker": "application-x-executable-symbolic",
    "flatpak": "package-x-generic-symbolic",
    "pacman": "package-x-generic-symbolic",
    "yay": "package-x-generic-symbolic",
    "paru": "package-x-generic-symbolic",
    "networkmanager": "network-wireless-symbolic",
    "openssh": "network-server-symbolic",
    "pipewire": "audio-speakers-symbolic",
    "alsa-utils": "audio-card-symbolic",
    "htop": "utilities-system-monitor-symbolic",
    "curl": "network-transmit-receive-symbolic",
    "wget": "network-transmit-receive-symbolic",
    "vim": "text-editor-symbolic",
    "nano": "text-editor-symbolic",
    "mesa": "video-display-symbolic",
    "timeshift": "document-revert-symbolic",
    "systemd": "preferences-system-symbolic",
    "firefox": "web-browser-symbolic",
    "chromium": "web-browser-symbolic",
    "google-chrome": "web-browser-symbolic",
    "gimp": "applications-graphics-symbolic",
    "vlc": "applications-multimedia-symbolic",
    "visual-studio-code-bin": "text-editor-symbolic",
}


def pkg_icon(name):
    return PKG_ICONS.get(name, "package-x-generic-symbolic")


class PackageItem(GObject.Object):
    __gtype_name__ = 'PacHubPackageItem'

    def __init__(self, name, version, repo="local", status="installed", description="", foreign=False):
        super().__init__()
        self.pkg_name = name
        self.pkg_version = version
        self.pkg_repo = repo
        self.pkg_status = status
        self.pkg_description = description
        self.pkg_foreign = foreign


class PackageRow(Gtk.ListBoxRow):
    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        self.set_activatable(True)
        self.add_css_class("pkg-row")

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_top(9); box.set_margin_bottom(9)
        box.set_margin_start(10); box.set_margin_end(10)

        icon = Gtk.Image.new_from_icon_name(pkg_icon(pkg.pkg_name))
        icon.set_pixel_size(20)
        icon.set_valign(Gtk.Align.CENTER)
        icon.add_css_class("dim-label")
        box.append(icon)

        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        info_box.set_hexpand(True); info_box.set_valign(Gtk.Align.CENTER)

        name_label = Gtk.Label(label=pkg.pkg_name)
        name_label.set_halign(Gtk.Align.START)
        name_label.add_css_class("body")
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_weight_new(Pango.Weight.SEMIBOLD))
        name_label.set_attributes(attrs)
        info_box.append(name_label)

        if pkg.pkg_description:
            desc_label = Gtk.Label(label=pkg.pkg_description)
            desc_label.set_halign(Gtk.Align.START)
            desc_label.add_css_class("caption"); desc_label.add_css_class("dim-label")
            desc_label.set_ellipsize(Pango.EllipsizeMode.END)
            info_box.append(desc_label)
        box.append(info_box)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        right.set_valign(Gtk.Align.CENTER); right.set_halign(Gtk.Align.END)

        repo_str = "aur" if pkg.pkg_foreign else (pkg.pkg_repo or "local")
        badge = Gtk.Label(label=repo_str.upper())
        badge.add_css_class("badge")
        badge.add_css_class(REPO_BADGE_CLASS.get(repo_str.lower(), "badge-local"))
        right.append(badge)

        ver_label = Gtk.Label(label=pkg.pkg_version)
        ver_label.add_css_class("caption"); ver_label.add_css_class("dim-label")
        ver_label.set_halign(Gtk.Align.END)
        right.append(ver_label)

        box.append(right)
        self.set_child(box)


class NavRow(Gtk.ListBoxRow):
    def __init__(self, icon_name, label, count=None, badge_css=None):
        super().__init__()
        self.add_css_class("nav-row")
        self.set_activatable(True)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_top(7); box.set_margin_bottom(7)
        box.set_margin_start(10); box.set_margin_end(10)

        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(16); icon.set_valign(Gtk.Align.CENTER)
        icon.add_css_class("dim-label")
        box.append(icon)

        lbl = Gtk.Label(label=label)
        lbl.set_hexpand(True); lbl.set_halign(Gtk.Align.START)
        lbl.set_valign(Gtk.Align.CENTER)
        box.append(lbl)

        self.count_lbl = None
        if count is not None:
            self.count_lbl = Gtk.Label(label=str(count))
            self.count_lbl.add_css_class("count-badge")
            if badge_css:
                self.count_lbl.add_css_class(badge_css)
            self.count_lbl.set_valign(Gtk.Align.CENTER)
            self.count_lbl.set_visible(int(str(count)) > 0 if str(count).isdigit() else True)
            box.append(self.count_lbl)

        self._badge_css = badge_css
        self.set_child(box)

    def set_count(self, n):
        if self.count_lbl:
            self.count_lbl.set_label(str(n))
            self.count_lbl.set_visible(n > 0)

# ─── Window ──────────────────────────────────────────────────────────────────



class pachubWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("PacHub")
        self.set_default_size(1240, 780)
        self.set_size_request(900, 560)
        self._all_packages = []
        self._selected_pkg = None
        self._current_filter = "all"
        self._search_query = ""
        self._updates = None
        self._build_ui()
        self._load_packages()

    # ── Build UI ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.nav_split = Adw.NavigationSplitView()
        self.nav_split.set_max_sidebar_width(230)
        self.nav_split.set_min_sidebar_width(190)
        self.nav_split.set_sidebar_width_fraction(0.20)

        # ── SIDEBAR ──
        sidebar_page = Adw.NavigationPage()
        sidebar_page.set_title("PacHub")
        sidebar_tv = Adw.ToolbarView()
        sidebar_hdr = Adw.HeaderBar()
        sidebar_hdr.set_show_end_title_buttons(False)
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        app_icon = Gtk.Image.new_from_icon_name("package-x-generic-symbolic")
        app_icon.set_pixel_size(18)
        title_lbl = Gtk.Label(label="PacHub")
        title_lbl.add_css_class("heading")
        title_box.append(app_icon); title_box.append(title_lbl)
        sidebar_hdr.set_title_widget(title_box)
        sidebar_tv.add_top_bar(sidebar_hdr)
        sidebar_tv.set_content(self._build_sidebar())
        sidebar_page.set_child(sidebar_tv)
        self.nav_split.set_sidebar(sidebar_page)

        # ── CONTENT ──
        content_page = Adw.NavigationPage()
        content_page.set_title("Packages")
        self.content_tv = Adw.ToolbarView()
        self.content_hdr = Adw.HeaderBar()
        self.content_hdr.set_show_back_button(False)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search packages…")
        self.search_entry.set_hexpand(True)
        self.search_entry.set_size_request(300, -1)
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.content_hdr.set_title_widget(self.search_entry)

        right_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.btn_upgrade = Gtk.Button()
        self.btn_upgrade.set_icon_name("software-update-available-symbolic")
        self.btn_upgrade.set_tooltip_text("System upgrade (pacman -Syu)")
        self.btn_upgrade.connect("clicked", self._on_upgrade)
        self.btn_upgrade.add_css_class("suggested-action")
        right_box.append(self.btn_upgrade)

        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.add_css_class("flat")
        menu = Gio.Menu()
        menu.append("Sync Databases", "app.sync")
        menu.append("Check for Updates", "app.check_updates")
        menu.append("Refresh List", "app.refresh")
        menu.append_section(None, Gio.Menu())
        menu.append("Manage Repositories…", "app.manage_repos")
        menu.append("Rate Mirrors…", "app.rate_mirrors")
        menu.append_section(None, Gio.Menu())
        menu.append("Find Orphans", "app.orphans")
        menu.append("System Info", "app.sysinfo")
        menu.append("Cache Cleaner", "app.cache")
        menu.append_section(None, Gio.Menu())
        menu.append("About PacHub", "app.about")
        menu_btn.set_menu_model(menu)
        right_box.append(menu_btn)
        self.content_hdr.pack_end(right_box)
        self.content_tv.add_top_bar(self.content_hdr)

        # Update banner (hidden by default)
        self.update_banner = Adw.Banner()
        self.update_banner.set_button_label("Upgrade Now")
        self.update_banner.connect("button-clicked", self._on_upgrade)
        self.update_banner.set_revealed(False)
        self.content_tv.add_top_bar(self.update_banner)

        self.content_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.content_paned.set_position(380)
        self.content_paned.set_shrink_start_child(False)
        self.content_paned.set_shrink_end_child(False)
        self.content_paned.set_start_child(self._build_package_list_panel())
        self.content_paned.set_end_child(self._build_detail_panel())
        self.content_tv.set_content(self.content_paned)
        content_page.set_child(self.content_tv)
        self.nav_split.set_content(content_page)
        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(self.nav_split)
        self.set_content(self._toast_overlay)

    def _build_sidebar(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_margin_top(8)
        outer.set_margin_bottom(16)

        # ── Stats strip ───────────────────────────────────────────────────
        stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        stats_box.set_margin_start(10)
        stats_box.set_margin_end(10)
        stats_box.set_margin_top(4)
        stats_box.set_margin_bottom(12)

        self.stat_total   = self._stat_card("—", "TOTAL",   "stat-card")
        self.stat_aur     = self._stat_card("—", "AUR",     "stat-card-aur")
        self.stat_updates = self._stat_card("—", "UPDATES", "stat-card-updates")
        for card in (self.stat_total, self.stat_aur, self.stat_updates):
            stats_box.append(card)
        outer.append(stats_box)

        # ── Browse section ────────────────────────────────────────────────
        outer.append(self._sidebar_header("BROWSE"))

        self.nav_listbox = Gtk.ListBox()
        self.nav_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.nav_listbox.add_css_class("navigation-sidebar")
        self.nav_listbox.set_margin_start(5)
        self.nav_listbox.set_margin_end(5)
        self.nav_listbox.connect("row-activated", self._on_nav_selected)

        self._nav_rows = {}
        browse_items = [
            ("all",       "view-app-grid-symbolic",              "All Packages",  None,     None),
            ("installed", "emblem-ok-symbolic",                  "Installed",     None,     None),
            ("foreign",   "application-x-executable-symbolic",   "AUR / Foreign", None,     "count-foreign"),
            ("updates",   "software-update-available-symbolic",  "Updates",       None,     "count-update"),
        ]
        for key, icon, label, cnt, badge_cls in browse_items:
            row = self._nav_row(icon, label, cnt, badge_cls)
            self.nav_listbox.append(row)
            self._nav_rows[key] = row

        self.nav_listbox.select_row(self.nav_listbox.get_row_at_index(0))
        outer.append(self.nav_listbox)

        # ── Repositories section ──────────────────────────────────────────
        sep = Gtk.Separator()
        sep.set_margin_top(8)
        sep.set_margin_bottom(0)
        sep.set_margin_start(14)
        sep.set_margin_end(14)
        outer.append(sep)

        outer.append(self._sidebar_header("REPOSITORIES"))

        self.repo_listbox = Gtk.ListBox()
        self.repo_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.repo_listbox.add_css_class("navigation-sidebar")
        self.repo_listbox.set_margin_start(5)
        self.repo_listbox.set_margin_end(5)
        self.repo_listbox.connect("row-activated", self._on_repo_nav_selected)

        self._repo_nav_rows = {}
        # Discover repos from installed packages + pacman.conf
        repo_icon_map = {
            "core":     "drive-harddisk-symbolic",
            "extra":    "folder-symbolic",
            "multilib": "folder-symbolic",
            "aur":      "application-x-executable-symbolic",
            "community":"folder-open-symbolic",
            "testing":  "folder-visiting-symbolic",
        }
        # Start with standard repos; will be augmented after packages load
        default_repos = ["core", "extra", "multilib", "aur"]
        for key in default_repos:
            icon = repo_icon_map.get(key, "folder-symbolic")
            row = self._nav_row(icon, key, 0, "count-badge")
            self.repo_listbox.append(row)
            self._repo_nav_rows[key] = row
        outer.append(self.repo_listbox)
        self._repo_icon_map = repo_icon_map

        # ── Tools section ─────────────────────────────────────────────────
        sep = Gtk.Separator()
        sep.set_margin_top(8)
        sep.set_margin_bottom(0)
        sep.set_margin_start(14)
        sep.set_margin_end(14)
        outer.append(sep)

        outer.append(self._sidebar_header("TOOLS"))

        tools_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        tools_box.set_margin_start(5)
        tools_box.set_margin_end(5)
        tools_box.set_margin_bottom(4)

        tool_items = [
            ("emblem-synchronizing-symbolic",      "Sync Databases",   self._on_sync_db),
            ("software-update-available-symbolic", "Check Updates",    self._on_check_updates),
            ("network-transmit-receive-symbolic",  "Rate Mirrors",     self._on_rate_mirrors),
            ("user-trash-symbolic",                "Find Orphans",     self._on_show_orphans),
            ("folder-download-symbolic",           "Clean Cache",      self._on_clean_cache),
        ]
        for icon_name, btn_label, cb in tool_items:
            btn = Gtk.Button()
            btn.add_css_class("flat")
            btn.add_css_class("nav-row")
            row_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row_inner.set_margin_top(5)
            row_inner.set_margin_bottom(5)
            row_inner.set_margin_start(10)
            ic = Gtk.Image.new_from_icon_name(icon_name)
            ic.set_pixel_size(16)
            ic.set_valign(Gtk.Align.CENTER)
            ic.add_css_class("dim-label")
            lbl_w = Gtk.Label(label=btn_label)
            lbl_w.set_halign(Gtk.Align.START)
            lbl_w.set_valign(Gtk.Align.CENTER)
            row_inner.append(ic)
            row_inner.append(lbl_w)
            btn.set_child(row_inner)
            btn.connect("clicked", cb)
            tools_box.append(btn)

        outer.append(tools_box)
        scroll.set_child(outer)
        return scroll

    def _nav_row(self, icon_name, label_text, count=None, badge_css=None):
        """Build a single sidebar navigation row with optional count badge."""
        row = NavRow(icon_name, label_text, count, badge_css)
        return row

    def _sidebar_header(self, text):
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("sidebar-section")
        lbl.set_halign(Gtk.Align.CENTER)
        lbl.set_hexpand(True)
        return lbl

    def _stat_card(self, number, label, css_class="stat-card"):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        card.add_css_class(css_class)
        card.set_hexpand(True)
        card.set_halign(Gtk.Align.FILL)
        num = Gtk.Label(label=number)
        num.add_css_class("stat-number")
        num.add_css_class("numeric")
        num.set_halign(Gtk.Align.CENTER)
        lbl = Gtk.Label(label=label)
        lbl.add_css_class("stat-label")
        lbl.set_halign(Gtk.Align.CENTER)
        card.append(num)
        card.append(lbl)
        card._num = num
        return card

    def _build_package_list_panel(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.list_scroll = Gtk.ScrolledWindow()
        self.list_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.list_scroll.set_vexpand(True)
        self.pkg_listbox = Gtk.ListBox()
        self.pkg_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.pkg_listbox.add_css_class("navigation-sidebar")
        self.pkg_listbox.connect("row-activated", self._on_pkg_selected)
        self.list_scroll.set_child(self.pkg_listbox)

        spinner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        spinner_box.set_halign(Gtk.Align.CENTER); spinner_box.set_valign(Gtk.Align.CENTER)
        self.spinner = Gtk.Spinner(); self.spinner.set_size_request(32, 32)
        sp_lbl = Gtk.Label(label="Loading packages…"); sp_lbl.add_css_class("dim-label")
        spinner_box.append(self.spinner); spinner_box.append(sp_lbl)

        # Empty state: system up to date (shown when updates filter has 0 results)
        self.empty_updates_page = Adw.StatusPage()
        self.empty_updates_page.set_icon_name("emblem-ok-symbolic")
        self.empty_updates_page.set_title("System is up to date")
        self.empty_updates_page.set_description("No pending updates found.")

        # Empty state: generic (no packages match current filter/search)
        self.empty_generic_page = Adw.StatusPage()
        self.empty_generic_page.set_icon_name("system-search-symbolic")
        self.empty_generic_page.set_title("No Packages Found")
        self.empty_generic_page.set_description("Try a different filter or search term.")

        self.list_stack = Gtk.Stack()
        self.list_stack.set_vexpand(True)
        self.list_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.list_stack.set_transition_duration(150)
        self.list_stack.add_named(spinner_box, "loading")
        self.list_stack.add_named(self.list_scroll, "list")
        self.list_stack.add_named(self.empty_updates_page, "empty_updates")
        self.list_stack.add_named(self.empty_generic_page, "empty_generic")
        self.list_stack.set_visible_child_name("loading")
        panel.append(self.list_stack)

        action_bar = Gtk.ActionBar()

        # Normal mode buttons (Install / Uninstall)
        self.btn_install = self._action_btn("package-x-generic-symbolic", "Install",
                                            "suggested-action", "install-btn", callback=self._on_install)
        self.btn_install.set_sensitive(False)
        action_bar.pack_start(self.btn_install)

        self.pkg_count_label = Gtk.Label(label="")
        self.pkg_count_label.add_css_class("caption"); self.pkg_count_label.add_css_class("dim-label")
        action_bar.set_center_widget(self.pkg_count_label)

        self.btn_remove = self._action_btn("user-trash-symbolic", "Uninstall",
                                           "destructive-action", "remove-btn", callback=self._on_remove)
        self.btn_remove.set_sensitive(False)
        action_bar.pack_end(self.btn_remove)

        # Updates mode buttons (Upgrade All / Check for Updates) — hidden by default
        self.btn_upgrade_all = self._action_btn(
            "software-update-available-symbolic", "Upgrade All",
            "suggested-action", callback=self._on_upgrade)
        self.btn_upgrade_all.set_sensitive(False)
        self.btn_upgrade_all.set_visible(False)
        action_bar.pack_start(self.btn_upgrade_all)

        self.btn_check_updates = self._action_btn(
            "view-refresh-symbolic", "Check for Updates",
            callback=self._on_check_updates)
        self.btn_check_updates.set_visible(False)
        action_bar.pack_end(self.btn_check_updates)

        panel.append(action_bar)
        return panel

    def _action_btn(self, icon, label, *css_classes, callback=None):
        btn = Gtk.Button()
        for cls in css_classes:
            btn.add_css_class(cls)
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        inner.set_margin_start(4); inner.set_margin_end(4)
        ic = Gtk.Image.new_from_icon_name(icon); ic.set_pixel_size(16)
        inner.append(ic); inner.append(Gtk.Label(label=label))
        btn.set_child(inner)
        if callback:
            btn.connect("clicked", callback)
        return btn

    def _build_detail_panel(self):
        self.detail_stack = Gtk.Stack()
        self.detail_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.detail_stack.set_transition_duration(180)

        empty = Adw.StatusPage()
        empty.set_icon_name("package-x-generic-symbolic")
        empty.set_title("Select a Package")
        empty.set_description("Choose a package to view its details, files, and dependencies.")
        self.detail_stack.add_named(empty, "empty")

        detail_scroll = Gtk.ScrolledWindow()
        detail_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        detail_box.set_margin_top(16); detail_box.set_margin_bottom(24)
        detail_box.set_margin_start(20); detail_box.set_margin_end(20)

        # Hero card
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        hero.add_css_class("pkg-hero")
        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        self.detail_icon = Gtk.Image()
        self.detail_icon.set_pixel_size(52); self.detail_icon.set_valign(Gtk.Align.CENTER)
        self.detail_icon.set_from_icon_name("package-x-generic-symbolic")
        top_row.append(self.detail_icon)
        title_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title_col.set_hexpand(True); title_col.set_valign(Gtk.Align.CENTER)
        self.detail_name = Gtk.Label(label="Package")
        self.detail_name.set_halign(Gtk.Align.START); self.detail_name.add_css_class("title-2")
        title_col.append(self.detail_name)
        self.detail_desc = Gtk.Label(label="Description")
        self.detail_desc.set_halign(Gtk.Align.START); self.detail_desc.add_css_class("body")
        self.detail_desc.add_css_class("dim-label"); self.detail_desc.set_wrap(True)
        self.detail_desc.set_wrap_mode(Pango.WrapMode.WORD)
        title_col.append(self.detail_desc)
        top_row.append(title_col)
        self.detail_status = Gtk.Label(label="INSTALLED")
        self.detail_status.add_css_class("status-pill"); self.detail_status.add_css_class("status-installed")
        self.detail_status.set_valign(Gtk.Align.START)
        top_row.append(self.detail_status)
        hero.append(top_row)

        meta_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.detail_ver_badge = Gtk.Label(label="1.0.0")
        self.detail_ver_badge.add_css_class("badge"); self.detail_ver_badge.add_css_class("badge-local")
        meta_row.append(self.detail_ver_badge)
        self.detail_repo_badge = Gtk.Label(label="CORE")
        self.detail_repo_badge.add_css_class("badge"); self.detail_repo_badge.add_css_class("badge-core")
        meta_row.append(self.detail_repo_badge)
        self.detail_arch_badge = Gtk.Label(label="x86_64")
        self.detail_arch_badge.add_css_class("badge"); self.detail_arch_badge.add_css_class("badge-local")
        meta_row.append(self.detail_arch_badge)
        hero.append(meta_row)

        # Action buttons in hero
        hero_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.detail_btn_install = self._action_btn("package-x-generic-symbolic", "Install",
            "suggested-action", "install-btn", callback=self._on_install)
        self.detail_btn_install.set_sensitive(False)
        self.detail_btn_remove = self._action_btn("user-trash-symbolic", "Uninstall",
            "destructive-action", "remove-btn", callback=self._on_remove)
        self.detail_btn_remove.set_sensitive(False)
        self.detail_btn_reinstall = self._action_btn("view-refresh-symbolic", "Reinstall",
            callback=self._on_reinstall)
        self.detail_btn_reinstall.set_sensitive(False)
        self.detail_btn_reinstall.add_css_class("flat")
        hero_actions.append(self.detail_btn_install)
        hero_actions.append(self.detail_btn_remove)
        hero_actions.append(self.detail_btn_reinstall)
        hero.append(hero_actions)
        detail_box.append(hero)

        # Tabs: Info / Files
        self.detail_tab_bar = Adw.ViewSwitcherBar()
        self.detail_view_stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher()
        switcher.set_stack(self.detail_view_stack)
        switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        detail_box.append(switcher)

        # ── Info tab ──
        info_scroll = Gtk.ScrolledWindow()
        info_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        info_scroll.set_min_content_height(200)
        info_box_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        info_box_inner.set_margin_start(4); info_box_inner.set_margin_end(4)

        info_group = Adw.PreferencesGroup()
        info_group.set_title("Package Information")
        info_box_inner.append(info_group)
        self.info_rows = {}
        for key in ["URL","Licenses","Groups","Depends On","Optional Deps",
                    "Conflicts With","Provides","Replaces",
                    "Installed Size","Packager","Build Date","Install Date","Install Reason"]:
            row = Adw.ActionRow()
            row.set_title(key)
            # Subtitle wraps naturally, is selectable, and never gets crunched
            row.set_subtitle("—")
            row.set_subtitle_selectable(True)
            info_group.add(row)
            self.info_rows[key] = row

        raw_group = Adw.PreferencesGroup(); raw_group.set_title("Raw Output")
        info_box_inner.append(raw_group)
        raw_exp = Adw.ExpanderRow(); raw_exp.set_title("pacman -Qi output")
        raw_exp.set_subtitle("Full package information"); raw_group.add(raw_exp)
        raw_scroll_inner = Gtk.ScrolledWindow()
        raw_scroll_inner.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        raw_scroll_inner.set_min_content_height(120); raw_scroll_inner.set_max_content_height(240)
        self.raw_text = Gtk.Label(label="")
        self.raw_text.set_selectable(True); self.raw_text.set_wrap(True)
        self.raw_text.set_wrap_mode(Pango.WrapMode.CHAR)
        self.raw_text.add_css_class("monospace"); self.raw_text.add_css_class("caption")
        self.raw_text.set_xalign(0)
        self.raw_text.set_margin_start(12); self.raw_text.set_margin_end(12)
        self.raw_text.set_margin_top(8); self.raw_text.set_margin_bottom(8)
        raw_scroll_inner.set_child(self.raw_text); raw_exp.add_row(raw_scroll_inner)
        info_scroll.set_child(info_box_inner)
        self.detail_view_stack.add_titled_with_icon(info_scroll, "info", "Info", "dialog-information-symbolic")

        # ── Files tab ──
        files_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        files_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        files_hdr.set_margin_start(6); files_hdr.set_margin_end(6)
        files_hdr.set_margin_top(6); files_hdr.set_margin_bottom(4)
        self.files_search = Gtk.SearchEntry()
        self.files_search.set_placeholder_text("Filter…")
        self.files_search.set_hexpand(True)
        self.files_search.connect("search-changed", self._on_files_search)
        files_hdr.append(self.files_search)
        self.files_count_lbl = Gtk.Label(label="")
        self.files_count_lbl.add_css_class("caption"); self.files_count_lbl.add_css_class("dim-label")
        self.files_count_lbl.set_halign(Gtk.Align.END)
        files_hdr.append(self.files_count_lbl)
        files_box.append(files_hdr)
        files_scroll = Gtk.ScrolledWindow()
        files_scroll.set_vexpand(True)
        files_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.files_listbox = Gtk.ListBox()
        self.files_listbox.add_css_class("navigation-sidebar")
        self.files_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        files_scroll.set_child(self.files_listbox)
        files_box.append(files_scroll)
        self.detail_view_stack.add_titled_with_icon(files_box, "files", "Files", "folder-symbolic")

        detail_box.append(self.detail_view_stack)
        detail_scroll.set_child(detail_box)
        self.detail_stack.add_named(detail_scroll, "detail")
        self.detail_stack.set_visible_child_name("empty")
        return self.detail_stack

    # ── Data Loading ──────────────────────────────────────────────────────────
    def _load_packages(self):
        self.list_stack.set_visible_child_name("loading")
        self.spinner.start()
        def worker():
            pkgs = get_packages()
            GLib.idle_add(self._on_packages_loaded, pkgs)
        threading.Thread(target=worker, daemon=True).start()

    def _on_packages_loaded(self, packages):
        self._all_packages = packages
        self.spinner.stop()
        self.list_stack.set_visible_child_name("list")
        self._update_sidebar_counts()
        self._apply_filter()
        # Check for updates in background
        threading.Thread(target=self._bg_check_updates, daemon=True).start()
        return False

    def _bg_check_updates(self):
        updates = check_updates()
        GLib.idle_add(self._on_updates_loaded, updates)

    def _on_updates_loaded(self, updates):
        self._updates = updates
        n = len(updates)
        self.stat_updates._num.set_label(str(n))
        self._nav_rows["updates"].set_count(n)
        if n > 0:
            self.update_banner.set_title(f"{n} update{'s' if n != 1 else ''} available")
            self.update_banner.set_revealed(True)
            self.empty_updates_page.set_title("System is up to date")
            self.empty_updates_page.set_description("No pending updates found.")
        else:
            self.update_banner.set_revealed(False)
            self.empty_updates_page.set_title("System is up to date")
            self.empty_updates_page.set_description("All packages are at their latest version.")
        self._update_action_bar_mode()
        # Tag packages with update status
        update_map = {u["name"]: u["new"] for u in updates}
        for pkg in self._all_packages:
            if pkg["name"] in update_map:
                pkg["status"] = "update"
                pkg["new_version"] = update_map[pkg["name"]]
        self._apply_filter()
        return False

    def _update_sidebar_counts(self):
        total = len(self._all_packages)
        foreign = sum(1 for p in self._all_packages if p.get("foreign", False))
        installed = sum(1 for p in self._all_packages if p["status"] == "installed")

        self.stat_total._num.set_label(str(total))
        self.stat_aur._num.set_label(str(foreign))

        self._nav_rows["all"].set_count(total)
        self._nav_rows["installed"].set_count(installed)
        self._nav_rows["foreign"].set_count(foreign)

        # Discover any repos in package list not yet in sidebar
        seen_repos = set(p.get("repo", "local").lower() for p in self._all_packages
                         if p.get("repo", "local") not in ("local",))
        for repo_key in sorted(seen_repos):
            if repo_key not in self._repo_nav_rows:
                icon = self._repo_icon_map.get(repo_key, "folder-symbolic")
                new_row = self._nav_row(icon, repo_key, 0, "count-badge")
                self.repo_listbox.append(new_row)
                self._repo_nav_rows[repo_key] = new_row

        for repo_key, nav_row in self._repo_nav_rows.items():
            count = sum(1 for p in self._all_packages if p.get("repo", "").lower() == repo_key)
            nav_row.set_count(count)
            nav_row.set_visible(count > 0 or repo_key in ("core","extra","multilib","aur"))

    # ── Filtering ─────────────────────────────────────────────────────────────
    def _apply_filter(self):
        query = self._search_query.lower().strip()
        filt = self._current_filter

        for child in list(self.pkg_listbox):
            self.pkg_listbox.remove(child)

        shown = 0
        for pkg in self._all_packages:
            if query and query not in pkg["name"].lower() and query not in pkg.get("description","").lower():
                continue
            if filt == "installed" and pkg["status"] not in ("installed", "update"):
                continue
            if filt == "foreign" and not pkg.get("foreign", False):
                continue
            if filt == "updates" and pkg.get("status") != "update":
                continue
            if filt == "orphans":
                continue  # orphans shown via separate dialog
            if filt in ("core", "extra", "multilib") and pkg.get("repo", "").lower() != filt:
                continue
            if filt == "aur_repo" and not pkg.get("foreign", False):
                continue

            item = PackageItem(pkg["name"], pkg["version"],
                               pkg.get("repo", "local"), pkg["status"],
                               pkg.get("description", ""), pkg.get("foreign", False))
            self.pkg_listbox.append(PackageRow(item))
            shown += 1

        total = len(self._all_packages)
        self.pkg_count_label.set_label(
            f"{shown} of {total} packages" if shown != total else f"{total} packages")

        # Switch to appropriate empty state when nothing is shown
        if shown == 0:
            if filt == "updates":
                # Only show "up to date" if updates have actually been checked
                if self._updates is not None:
                    self.list_stack.set_visible_child_name("empty_updates")
                else:
                    self.list_stack.set_visible_child_name("list")
            else:
                self.list_stack.set_visible_child_name("empty_generic")
        else:
            self.list_stack.set_visible_child_name("list")

    def _on_search_changed(self, entry):
        self._search_query = entry.get_text()
        if len(self._search_query) >= 3:
            def search_worker(q):
                results = search_packages_cmd(q)
                GLib.idle_add(self._merge_search, results)
            threading.Thread(target=search_worker, args=(self._search_query,), daemon=True).start()
        self._apply_filter()

    def _merge_search(self, results):
        existing = {p["name"] for p in self._all_packages}
        for r in results:
            if r["name"] not in existing:
                self._all_packages.append(r)
        self._apply_filter()
        return False

    def _on_nav_selected(self, listbox, row):
        self.repo_listbox.unselect_all()
        keys = list(self._nav_rows.keys())
        idx = row.get_index()
        if idx < len(keys):
            key = keys[idx]
            if key == "orphans":
                self._on_show_orphans()
                return
            self._current_filter = key
        self._apply_filter()

    def _on_repo_nav_selected(self, listbox, row):
        self.nav_listbox.unselect_all()
        keys = list(self._repo_nav_rows.keys())
        idx = row.get_index()
        if idx < len(keys):
            self._current_filter = keys[idx]
        self._apply_filter()

    def _update_action_bar_mode(self):
        """Switch action bar between normal and updates mode."""
        if not hasattr(self, 'btn_upgrade_all'):
            return
        is_updates = (self._current_filter == "updates")
        self.btn_install.set_visible(not is_updates)
        self.btn_remove.set_visible(not is_updates)
        self.btn_upgrade_all.set_visible(is_updates)
        self.btn_check_updates.set_visible(is_updates)
        if is_updates:
            n = len(self._updates) if self._updates else 0
            self.btn_upgrade_all.set_sensitive(n > 0)

        # ── Package Details ───────────────────────────────────────────────────────
    def _on_pkg_selected(self, listbox, row):
        if row is None: return
        pkg = row.pkg
        self._selected_pkg = pkg
        installed = pkg.pkg_status in ("installed", "update")
        self.btn_install.set_sensitive(not installed)
        self.btn_remove.set_sensitive(installed)
        self.detail_btn_install.set_sensitive(not installed)
        self.detail_btn_remove.set_sensitive(installed)
        self.detail_btn_reinstall.set_sensitive(installed)
        self._show_pkg_detail(pkg)

    def _show_pkg_detail(self, pkg):
        self.detail_name.set_label(pkg.pkg_name)
        self.detail_desc.set_label(pkg.pkg_description or "No description available.")
        self.detail_icon.set_from_icon_name(pkg_icon(pkg.pkg_name))

        repo_str = "aur" if pkg.pkg_foreign else (pkg.pkg_repo or "local").lower()
        self.detail_repo_badge.set_label(repo_str.upper())
        for cls in REPO_BADGE_CLASS.values():
            self.detail_repo_badge.remove_css_class(cls)
        self.detail_repo_badge.add_css_class(REPO_BADGE_CLASS.get(repo_str, "badge-local"))
        self.detail_ver_badge.set_label(pkg.pkg_version)

        for cls in ("status-installed","status-available","status-update","status-foreign"):
            self.detail_status.remove_css_class(cls)
        if pkg.pkg_status == "update":
            self.detail_status.set_label("UPDATE AVAILABLE")
            self.detail_status.add_css_class("status-update")
        elif pkg.pkg_status == "installed":
            if pkg.pkg_foreign:
                self.detail_status.set_label("INSTALLED (AUR)")
                self.detail_status.add_css_class("status-foreign")
            else:
                self.detail_status.set_label("INSTALLED")
                self.detail_status.add_css_class("status-installed")
        else:
            self.detail_status.set_label("AVAILABLE")
            self.detail_status.add_css_class("status-available")

        self.detail_stack.set_visible_child_name("detail")
        for row in self.info_rows.values(): row.set_subtitle(GLib.markup_escape_text("…"))
        self.raw_text.set_label("Loading…")

        # Clear files
        for child in list(self.files_listbox):
            self.files_listbox.remove(child)
        self.files_count_lbl.set_label("Loading…")
        self._pkg_files_all = []

        def worker():
            info = get_package_info(pkg.pkg_name)
            files = get_package_files(pkg.pkg_name)
            GLib.idle_add(self._populate_detail, info, files)
        threading.Thread(target=worker, daemon=True).start()

    def _populate_detail(self, raw, files):
        self.raw_text.set_label(raw)
        parsed = {}
        for line in raw.splitlines():
            if ':' in line:
                k, _, v = line.partition(':')
                parsed[k.strip()] = v.strip()

        field_map = {
            "URL":"URL","Licenses":"Licenses","Groups":"Groups",
            "Depends On":"Depends On","Optional Deps":"Optional Deps",
            "Conflicts With":"Conflicts With","Provides":"Provides","Replaces":"Replaces",
            "Installed Size":"Installed Size","Packager":"Packager",
            "Build Date":"Build Date","Install Date":"Install Date","Install Reason":"Install Reason",
        }
        for pk, rk in field_map.items():
            val = parsed.get(pk, "—") or "—"
            if val in ("None", ""): val = "—"
            if rk in self.info_rows:
                self.info_rows[rk].set_subtitle(GLib.markup_escape_text(val))
        self.detail_arch_badge.set_label(parsed.get("Architecture","x86_64"))

        # Populate files
        self._pkg_files_all = files
        self._populate_files(files)
        return False

    def _populate_files(self, files):
        for child in list(self.files_listbox):
            self.files_listbox.remove(child)
        q = self.files_search.get_text().lower().strip()
        shown = []
        for line in files:
            parts = line.split(None, 1)
            path = parts[1] if len(parts) == 2 else line
            if q and q not in path.lower(): continue
            shown.append(path)
        for path in shown:
            row = Gtk.ListBoxRow()
            row.set_activatable(False)
            lbl = Gtk.Label(label=path)
            lbl.set_halign(Gtk.Align.START); lbl.set_selectable(True)
            lbl.add_css_class("monospace"); lbl.add_css_class("caption")
            lbl.set_margin_start(12); lbl.set_margin_top(4); lbl.set_margin_bottom(4)
            row.set_child(lbl)
            self.files_listbox.append(row)
        total = len([l for l in files if len(l.split(None,1)) >= 2])
        self.files_count_lbl.set_label(
            f"{len(shown)} of {total} files" if q else f"{total} files")

    def _on_files_search(self, entry):
        if hasattr(self, '_pkg_files_all'):
            self._populate_files(self._pkg_files_all)

    # ── Actions ───────────────────────────────────────────────────────────────
    def _on_refresh(self, *_):
        self._all_packages = []; self._updates = None
        self.search_entry.set_text(""); self._search_query = ""
        self.detail_stack.set_visible_child_name("empty")
        self._selected_pkg = None
        self.btn_install.set_sensitive(False); self.btn_remove.set_sensitive(False)
        self.update_banner.set_revealed(False)
        self._load_packages()

    def _on_sync_db(self, *_):
        self._run_terminal("sudo -S pacman -Sy --noconfirm", "Sync Databases")

    def _on_upgrade(self, *_):
        def _after_upgrade():
            self.update_banner.set_revealed(False)
            self._updates = []
            self.stat_updates._num.set_label("0")
            self._nav_rows["updates"].set_count(0)
        self._run_terminal("sudo -S pacman -Syu --noconfirm", "System Upgrade",
                           on_success=_after_upgrade)

    def _on_clean_cache(self, *_):
        self._run_terminal("sudo -S -v && { paccache -rk2 2>/dev/null || sudo pacman -Sc --noconfirm; }", "Clean Cache")

    def _on_check_updates(self, *_):
        self._run_terminal("checkupdates 2>/dev/null || pacman -Qu 2>/dev/null || echo 'No updates available'", "Check for Updates")

    def _on_manage_repos(self, *_):
        self._show_repo_manager()

    def _on_rate_mirrors(self, *_):
        self._show_mirror_rater()

    def _on_show_orphans(self, *_):
        self._show_orphan_finder()

    def _on_show_sysinfo(self, *_):
        self._show_sysinfo_dialog()

    def _on_install(self, *_):
        if self._selected_pkg:
            pkg = self._selected_pkg
            if pkg.pkg_foreign:
                helper = self._get_aur_helper()
                cmd = f"{helper} -S --noconfirm {pkg.pkg_name}" if helper else f"sudo -S pacman -Sy --noconfirm {pkg.pkg_name}"
            else:
                cmd = f"sudo -S pacman -Sy --noconfirm {pkg.pkg_name}"
            self._run_terminal(cmd, f"Install {pkg.pkg_name}", on_success=lambda: self._refresh_selected_pkg())

    def _on_remove(self, *_):
        if not self._selected_pkg: return
        pkg = self._selected_pkg
        d = Adw.AlertDialog()
        d.set_heading(f"Remove {pkg.pkg_name}?")
        d.set_body(f"This will remove {pkg.pkg_name} ({pkg.pkg_version}) from your system.")
        d.add_response("cancel", "Cancel"); d.add_response("remove", "Remove")
        d.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        d.set_default_response("cancel"); d.set_close_response("cancel")
        def on_resp(d, resp):
            if resp == "remove":
                self._run_terminal(f"sudo -S pacman -R --noconfirm {pkg.pkg_name}", f"Remove {pkg.pkg_name}", on_success=lambda: self._refresh_selected_pkg())
        d.connect("response", on_resp); d.present(self)

    def _on_reinstall(self, *_):
        if not self._selected_pkg: return
        pkg = self._selected_pkg
        if pkg.pkg_foreign:
            helper = self._get_aur_helper()
            cmd = f"{helper} -S --noconfirm {pkg.pkg_name}" if helper else f"sudo -S pacman -Sy --noconfirm {pkg.pkg_name}"
        else:
            cmd = f"sudo -S pacman -Sy --noconfirm {pkg.pkg_name}"
        self._run_terminal(cmd, f"Reinstall {pkg.pkg_name}", on_success=lambda: self._refresh_selected_pkg())

    # ── Repo Manager ─────────────────────────────────────────────────────────
    def _show_repo_manager(self, *_):
        """Show /etc/pacman.conf repos in a read-only viewer with an edit button."""
        dialog = Adw.Dialog()
        dialog.set_title("Manage Repositories")
        dialog.set_content_width(640)
        dialog.set_content_height(500)

        tv = Adw.ToolbarView()
        hdr = Adw.HeaderBar()
        hdr.set_show_end_title_buttons(False)

        edit_btn = Gtk.Button(label="Edit pacman.conf")
        edit_btn.add_css_class("suggested-action")
        edit_btn.connect("clicked", lambda *_: (
            dialog.close(),
            self._run_terminal("sudo -S ${VISUAL:-${EDITOR:-nano}} /etc/pacman.conf", "Edit pacman.conf")
        ))
        hdr.pack_end(edit_btn)

        close_btn = Gtk.Button(label="Close")
        close_btn.add_css_class("flat")
        close_btn.connect("clicked", lambda *_: dialog.close())
        hdr.pack_start(close_btn)
        tv.add_top_bar(hdr)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_margin_top(12); outer.set_margin_bottom(16)
        outer.set_margin_start(16); outer.set_margin_end(16)

        # Active repos list
        repos_group = Adw.PreferencesGroup()
        repos_group.set_title("Active Repositories")
        repos_group.set_description("Repositories currently enabled in /etc/pacman.conf")

        out, code = run_command("pacman -Sl 2>/dev/null | awk '{print $1}' | sort -u")
        repos = []
        if out and code == 0:
            repos = [r for r in out.splitlines() if r.strip()]
        if not repos:
            repos = ["core", "extra", "multilib"]

        for repo in repos:
            row = Adw.ActionRow()
            row.set_title(repo)
            icon = Gtk.Image.new_from_icon_name("folder-symbolic")
            icon.add_css_class("dim-label")
            row.add_prefix(icon)
            # Count packages in repo
            pkg_out, _ = run_command(f"pacman -Sl {repo} 2>/dev/null | wc -l")
            if pkg_out and pkg_out.strip().isdigit():
                count_lbl = Gtk.Label(label=f"{pkg_out.strip()} pkgs")
                count_lbl.add_css_class("caption")
                count_lbl.add_css_class("dim-label")
                row.add_suffix(count_lbl)
            repos_group.add(row)

        outer.append(repos_group)

        # Raw conf section
        conf_group = Adw.PreferencesGroup()
        conf_group.set_title("pacman.conf")
        conf_group.set_description("/etc/pacman.conf — read-only view")

        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(180)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add_css_class("card")

        conf_out, _ = run_command("cat /etc/pacman.conf 2>/dev/null")
        if not conf_out:
            conf_out = "# /etc/pacman.conf not found or not readable"

        buf = Gtk.TextBuffer()
        buf.set_text(conf_out)
        conf_view = Gtk.TextView(buffer=buf)
        conf_view.set_editable(False)
        conf_view.set_monospace(True)
        conf_view.set_wrap_mode(Gtk.WrapMode.NONE)
        conf_view.add_css_class("terminal-view")
        scroll.set_child(conf_view)
        conf_group.add(scroll)
        outer.append(conf_group)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        scroller.set_child(outer)
        tv.set_content(scroller)
        dialog.set_child(tv)
        dialog.present(self)

    # ── Mirror Rater ─────────────────────────────────────────────────────────
    def _show_mirror_rater(self, *_):
        """Rate and update Arch mirrors using rate-mirrors."""
        dialog = Adw.Dialog()
        dialog.set_title("Rate Mirrors")
        dialog.set_content_width(600)
        dialog.set_content_height(560)

        tv = Adw.ToolbarView()
        hdr = Adw.HeaderBar()
        hdr.set_show_end_title_buttons(False)
        close_btn = Gtk.Button(label="Close")
        close_btn.add_css_class("flat")
        close_btn.connect("clicked", lambda *_: dialog.close())
        hdr.pack_start(close_btn)
        tv.add_top_bar(hdr)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        outer.set_margin_top(16); outer.set_margin_bottom(24)
        outer.set_margin_start(16); outer.set_margin_end(16)

        _, code = run_command("which rate-mirrors 2>/dev/null")
        has_rate_mirrors = (code == 0)

        if has_rate_mirrors:
            # ── Options group ────────────────────────────────────────────
            options_group = Adw.PreferencesGroup()
            options_group.set_title("Mirror Options")
            options_group.set_description(
                "rate-mirrors tests all Arch mirrors and saves the fastest to /etc/pacman.d/mirrorlist"
            )

            # Country entry
            country_row = Adw.ActionRow()
            country_row.set_title("Countries")
            country_row.set_subtitle("Comma-separated country names, or blank for all")
            country_entry = Gtk.Entry()
            country_entry.set_placeholder_text("e.g. India, Germany, France")
            country_entry.set_hexpand(True)
            country_entry.set_valign(Gtk.Align.CENTER)
            country_entry.set_width_chars(24)
            country_row.add_suffix(country_entry)
            options_group.add(country_row)

            # Sort / rating type
            sort_row = Adw.ActionRow()
            sort_row.set_title("Sort by")
            sort_row.set_subtitle("How mirrors are ranked")
            sort_store = Gtk.StringList()
            sort_options = [
                ("score_asc",  "Score ↑  (best reliability first)"),
                ("score_desc", "Score ↓  (worst reliability first)"),
                ("delay_asc",  "Delay ↑  (freshest mirrors first)"),
                ("delay_desc", "Delay ↓  (oldest mirrors first)"),
                ("random",     "Random   (shuffle before testing)"),
            ]
            for key, label in sort_options:
                sort_store.append(label)
            sort_drop = Gtk.DropDown(model=sort_store)
            sort_drop.set_selected(0)
            sort_drop.set_valign(Gtk.Align.CENTER)
            sort_row.add_suffix(sort_drop)
            options_group.add(sort_row)

            # Protocol toggle
            protocol_row = Adw.ActionRow()
            protocol_row.set_title("HTTPS only")
            protocol_row.set_subtitle("Filter out plain HTTP mirrors")
            https_switch = Gtk.Switch()
            https_switch.set_active(True)
            https_switch.set_valign(Gtk.Align.CENTER)
            protocol_row.add_suffix(https_switch)
            protocol_row.set_activatable_widget(https_switch)
            options_group.add(protocol_row)

            # Backup toggle
            backup_row = Adw.ActionRow()
            backup_row.set_title("Backup current mirrorlist")
            backup_row.set_subtitle("Saves existing list to mirrorlist-backup first")
            backup_switch = Gtk.Switch()
            backup_switch.set_active(True)
            backup_switch.set_valign(Gtk.Align.CENTER)
            backup_row.add_suffix(backup_switch)
            backup_row.set_activatable_widget(backup_switch)
            options_group.add(backup_row)

            # Max delay
            delay_row = Adw.ActionRow()
            delay_row.set_title("Max mirror delay (hours)")
            delay_row.set_subtitle("Skip mirrors that are behind by more than this")
            delay_spin = Gtk.SpinButton()
            delay_spin.set_range(1, 72)
            delay_spin.set_increments(1, 6)
            delay_spin.set_value(6)
            delay_spin.set_valign(Gtk.Align.CENTER)
            delay_row.add_suffix(delay_spin)
            options_group.add(delay_row)

            # Top N mirrors
            top_row = Adw.ActionRow()
            top_row.set_title("Number of mirrors to keep")
            top_row.set_subtitle("0 = keep all ranked mirrors")
            top_spin = Gtk.SpinButton()
            top_spin.set_range(0, 50)
            top_spin.set_increments(1, 5)
            top_spin.set_value(0)
            top_spin.set_valign(Gtk.Align.CENTER)
            top_row.add_suffix(top_spin)
            options_group.add(top_row)

            outer.append(options_group)

            # ── Run button ───────────────────────────────────────────────
            run_btn = Gtk.Button(label="Find Fastest Mirrors")
            run_btn.add_css_class("suggested-action")
            run_btn.set_halign(Gtk.Align.CENTER)

            def on_run(*_):
                countries_raw = country_entry.get_text().strip()
                sort_idx      = sort_drop.get_selected()
                sort_key      = sort_options[sort_idx][0]
                https_only    = https_switch.get_active()
                backup        = backup_switch.get_active()
                max_delay     = int(delay_spin.get_value()) * 3600
                top_n         = int(top_spin.get_value())

                # Global flags go BEFORE the 'arch' subcommand
                global_flags = []
                if https_only:
                    global_flags.append("--protocol=https")
                if top_n > 0:
                    global_flags.append(f"--top-mirrors={top_n}")
                if countries_raw:
                    # --entry-country sets the geographic starting point (2-letter code or name)
                    first = countries_raw.split(",")[0].strip()
                    global_flags.append(f"--entry-country={first!r}")

                # Subcommand flags go AFTER 'arch'
                sub_flags = [f"--sort-mirrors-by={sort_key}", f"--max-delay={max_delay}"]
                # Note: rate-mirrors has no per-country filter flag; entry-country is enough

                gf = " ".join(global_flags)
                sf = " ".join(sub_flags)

                if backup:
                    cmd = (
                        f'sudo -S -v && '
                        f'TMPFILE="$(mktemp)" && '
                        f'rate-mirrors {gf} --save="$TMPFILE" arch {sf} '
                        f'&& sudo mv /etc/pacman.d/mirrorlist /etc/pacman.d/mirrorlist-backup '
                        f'&& sudo mv "$TMPFILE" /etc/pacman.d/mirrorlist '
                        f'&& echo "Done — backup saved to /etc/pacman.d/mirrorlist-backup"'
                    )
                else:
                    cmd = (
                        f'sudo -S -v && '
                        f'rate-mirrors {gf} arch {sf} '
                        f'| sudo tee /etc/pacman.d/mirrorlist > /dev/null '
                        f'&& echo "Done — /etc/pacman.d/mirrorlist updated"'
                    )

                dialog.close()
                self._run_terminal(cmd, "Rate Mirrors")

            run_btn.connect("clicked", on_run)
            outer.append(run_btn)

            # Command preview label
            preview_lbl = Gtk.Label()
            preview_lbl.add_css_class("caption")
            preview_lbl.add_css_class("dim-label")
            preview_lbl.set_wrap(True)
            preview_lbl.set_wrap_mode(Pango.WrapMode.CHAR)
            preview_lbl.set_selectable(True)
            preview_lbl.set_halign(Gtk.Align.CENTER)

            def update_preview(*_):
                countries_raw = country_entry.get_text().strip()
                sort_idx  = sort_drop.get_selected()
                sort_key  = sort_options[sort_idx][0]
                https_only = https_switch.get_active()
                max_delay = int(delay_spin.get_value()) * 3600
                top_n     = int(top_spin.get_value())

                gflags = []
                if https_only: gflags.append("--protocol=https")
                if top_n > 0:  gflags.append(f"--top-mirrors={top_n}")
                if countries_raw:
                    first = countries_raw.split(",")[0].strip()
                    gflags.append(f"--entry-country={first!r}")
                sflags = [f"--sort-mirrors-by={sort_key}", f"--max-delay={max_delay}"]
                preview = f"rate-mirrors {' '.join(gflags)} arch {' '.join(sflags)} | sudo tee /etc/pacman.d/mirrorlist"
                preview_lbl.set_label(preview)

            country_entry.connect("changed", update_preview)
            sort_drop.connect("notify::selected", update_preview)
            https_switch.connect("notify::active", update_preview)
            delay_spin.connect("value-changed", update_preview)
            top_spin.connect("value-changed", update_preview)
            update_preview()
            outer.append(preview_lbl)

        else:
            status = Adw.StatusPage()
            status.set_icon_name("network-transmit-receive-symbolic")
            status.set_title("rate-mirrors not installed")
            status.set_description(
                "rate-mirrors uses geo-aware routing to benchmark\n"
                "all Arch mirrors and pick the fastest ones."
            )
            install_btn = Gtk.Button(label="Install rate-mirrors")
            install_btn.add_css_class("suggested-action")
            install_btn.set_halign(Gtk.Align.CENTER)
            install_btn.connect("clicked", lambda *_: (
                dialog.close(),
                self._run_terminal("sudo -S pacman -S --noconfirm rate-mirrors", "Install rate-mirrors")
            ))
            status.set_child(install_btn)
            outer.append(status)

        scroll.set_child(outer)
        tv.set_content(scroll)
        dialog.set_child(tv)
        dialog.present(self)

    # ── Orphan Finder
    # ── Orphan Finder ─────────────────────────────────────────────────────────
    def _show_orphan_finder(self, *_):
        """Show orphaned packages with option to remove them."""
        dialog = Adw.Dialog()
        dialog.set_title("Orphaned Packages")
        dialog.set_content_width(560)
        dialog.set_content_height(460)

        tv = Adw.ToolbarView()
        hdr = Adw.HeaderBar()
        hdr.set_show_end_title_buttons(False)

        close_btn = Gtk.Button(label="Close")
        close_btn.add_css_class("flat")
        close_btn.connect("clicked", lambda *_: dialog.close())
        hdr.pack_start(close_btn)
        tv.add_top_bar(hdr)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_margin_top(0); outer.set_margin_bottom(0)

        orphans = get_orphans()

        if not orphans:
            # Empty state
            status = Adw.StatusPage()
            status.set_icon_name("emblem-ok-symbolic")
            status.set_title("No Orphans Found")
            status.set_description("Your system has no orphaned packages.")
            status.set_vexpand(True)
            outer.append(status)
        else:
            info_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            info_bar.set_margin_start(16); info_bar.set_margin_end(16)
            info_bar.set_margin_top(12); info_bar.set_margin_bottom(8)

            info_icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
            info_icon.set_pixel_size(16)
            info_bar.append(info_icon)

            info_lbl = Gtk.Label(
                label=f"{len(orphans)} orphaned package(s) — installed as dependencies but no longer required"
            )
            info_lbl.add_css_class("caption")
            info_lbl.set_hexpand(True)
            info_lbl.set_halign(Gtk.Align.START)
            info_lbl.set_wrap(True)
            info_bar.append(info_lbl)
            outer.append(info_bar)

            scroll = Gtk.ScrolledWindow()
            scroll.set_vexpand(True)
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroll.set_margin_start(12); scroll.set_margin_end(12)

            listbox = Gtk.ListBox()
            listbox.set_selection_mode(Gtk.SelectionMode.NONE)
            listbox.add_css_class("boxed-list")

            for o in orphans:
                row = Adw.ActionRow()
                row.set_title(o["name"])
                row.set_subtitle(o["version"])
                icon = Gtk.Image.new_from_icon_name("package-x-generic-symbolic")
                icon.add_css_class("dim-label")
                row.add_prefix(icon)
                rm_btn = Gtk.Button(label="Remove")
                rm_btn.add_css_class("destructive-action")
                rm_btn.add_css_class("flat")
                rm_btn.set_valign(Gtk.Align.CENTER)
                name = o["name"]
                rm_btn.connect("clicked", lambda *_, n=name: (
                    dialog.close(),
                    self._run_terminal(f"sudo -S pacman -R --noconfirm {n}", f"Remove {n}")
                ))
                row.add_suffix(rm_btn)
                listbox.append(row)

            scroll.set_child(listbox)
            outer.append(scroll)

            # Remove all button
            btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            btn_box.set_halign(Gtk.Align.CENTER)
            btn_box.set_margin_top(12); btn_box.set_margin_bottom(16)

            names = " ".join(o["name"] for o in orphans)
            remove_all_btn = Gtk.Button(label=f"Remove All {len(orphans)} Orphans")
            remove_all_btn.add_css_class("destructive-action")
            remove_all_btn.connect("clicked", lambda *_: (
                dialog.close(),
                self._run_terminal(f"sudo -S pacman -Rns --noconfirm {names}", "Remove All Orphans")
            ))
            btn_box.append(remove_all_btn)
            outer.append(btn_box)

        tv.set_content(outer)
        dialog.set_child(tv)
        dialog.present(self)

    # ── System Info ───────────────────────────────────────────────────────────
    def _show_sysinfo_dialog(self, *_):
        """Show system information in a clean preferences-style dialog."""
        dialog = Adw.Dialog()
        dialog.set_title("System Information")
        dialog.set_content_width(520)
        dialog.set_content_height(520)

        tv = Adw.ToolbarView()
        hdr = Adw.HeaderBar()
        hdr.set_show_end_title_buttons(False)

        close_btn = Gtk.Button(label="Close")
        close_btn.add_css_class("flat")
        close_btn.connect("clicked", lambda *_: dialog.close())
        hdr.pack_start(close_btn)
        tv.add_top_bar(hdr)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        outer.set_margin_top(16); outer.set_margin_bottom(24)
        outer.set_margin_start(16); outer.set_margin_end(16)

        # Loading spinner while we fetch
        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading_box.set_halign(Gtk.Align.CENTER)
        loading_box.set_valign(Gtk.Align.CENTER)
        loading_box.set_vexpand(True)
        loading_spinner = Gtk.Spinner()
        loading_spinner.start()
        loading_spinner.set_size_request(32, 32)
        loading_spinner.set_halign(Gtk.Align.CENTER)
        loading_box.append(loading_spinner)
        loading_lbl = Gtk.Label(label="Gathering system info…")
        loading_lbl.add_css_class("dim-label")
        loading_box.append(loading_lbl)
        outer.append(loading_box)

        scroll.set_child(outer)
        tv.set_content(scroll)
        dialog.set_child(tv)
        dialog.present(self)

        def populate(info):
            # Remove loading box
            outer.remove(loading_box)

            # System group
            sys_group = Adw.PreferencesGroup()
            sys_group.set_title("System")
            for key in ("OS", "Kernel", "Architecture"):
                if key in info:
                    row = Adw.ActionRow()
                    row.set_title(key)
                    val_lbl = Gtk.Label(label=info[key])
                    val_lbl.add_css_class("caption")
                    val_lbl.add_css_class("dim-label")
                    val_lbl.set_selectable(True)
                    row.add_suffix(val_lbl)
                    sys_group.add(row)
            outer.append(sys_group)

            # Hardware group
            hw_group = Adw.PreferencesGroup()
            hw_group.set_title("Hardware")
            for key in ("RAM", "Disk (/)"):
                if key in info:
                    row = Adw.ActionRow()
                    row.set_title(key)
                    val_lbl = Gtk.Label(label=info[key])
                    val_lbl.add_css_class("caption")
                    val_lbl.add_css_class("dim-label")
                    val_lbl.set_selectable(True)
                    row.add_suffix(val_lbl)
                    hw_group.add(row)
            outer.append(hw_group)

            # Packages group
            pkg_group = Adw.PreferencesGroup()
            pkg_group.set_title("Packages")
            for key in ("Pacman", "Installed Packages", "Foreign (AUR) Packages", "Package Cache Size"):
                if key in info:
                    row = Adw.ActionRow()
                    row.set_title(key)
                    val_lbl = Gtk.Label(label=info[key])
                    val_lbl.add_css_class("caption")
                    val_lbl.add_css_class("dim-label")
                    val_lbl.set_selectable(True)
                    row.add_suffix(val_lbl)
                    pkg_group.add(row)
            outer.append(pkg_group)
            return False

        def worker():
            info = get_system_info()
            GLib.idle_add(populate, info)

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_selected_pkg(self):
        """Re-query package status and refresh the detail panel for the selected package."""
        if not self._selected_pkg:
            return
        pkg = self._selected_pkg
        # Determine new installed status
        out, code = run_command(f"pacman -Qi '{pkg.pkg_name}' 2>/dev/null")
        if code == 0 and out:
            pkg.pkg_status = "installed"
        else:
            pkg.pkg_status = "available"
        installed = pkg.pkg_status == "installed"
        self.btn_install.set_sensitive(not installed)
        self.btn_remove.set_sensitive(installed)
        self.detail_btn_install.set_sensitive(not installed)
        self.detail_btn_remove.set_sensitive(installed)
        self.detail_btn_reinstall.set_sensitive(installed)
        # Update status badge
        for cls in ("status-installed", "status-available", "status-update", "status-foreign"):
            self.detail_status.remove_css_class(cls)
        if installed:
            if pkg.pkg_foreign:
                self.detail_status.set_label("INSTALLED (AUR)")
                self.detail_status.add_css_class("status-foreign")
            else:
                self.detail_status.set_label("INSTALLED")
                self.detail_status.add_css_class("status-installed")
        else:
            self.detail_status.set_label("AVAILABLE")
            self.detail_status.add_css_class("status-available")
        # Refresh full detail info in background
        if installed:
            def worker():
                info = get_package_info(pkg.pkg_name)
                files = get_package_files(pkg.pkg_name)
                GLib.idle_add(self._populate_detail, info, files)
            threading.Thread(target=worker, daemon=True).start()

    def _get_aur_helper(self):
        """Return the first available AUR helper (cached), or None."""
        if not hasattr(self, '_aur_helper_cache'):
            self._aur_helper_cache = None
            for h in ("paru", "yay", "pikaur", "trizen"):
                _, c = run_command(f"which {h} 2>/dev/null")
                if c == 0:
                    self._aur_helper_cache = h
                    break
        return self._aur_helper_cache

    def _run_terminal(self, cmd, title, on_success=None, needs_sudo=False):
        """
        Run cmd in a built-in PTY terminal dialog.
        Uses sudo -S so the password can be piped via the GTK entry widget.
        """
        import pty, os, select, fcntl, termios, struct, re as _re

        # ── Dialog ────────────────────────────────────────────────────────
        dialog = Adw.Dialog()
        dialog.set_title(title)
        dialog.set_content_width(720)
        dialog.set_content_height(520)
        dialog.set_follows_content_size(False)

        tv = Adw.ToolbarView()
        hdr = Adw.HeaderBar()
        hdr.set_show_end_title_buttons(False)

        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        spinner = Gtk.Spinner()
        spinner.start()
        spinner.set_size_request(16, 16)
        title_box.append(spinner)
        lbl = Gtk.Label(label=title)
        lbl.add_css_class("heading")
        title_box.append(lbl)
        hdr.set_title_widget(title_box)

        close_btn = Gtk.Button(label="Close")
        close_btn.add_css_class("suggested-action")
        close_btn.set_sensitive(False)
        hdr.pack_end(close_btn)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.add_css_class("destructive-action")
        cancel_btn.add_css_class("flat")
        hdr.pack_start(cancel_btn)
        tv.add_top_bar(hdr)

        # ── Cmd display banner ─────────────────────────────────────────────
        cmd_lbl = Gtk.Label(label=f"$ {cmd}")
        cmd_lbl.add_css_class("caption")
        cmd_lbl.add_css_class("dim-label")
        cmd_lbl.set_halign(Gtk.Align.START)
        cmd_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        cmd_lbl.set_margin_start(14)
        cmd_lbl.set_margin_end(14)
        cmd_lbl.set_margin_top(6)
        cmd_lbl.set_margin_bottom(4)
        tv.add_top_bar(cmd_lbl)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.set_margin_top(8)
        outer.set_margin_bottom(12)
        outer.set_margin_start(12)
        outer.set_margin_end(12)

        # ── Output TextView ────────────────────────────────────────────────
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add_css_class("card")

        term_buf = Gtk.TextBuffer()
        term_view = Gtk.TextView(buffer=term_buf)
        term_view.set_editable(False)
        term_view.set_cursor_visible(False)
        term_view.set_wrap_mode(Gtk.WrapMode.CHAR)
        term_view.add_css_class("terminal-view")
        term_view.set_monospace(True)
        scroll.set_child(term_view)
        outer.append(scroll)

        # ── Input row (always visible, used for password + any stdin) ─────
        input_frame = Gtk.Frame()
        input_frame.add_css_class("card")
        input_frame.set_margin_top(2)

        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        input_box.set_margin_top(8)
        input_box.set_margin_bottom(8)
        input_box.set_margin_start(10)
        input_box.set_margin_end(10)

        pw_icon = Gtk.Image.new_from_icon_name("dialog-password-symbolic")
        pw_icon.set_pixel_size(16)
        pw_icon.add_css_class("dim-label")
        input_box.append(pw_icon)

        pw_entry = Gtk.Entry()
        pw_entry.set_hexpand(True)
        pw_entry.set_visibility(False)
        pw_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        pw_entry.set_placeholder_text("Password or input — press Enter to send")
        input_box.append(pw_entry)

        send_btn = Gtk.Button(label="Send")
        send_btn.add_css_class("suggested-action")
        input_box.append(send_btn)

        toggle_vis_btn = Gtk.ToggleButton()
        toggle_vis_btn.set_icon_name("view-reveal-symbolic")
        toggle_vis_btn.add_css_class("flat")
        toggle_vis_btn.set_tooltip_text("Show/hide input")
        toggle_vis_btn.connect("toggled", lambda b, *_: pw_entry.set_visibility(b.get_active()))
        input_box.append(toggle_vis_btn)

        input_frame.set_child(input_box)
        outer.append(input_frame)

        tv.set_content(outer)
        dialog.set_child(tv)
        dialog.present(self)

        # ── State ─────────────────────────────────────────────────────────
        _master_fd = [None]
        _proc      = [None]
        _running   = [True]

        _ANSI = _re.compile(
            r'\x1b\[[0-9;?]*[ -/]*[@-~]'   # CSI sequences
            r'|\x1b[()][AB012]'             # charset
            r'|\x1b[^[]'                    # other ESC+char
            r'|\x08'                        # backspace
            r'|\r'                          # CR (handle below)
        )

        def strip_ansi(s):
            # Replace \r\n → \n, bare \r → \n, then strip remaining ANSI
            s = s.replace('\r\n', '\n').replace('\r', '\n')
            return _ANSI.sub('', s)

        def append_output(raw_text):
            cleaned = strip_ansi(raw_text)
            if not cleaned:
                return False
            end_iter = term_buf.get_end_iter()
            term_buf.insert(end_iter, cleaned)
            # Auto-scroll to bottom
            mark = term_buf.get_insert()
            term_view.scroll_mark_onscreen(mark)
            adj = scroll.get_vadjustment()
            GLib.idle_add(lambda: adj.set_value(adj.get_upper()))
            return False

        def send_input(*_):
            text = pw_entry.get_text()
            pw_entry.set_text("")
            if _master_fd[0] is not None:
                try:
                    os.write(_master_fd[0], (text + "\n").encode())
                    # Echo a masked line so user sees something happened
                    append_output("(input sent)\n")
                except OSError:
                    pass

        pw_entry.connect("activate", send_input)
        send_btn.connect("clicked", send_input)

        def on_close_clicked(*_):
            close_btn.grab_focus()
            dialog.close()
        close_btn.connect("clicked", on_close_clicked)

        def do_cancel(*_):
            if _proc[0] is not None:
                try:
                    os.killpg(os.getpgid(_proc[0].pid), __import__('signal').SIGTERM)
                except Exception:
                    try:
                        _proc[0].terminate()
                    except Exception:
                        pass
            cancel_btn.set_sensitive(False)
            cancel_btn.grab_focus()
            append_output("\n— Cancelled —\n")
        cancel_btn.connect("clicked", do_cancel)

        def on_done(code):
            _running[0] = False
            spinner.stop()
            # Hide Cancel, enable Close (now the primary action)
            cancel_btn.set_visible(False)
            close_btn.set_sensitive(True)
            close_btn.grab_focus()
            sep = "\n" + "─" * 56 + "\n"
            if code == 0:
                append_output(sep + "✓  Completed successfully\n")
            else:
                append_output(sep + f"✗  Failed  (exit code {code})\n")
            # Disable input and move focus away to avoid GtkText focus-out warning
            pw_entry.set_sensitive(False)
            send_btn.set_sensitive(False)
            if code == 0 and on_success:
                on_success()
            self._load_packages()
            toast = Adw.Toast()
            toast.set_title(
                f"✓ {title} completed" if code == 0
                else f"✗ {title} failed (exit {code})"
            )
            toast.set_timeout(4)
            try:
                self._toast_overlay.add_toast(toast)
            except AttributeError:
                pass
            return False

        # ── PTY worker ────────────────────────────────────────────────────
        def worker():
            master_fd, slave_fd = pty.openpty()
            _master_fd[0] = master_fd

            # Set a reasonable terminal size
            try:
                ws = struct.pack('HHHH', 40, 120, 0, 0)
                fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, ws)
            except Exception:
                pass

            # Wrap command: header line, then run, then exit with its code
            safe_title = title.replace("'", "")
            safe_cmd   = cmd.replace("'", "'\\''")  # shell-escape single quotes
            wrapped = (
                f"printf '\\033[1m>>> {safe_title}\\033[0m\\n'; "
                f"echo; "
                f"{cmd}; "
                f"_ec=$?; "
                f"exit $_ec"
            )

            env = dict(os.environ)
            env['TERM'] = 'xterm-256color'
            # Tell sudo to read password from stdin (required for -S)
            env.pop('SUDO_ASKPASS', None)

            try:
                proc = subprocess.Popen(
                    ["sh", "-c", wrapped],
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    close_fds=True,
                    preexec_fn=os.setsid,
                    env=env,
                )
                _proc[0] = proc
                os.close(slave_fd)

                partial = b""
                while True:
                    try:
                        rlist, _, _ = select.select([master_fd], [], [], 0.05)
                    except (ValueError, OSError):
                        break

                    if rlist:
                        try:
                            chunk = os.read(master_fd, 8192)
                        except OSError:
                            break
                        if not chunk:
                            break
                        partial += chunk
                        # Decode what we have; keep incomplete sequences
                        try:
                            text = partial.decode('utf-8')
                            partial = b""
                        except UnicodeDecodeError:
                            # Try to decode up to the last safe boundary
                            for cut in range(len(partial), 0, -1):
                                try:
                                    text = partial[:cut].decode('utf-8')
                                    partial = partial[cut:]
                                    break
                                except UnicodeDecodeError:
                                    continue
                            else:
                                text = partial.decode('latin-1')
                                partial = b""
                        GLib.idle_add(append_output, text)

                    elif proc.poll() is not None:
                        # Drain any remaining bytes
                        try:
                            while True:
                                r2, _, _ = select.select([master_fd], [], [], 0.05)
                                if not r2:
                                    break
                                chunk = os.read(master_fd, 8192)
                                if not chunk:
                                    break
                                GLib.idle_add(append_output, chunk.decode('utf-8', errors='replace'))
                        except OSError:
                            pass
                        break

                proc.wait()
                code = proc.returncode

            except Exception as exc:
                GLib.idle_add(append_output, f"\nInternal error: {exc}\n")
                code = 1

            finally:
                try:
                    os.close(master_fd)
                except OSError:
                    pass
                _master_fd[0] = None

            GLib.idle_add(on_done, code)

        threading.Thread(target=worker, daemon=True).start()


# ─── App ─────────────────────────────────────────────────────────────────────




class pachubApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="io.github.mrks1469.pachub", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.connect("activate", self._on_activate)

    def _on_activate(self, app):
        load_css()
        self.win = pachubWindow(app)
        for name, cb in {
            "sync":         self.win._on_sync_db,
            "refresh":      self.win._on_refresh,
            "install":      self.win._on_install,
            "remove":       self.win._on_remove,
            "cache":        self.win._on_clean_cache,
            "check_updates":self.win._on_check_updates,
            "manage_repos": self.win._on_manage_repos,
            "rate_mirrors": self.win._on_rate_mirrors,
            "orphans":      self.win._on_show_orphans,
            "sysinfo":      self.win._on_show_sysinfo,
            "about":        self._on_about,
        }.items():
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", cb)
            self.add_action(act)
        self.win.present()

    def _on_about(self, *_):
        about = Adw.AboutDialog()
        about.set_application_name("PacHub")
        about.set_application_icon("io.github.mrks1469.pachub")
        about.set_version("1.0.0")
        about.set_developer_name("Manpreet Singh")
        about.set_license_type(Gtk.License.GPL_2_0)
        about.set_website("https://github.com/mrks1469/PacHub")
        about.set_issue_url("https://github.com/mrks1469/PacHub/issues")
        about.set_comments("A powerful Pacman/AUR front end.\n")
        about.set_developers(["Manpreet Singh https://github.com/mrks1469"])
        about.present(self.win)


def main():
    return pachubApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
