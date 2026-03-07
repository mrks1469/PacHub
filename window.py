"""
PacHub — window.py
Main application window: sidebar, package list, detail panel,
filtering, search, and all action handlers.
"""

import threading

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio, Pango

from backend import (
    get_packages, get_package_info, get_package_files,
    check_updates, search_packages_cmd, run_command,
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
        self._all_packages   = []
        self._selected_pkg   = None
        self._current_filter = "all"
        self._search_query   = ""
        self._updates        = None
        self._build_ui()
        self._load_packages()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.nav_split = Adw.NavigationSplitView()
        self.nav_split.set_max_sidebar_width(230)
        self.nav_split.set_min_sidebar_width(190)
        self.nav_split.set_sidebar_width_fraction(0.20)

        # ── Sidebar page ──
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
        title_box.append(app_icon); title_box.append(title_lbl)
        sidebar_hdr.set_title_widget(title_box)
        sidebar_tv.add_top_bar(sidebar_hdr)
        sidebar_tv.set_content(self._build_sidebar())
        sidebar_page.set_child(sidebar_tv)
        self.nav_split.set_sidebar(sidebar_page)

        # ── Content page ──
        content_page = Adw.NavigationPage()
        content_page.set_title("Packages")
        self.content_tv  = Adw.ToolbarView()
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
        menu.append("Sync Databases",    "app.sync")
        menu.append("Check for Updates", "app.check_updates")
        menu.append("Refresh List",      "app.refresh")
        menu.append_section(None, Gio.Menu())
        menu.append("Manage Repositories…", "app.manage_repos")
        menu.append("Rate Mirrors…",        "app.rate_mirrors")
        menu.append_section(None, Gio.Menu())
        menu.append("Find Orphans",  "app.orphans")
        menu.append("System Info",   "app.sysinfo")
        menu.append("Cache Cleaner", "app.cache")
        menu.append_section(None, Gio.Menu())
        menu.append("About PacHub",  "app.about")
        menu_btn.set_menu_model(menu)
        right_box.append(menu_btn)
        self.content_hdr.pack_end(right_box)
        self.content_tv.add_top_bar(self.content_hdr)

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
        stats_box.set_margin_top(4);    stats_box.set_margin_bottom(12)
        self.stat_total   = self._stat_card("—", "TOTAL",   "stat-card")
        self.stat_aur     = self._stat_card("—", "AUR",     "stat-card-aur")
        self.stat_updates = self._stat_card("—", "UPDATES", "stat-card-updates")
        for card in (self.stat_total, self.stat_aur, self.stat_updates):
            stats_box.append(card)
        outer.append(stats_box)

        # Browse section
        outer.append(self._sidebar_header("BROWSE"))
        self.nav_listbox = Gtk.ListBox()
        self.nav_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.nav_listbox.add_css_class("navigation-sidebar")
        self.nav_listbox.set_margin_start(5); self.nav_listbox.set_margin_end(5)
        self.nav_listbox.connect("row-activated", self._on_nav_selected)

        self._nav_rows = {}
        browse_items = [
            ("all",       "view-app-grid-symbolic",             "All Packages",  None, None),
            ("installed", "emblem-ok-symbolic",                  "Installed",     None, None),
            ("foreign",   "application-x-executable-symbolic",  "AUR / Foreign", None, "count-foreign"),
            ("updates",   "software-update-available-symbolic", "Updates",       None, "count-update"),
        ]
        for key, icon, label, cnt, badge_cls in browse_items:
            row = self._nav_row(icon, label, cnt, badge_cls)
            self.nav_listbox.append(row)
            self._nav_rows[key] = row
        self.nav_listbox.select_row(self.nav_listbox.get_row_at_index(0))
        outer.append(self.nav_listbox)

        # Repositories section
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
            row = self._nav_row(self._repo_icon_map[key], key, 0, "count-badge")
            self.repo_listbox.append(row)
            self._repo_nav_rows[key] = row
        outer.append(self.repo_listbox)

        # Tools section
        outer.append(self._separator())
        outer.append(self._sidebar_header("TOOLS"))
        tools_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        tools_box.set_margin_start(5); tools_box.set_margin_end(5); tools_box.set_margin_bottom(4)
        tool_items = [
            ("emblem-synchronizing-symbolic",      "Sync Databases",   self._on_sync_db),
            ("software-update-available-symbolic", "Check Updates",    self._on_check_updates),
            ("network-transmit-receive-symbolic",  "Rate Mirrors",     self._on_rate_mirrors),
            ("user-trash-symbolic",                "Find Orphans",     self._on_show_orphans),
            ("folder-download-symbolic",           "Clean Cache",      self._on_clean_cache),
        ]
        for icon_name, btn_label, cb in tool_items:
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

    def _nav_row(self, icon_name, label_text, count=None, badge_css=None):
        return NavRow(icon_name, label_text, count, badge_css)

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
        card.add_css_class(css_class); card.set_hexpand(True); card.set_halign(Gtk.Align.FILL)
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
        self.list_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.list_stack.set_transition_duration(150)
        self.list_stack.add_named(spinner_box,            "loading")
        self.list_stack.add_named(self.list_scroll,       "list")
        self.list_stack.add_named(self.empty_updates_page,"empty_updates")
        self.list_stack.add_named(self.empty_generic_page,"empty_generic")
        self.list_stack.set_visible_child_name("loading")
        panel.append(self.list_stack)

        action_bar = Gtk.ActionBar()
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
        self.detail_stack.set_transition_duration(180)

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
        self.detail_ver_badge  = Gtk.Label(label="1.0.0")
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
        for key in ["URL","Licenses","Groups","Depends On","Optional Deps",
                    "Conflicts With","Provides","Replaces",
                    "Installed Size","Packager","Build Date","Install Date","Install Reason"]:
            row = Adw.ActionRow(); row.set_title(key); row.set_subtitle("—")
            row.set_subtitle_selectable(True)
            info_group.add(row); self.info_rows[key] = row
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

        # Files tab
        files_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        files_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        files_hdr.set_margin_start(6); files_hdr.set_margin_end(6)
        files_hdr.set_margin_top(6);   files_hdr.set_margin_bottom(4)
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

    # ── Data loading ──────────────────────────────────────────────────────────

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
        self._apply_filter()
        return False

    def _update_sidebar_counts(self):
        total    = len(self._all_packages)
        foreign  = sum(1 for p in self._all_packages if p.get("foreign", False))
        installed = sum(1 for p in self._all_packages if p["status"] == "installed")
        self.stat_total._num.set_label(str(total))
        self.stat_aur._num.set_label(str(foreign))
        self._nav_rows["all"].set_count(total)
        self._nav_rows["installed"].set_count(installed)
        self._nav_rows["foreign"].set_count(foreign)

        seen_repos = set(p.get("repo", "local").lower() for p in self._all_packages
                         if p.get("repo", "local") != "local")
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
        filt  = self._current_filter
        for child in list(self.pkg_listbox):
            self.pkg_listbox.remove(child)
        shown = 0
        for pkg in self._all_packages:
            if query and query not in pkg["name"].lower() and query not in pkg.get("description","").lower():
                continue
            if filt == "installed" and pkg["status"] not in ("installed","update"):
                continue
            if filt == "foreign"   and not pkg.get("foreign", False):
                continue
            if filt == "updates"   and pkg.get("status") != "update":
                continue
            if filt == "orphans":
                continue
            if filt in ("core","extra","multilib") and pkg.get("repo","").lower() != filt:
                continue
            if filt == "aur_repo" and not pkg.get("foreign", False):
                continue
            item = PackageItem(pkg["name"], pkg["version"],
                               pkg.get("repo","local"), pkg["status"],
                               pkg.get("description",""), pkg.get("foreign",False))
            self.pkg_listbox.append(PackageRow(item))
            shown += 1
        total = len(self._all_packages)
        self.pkg_count_label.set_label(
            f"{shown} of {total} packages" if shown != total else f"{total} packages")
        if shown == 0:
            if filt == "updates":
                self.list_stack.set_visible_child_name(
                    "empty_updates" if self._updates is not None else "list")
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
        idx  = row.get_index()
        if idx < len(keys):
            key = keys[idx]
            if key == "orphans":
                self._on_show_orphans(); return
            self._current_filter = key
        self._update_action_bar_mode()
        self._apply_filter()

    def _on_repo_nav_selected(self, listbox, row):
        self.nav_listbox.unselect_all()
        keys = list(self._repo_nav_rows.keys())
        idx  = row.get_index()
        if idx < len(keys):
            self._current_filter = keys[idx]
        self._update_action_bar_mode()
        self._apply_filter()

    def _update_action_bar_mode(self):
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

    # ── Package detail ────────────────────────────────────────────────────────

    def _on_pkg_selected(self, listbox, row):
        if row is None: return
        pkg = row.pkg
        self._selected_pkg = pkg
        installed = pkg.pkg_status in ("installed","update")
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
        self.detail_repo_badge.add_css_class(REPO_BADGE_CLASS.get(repo_str,"badge-local"))
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
        for row in self.info_rows.values():
            row.set_subtitle(GLib.markup_escape_text("…"))
        self.raw_text.set_label("Loading…")
        for child in list(self.files_listbox):
            self.files_listbox.remove(child)
        self.files_count_lbl.set_label("Loading…")
        self._pkg_files_all = []

        def worker():
            info  = get_package_info(pkg.pkg_name)
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
            val = parsed.get(pk,"—") or "—"
            if val in ("None",""): val = "—"
            if rk in self.info_rows:
                self.info_rows[rk].set_subtitle(GLib.markup_escape_text(val))
        self.detail_arch_badge.set_label(parsed.get("Architecture","x86_64"))
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
            path  = parts[1] if len(parts) == 2 else line
            if q and q not in path.lower(): continue
            shown.append(path)
        for path in shown:
            row = Gtk.ListBoxRow(); row.set_activatable(False)
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

    def _run_terminal(self, cmd, title, on_success=None):
        def _on_done(code):
            toast = Adw.Toast()
            toast.set_title(
                f"✓ {title} completed" if code == 0 else f"✗ {title} failed (exit {code})")
            toast.set_timeout(4)
            try:
                self._toast_overlay.add_toast(toast)
            except AttributeError:
                pass
            self._load_packages()
        run_terminal_dialog(self, cmd, title,
                            on_success=on_success,
                            on_done_extra=_on_done)

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
        if not self._selected_pkg: return
        pkg = self._selected_pkg
        if pkg.pkg_foreign:
            helper = self._get_aur_helper()
            cmd = f"{helper} -S --noconfirm {pkg.pkg_name}" if helper \
                  else f"sudo -S pacman -Sy --noconfirm {pkg.pkg_name}"
        else:
            cmd = f"sudo -S pacman -Sy --noconfirm {pkg.pkg_name}"
        self._run_terminal(cmd, f"Install {pkg.pkg_name}",
                           on_success=self._refresh_selected_pkg)

    def _on_remove(self, *_):
        if not self._selected_pkg: return
        pkg = self._selected_pkg
        d = Adw.AlertDialog()
        d.set_heading(f"Remove {pkg.pkg_name}?")
        d.set_body(f"This will remove {pkg.pkg_name} ({pkg.pkg_version}) from your system.")
        d.add_response("cancel","Cancel"); d.add_response("remove","Remove")
        d.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        d.set_default_response("cancel"); d.set_close_response("cancel")
        def on_resp(d, resp):
            if resp == "remove":
                self._run_terminal(
                    f"sudo -S pacman -R --noconfirm {pkg.pkg_name}",
                    f"Remove {pkg.pkg_name}",
                    on_success=self._refresh_selected_pkg)
        d.connect("response", on_resp); d.present(self)

    def _on_reinstall(self, *_):
        if not self._selected_pkg: return
        pkg = self._selected_pkg
        if pkg.pkg_foreign:
            helper = self._get_aur_helper()
            cmd = f"{helper} -S --noconfirm {pkg.pkg_name}" if helper \
                  else f"sudo -S pacman -Sy --noconfirm {pkg.pkg_name}"
        else:
            cmd = f"sudo -S pacman -Sy --noconfirm {pkg.pkg_name}"
        self._run_terminal(cmd, f"Reinstall {pkg.pkg_name}",
                           on_success=self._refresh_selected_pkg)

    def _refresh_selected_pkg(self):
        if not self._selected_pkg: return
        pkg = self._selected_pkg
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
        for cls in ("status-installed","status-available","status-update","status-foreign"):
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
                GLib.idle_add(self._populate_detail, info, files)
            threading.Thread(target=worker, daemon=True).start()

    def _get_aur_helper(self):
        if not hasattr(self, '_aur_helper_cache'):
            self._aur_helper_cache = None
            for h in ("paru","yay","pikaur","trizen"):
                _, c = run_command(f"which {h} 2>/dev/null")
                if c == 0:
                    self._aur_helper_cache = h
                    break
        return self._aur_helper_cache
