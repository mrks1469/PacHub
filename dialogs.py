"""
PacHub — dialogs.py
All modal tool dialogs:
  - TerminalDialog  : PTY-backed command runner with sudo password input
  - RepoManagerDialog : View/edit /etc/pacman.conf repositories
  - MirrorRaterDialog : rate-mirrors front end
  - OrphanFinderDialog: list and remove orphaned packages
  - SysInfoDialog     : system information overview
"""

import os
import pty
import re as _re
import select
import fcntl
import shlex
import shutil
import termios
import struct
import threading

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Pango

from backend import (
    get_orphans, get_system_info, is_safe_package_name, is_safe_repo_name,
    run_command,
)

_COUNTRY_RE = _re.compile(r"^[A-Za-z][A-Za-z .'-]{0,63}$")


def _display_cmd(cmd):
    return shlex.join(cmd) if isinstance(cmd, (list, tuple)) else cmd


def _editor_cmd(path):
    allowed = {"nano", "vim", "vi", "micro", "emacs"}
    raw = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano"
    try:
        parts = shlex.split(raw)
    except ValueError:
        parts = ["nano"]
    editor = parts[0] if parts else "nano"
    if os.path.basename(editor) not in allowed:
        editor = "nano"
        parts = [editor]
    return ["sudo", "-S", *parts, path]


# ─── Terminal dialog ──────────────────────────────────────────────────────────

def run_terminal_dialog(parent, cmd, title, on_success=None, on_done_extra=None):
    """
    Open a PTY-backed terminal dialog that runs *cmd*.
    Calls on_success() (on the main thread) if the command exits with code 0.
    """
    dialog = Adw.Dialog()
    dialog.set_title(title)
    dialog.set_content_width(720)
    dialog.set_content_height(520)
    dialog.set_follows_content_size(False)

    tv  = Adw.ToolbarView()
    hdr = Adw.HeaderBar()
    hdr.set_show_end_title_buttons(False)

    title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    spinner   = Gtk.Spinner()
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

    cmd_lbl = Gtk.Label(label=f"$ {_display_cmd(cmd)}")
    cmd_lbl.add_css_class("caption")
    cmd_lbl.add_css_class("dim-label")
    cmd_lbl.set_halign(Gtk.Align.START)
    cmd_lbl.set_ellipsize(Pango.EllipsizeMode.END)
    cmd_lbl.set_margin_start(14); cmd_lbl.set_margin_end(14)
    cmd_lbl.set_margin_top(6);    cmd_lbl.set_margin_bottom(4)
    tv.add_top_bar(cmd_lbl)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    outer.set_margin_top(8);    outer.set_margin_bottom(12)
    outer.set_margin_start(12); outer.set_margin_end(12)

    scroll = Gtk.ScrolledWindow()
    scroll.set_vexpand(True); scroll.set_hexpand(True)
    scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroll.add_css_class("card")

    term_buf  = Gtk.TextBuffer()
    term_view = Gtk.TextView(buffer=term_buf)
    term_view.set_editable(False)
    term_view.set_cursor_visible(False)
    term_view.set_wrap_mode(Gtk.WrapMode.CHAR)
    term_view.add_css_class("terminal-view")
    term_view.set_monospace(True)
    scroll.set_child(term_view)
    outer.append(scroll)

    # Password / stdin input row
    input_frame = Gtk.Frame()
    input_frame.add_css_class("card")
    input_frame.set_margin_top(2)

    input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    input_box.set_margin_top(8);    input_box.set_margin_bottom(8)
    input_box.set_margin_start(10); input_box.set_margin_end(10)

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
    dialog.present(parent)

    # ── Internal state ────────────────────────────────────────────────────────
    _master_fd = [None]
    _proc      = [None]
    _running   = [True]

    _ANSI = _re.compile(
        r'\x1b\[[0-9;?]*[ -/]*[@-~]'
        r'|\x1b[()][AB012]'
        r'|\x1b[^[]'
        r'|\x08'
        r'|\r'
    )

    def strip_ansi(s):
        s = s.replace('\r\n', '\n').replace('\r', '\n')
        return _ANSI.sub('', s)

    def append_output(raw_text):
        cleaned = strip_ansi(raw_text)
        if not cleaned:
            return False
        end_iter = term_buf.get_end_iter()
        term_buf.insert(end_iter, cleaned)
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
        cancel_btn.set_visible(False)
        close_btn.set_sensitive(True)
        close_btn.grab_focus()
        sep = "\n" + "─" * 56 + "\n"
        if code == 0:
            append_output(sep + "✓  Completed successfully\n")
        else:
            append_output(sep + f"✗  Failed  (exit code {code})\n")
        pw_entry.set_sensitive(False)
        send_btn.set_sensitive(False)
        if code == 0 and on_success:
            on_success()
        if on_done_extra:
            on_done_extra(code)
        return False

    # ── PTY worker ────────────────────────────────────────────────────────────
    def worker():
        master_fd, slave_fd = pty.openpty()
        _master_fd[0] = master_fd

        try:
            ws = struct.pack('HHHH', 40, 120, 0, 0)
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, ws)
        except Exception:
            pass

        env = dict(os.environ)
        env['TERM'] = 'xterm-256color'
        env.pop('SUDO_ASKPASS', None)

        try:
            import subprocess
            GLib.idle_add(append_output, f">>> {title}\n\n")
            if isinstance(cmd, str):
                raise TypeError("terminal commands must be argv lists")
            popen_cmd = cmd
            proc = subprocess.Popen(
                popen_cmd,
                stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                close_fds=True, preexec_fn=os.setsid, env=env,
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
                    try:
                        text = partial.decode('utf-8')
                        partial = b""
                    except UnicodeDecodeError:
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


# ─── Repository manager dialog ────────────────────────────────────────────────

def show_repo_manager(parent, run_terminal_fn):
    dialog = Adw.Dialog()
    dialog.set_title("Manage Repositories")
    dialog.set_content_width(640)
    dialog.set_content_height(500)

    tv  = Adw.ToolbarView()
    hdr = Adw.HeaderBar()
    hdr.set_show_end_title_buttons(False)

    edit_btn = Gtk.Button(label="Edit pacman.conf")
    edit_btn.add_css_class("suggested-action")
    edit_btn.connect("clicked", lambda *_: (
        dialog.close(),
        run_terminal_fn(_editor_cmd("/etc/pacman.conf"), "Edit pacman.conf")
    ))
    hdr.pack_end(edit_btn)

    close_btn = Gtk.Button(label="Close")
    close_btn.add_css_class("flat")
    close_btn.connect("clicked", lambda *_: dialog.close())
    hdr.pack_start(close_btn)
    tv.add_top_bar(hdr)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    outer.set_margin_top(12);   outer.set_margin_bottom(16)
    outer.set_margin_start(16); outer.set_margin_end(16)

    repos_group = Adw.PreferencesGroup()
    repos_group.set_title("Active Repositories")
    repos_group.set_description("Repositories currently enabled in /etc/pacman.conf")

    out, code = run_command(["pacman", "-Sl"])
    repo_counts = {}
    if out and code == 0:
        for line in out.splitlines():
            parts = line.split()
            if parts and is_safe_repo_name(parts[0]):
                repo_counts[parts[0]] = repo_counts.get(parts[0], 0) + 1
    repos = sorted(repo_counts) if repo_counts else ["core", "extra", "multilib"]

    for repo in repos:
        row = Adw.ActionRow()
        row.set_title(repo)
        icon = Gtk.Image.new_from_icon_name("folder-symbolic")
        icon.add_css_class("dim-label")
        row.add_prefix(icon)
        pkg_count = repo_counts.get(repo)
        if pkg_count is not None:
            count_lbl = Gtk.Label(label=f"{pkg_count} pkgs")
            count_lbl.add_css_class("caption"); count_lbl.add_css_class("dim-label")
            row.add_suffix(count_lbl)
        repos_group.add(row)
    outer.append(repos_group)

    conf_group = Adw.PreferencesGroup()
    conf_group.set_title("pacman.conf")
    conf_group.set_description("/etc/pacman.conf — read-only view")

    scroll = Gtk.ScrolledWindow()
    scroll.set_min_content_height(180)
    scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroll.add_css_class("card")

    try:
        with open("/etc/pacman.conf", "r") as f:
            conf_out = f.read()
    except Exception:
        conf_out = ""
    buf = Gtk.TextBuffer()
    buf.set_text(conf_out or "# /etc/pacman.conf not found or not readable")
    conf_view = Gtk.TextView(buffer=buf)
    conf_view.set_editable(False); conf_view.set_monospace(True)
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
    dialog.present(parent)


# ─── Mirror rater dialog ──────────────────────────────────────────────────────

def show_mirror_rater(parent, run_terminal_fn):
    dialog = Adw.Dialog()
    dialog.set_title("Rate Mirrors")
    dialog.set_content_width(600)
    dialog.set_content_height(560)

    tv  = Adw.ToolbarView()
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
    outer.set_margin_top(16);   outer.set_margin_bottom(24)
    outer.set_margin_start(16); outer.set_margin_end(16)

    has_rate_mirrors = shutil.which("rate-mirrors") is not None

    if has_rate_mirrors:
        options_group = Adw.PreferencesGroup()
        options_group.set_title("Mirror Options")
        options_group.set_description(
            "rate-mirrors tests all Arch mirrors and saves the fastest to /etc/pacman.d/mirrorlist"
        )

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
        for _, label in sort_options:
            sort_store.append(label)
        sort_drop = Gtk.DropDown(model=sort_store)
        sort_drop.set_selected(0)
        sort_drop.set_valign(Gtk.Align.CENTER)
        sort_row.add_suffix(sort_drop)
        options_group.add(sort_row)

        protocol_row = Adw.ActionRow()
        protocol_row.set_title("HTTPS only")
        protocol_row.set_subtitle("Filter out plain HTTP mirrors")
        https_switch = Gtk.Switch()
        https_switch.set_active(True)
        https_switch.set_valign(Gtk.Align.CENTER)
        protocol_row.add_suffix(https_switch)
        protocol_row.set_activatable_widget(https_switch)
        options_group.add(protocol_row)

        backup_row = Adw.ActionRow()
        backup_row.set_title("Backup current mirrorlist")
        backup_row.set_subtitle("Saves existing list to mirrorlist-backup first")
        backup_switch = Gtk.Switch()
        backup_switch.set_active(True)
        backup_switch.set_valign(Gtk.Align.CENTER)
        backup_row.add_suffix(backup_switch)
        backup_row.set_activatable_widget(backup_switch)
        options_group.add(backup_row)

        delay_row = Adw.ActionRow()
        delay_row.set_title("Max mirror delay (hours)")
        delay_row.set_subtitle("Skip mirrors that are behind by more than this")
        delay_spin = Gtk.SpinButton()
        delay_spin.set_range(1, 72); delay_spin.set_increments(1, 6); delay_spin.set_value(6)
        delay_spin.set_valign(Gtk.Align.CENTER)
        delay_row.add_suffix(delay_spin)
        options_group.add(delay_row)

        top_row = Adw.ActionRow()
        top_row.set_title("Number of mirrors to keep")
        top_row.set_subtitle("0 = keep all ranked mirrors")
        top_spin = Gtk.SpinButton()
        top_spin.set_range(0, 50); top_spin.set_increments(1, 5); top_spin.set_value(0)
        top_spin.set_valign(Gtk.Align.CENTER)
        top_row.add_suffix(top_spin)
        options_group.add(top_row)

        outer.append(options_group)

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

            global_flags = []
            if https_only:
                global_flags.append(shlex.quote("--protocol=https"))
            if top_n > 0:
                global_flags.append(shlex.quote(f"--top-mirrors={top_n}"))
            if countries_raw:
                first = countries_raw.split(",")[0].strip()
                if not _COUNTRY_RE.fullmatch(first):
                    country_entry.add_css_class("error")
                    return
                country_entry.remove_css_class("error")
                global_flags.append(shlex.quote(f"--entry-country={first}"))

            sub_flags = [
                shlex.quote(f"--sort-mirrors-by={sort_key}"),
                shlex.quote(f"--max-delay={max_delay}"),
            ]
            gf = " ".join(global_flags)
            sf = " ".join(sub_flags)

            if backup:
                script = (
                    f'sudo -S -v && '
                    f'TMPFILE="$(mktemp)" && '
                    f'rate-mirrors {gf} --save="$TMPFILE" arch {sf} '
                    f'&& sudo mv /etc/pacman.d/mirrorlist /etc/pacman.d/mirrorlist-backup '
                    f'&& sudo mv "$TMPFILE" /etc/pacman.d/mirrorlist '
                    f'&& echo "Done — backup saved to /etc/pacman.d/mirrorlist-backup"'
                )
            else:
                script = (
                    f'sudo -S -v && '
                    f'rate-mirrors {gf} arch {sf} '
                    f'| sudo tee /etc/pacman.d/mirrorlist > /dev/null '
                    f'&& echo "Done — /etc/pacman.d/mirrorlist updated"'
                )
            cmd = ["sh", "-c", script]

            dialog.close()
            run_terminal_fn(cmd, "Rate Mirrors")

        run_btn.connect("clicked", on_run)
        outer.append(run_btn)

        preview_lbl = Gtk.Label()
        preview_lbl.add_css_class("caption"); preview_lbl.add_css_class("dim-label")
        preview_lbl.set_wrap(True); preview_lbl.set_wrap_mode(Pango.WrapMode.CHAR)
        preview_lbl.set_selectable(True); preview_lbl.set_halign(Gtk.Align.CENTER)

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
                if _COUNTRY_RE.fullmatch(first):
                    country_entry.remove_css_class("error")
                    gflags.append(f"--entry-country={first}")
                else:
                    country_entry.add_css_class("error")
                    gflags.append("--entry-country=<invalid>")
            sflags = [f"--sort-mirrors-by={sort_key}", f"--max-delay={max_delay}"]
            preview_lbl.set_label(
                f"rate-mirrors {' '.join(gflags)} arch {' '.join(sflags)} | sudo tee /etc/pacman.d/mirrorlist"
            )

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
            run_terminal_fn(["sudo", "-S", "pacman", "-S", "rate-mirrors"], "Install rate-mirrors")
        ))
        status.set_child(install_btn)
        outer.append(status)

    scroll.set_child(outer)
    tv.set_content(scroll)
    dialog.set_child(tv)
    dialog.present(parent)


# ─── Orphan finder dialog ─────────────────────────────────────────────────────

def show_orphan_finder(parent, run_terminal_fn):
    dialog = Adw.Dialog()
    dialog.set_title("Orphaned Packages")
    dialog.set_content_width(560)
    dialog.set_content_height(460)

    tv  = Adw.ToolbarView()
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
        status = Adw.StatusPage()
        status.set_icon_name("emblem-ok-symbolic")
        status.set_title("No Orphans Found")
        status.set_description("Your system has no orphaned packages.")
        status.set_vexpand(True)
        outer.append(status)
    else:
        info_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        info_bar.set_margin_start(16); info_bar.set_margin_end(16)
        info_bar.set_margin_top(12);   info_bar.set_margin_bottom(8)
        info_icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
        info_icon.set_pixel_size(16)
        info_bar.append(info_icon)
        info_lbl = Gtk.Label(
            label=f"{len(orphans)} orphaned package(s) — installed as dependencies but no longer required"
        )
        info_lbl.add_css_class("caption")
        info_lbl.set_hexpand(True); info_lbl.set_halign(Gtk.Align.START); info_lbl.set_wrap(True)
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
            row.set_title(o["name"]); row.set_subtitle(o["version"])
            icon = Gtk.Image.new_from_icon_name("package-x-generic-symbolic")
            icon.add_css_class("dim-label")
            row.add_prefix(icon)
            rm_btn = Gtk.Button(label="Remove")
            rm_btn.add_css_class("destructive-action"); rm_btn.add_css_class("flat")
            rm_btn.set_valign(Gtk.Align.CENTER)
            name = o["name"]
            if not is_safe_package_name(name):
                rm_btn.set_sensitive(False)
            rm_btn.connect("clicked", lambda *_, n=name: (
                dialog.close(),
                run_terminal_fn(["sudo", "-S", "pacman", "-R", n], f"Remove {n}")
                if is_safe_package_name(n) else None
            ))
            row.add_suffix(rm_btn)
            listbox.append(row)

        scroll.set_child(listbox)
        outer.append(scroll)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.CENTER)
        btn_box.set_margin_top(12); btn_box.set_margin_bottom(16)
        names = [o["name"] for o in orphans if is_safe_package_name(o["name"])]
        remove_all_btn = Gtk.Button(label=f"Remove All {len(orphans)} Orphans")
        remove_all_btn.add_css_class("destructive-action")
        remove_all_btn.set_sensitive(len(names) == len(orphans))
        remove_all_btn.connect("clicked", lambda *_: (
            dialog.close(),
            run_terminal_fn(["sudo", "-S", "pacman", "-Rns", *names], "Remove All Orphans")
        ))
        btn_box.append(remove_all_btn)
        outer.append(btn_box)

    tv.set_content(outer)
    dialog.set_child(tv)
    dialog.present(parent)


# ─── System info dialog ───────────────────────────────────────────────────────

def show_sysinfo_dialog(parent):
    dialog = Adw.Dialog()
    dialog.set_title("System Information")
    dialog.set_content_width(520)
    dialog.set_content_height(520)

    tv  = Adw.ToolbarView()
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
    outer.set_margin_top(16);   outer.set_margin_bottom(24)
    outer.set_margin_start(16); outer.set_margin_end(16)

    loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    loading_box.set_halign(Gtk.Align.CENTER); loading_box.set_valign(Gtk.Align.CENTER)
    loading_box.set_vexpand(True)
    loading_spinner = Gtk.Spinner()
    loading_spinner.start(); loading_spinner.set_size_request(32, 32)
    loading_spinner.set_halign(Gtk.Align.CENTER)
    loading_box.append(loading_spinner)
    loading_lbl = Gtk.Label(label="Gathering system info…")
    loading_lbl.add_css_class("dim-label")
    loading_box.append(loading_lbl)
    outer.append(loading_box)

    scroll.set_child(outer)
    tv.set_content(scroll)
    dialog.set_child(tv)
    dialog.present(parent)

    def populate(info):
        outer.remove(loading_box)

        sys_group = Adw.PreferencesGroup()
        sys_group.set_title("System")
        for key in ("OS", "Kernel", "Architecture"):
            if key in info:
                row = Adw.ActionRow(); row.set_title(key)
                val_lbl = Gtk.Label(label=info[key])
                val_lbl.add_css_class("caption"); val_lbl.add_css_class("dim-label")
                val_lbl.set_selectable(True)
                row.add_suffix(val_lbl)
                sys_group.add(row)
        outer.append(sys_group)

        hw_group = Adw.PreferencesGroup()
        hw_group.set_title("Hardware")
        for key in ("RAM", "Disk (/)"):
            if key in info:
                row = Adw.ActionRow(); row.set_title(key)
                val_lbl = Gtk.Label(label=info[key])
                val_lbl.add_css_class("caption"); val_lbl.add_css_class("dim-label")
                val_lbl.set_selectable(True)
                row.add_suffix(val_lbl)
                hw_group.add(row)
        outer.append(hw_group)

        pkg_group = Adw.PreferencesGroup()
        pkg_group.set_title("Packages")
        for key in ("Pacman", "Installed Packages", "Foreign (AUR) Packages", "Package Cache Size"):
            if key in info:
                row = Adw.ActionRow(); row.set_title(key)
                val_lbl = Gtk.Label(label=info[key])
                val_lbl.add_css_class("caption"); val_lbl.add_css_class("dim-label")
                val_lbl.set_selectable(True)
                row.add_suffix(val_lbl)
                pkg_group.add(row)
        outer.append(pkg_group)
        return False

    def worker():
        info = get_system_info()
        GLib.idle_add(populate, info)

    threading.Thread(target=worker, daemon=True).start()
