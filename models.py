"""
PacHub — models.py
GObject data model (PackageItem) and reusable GTK row widgets
(PackageRow, NavRow) used throughout the UI.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, GObject, Pango

# ─── Repository badge mapping ─────────────────────────────────────────────────

REPO_BADGE_CLASS = {
    "core":     "badge-core",
    "extra":    "badge-extra",
    "aur":      "badge-aur",
    "multilib": "badge-multilib",
    "local":    "badge-local",
    "foreign":  "badge-foreign",
}

# ─── Symbolic icon fallbacks per package name ─────────────────────────────────

PKG_ICONS = {
    "linux":                  "utilities-terminal-symbolic",
    "linux-firmware":         "drive-harddisk-symbolic",
    "base":                   "package-x-generic-symbolic",
    "bash":                   "utilities-terminal-symbolic",
    "zsh":                    "utilities-terminal-symbolic",
    "fish":                   "utilities-terminal-symbolic",
    "git":                    "preferences-system-details-symbolic",
    "python":                 "text-x-script-symbolic",
    "python-pip":             "text-x-script-symbolic",
    "nodejs":                 "text-x-script-symbolic",
    "npm":                    "text-x-script-symbolic",
    "rust":                   "application-x-executable-symbolic",
    "go":                     "application-x-executable-symbolic",
    "cmake":                  "applications-engineering-symbolic",
    "docker":                 "application-x-executable-symbolic",
    "flatpak":                "package-x-generic-symbolic",
    "pacman":                 "package-x-generic-symbolic",
    "yay":                    "package-x-generic-symbolic",
    "paru":                   "package-x-generic-symbolic",
    "networkmanager":         "network-wireless-symbolic",
    "openssh":                "network-server-symbolic",
    "pipewire":               "audio-speakers-symbolic",
    "alsa-utils":             "audio-card-symbolic",
    "htop":                   "utilities-system-monitor-symbolic",
    "curl":                   "network-transmit-receive-symbolic",
    "wget":                   "network-transmit-receive-symbolic",
    "vim":                    "text-editor-symbolic",
    "nano":                   "text-editor-symbolic",
    "mesa":                   "video-display-symbolic",
    "timeshift":              "document-revert-symbolic",
    "systemd":                "preferences-system-symbolic",
    "firefox":                "web-browser-symbolic",
    "chromium":               "web-browser-symbolic",
    "google-chrome":          "web-browser-symbolic",
    "gimp":                   "applications-graphics-symbolic",
    "vlc":                    "applications-multimedia-symbolic",
    "visual-studio-code-bin": "text-editor-symbolic",
}


def pkg_icon(name):
    return PKG_ICONS.get(name, "package-x-generic-symbolic")


# ─── GObject model ────────────────────────────────────────────────────────────

class PackageItem(GObject.Object):
    __gtype_name__ = 'PacHubPackageItem'

    def __init__(self, name, version, repo="local", status="installed",
                 description="", foreign=False):
        super().__init__()
        self.pkg_name        = name
        self.pkg_version     = version
        self.pkg_repo        = repo
        self.pkg_status      = status
        self.pkg_description = description
        self.pkg_foreign     = foreign


# ─── Package list row ─────────────────────────────────────────────────────────

class PackageRow(Gtk.ListBoxRow):
    def __init__(self, pkg):
        super().__init__()
        self.pkg = pkg
        self.set_activatable(True)
        self.add_css_class("pkg-row")

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_top(9);    box.set_margin_bottom(9)
        box.set_margin_start(10); box.set_margin_end(10)

        icon = Gtk.Image.new_from_icon_name(pkg_icon(pkg.pkg_name))
        icon.set_pixel_size(20)
        icon.set_valign(Gtk.Align.CENTER)
        icon.add_css_class("dim-label")
        box.append(icon)

        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        info_box.set_hexpand(True)
        info_box.set_valign(Gtk.Align.CENTER)

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
            desc_label.add_css_class("caption")
            desc_label.add_css_class("dim-label")
            desc_label.set_ellipsize(Pango.EllipsizeMode.END)
            info_box.append(desc_label)
        box.append(info_box)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        right.set_valign(Gtk.Align.CENTER)
        right.set_halign(Gtk.Align.END)

        badges_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        badges_row.set_halign(Gtk.Align.END)

        # "INSTALLED" pill for installed/update packages
        if pkg.pkg_status in ("installed", "update"):
            status_css = "status-update" if pkg.pkg_status == "update" else "status-installed"
            status_text = "UPDATE" if pkg.pkg_status == "update" else "INSTALLED"
            inst_badge = Gtk.Label(label=status_text)
            inst_badge.add_css_class("row-status-pill")
            inst_badge.add_css_class(status_css)
            badges_row.append(inst_badge)

        repo_str = "aur" if pkg.pkg_foreign else (pkg.pkg_repo or "local")
        badge = Gtk.Label(label=repo_str.upper())
        badge.add_css_class("badge")
        badge.add_css_class(REPO_BADGE_CLASS.get(repo_str.lower(), "badge-local"))
        badges_row.append(badge)
        right.append(badges_row)

        ver_label = Gtk.Label(label=pkg.pkg_version)
        ver_label.add_css_class("caption")
        ver_label.add_css_class("dim-label")
        ver_label.set_halign(Gtk.Align.END)
        right.append(ver_label)

        box.append(right)
        self.set_child(box)


# ─── Sidebar navigation row ───────────────────────────────────────────────────

class NavRow(Gtk.ListBoxRow):
    def __init__(self, icon_name, label, count=None, badge_css=None):
        super().__init__()
        self.add_css_class("nav-row")
        self.set_activatable(True)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_top(7);    box.set_margin_bottom(7)
        box.set_margin_start(10); box.set_margin_end(10)

        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(16)
        icon.set_valign(Gtk.Align.CENTER)
        icon.add_css_class("dim-label")
        box.append(icon)

        lbl = Gtk.Label(label=label)
        lbl.set_hexpand(True)
        lbl.set_halign(Gtk.Align.START)
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
