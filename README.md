<h1>PacHub</h1>
  <p>A powerful Pacman & AUR front end built with GTK4 and libadwaita</p>

  ![Arch Linux](https://img.shields.io/badge/Arch_Linux-1793D1?style=flat&logo=arch-linux&logoColor=white)
  ![Python](https://img.shields.io/badge/Python-3.x-3584e4?style=flat&logo=python&logoColor=white)
  ![GTK4](https://img.shields.io/badge/GTK-4.0-4a86c8?style=flat)
  ![libadwaita](https://img.shields.io/badge/libadwaita-1.x-9141ac?style=flat)
  ![License](https://img.shields.io/badge/License-GPL--2.0-green?style=flat)
</div>

<img width="1660" height="1057" alt="Screenshot" src="https://github.com/user-attachments/assets/de7717cc-620b-425b-9171-f2e00a7f8762" />
<img width="1660" height="1057" alt="Screenshot-1" src="https://github.com/user-attachments/assets/336f31c4-3e7a-469d-a29a-d0b3f5b80ff5" />

---

PacHub is a native GTK4 graphical front end for `pacman` and AUR helpers. It follows the GNOME Human Interface Guidelines via libadwaita, giving you a clean and modern way to browse, search, install, and manage packages on Arch Linux — without ever opening a terminal.

## Features

**Package management**
- Browse all installed packages with live search and per-repository filtering
- Install packages from official repos (core, extra, multilib) and the AUR
- Uninstall packages with a single click
- One-click full system upgrade (`pacman -Syu`)
- Automatic AUR support via `yay` or `paru` if either is installed

**Package detail panel**
- Full package info (`pacman -Qi` / `-Si`) shown inline
- Installed file list per package
- Colour-coded repository badges (CORE · EXTRA · AUR · MULTILIB · LOCAL)
- Status pills showing installed / available / needs update / foreign state

**Sidebar at a glance**
- Live stat cards showing total packages, AUR count, and pending update count
- Browse filters: All Packages · Installed · AUR / Foreign · Updates
- Per-repository navigation with package counts
- Quick-access tools panel

**Tools**
- Sync databases (`pacman -Sy`)
- Check for updates (`checkupdates` or `pacman -Qu`)
- Rate and select the fastest mirrors
- Find and remove orphaned packages (`pacman -Qdt`)
- Clean the package cache (`pacman -Sc`)
- Manage `/etc/pacman.conf` repositories
- System info overview (kernel, RAM, disk, cache size, package counts)

**UI / UX**
- Built on GTK4 + libadwaita — follows your system light/dark theme
- Embedded PTY terminal for live command output with password prompt support
- Update banner notification when pending upgrades are detected
- Toast notifications on operation completion
- Responsive split-view layout (resizable list + detail pane)
- Graceful demo mode when run outside Arch Linux



## Requirements

| Dependency | Package |
|---|---|
| Python 3.x | `python` |
| GTK 4 | `gtk4` |
| libadwaita 1.x | `libadwaita` |
| Python GObject bindings | `python-gobject` |

Optional (for AUR search and install):

| AUR Helper | Package |
|---|---|
| yay | `yay` _(AUR)_ |
| paru | `paru` _(AUR)_ |

## Installation

Place the repository files in the same directory, then run:

```bash
chmod +x install.sh
./install.sh
```

The installer will:
1. Check for and install any missing dependencies via `pacman`
2. Copy `application files` to `/usr/local/share/pachub/`
3. Create a `/usr/local/bin/pachub` launcher
4. Install the application icon
5. Register a `.desktop` entry so PacHub appears in your app launcher

**Files required alongside `install.sh`:**
```
install.sh
app.py
backend.py
dialogs.py
models.py
styles.py
window.py
io.github.mrks1469.pachub.svg
```

### Build a local pacman package

This repository now includes a `PKGBUILD`, so you can build and install PacHub with:

```bash
makepkg -si
```

### Running without installing

```bash
python3 app.py
```

## Usage

Launch from your application menu under **System → PacHub**, or run from a terminal:

```bash
pachub
```

**Basic workflow:**
- Use the **sidebar** to filter by category or repository
- Use the **search bar** to find any package by name or description
- Click a package row to view its full details in the right panel
- Use **Install** / **Uninstall** buttons in the action bar
- Click the **↑ upgrade** button in the toolbar for a full system upgrade
- Access tools like mirror rating, orphan cleanup, and cache cleaning from the **☰ menu**

## Project Structure

```
app.py                           # Application entry point
backend.py                       # Package and system data helpers
dialogs.py                       # Modal dialogs and terminal UI
models.py                        # Package row and model types
styles.py                        # Shared UI styling
window.py                        # Main application window
io.github.mrks1469.pachub.svg    # Application icon
install.sh                       # Installer script
PKGBUILD                         # Local pacman package definition
```

## License

PacHub is licensed under the **GNU General Public License v2.0**. See the [GPL-2.0 license](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html) for details.

## Author

**Manpreet Singh** — [github.com/mrks1469](https://github.com/mrks1469)

- Homepage: [github.com/mrks1469/PacHub](https://github.com/mrks1469/PacHub)
- Bug reports: [github.com/mrks1469/PacHub/issues](https://github.com/mrks1469/PacHub/issues)


[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://buymeacoffee.com/mrks0001)
