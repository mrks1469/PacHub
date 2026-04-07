"""
PacHub — window.py
Main application window: sidebar, search page, package list, detail panel,
filtering, and all action handlers.
"""

import shutil
import threading

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio, Pango

from backend import (
    get_packages, get_package_info, get_package_files,
    check_updates, search_packages_cmd, run_command,
    invalidate_cache, invalidate_syncdb_cache,
    is_safe_package_name,
)
from models import PackageItem, PackageRow, NavRow, REPO_BADGE_CLASS, pkg_icon
from dialogs import (
    run_terminal_dialog,
    show_repo_manager,
    show_mirror_rater,
    show_orphan_finder,
    show_sysinfo_dialog,
)


class pachubWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("PacHub")
        self.set_default_size(1240, 780)
        self.set_size_request(900, 560)
        self._all_packages     = []
        self._selected_pkg     = None
        self._current_filter   = "installed"
        self._updates          = None
        self._aur_helper_cache = None
        self._pkg_files_all    = []
        self._alive            = True   # set False on close to stop background workers
        self.connect("close-request", self._on_close_request)
        self._build_ui()
        self._load_packages()

    def _on_close_request(self, *_):
        self._alive = False
        return False   # allow window to close

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.nav_split = Adw.NavigationSplitView()
        self.nav_split.set_max_sidebar_width(230)
        self.nav_split.set_min_sidebar_width(190)
        self.nav_split.set_sidebar_width_fraction(0.20)

        # Sidebar
        sidebar_page = Adw.NavigationPage()
        sidebar_page.set_title("PacHub")
        sidebar_tv  = Adw.ToolbarView()
        sidebar_hdr = Adw.HeaderBar()
        sidebar_hdr.set_show_end_title_buttons(False)
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        app_icon  = Gtk.Image.new_from_icon_name("package-x-generic-symbolic")
        app_icon.set_pixel_size(18)
        title_lbl = Gtk.Label(label="PacHub")
        title_lbl.add_css_class("heading")
        title_box.append(app_icon)
        title_box.append(title_lbl)
        sidebar_hdr.set_title_widget(title_box)
        sidebar_tv.add_top_bar(sidebar_hdr)
        sidebar_tv.set_content(self._build_sidebar())
        sidebar_page.set_child(sidebar_tv)
        self.nav_split.set_sidebar(sidebar_page)

        # Content
        content_page = Adw.NavigationPage()
        content_page.set_title("PacHub")
        self.content_tv  = Adw.ToolbarView()
        self.content_hdr = Adw.HeaderBar()
        self.content_hdr.set_show_back_button(False)
        self.content_hdr.set_show_title(False)

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
        menu.append("Sync Databases",       "app.sync")
        menu.append("Check for Updates",    "app.check_updates")
        menu.append("Refresh List",         "app.refresh")
        menu.append_section(None, Gio.Menu())
        menu.append("Manage Repositories…", "app.manage_repos")
        menu.append("Rate Mirrors…",        "app.rate_mirrors")
        menu.append_section(None, Gio.Menu())
        menu.append("Find Orphans",         "app.orphans")
        menu.append("System Info",          "app.sysinfo")
        menu.append("Cache Cleaner",        "app.cache")
        menu.append_section(None, Gio.Menu())
        menu.append("About PacHub",         "app.about")
        menu_btn.set_menu_model(menu)
        right_box.append(menu_btn)
        self.content_hdr.pack_end(right_box)
        self.content_tv.add_top_bar(self.content_hdr)

        self.update_banner = Adw.Banner()
        self.update_banner.set_button_label("Upgrade Now")
        self.update_banner.connect("button-clicked", self._on_upgrade)
        self.update_banner.set_revealed(False)
        self.content_tv.add_top_bar(self.update_banner)

        # Main stack: search page | list+detail paned
        self.main_stack = Gtk.Stack()
        self.main_stack.set_transition_type(Gtk.StackTransitionType.NONE)  # instant — no freeze
        self.main_stack.add_named(self._build_search_page(),      "search")
        self.main_stack.add_named(self._build_list_detail_paned(), "list")
        self.main_stack.set_visible_child_name("search")

        self.content_tv.set_content(self.main_stack)
        content_page.set_child(self.content_tv)
        self.nav_split.set_content(content_page)

        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(self.nav_split)
        self.set_content(self._toast_overlay)

    # ── Search page ───────────────────────────────────────────────────────────

    def _build_search_page(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Hero
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        hero.set_halign(Gtk.Align.FILL)
        hero.set_margin_top(48); hero.set_margin_bottom(24)
        hero.set_margin_start(60); hero.set_margin_end(60)

        headline = Gtk.Label(label="Search Packages")
        headline.add_css_class("title-1")
        headline.set_halign(Gtk.Align.CENTER)
        hero.append(headline)

        sub = Gtk.Label(label="Search official repos and AUR")
        sub.add_css_class("body"); sub.add_css_class("dim-label")
        sub.set_halign(Gtk.Align.CENTER)
        hero.append(sub)

        search_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        search_row.set_halign(Gtk.Align.CENTER)
        search_row.set_size_request(520, -1)
        search_row.add_css_class("linked")

        self.search_entry = Gtk.Entry()
        self.search_entry.set_placeholder_text("Search packages, e.g. firefox, vlc, git…")
        self.search_entry.set_hexpand(True)
        self.search_entry.add_css_class("search-page-entry")
        self.search_entry.connect("activate", self._on_search_activate)
        search_row.append(self.search_entry)

        search_btn = Gtk.Button()
        search_btn.set_icon_name("system-search-symbolic")
        search_btn.add_css_class("suggested-action")
        search_btn.connect("clicked", lambda *_: self._on_search_activate())
        search_row.append(search_btn)
        hero.append(search_row)
        root.append(hero)

        root.append(Gtk.Separator())

        # Results stack
        self._search_results_stack = Gtk.Stack()
        self._search_results_stack.set_vexpand(True)
        self._search_results_stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self._search_results_stack.set_transition_duration(0)

        idle_page = Adw.StatusPage()
        idle_page.set_icon_name("system-search-symbolic")
        idle_page.set_title("Find Packages")
        idle_page.set_description("Type above to search the official repositories and AUR.")
        self._search_results_stack.add_named(idle_page, "idle")

        spin_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        spin_box.set_halign(Gtk.Align.CENTER); spin_box.set_valign(Gtk.Align.CENTER)
        self._search_spinner = Gtk.Spinner()
        self._search_spinner.set_size_request(36, 36)
        spin_lbl = Gtk.Label(label="Searching…")
        spin_lbl.add_css_class("dim-label")
        spin_box.append(self._search_spinner)
        spin_box.append(spin_lbl)
        self._search_results_stack.add_named(spin_box, "searching")

        no_results = Adw.StatusPage()
        no_results.set_icon_name("system-search-symbolic")
        no_results.set_title("No Results")
        no_results.set_description("Try different keywords or check your spelling.")
        self._search_results_stack.add_named(no_results, "empty")

        # Results paned — reuses the shared detail_stack built in _build_detail_panel
        self._search_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self._search_paned.set_position(380)
        self._search_paned.set_shrink_start_child(False)
        self._search_paned.set_shrink_end_child(False)

        results_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        results_scroll = Gtk.ScrolledWindow()
        results_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        results_scroll.set_vexpand(True)
        self.search_listbox = Gtk.ListBox()
        self.search_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.search_listbox.add_css_class("navigation-sidebar")
        self.search_listbox.connect("row-activated", self._on_search_pkg_selected)
        results_scroll.set_child(self.search_listbox)
        results_panel.append(results_scroll)

        results_action = Gtk.ActionBar()
        self._search_btn_install = self._action_btn(
            "package-x-generic-symbolic", "Install",
            "suggested-action", "install-btn", callback=self._on_install)
        self._search_btn_install.set_sensitive(False)
        results_action.pack_start(self._search_btn_install)
        self._search_count_lbl = Gtk.Label(label="")
        self._search_count_lbl.add_css_class("caption")
        self._search_count_lbl.add_css_class("dim-label")
        results_action.set_center_widget(self._search_count_lbl)
        self._search_btn_remove = self._action_btn(
            "user-trash-symbolic", "Uninstall",
            "destructive-action", "remove-btn", callback=self._on_remove)
        self._search_btn_remove.set_sensitive(False)
        results_action.pack_end(self._search_btn_remove)
        results_panel.append(results_action)

        self._search_paned.set_start_child(results_panel)
        self._search_paned.set_end_child(self._build_search_detail_panel())
        self._search_results_stack.add_named(self._search_paned, "results")

        root.append(self._search_results_stack)
        return root

    # ── List+detail paned (Installed / AUR / Updates / Repos) ─────────────────

    def _build_list_detail_paned(self):
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(380)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)
        paned.set_start_child(self._build_package_list_panel())
        paned.set_end_child(self._build_detail_panel())
        return paned


    # ── Search detail panel (independent copy for search paned) ──────────────

    def _build_search_detail_panel(self):
        self.search_detail_stack = Gtk.Stack()
        self.search_detail_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.search_detail_stack.set_transition_duration(120)

        empty = Adw.StatusPage()
        empty.set_icon_name("package-x-generic-symbolic")
        empty.set_title("Select a Package")
        empty.set_description("Choose a search result to view its details.")
        self.search_detail_stack.add_named(empty, "empty")

        detail_scroll = Gtk.ScrolledWindow()
        detail_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        detail_box.set_margin_top(16); detail_box.set_margin_bottom(24)
        detail_box.set_margin_start(20); detail_box.set_margin_end(20)

        # Hero
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        hero.add_css_class("pkg-hero")
        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        self.sd_icon = Gtk.Image()
        self.sd_icon.set_pixel_size(52); self.sd_icon.set_valign(Gtk.Align.CENTER)
        self.sd_icon.set_from_icon_name("package-x-generic-symbolic")
        top_row.append(self.sd_icon)
        title_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title_col.set_hexpand(True); title_col.set_valign(Gtk.Align.CENTER)
        self.sd_name = Gtk.Label(label="Package")
        self.sd_name.set_halign(Gtk.Align.START); self.sd_name.add_css_class("title-2")
        title_col.append(self.sd_name)
        self.sd_desc = Gtk.Label(label="Description")
        self.sd_desc.set_halign(Gtk.Align.START); self.sd_desc.add_css_class("body")
        self.sd_desc.add_css_class("dim-label"); self.sd_desc.set_wrap(True)
        self.sd_desc.set_wrap_mode(Pango.WrapMode.WORD)
        title_col.append(self.sd_desc)
        top_row.append(title_col)
        self.sd_status = Gtk.Label(label="AVAILABLE")
        self.sd_status.add_css_class("status-pill"); self.sd_status.add_css_class("status-available")
        self.sd_status.set_valign(Gtk.Align.START)
        top_row.append(self.sd_status)
        hero.append(top_row)

        meta_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.sd_ver_badge = Gtk.Label(label="1.0.0")
        self.sd_ver_badge.add_css_class("badge"); self.sd_ver_badge.add_css_class("badge-local")
        meta_row.append(self.sd_ver_badge)
        self.sd_repo_badge = Gtk.Label(label="REPO")
        self.sd_repo_badge.add_css_class("badge"); self.sd_repo_badge.add_css_class("badge-core")
        meta_row.append(self.sd_repo_badge)
        self.sd_arch_badge = Gtk.Label(label="x86_64")
        self.sd_arch_badge.add_css_class("badge"); self.sd_arch_badge.add_css_class("badge-local")
        meta_row.append(self.sd_arch_badge)
        hero.append(meta_row)

        hero_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.sd_btn_install = self._action_btn(
            "package-x-generic-symbolic", "Install",
            "suggested-action", "install-btn", callback=self._on_install)
        self.sd_btn_install.set_sensitive(False)
        self.sd_btn_remove = self._action_btn(
            "user-trash-symbolic", "Uninstall",
            "destructive-action", "remove-btn", callback=self._on_remove)
        self.sd_btn_remove.set_sensitive(False)
        self.sd_btn_reinstall = self._action_btn(
            "view-refresh-symbolic", "Reinstall", callback=self._on_reinstall)
        self.sd_btn_reinstall.set_sensitive(False)
        self.sd_btn_reinstall.add_css_class("flat")
        hero_actions.append(self.sd_btn_install)
        hero_actions.append(self.sd_btn_remove)
        hero_actions.append(self.sd_btn_reinstall)
        hero.append(hero_actions)
        detail_box.append(hero)

        # Info group
        self.sd_view_stack = Adw.ViewStack()
        sd_switcher = Adw.ViewSwitcher()
        sd_switcher.set_stack(self.sd_view_stack)
        sd_switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        detail_box.append(sd_switcher)

        info_scroll = Gtk.ScrolledWindow()
        info_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        info_scroll.set_min_content_height(200)
        info_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        info_inner.set_margin_start(4); info_inner.set_margin_end(4)
        sd_info_group = Adw.PreferencesGroup()
        sd_info_group.set_title("Package Information")
        info_inner.append(sd_info_group)
        self.sd_info_rows = {}
        self.sd_dep_rows = {}
        for key in ["URL", "Licenses", "Groups", "Depends On", "Optional Deps",
                    "Conflicts With", "Provides", "Replaces",
                    "Installed Size", "Packager", "Build Date", "Install Date", "Install Reason"]:
            if key in ("Depends On", "Optional Deps"):
                exp_row = Adw.ExpanderRow()
                exp_row.set_title(key); exp_row.set_subtitle("—")
                flow = Gtk.FlowBox()
                flow.set_selection_mode(Gtk.SelectionMode.NONE)
                flow.set_column_spacing(6); flow.set_row_spacing(6)
                flow.set_margin_start(12); flow.set_margin_end(12)
                flow.set_margin_top(8); flow.set_margin_bottom(10)
                flow_row = Gtk.ListBoxRow()
                flow_row.set_activatable(False)
                flow_row.set_child(flow)
                exp_row.add_row(flow_row)
                sd_info_group.add(exp_row)
                self.sd_dep_rows[key] = (exp_row, flow)
                self.sd_info_rows[key] = exp_row
            else:
                row = Adw.ActionRow()
                row.set_title(key); row.set_subtitle("—")
                row.set_subtitle_selectable(True)
                sd_info_group.add(row)
                self.sd_info_rows[key] = row

        raw_group = Adw.PreferencesGroup()
        raw_group.set_title("Raw Output")
        info_inner.append(raw_group)
        raw_exp = Adw.ExpanderRow()
        raw_exp.set_title("pacman -Qi output")
        raw_exp.set_subtitle("Full package information")
        raw_group.add(raw_exp)
        raw_scroll = Gtk.ScrolledWindow()
        raw_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        raw_scroll.set_min_content_height(120); raw_scroll.set_max_content_height(240)
        self.sd_raw_text = Gtk.Label(label="")
        self.sd_raw_text.set_selectable(True); self.sd_raw_text.set_wrap(True)
        self.sd_raw_text.set_wrap_mode(Pango.WrapMode.CHAR)
        self.sd_raw_text.add_css_class("monospace"); self.sd_raw_text.add_css_class("caption")
        self.sd_raw_text.set_xalign(0)
        self.sd_raw_text.set_margin_start(12); self.sd_raw_text.set_margin_end(12)
        self.sd_raw_text.set_margin_top(8); self.sd_raw_text.set_margin_bottom(8)
        raw_scroll.set_child(self.sd_raw_text)
        raw_exp.add_row(raw_scroll)
        info_scroll.set_child(info_inner)
        self.sd_view_stack.add_titled_with_icon(
            info_scroll, "info", "Info", "dialog-information-symbolic")

        # Files tab
        sd_files_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sd_files_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sd_files_hdr.set_margin_start(6); sd_files_hdr.set_margin_end(6)
        sd_files_hdr.set_margin_top(6); sd_files_hdr.set_margin_bottom(4)
        self.sd_files_search = Gtk.SearchEntry()
        self.sd_files_search.set_placeholder_text("Filter…")
        self.sd_files_search.set_hexpand(True)
        self.sd_files_search.connect("search-changed", self._on_sd_files_search)
        sd_files_hdr.append(self.sd_files_search)
        self.sd_files_count_lbl = Gtk.Label(label="")
        self.sd_files_count_lbl.add_css_class("caption"); self.sd_files_count_lbl.add_css_class("dim-label")
        self.sd_files_count_lbl.set_halign(Gtk.Align.END)
        sd_files_hdr.append(self.sd_files_count_lbl)
        sd_files_box.append(sd_files_hdr)
        sd_files_scroll = Gtk.ScrolledWindow()
        sd_files_scroll.set_vexpand(True)
        self.sd_files_listbox = Gtk.ListBox()
        self.sd_files_listbox.add_css_class("navigation-sidebar")
        self.sd_files_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        sd_files_scroll.set_child(self.sd_files_listbox)
        sd_files_box.append(sd_files_scroll)
        self.sd_view_stack.add_titled_with_icon(
            sd_files_box, "files", "Files", "folder-symbolic")

        detail_box.append(self.sd_view_stack)
        detail_scroll.set_child(detail_box)
        self.search_detail_stack.add_named(detail_scroll, "detail")
        self.search_detail_stack.set_visible_child_name("empty")
        return self.search_detail_stack

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_margin_top(8); outer.set_margin_bottom(16)

        # Stat strip
        stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        stats_box.set_margin_start(10); stats_box.set_margin_end(10)
        stats_box.set_margin_top(4); stats_box.set_margin_bottom(12)
        self.stat_total   = self._stat_card("—", "TOTAL",   "stat-card")
        self.stat_aur     = self._stat_card("—", "AUR",     "stat-card-aur")
        self.stat_updates = self._stat_card("—", "UPDATES", "stat-card-updates")
        for card in (self.stat_total, self.stat_aur, self.stat_updates):
            stats_box.append(card)
        outer.append(stats_box)

        # Browse
        outer.append(self._sidebar_header("BROWSE"))
        self.nav_listbox = Gtk.ListBox()
        self.nav_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.nav_listbox.add_css_class("navigation-sidebar")
        self.nav_listbox.set_margin_start(5); self.nav_listbox.set_margin_end(5)
        self.nav_listbox.connect("row-activated", self._on_nav_selected)

        self._nav_rows = {}
        browse_items = [
            ("search",    "system-search-symbolic",             "Search",        None, None),
            ("installed", "emblem-ok-symbolic",                 "Installed",     None, None),
            ("foreign",   "application-x-executable-symbolic", "AUR / Foreign", None, "count-foreign"),
            ("updates",   "software-update-available-symbolic","Updates",        None, "count-update"),
        ]
        for key, icon, label, cnt, badge_cls in browse_items:
            row = NavRow(icon, label, cnt, badge_cls)
            self.nav_listbox.append(row)
            self._nav_rows[key] = row
        self.nav_listbox.select_row(self.nav_listbox.get_row_at_index(0))
        outer.append(self.nav_listbox)

        # Repositories
        outer.append(self._separator())
        outer.append(self._sidebar_header("REPOSITORIES"))
        self.repo_listbox = Gtk.ListBox()
        self.repo_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.repo_listbox.add_css_class("navigation-sidebar")
        self.repo_listbox.set_margin_start(5); self.repo_listbox.set_margin_end(5)
        self.repo_listbox.connect("row-activated", self._on_repo_nav_selected)

        self._repo_nav_rows = {}
        self._repo_icon_map = {
            "core":      "drive-harddisk-symbolic",
            "extra":     "folder-symbolic",
            "multilib":  "folder-symbolic",
            "aur":       "application-x-executable-symbolic",
            "community": "folder-open-symbolic",
            "testing":   "folder-visiting-symbolic",
        }
        for key in ("core", "extra", "multilib", "aur"):
            row = NavRow(self._repo_icon_map[key], key, 0, "count-badge")
            self.repo_listbox.append(row)
            self._repo_nav_rows[key] = row
        outer.append(self.repo_listbox)

        # Tools
        outer.append(self._separator())
        outer.append(self._sidebar_header("TOOLS"))
        tools_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        tools_box.set_margin_start(5); tools_box.set_margin_end(5); tools_box.set_margin_bottom(4)
        for icon_name, btn_label, cb in [
            ("software-update-available-symbolic", "Check Updates", self._on_check_updates),
            ("network-transmit-receive-symbolic",  "Rate Mirrors",  self._on_rate_mirrors),
            ("user-trash-symbolic",                "Find Orphans",  self._on_show_orphans),
            ("folder-download-symbolic",           "Clean Cache",   self._on_clean_cache),
        ]:
            btn = Gtk.Button()
            btn.add_css_class("flat"); btn.add_css_class("nav-row")
            row_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row_inner.set_margin_top(5); row_inner.set_margin_bottom(5); row_inner.set_margin_start(10)
            ic = Gtk.Image.new_from_icon_name(icon_name)
            ic.set_pixel_size(16); ic.set_valign(Gtk.Align.CENTER); ic.add_css_class("dim-label")
            lbl_w = Gtk.Label(label=btn_label)
            lbl_w.set_halign(Gtk.Align.START); lbl_w.set_valign(Gtk.Align.CENTER)
            row_inner.append(ic); row_inner.append(lbl_w)
            btn.set_child(row_inner)
            btn.connect("clicked", cb)
            tools_box.append(btn)
        outer.append(tools_box)

        scroll.set_child(outer)
        return scroll

    def _sidebar_header(self, text):
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("sidebar-section")
        lbl.set_halign(Gtk.Align.CENTER); lbl.set_hexpand(True)
        return lbl

    def _separator(self):
        sep = Gtk.Separator()
        sep.set_margin_top(8); sep.set_margin_start(14); sep.set_margin_end(14)
        return sep

    def _stat_card(self, number, label, css_class="stat-card"):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        card.add_css_class(css_class); card.set_hexpand(True)
        num = Gtk.Label(label=number)
        num.add_css_class("stat-number"); num.add_css_class("numeric"); num.set_halign(Gtk.Align.CENTER)
        lbl = Gtk.Label(label=label)
        lbl.add_css_class("stat-label"); lbl.set_halign(Gtk.Align.CENTER)
        card.append(num); card.append(lbl)
        card._num = num
        return card

    # ── Package list panel ────────────────────────────────────────────────────

    def _build_package_list_panel(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        pkg_scroll = Gtk.ScrolledWindow()
        pkg_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        pkg_scroll.set_vexpand(True)
        self.pkg_listbox = Gtk.ListBox()
        self.pkg_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.pkg_listbox.add_css_class("navigation-sidebar")
        self.pkg_listbox.connect("row-activated", self._on_pkg_selected)
        pkg_scroll.set_child(self.pkg_listbox)

        spinner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        spinner_box.set_halign(Gtk.Align.CENTER); spinner_box.set_valign(Gtk.Align.CENTER)
        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(32, 32)
        sp_lbl = Gtk.Label(label="Loading packages…")
        sp_lbl.add_css_class("dim-label")
        spinner_box.append(self.spinner); spinner_box.append(sp_lbl)

        self.empty_updates_page = Adw.StatusPage()
        self.empty_updates_page.set_icon_name("emblem-ok-symbolic")
        self.empty_updates_page.set_title("System is up to date")
        self.empty_updates_page.set_description("No pending updates found.")

        self.empty_generic_page = Adw.StatusPage()
        self.empty_generic_page.set_icon_name("system-search-symbolic")
        self.empty_generic_page.set_title("No Packages Found")
        self.empty_generic_page.set_description("Try a different filter or search term.")

        self.list_stack = Gtk.Stack()
        self.list_stack.set_vexpand(True)
        self.list_stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.list_stack.add_named(spinner_box,             "loading")
        self.list_stack.add_named(pkg_scroll,              "list")
        self.list_stack.add_named(self.empty_updates_page, "empty_updates")
        self.list_stack.add_named(self.empty_generic_page, "empty_generic")
        self.list_stack.set_visible_child_name("loading")
        panel.append(self.list_stack)

        action_bar = Gtk.ActionBar()
        self.btn_install = self._action_btn(
            "package-x-generic-symbolic", "Install",
            "suggested-action", "install-btn", callback=self._on_install)
        self.btn_install.set_sensitive(False)
        action_bar.pack_start(self.btn_install)

        self.pkg_count_label = Gtk.Label(label="")
        self.pkg_count_label.add_css_class("caption"); self.pkg_count_label.add_css_class("dim-label")
        action_bar.set_center_widget(self.pkg_count_label)

        self.btn_remove = self._action_btn(
            "user-trash-symbolic", "Uninstall",
            "destructive-action", "remove-btn", callback=self._on_remove)
        self.btn_remove.set_sensitive(False)
        action_bar.pack_end(self.btn_remove)

        self.btn_upgrade_all = self._action_btn(
            "software-update-available-symbolic", "Upgrade All",
            "suggested-action", callback=self._on_upgrade)
        self.btn_upgrade_all.set_sensitive(False); self.btn_upgrade_all.set_visible(False)
        action_bar.pack_start(self.btn_upgrade_all)

        self.btn_check_updates = self._action_btn(
            "view-refresh-symbolic", "Check for Updates", callback=self._on_check_updates)
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

    # ── Detail panel ──────────────────────────────────────────────────────────

    def _build_detail_panel(self):
        self.detail_stack = Gtk.Stack()
        self.detail_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.detail_stack.set_transition_duration(120)

        empty = Adw.StatusPage()
        empty.set_icon_name("package-x-generic-symbolic")
        empty.set_title("Select a Package")
        empty.set_description("Choose a package to view its details, files, and dependencies.")
        self.detail_stack.add_named(empty, "empty")

        detail_scroll = Gtk.ScrolledWindow()
        detail_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        detail_box.set_margin_top(16);   detail_box.set_margin_bottom(24)
        detail_box.set_margin_start(20); detail_box.set_margin_end(20)

        # Hero
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

        hero_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.detail_btn_install = self._action_btn(
            "package-x-generic-symbolic", "Install",
            "suggested-action", "install-btn", callback=self._on_install)
        self.detail_btn_install.set_sensitive(False)
        self.detail_btn_remove = self._action_btn(
            "user-trash-symbolic", "Uninstall",
            "destructive-action", "remove-btn", callback=self._on_remove)
        self.detail_btn_remove.set_sensitive(False)
        self.detail_btn_reinstall = self._action_btn(
            "view-refresh-symbolic", "Reinstall", callback=self._on_reinstall)
        self.detail_btn_reinstall.set_sensitive(False)
        self.detail_btn_reinstall.add_css_class("flat")
        hero_actions.append(self.detail_btn_install)
        hero_actions.append(self.detail_btn_remove)
        hero_actions.append(self.detail_btn_reinstall)
        hero.append(hero_actions)
        detail_box.append(hero)

        # Tabs
        self.detail_view_stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher()
        switcher.set_stack(self.detail_view_stack)
        switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        detail_box.append(switcher)

        # Info tab
        info_scroll = Gtk.ScrolledWindow()
        info_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        info_scroll.set_min_content_height(200)
        info_box_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        info_box_inner.set_margin_start(4); info_box_inner.set_margin_end(4)
        info_group = Adw.PreferencesGroup()
        info_group.set_title("Package Information")
        info_box_inner.append(info_group)
        self.info_rows = {}
        self._dep_rows = {}
        for key in ["URL", "Licenses", "Groups", "Depends On", "Optional Deps",
                    "Conflicts With", "Provides", "Replaces",
                    "Installed Size", "Packager", "Build Date", "Install Date", "Install Reason"]:
            if key in ("Depends On", "Optional Deps"):
                exp_row = Adw.ExpanderRow()
                exp_row.set_title(key); exp_row.set_subtitle("—")
                flow = Gtk.FlowBox()
                flow.set_selection_mode(Gtk.SelectionMode.NONE)
                flow.set_column_spacing(6); flow.set_row_spacing(6)
                flow.set_margin_start(12); flow.set_margin_end(12)
                flow.set_margin_top(8); flow.set_margin_bottom(10)
                flow_row = Gtk.ListBoxRow()
                flow_row.set_activatable(False)
                flow_row.set_child(flow)
                exp_row.add_row(flow_row)
                info_group.add(exp_row)
                self._dep_rows[key] = (exp_row, flow)
                self.info_rows[key] = exp_row
            else:
                row = Adw.ActionRow()
                row.set_title(key); row.set_subtitle("—")
                row.set_subtitle_selectable(True)
                info_group.add(row)
                self.info_rows[key] = row

        raw_group = Adw.PreferencesGroup()
        raw_group.set_title("Raw Output")
        info_box_inner.append(raw_group)
        raw_exp = Adw.ExpanderRow()
        raw_exp.set_title("pacman -Qi output")
        raw_exp.set_subtitle("Full package information")
        raw_group.add(raw_exp)
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
        raw_scroll_inner.set_child(self.raw_text)
        raw_exp.add_row(raw_scroll_inner)
        info_scroll.set_child(info_box_inner)
        self.detail_view_stack.add_titled_with_icon(
            info_scroll, "info", "Info", "dialog-information-symbolic")

        # Files tab
        files_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        files_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        files_hdr.set_margin_start(6); files_hdr.set_margin_end(6)
        files_hdr.set_margin_top(6); files_hdr.set_margin_bottom(4)
        self.files_search = Gtk.SearchEntry()
        self.files_search.set_placeholder_text("Filter…"); self.files_search.set_hexpand(True)
        self.files_search.connect("search-changed", self._on_files_search)
        files_hdr.append(self.files_search)
        self.files_count_lbl = Gtk.Label(label="")
        self.files_count_lbl.add_css_class("caption"); self.files_count_lbl.add_css_class("dim-label")
        self.files_count_lbl.set_halign(Gtk.Align.END)
        files_hdr.append(self.files_count_lbl)
        files_box.append(files_hdr)
        files_scroll = Gtk.ScrolledWindow()
        files_scroll.set_vexpand(True)
        self.files_listbox = Gtk.ListBox()
        self.files_listbox.add_css_class("navigation-sidebar")
        self.files_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        files_scroll.set_child(self.files_listbox)
        files_box.append(files_scroll)
        self.detail_view_stack.add_titled_with_icon(
            files_box, "files", "Files", "folder-symbolic")

        detail_box.append(self.detail_view_stack)
        detail_scroll.set_child(detail_box)
        self.detail_stack.add_named(detail_scroll, "detail")
        self.detail_stack.set_visible_child_name("empty")
        return self.detail_stack

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_packages(self):
        self.list_stack.set_visible_child_name("loading")
        self.spinner.start()
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        pkgs = get_packages()
        if self._alive:
            GLib.idle_add(self._on_packages_loaded, pkgs)

    def _on_packages_loaded(self, packages):
        self._all_packages = packages
        self.spinner.stop()
        self._update_sidebar_counts()
        # Only render the list if we're on a list page — skip if on Search
        if self.main_stack.get_visible_child_name() != "search":
            self._apply_filter()
        else:
            self.list_stack.set_visible_child_name("list")
        threading.Thread(target=self._bg_check_updates, daemon=True).start()
        return False

    def _bg_check_updates(self):
        updates = check_updates()
        if self._alive:
            GLib.idle_add(self._on_updates_loaded, updates)

    def _on_updates_loaded(self, updates):
        self._updates = updates
        n = len(updates)
        self.stat_updates._num.set_label(str(n))
        self._nav_rows["updates"].set_count(n)
        if n > 0:
            self.update_banner.set_title(f"{n} update{'s' if n != 1 else ''} available")
            self.update_banner.set_revealed(True)
        else:
            self.update_banner.set_revealed(False)
        self.empty_updates_page.set_description(
            "No pending updates found." if n == 0 else f"{n} update(s) available.")
        self._update_action_bar_mode()
        update_map = {u["name"]: u["new"] for u in updates}
        for pkg in self._all_packages:
            if pkg["name"] in update_map:
                pkg["status"] = "update"
                pkg["new_version"] = update_map[pkg["name"]]
        if self.main_stack.get_visible_child_name() != "search":
            self._apply_filter()
        return False

    def _update_sidebar_counts(self):
        total     = len(self._all_packages)
        foreign   = sum(1 for p in self._all_packages if p.get("foreign", False))
        installed = sum(1 for p in self._all_packages if p["status"] == "installed")
        self.stat_total._num.set_label(str(total))
        self.stat_aur._num.set_label(str(foreign))
        self._nav_rows["installed"].set_count(installed)
        self._nav_rows["foreign"].set_count(foreign)

        seen_repos = set(
            p.get("repo", "").lower() for p in self._all_packages
            if p.get("repo", "") not in ("local", "")
        )
        for repo_key in sorted(seen_repos):
            if repo_key not in self._repo_nav_rows:
                icon = self._repo_icon_map.get(repo_key, "folder-symbolic")
                new_row = NavRow(icon, repo_key, 0, "count-badge")
                self.repo_listbox.append(new_row)
                self._repo_nav_rows[repo_key] = new_row
        for repo_key, nav_row in self._repo_nav_rows.items():
            count = sum(1 for p in self._all_packages if p.get("repo", "").lower() == repo_key)
            nav_row.set_count(count)
            nav_row.set_visible(count > 0 or repo_key in ("core", "extra", "multilib", "aur"))

    # ── Filtering ─────────────────────────────────────────────────────────────

    def _apply_filter(self):
        """Filter in a background thread, render in batches to avoid UI freeze."""
        filt = self._current_filter
        pkgs_snapshot = list(self._all_packages)

        def do_filter():
            filtered = []
            for pkg in pkgs_snapshot:
                if filt == "installed" and pkg["status"] not in ("installed", "update"):
                    continue
                if filt == "foreign" and not pkg.get("foreign", False):
                    continue
                if filt == "updates" and pkg.get("status") != "update":
                    continue
                if filt in ("core", "extra", "multilib", "community")                         and pkg.get("repo", "").lower() != filt:
                    continue
                if filt == "aur" and not pkg.get("foreign", False):
                    continue
                filtered.append(pkg)
            if self._alive:
                GLib.idle_add(self._render_filter_results, filtered, filt)

        threading.Thread(target=do_filter, daemon=True).start()

    def _render_filter_results(self, filtered, filt):
        if not self._alive:
            return False
        # Only apply if filter hasn't changed since we started
        if self._current_filter != filt:
            return False

        while self.pkg_listbox.get_first_child():
            self.pkg_listbox.remove(self.pkg_listbox.get_first_child())

        # Batch-append in chunks via idle to keep UI responsive
        CHUNK = 100
        total = len(self._all_packages)
        shown = len(filtered)

        def append_chunk(start):
            if not self._alive or self._current_filter != filt:
                return False
            end = min(start + CHUNK, len(filtered))
            for pkg in filtered[start:end]:
                item = PackageItem(
                    pkg["name"], pkg["version"],
                    pkg.get("repo", "local"), pkg["status"],
                    pkg.get("description", ""), pkg.get("foreign", False))
                self.pkg_listbox.append(PackageRow(item))
            if end < len(filtered):
                GLib.idle_add(append_chunk, end)
            return False

        self.pkg_count_label.set_label(
            f"{shown} of {total} packages" if shown != total else f"{total} packages")

        if shown == 0:
            self.list_stack.set_visible_child_name(
                "empty_updates" if filt == "updates" and self._updates is not None
                else "empty_generic")
        else:
            self.list_stack.set_visible_child_name("list")
            GLib.idle_add(append_chunk, 0)

        return False

    # ── Search ────────────────────────────────────────────────────────────────

    def _on_search_changed(self, entry):
        q = entry.get_text().strip()
        if not q:
            self._search_spinner.stop()
            self._search_results_stack.set_visible_child_name("idle")
            return
        self._search_results_stack.set_visible_child_name("searching")
        self._search_spinner.start()

        def worker(query):
            ql = query.lower()
            local = [p for p in self._all_packages
                     if ql in p["name"].lower() or ql in p.get("description", "").lower()]
            if self._alive:
                GLib.idle_add(self._show_search_results, local, query)
            remote = search_packages_cmd(query)
            if self._alive:
                GLib.idle_add(self._merge_and_show_search, remote, query)

        threading.Thread(target=worker, args=(q,), daemon=True).start()

    def _on_search_activate(self, *_):
        q = self.search_entry.get_text().strip()
        if not q:
            self._search_results_stack.set_visible_child_name("idle")
            return
        self._on_search_changed(self.search_entry)

    def _show_search_results(self, results, query):
        if self.search_entry.get_text().strip().lower() != query.lower():
            return False
        self._populate_search_list(results)
        return False

    def _merge_and_show_search(self, remote_results, query):
        if self.search_entry.get_text().strip().lower() != query.lower():
            return False
        existing = {p["name"] for p in self._all_packages}
        for r in remote_results:
            if r["name"] not in existing:
                self._all_packages.append(r)
                existing.add(r["name"])
        ql = query.lower()
        merged = [p for p in self._all_packages
                  if ql in p["name"].lower() or ql in p.get("description", "").lower()]
        self._populate_search_list(merged)
        return False

    def _populate_search_list(self, results):
        self._search_spinner.stop()
        while self.search_listbox.get_first_child():
            self.search_listbox.remove(self.search_listbox.get_first_child())
        if not results:
            if self._search_results_stack.get_visible_child_name() != "empty":
                self._search_results_stack.set_visible_child_name("empty")
            return
        for pkg in results:
            item = PackageItem(
                pkg["name"], pkg["version"],
                pkg.get("repo", "local"), pkg["status"],
                pkg.get("description", ""), pkg.get("foreign", False))
            self.search_listbox.append(PackageRow(item))
        n = len(results)
        self._search_count_lbl.set_label(f"{n} result{'s' if n != 1 else ''}")
        # Only switch to results page if not already there — avoids any redraw flash
        if self._search_results_stack.get_visible_child_name() != "results":
            self._search_results_stack.set_visible_child_name("results")

    def _on_search_pkg_selected(self, listbox, row):
        if row is None:
            return
        pkg = row.pkg
        self._selected_pkg = pkg
        installed = pkg.pkg_status in ("installed", "update")
        self._search_btn_install.set_sensitive(not installed)
        self._search_btn_remove.set_sensitive(installed)
        self.sd_btn_install.set_sensitive(not installed)
        self.sd_btn_remove.set_sensitive(installed)
        self.sd_btn_reinstall.set_sensitive(installed)
        self._show_search_detail(pkg)

    def _show_search_detail(self, pkg):
        """Populate the search page's own detail panel."""
        self.sd_name.set_label(pkg.pkg_name)
        self.sd_desc.set_label(pkg.pkg_description or "No description available.")
        self.sd_icon.set_from_icon_name(pkg_icon(pkg.pkg_name))

        repo_str = "aur" if pkg.pkg_foreign else (pkg.pkg_repo or "local").lower()
        self.sd_repo_badge.set_label(repo_str.upper())
        for cls in REPO_BADGE_CLASS.values():
            self.sd_repo_badge.remove_css_class(cls)
        self.sd_repo_badge.add_css_class(REPO_BADGE_CLASS.get(repo_str, "badge-local"))
        self.sd_ver_badge.set_label(pkg.pkg_version)

        for cls in ("status-installed", "status-available", "status-update", "status-foreign"):
            self.sd_status.remove_css_class(cls)
        if pkg.pkg_status == "update":
            self.sd_status.set_label("UPDATE AVAILABLE")
            self.sd_status.add_css_class("status-update")
        elif pkg.pkg_status == "installed":
            if pkg.pkg_foreign:
                self.sd_status.set_label("INSTALLED (AUR)")
                self.sd_status.add_css_class("status-foreign")
            else:
                self.sd_status.set_label("INSTALLED")
                self.sd_status.add_css_class("status-installed")
        else:
            self.sd_status.set_label("AVAILABLE")
            self.sd_status.add_css_class("status-available")

        self.search_detail_stack.set_visible_child_name("detail")
        for row in self.sd_info_rows.values():
            if isinstance(row, Adw.ActionRow):
                row.set_subtitle("…")
        for exp_row, _ in self.sd_dep_rows.values():
            exp_row.set_subtitle("…")
        self.sd_raw_text.set_label("Loading…")
        while self.sd_files_listbox.get_first_child():
            self.sd_files_listbox.remove(self.sd_files_listbox.get_first_child())
        self.sd_files_count_lbl.set_label("Loading…")
        self._sd_files_all = []

        def worker():
            info  = get_package_info(pkg.pkg_name)
            files = get_package_files(pkg.pkg_name)
            if self._alive:
                GLib.idle_add(self._populate_search_detail, info, files)
        threading.Thread(target=worker, daemon=True).start()

    def _populate_search_detail(self, raw, files):
        self.sd_raw_text.set_label(raw)
        parsed = self._parse_pkginfo(raw)
        field_map = {
            "URL": "URL", "Licenses": "Licenses", "Groups": "Groups",
            "Depends On": "Depends On", "Optional Deps": "Optional Deps",
            "Conflicts With": "Conflicts With", "Provides": "Provides", "Replaces": "Replaces",
            "Installed Size": "Installed Size", "Packager": "Packager",
            "Build Date": "Build Date", "Install Date": "Install Date",
            "Install Reason": "Install Reason",
        }
        for pk, rk in field_map.items():
            val = parsed.get(pk, "—") or "—"
            if val in ("None", ""):
                val = "—"
            if rk in self.sd_dep_rows:
                exp_row, flow = self.sd_dep_rows[rk]
                self._populate_dep_flow_widget(flow, exp_row, val, in_search=True)
            elif rk in self.sd_info_rows:
                self.sd_info_rows[rk].set_subtitle(GLib.markup_escape_text(val))
        self.sd_arch_badge.set_label(parsed.get("Architecture", "x86_64"))
        self._sd_files_all = files
        self._populate_sd_files(files)
        return False

    def _populate_sd_files(self, files):
        while self.sd_files_listbox.get_first_child():
            self.sd_files_listbox.remove(self.sd_files_listbox.get_first_child())
        q = self.sd_files_search.get_text().lower().strip()
        shown = []
        for line in files:
            parts = line.split(None, 1)
            path = parts[1] if len(parts) == 2 else line
            if not q or q in path.lower():
                shown.append(path)
        for path in shown:
            row = Gtk.ListBoxRow()
            row.set_activatable(False)
            lbl = Gtk.Label(label=path)
            lbl.set_halign(Gtk.Align.START); lbl.set_selectable(True)
            lbl.add_css_class("monospace"); lbl.add_css_class("caption")
            lbl.set_margin_start(12); lbl.set_margin_top(4); lbl.set_margin_bottom(4)
            row.set_child(lbl)
            self.sd_files_listbox.append(row)
        total = sum(1 for l in files if len(l.split(None, 1)) >= 2)
        self.sd_files_count_lbl.set_label(
            f"{len(shown)} of {total} files" if q else f"{total} files")

    def _on_sd_files_search(self, entry):
        if hasattr(self, "_sd_files_all"):
            self._populate_sd_files(self._sd_files_all)

    # ── Nav ───────────────────────────────────────────────────────────────────

    def _on_nav_selected(self, listbox, row):
        self.repo_listbox.unselect_all()
        keys = list(self._nav_rows.keys())
        idx  = row.get_index()
        if idx >= len(keys):
            return
        key = keys[idx]
        if key == "search":
            self.main_stack.set_visible_child_name("search")
            self._current_filter = "search"
            GLib.idle_add(self.search_entry.grab_focus)
            return
        if key == "orphans":
            self._on_show_orphans()
            return
        self._current_filter = key
        self.main_stack.set_visible_child_name("list")
        self._update_action_bar_mode()
        self._apply_filter()

    def _on_repo_nav_selected(self, listbox, row):
        self.nav_listbox.unselect_all()
        keys = list(self._repo_nav_rows.keys())
        idx  = row.get_index()
        if idx < len(keys):
            self._current_filter = keys[idx]
        self.main_stack.set_visible_child_name("list")
        self._update_action_bar_mode()
        self._apply_filter()

    def _update_action_bar_mode(self):
        is_updates = (self._current_filter == "updates")
        self.btn_install.set_visible(not is_updates)
        self.btn_remove.set_visible(not is_updates)
        self.btn_upgrade_all.set_visible(is_updates)
        self.btn_check_updates.set_visible(is_updates)
        if is_updates:
            n = len(self._updates) if self._updates else 0
            self.btn_upgrade_all.set_sensitive(n > 0)

    # ── Package detail ────────────────────────────────────────────────────────

    def _on_pkg_selected(self, listbox, row):
        if row is None:
            return
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

        for cls in ("status-installed", "status-available", "status-update", "status-foreign"):
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
        for row in self.info_rows.values():
            if isinstance(row, Adw.ActionRow):
                row.set_subtitle("…")
        for exp_row, _ in self._dep_rows.values():
            exp_row.set_subtitle("…")
        self.raw_text.set_label("Loading…")
        while self.files_listbox.get_first_child():
            self.files_listbox.remove(self.files_listbox.get_first_child())
        self.files_count_lbl.set_label("Loading…")
        self._pkg_files_all = []

        def worker():
            info  = get_package_info(pkg.pkg_name)
            files = get_package_files(pkg.pkg_name)
            if self._alive:
                GLib.idle_add(self._populate_detail, info, files)
        threading.Thread(target=worker, daemon=True).start()

    def _populate_detail(self, raw, files):
        self.raw_text.set_label(raw)
        parsed = self._parse_pkginfo(raw)
        field_map = {
            "URL": "URL", "Licenses": "Licenses", "Groups": "Groups",
            "Depends On": "Depends On", "Optional Deps": "Optional Deps",
            "Conflicts With": "Conflicts With", "Provides": "Provides", "Replaces": "Replaces",
            "Installed Size": "Installed Size", "Packager": "Packager",
            "Build Date": "Build Date", "Install Date": "Install Date",
            "Install Reason": "Install Reason",
        }
        for pk, rk in field_map.items():
            val = parsed.get(pk, "—") or "—"
            if val in ("None", ""):
                val = "—"
            if rk in self._dep_rows:
                exp_row, flow = self._dep_rows[rk]
                self._populate_dep_flow(flow, exp_row, val)
            elif rk in self.info_rows:
                self.info_rows[rk].set_subtitle(GLib.markup_escape_text(val))
        self.detail_arch_badge.set_label(parsed.get("Architecture", "x86_64"))
        self._pkg_files_all = files
        self._populate_files(files)
        return False


    def _parse_pkginfo(self, raw):
        """Parse pacman -Qi / -Si output handling multi-line values correctly."""
        parsed = {}
        current_key = None
        for line in raw.splitlines():
            if line and not line[0].isspace() and ":" in line:
                k, _, v = line.partition(":")
                current_key = k.strip()
                val = v.strip()
                parsed[current_key] = val
            elif current_key and line.startswith(" ") and line.strip():
                # continuation — append to current key
                parsed[current_key] = parsed[current_key] + " " + line.strip()
        return parsed

    def _populate_dep_flow(self, flow, exp_row, val):
        self._populate_dep_flow_widget(flow, exp_row, val, in_search=False)

    def _populate_dep_flow_widget(self, flow, exp_row, val, in_search=False):
        while flow.get_first_child():
            flow.remove(flow.get_first_child())
        if val == "—":
            exp_row.set_subtitle("—")
            exp_row.set_expanded(False)
            return
        import re
        # Each dep token may look like: "libfoo>=1.0" or "libfoo: for something"
        # Split on whitespace first, then strip version constraints and inline descriptions
        raw_tokens = val.split()
        dep_names = []
        for token in raw_tokens:
            # Skip pure description words (tokens after a "name:" token)
            # A dep token starts with a letter/number and contains the package name
            if not token or token[0] in (":", "(", ")"):
                continue
            # Strip inline description separator "name:" — take only up to the colon
            name_part = token.split(":")[0]
            # Strip version constraints
            clean = re.split(r"[><=!]", name_part)[0].strip()
            if clean and re.match(r"^[a-zA-Z0-9_@.+-]+$", clean):
                dep_names.append(clean)
        # Deduplicate while preserving order
        seen = set()
        dep_names = [d for d in dep_names if not (d in seen or seen.add(d))]
        exp_row.set_subtitle(f"{len(dep_names)} package{'s' if len(dep_names) != 1 else ''}")
        for dep in dep_names:
            btn = Gtk.Button(label=dep)
            btn.add_css_class("dep-chip")
            btn.set_tooltip_text(f"Look up {dep}")
            if in_search:
                btn.connect("clicked", lambda b, name=dep: self._search_dep(name))
            else:
                btn.connect("clicked", lambda b, name=dep: self._lookup_dep_in_list(name))
            flow.append(btn)

    def _lookup_dep_in_list(self, pkg_name):
        """Highlight dependency in the middle panel only; leave the right panel unchanged."""
        def _highlight_in_list():
            row = self.pkg_listbox.get_first_child()
            while row:
                if hasattr(row, "pkg") and row.pkg.pkg_name == pkg_name:
                    # Select row visually but do NOT trigger detail panel update
                    self.pkg_listbox.select_row(row)
                    row.grab_focus()
                    return True
                row = row.get_next_sibling()
            return False

        # Try current list first
        if _highlight_in_list():
            return

        # Switch to "installed" filter to make it visible, then highlight
        self._current_filter = "installed"
        self.nav_listbox.select_row(self._nav_rows["installed"])

        def after_filter():
            _highlight_in_list()
            return False

        self._apply_filter_then(after_filter)

    def _apply_filter_then(self, callback):
        """Apply filter and run callback once rendering is done."""
        filt = self._current_filter
        pkgs_snapshot = list(self._all_packages)

        def do_filter():
            filtered = []
            for pkg in pkgs_snapshot:
                if filt == "installed" and pkg["status"] not in ("installed", "update"):
                    continue
                if filt == "foreign" and not pkg.get("foreign", False):
                    continue
                if filt == "updates" and pkg.get("status") != "update":
                    continue
                if filt in ("core", "extra", "multilib", "community")                         and pkg.get("repo", "").lower() != filt:
                    continue
                if filt == "aur" and not pkg.get("foreign", False):
                    continue
                filtered.append(pkg)
            if self._alive:
                GLib.idle_add(self._render_filter_results_then, filtered, filt, callback)

        threading.Thread(target=do_filter, daemon=True).start()

    def _render_filter_results_then(self, filtered, filt, callback):
        """Same as _render_filter_results but fires callback after first chunk."""
        if not self._alive or self._current_filter != filt:
            return False

        while self.pkg_listbox.get_first_child():
            self.pkg_listbox.remove(self.pkg_listbox.get_first_child())

        CHUNK = 100
        total = len(self._all_packages)
        shown = len(filtered)

        def append_chunk(start, first=False):
            if not self._alive or self._current_filter != filt:
                return False
            end = min(start + CHUNK, len(filtered))
            for pkg in filtered[start:end]:
                item = PackageItem(
                    pkg["name"], pkg["version"],
                    pkg.get("repo", "local"), pkg["status"],
                    pkg.get("description", ""), pkg.get("foreign", False))
                self.pkg_listbox.append(PackageRow(item))
            if first and callback:
                GLib.idle_add(callback)
            if end < len(filtered):
                GLib.idle_add(append_chunk, end, False)
            return False

        self.pkg_count_label.set_label(
            f"{shown} of {total} packages" if shown != total else f"{total} packages")

        if shown == 0:
            self.list_stack.set_visible_child_name(
                "empty_updates" if filt == "updates" and self._updates is not None
                else "empty_generic")
            if callback:
                GLib.idle_add(callback)
        else:
            self.list_stack.set_visible_child_name("list")
            GLib.idle_add(append_chunk, 0, True)

        return False

    def _search_dep(self, pkg_name):
        """Highlight dependency in the search results list only — no entry change, no flicker."""
        ql = pkg_name.lower()

        def _highlight_in_search_list():
            row = self.search_listbox.get_first_child()
            while row:
                if hasattr(row, "pkg") and row.pkg.pkg_name == pkg_name:
                    self.search_listbox.select_row(row)
                    row.grab_focus()
                    return True
                row = row.get_next_sibling()
            return False

        # If already in the current results list, just highlight it
        if _highlight_in_search_list():
            return

        # Not visible — find it in _all_packages and insert it at the top of the list
        for pkg in self._all_packages:
            if pkg["name"] == pkg_name:
                item = PackageItem(
                    pkg["name"], pkg["version"],
                    pkg.get("repo", "local"), pkg["status"],
                    pkg.get("description", ""), pkg.get("foreign", False))
                row = PackageRow(item)
                self.search_listbox.prepend(row)
                self.search_listbox.select_row(row)
                row.grab_focus()
                n_str = self._search_count_lbl.get_label()
                return

        # Not in cache at all — fetch in background and prepend when ready
        def worker():
            results = search_packages_cmd(pkg_name)
            if self._alive:
                GLib.idle_add(self._prepend_dep_result, pkg_name, results)

        threading.Thread(target=worker, daemon=True).start()

    def _prepend_dep_result(self, pkg_name, results):
        for r in results:
            if r["name"] == pkg_name:
                if r["name"] not in {p["name"] for p in self._all_packages}:
                    self._all_packages.append(r)
                item = PackageItem(r["name"], r["version"],
                                   r.get("repo", "local"), r["status"],
                                   r.get("description", ""), r.get("foreign", False))
                row = PackageRow(item)
                self.search_listbox.prepend(row)
                self.search_listbox.select_row(row)
                row.grab_focus()
                return
        return False

    def _populate_files(self, files):
        while self.files_listbox.get_first_child():
            self.files_listbox.remove(self.files_listbox.get_first_child())
        q = self.files_search.get_text().lower().strip()
        shown = []
        for line in files:
            parts = line.split(None, 1)
            path = parts[1] if len(parts) == 2 else line
            if not q or q in path.lower():
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
        total = sum(1 for l in files if len(l.split(None, 1)) >= 2)
        self.files_count_lbl.set_label(
            f"{len(shown)} of {total} files" if q else f"{total} files")

    def _on_files_search(self, entry):
        self._populate_files(self._pkg_files_all)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _run_terminal(self, cmd, title, on_success=None):
        def _on_done(code):
            if code == 0:
                invalidate_cache()
            toast = Adw.Toast()
            toast.set_title(
                f"✓ {title} completed" if code == 0 else f"✗ {title} failed (exit {code})")
            toast.set_timeout(4)
            try:
                self._toast_overlay.add_toast(toast)
            except AttributeError:
                pass
            self._load_packages()
        run_terminal_dialog(self, cmd, title, on_success=on_success, on_done_extra=_on_done)

    def _on_refresh(self, *_):
        self._all_packages = []
        self._updates = None
        self.search_entry.set_text("")
        self._search_results_stack.set_visible_child_name("idle")
        self.detail_stack.set_visible_child_name("empty")
        self._selected_pkg = None
        self.btn_install.set_sensitive(False)
        self.btn_remove.set_sensitive(False)
        self.update_banner.set_revealed(False)
        self._load_packages()

    def _on_sync_db(self, *_):
        invalidate_syncdb_cache()
        self._run_terminal("sudo -S pacman -Sy --noconfirm", "Sync Databases")

    def _on_upgrade(self, *_):
        def _after():
            self.update_banner.set_revealed(False)
            self._updates = []
            self.stat_updates._num.set_label("0")
            self._nav_rows["updates"].set_count(0)
        self._run_terminal("sudo -S pacman -Syu --noconfirm", "System Upgrade", on_success=_after)

    def _on_clean_cache(self, *_):
        self._run_terminal(
            "sudo -S -v && { paccache -rk2 2>/dev/null || sudo pacman -Sc --noconfirm; }",
            "Clean Cache")

    def _on_check_updates(self, *_):
        self._run_terminal(
            "checkupdates 2>/dev/null || pacman -Qu 2>/dev/null || echo 'No updates available'",
            "Check for Updates")

    def _on_manage_repos(self, *_):
        show_repo_manager(self, self._run_terminal)

    def _on_rate_mirrors(self, *_):
        show_mirror_rater(self, self._run_terminal)

    def _on_show_orphans(self, *_):
        show_orphan_finder(self, self._run_terminal)

    def _on_show_sysinfo(self, *_):
        show_sysinfo_dialog(self)

    def _on_install(self, *_):
        if not self._selected_pkg:
            return
        pkg = self._selected_pkg
        if not is_safe_package_name(pkg.pkg_name):
            return
        if pkg.pkg_foreign:
            helper = self._get_aur_helper()
            cmd = [helper, "-S", "--noconfirm", pkg.pkg_name] if helper \
                  else ["sudo", "-S", "pacman", "-Sy", "--noconfirm", pkg.pkg_name]
        else:
            cmd = ["sudo", "-S", "pacman", "-Sy", "--noconfirm", pkg.pkg_name]
        self._run_terminal(cmd, f"Install {pkg.pkg_name}",
                           on_success=self._refresh_selected_pkg)

    def _on_remove(self, *_):
        if not self._selected_pkg:
            return
        pkg = self._selected_pkg
        if not is_safe_package_name(pkg.pkg_name):
            return
        d = Adw.AlertDialog()
        d.set_heading(f"Remove {pkg.pkg_name}?")
        d.set_body(f"This will remove {pkg.pkg_name} ({pkg.pkg_version}) from your system.")
        d.add_response("cancel", "Cancel"); d.add_response("remove", "Remove")
        d.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        d.set_default_response("cancel"); d.set_close_response("cancel")
        def on_resp(dlg, resp):
            if resp == "remove":
                self._run_terminal(
                    ["sudo", "-S", "pacman", "-R", "--noconfirm", pkg.pkg_name],
                    f"Remove {pkg.pkg_name}",
                    on_success=self._refresh_selected_pkg)
        d.connect("response", on_resp)
        d.present(self)

    def _on_reinstall(self, *_):
        if not self._selected_pkg:
            return
        pkg = self._selected_pkg
        if not is_safe_package_name(pkg.pkg_name):
            return
        if pkg.pkg_foreign:
            helper = self._get_aur_helper()
            cmd = [helper, "-S", "--noconfirm", pkg.pkg_name] if helper \
                  else ["sudo", "-S", "pacman", "-Sy", "--noconfirm", pkg.pkg_name]
        else:
            cmd = ["sudo", "-S", "pacman", "-Sy", "--noconfirm", pkg.pkg_name]
        self._run_terminal(cmd, f"Reinstall {pkg.pkg_name}",
                           on_success=self._refresh_selected_pkg)

    def _refresh_selected_pkg(self):
        if not self._selected_pkg:
            return
        pkg = self._selected_pkg
        if not is_safe_package_name(pkg.pkg_name):
            pkg.pkg_status = "available"
            return
        out, code = run_command(["pacman", "-Qi", pkg.pkg_name])
        pkg.pkg_status = "installed" if (code == 0 and out) else "available"
        installed = pkg.pkg_status == "installed"
        self.btn_install.set_sensitive(not installed)
        self.btn_remove.set_sensitive(installed)
        self._search_btn_install.set_sensitive(not installed)
        self._search_btn_remove.set_sensitive(installed)
        self.detail_btn_install.set_sensitive(not installed)
        self.detail_btn_remove.set_sensitive(installed)
        self.detail_btn_reinstall.set_sensitive(installed)
        self.sd_btn_install.set_sensitive(not installed)
        self.sd_btn_remove.set_sensitive(installed)
        self.sd_btn_reinstall.set_sensitive(installed)
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
        if installed:
            def worker():
                info  = get_package_info(pkg.pkg_name)
                files = get_package_files(pkg.pkg_name)
                if self._alive:
                    GLib.idle_add(self._populate_detail, info, files)
            threading.Thread(target=worker, daemon=True).start()

    def _get_aur_helper(self):
        if self._aur_helper_cache is None:
            for h in ("paru", "yay", "pikaur", "trizen"):
                if shutil.which(h):
                    self._aur_helper_cache = h
                    break
        return self._aur_helper_cache
