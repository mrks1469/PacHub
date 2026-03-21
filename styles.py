"""
PacHub — styles.py
Application-wide CSS and style loading.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gdk

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

/* ── Row inline status pill (next to repo badge in list rows) ── */
.row-status-pill {
    border-radius: 999px;
    padding: 1px 6px;
    font-size: 0.65rem;
    font-weight: 800;
    letter-spacing: 0.05em;
}

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

/* ── Dependency chips ── */
.dep-chip {
    border-radius: 999px;
    padding: 2px 10px;
    font-size: 0.78rem;
    font-weight: 600;
    background: alpha(@card_fg_color, 0.07);
    border: 1px solid alpha(@card_fg_color, 0.12);
    min-height: 0;
}
.dep-chip:hover {
    background: alpha(@accent_bg_color, 0.15);
    border-color: alpha(@accent_bg_color, 0.35);
    color: @accent_color;
}

/* ── Misc ── */
.install-btn { border-radius: 8px; font-weight: 600; }
.remove-btn  { border-radius: 8px; font-weight: 600; }
.orphan-row  { border-left: 3px solid alpha(#e66100, 0.6); }

progressbar.success trough progress { background: #2ec27e; }
progressbar.warning trough progress { background: #e5a50a; }
progressbar trough { border-radius: 999px; min-height: 6px; }
progressbar trough progress { border-radius: 999px; }

/* Search page large entry */
.search-page-entry {
    font-size: 1.05rem;
    padding: 6px 4px;
    min-height: 42px;
}
.search-page-entry:focus {
    outline: none;
}
"""


def load_css():
    p = Gtk.CssProvider()
    p.load_from_data(CSS.encode())
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
