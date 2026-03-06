#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
#  PacHub Installer
#  A powerful Pacman/AUR front end using GTK4 and libadwaita
#  https://github.com/mrks1469/PacHub
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}${BOLD}[·]${RESET} $*"; }
success() { echo -e "${GREEN}${BOLD}[✓]${RESET} $*"; }
warn()    { echo -e "${YELLOW}${BOLD}[!]${RESET} $*"; }
error()   { echo -e "${RED}${BOLD}[✗]${RESET} $*" >&2; }
die()     { error "$*"; exit 1; }

# ── Paths ─────────────────────────────────────────────────────────────────────
APP_NAME="pachub"
INSTALL_DIR="/usr/local/bin"
DATA_DIR="/usr/local/share/${APP_NAME}"
DESKTOP_DIR="/usr/share/applications"
ICON_DIR="/usr/share/icons/hicolor/scalable/apps"
ICON_ID="io.github.mrks1469.pachub"
DESKTOP_FILE="${DESKTOP_DIR}/${ICON_ID}.desktop"
SCRIPT_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/pachub.py"

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "
${BOLD}${CYAN}  
  ██████╗  █████╗  ██████╗██╗  ██╗██╗   ██╗██████╗
  ██╔══██╗██╔══██╗██╔════╝██║  ██║██║   ██║██╔══██╗
  ██████╔╝███████║██║     ███████║██║   ██║██████╔╝
  ██╔═══╝ ██╔══██║██║     ██╔══██║██║   ██║██╔══██╗
  ██║     ██║  ██║╚██████╗██║  ██║╚██████╔╝██████╔╝
  ╚═╝     ╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ${RESET}
  ${BOLD}Pacman/AUR Front End${RESET} — Installer v1.0.0
"

# ── Root check ────────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    warn "Not running as root — re-launching with sudo…"
    exec sudo bash "$0" "$@"
fi

# ── Arch Linux check ──────────────────────────────────────────────────────────
if ! command -v pacman &>/dev/null; then
    die "PacHub requires Arch Linux (pacman not found)."
fi

# ── Source file check ─────────────────────────────────────────────────────────
if [[ ! -f "$SCRIPT_SRC" ]]; then
    die "pachub.py not found next to this installer.\n   Expected: ${SCRIPT_SRC}"
fi

ICON_SRC_CHECK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/${ICON_ID}.svg"
if [[ ! -f "$ICON_SRC_CHECK" ]]; then
    die "${ICON_ID}.svg not found next to this installer.\n   Expected: ${ICON_SRC_CHECK}"
fi

# ─────────────────────────────────────────────────────────────────────────────
#  1. Dependencies
# ─────────────────────────────────────────────────────────────────────────────
info "Checking dependencies…"

REQUIRED_PKGS=(python gtk4 libadwaita python-gobject)
MISSING=()
for pkg in "${REQUIRED_PKGS[@]}"; do
    if ! pacman -Qi "$pkg" &>/dev/null; then
        MISSING+=("$pkg")
    fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
    warn "Installing missing packages: ${MISSING[*]}"
    pacman -Sy --noconfirm --needed "${MISSING[@]}" || die "Failed to install dependencies."
    success "Dependencies installed."
else
    success "All dependencies satisfied."
fi

# ─────────────────────────────────────────────────────────────────────────────
#  2. Install application
# ─────────────────────────────────────────────────────────────────────────────
info "Installing PacHub…"

# Data directory
install -d "$DATA_DIR"
install -m 644 "$SCRIPT_SRC" "${DATA_DIR}/pachub.py"

# Launcher wrapper in PATH
cat > "${INSTALL_DIR}/${APP_NAME}" <<'EOF'
#!/usr/bin/env bash
exec python3 /usr/local/share/pachub/pachub.py "$@"
EOF
chmod 755 "${INSTALL_DIR}/${APP_NAME}"

success "Installed to ${INSTALL_DIR}/${APP_NAME}"

# ─────────────────────────────────────────────────────────────────────────────
#  3. Desktop entry
# ─────────────────────────────────────────────────────────────────────────────
info "Creating desktop entry…"

install -d "$DESKTOP_DIR"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=PacHub
GenericName=Package Manager
Comment=A powerful Pacman/AUR front end
Exec=${INSTALL_DIR}/${APP_NAME}
Icon=${ICON_ID}
Categories=System;PackageManager;
Keywords=pacman;aur;packages;arch;
Terminal=false
StartupWMClass=pachub
EOF

success "Desktop entry created."

# ─────────────────────────────────────────────────────────────────────────────
#  4. Icon (SVG placeholder — replace with real asset if available)
# ─────────────────────────────────────────────────────────────────────────────
info "Installing icon…"

install -d "$ICON_DIR"
ICON_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/${ICON_ID}.svg"
ICON_FILE="${ICON_DIR}/${ICON_ID}.svg"

if [[ ! -f "$ICON_SRC" ]]; then
    die "Icon file not found next to this installer.\n   Expected: ${ICON_SRC}"
fi

install -m 644 "$ICON_SRC" "$ICON_FILE"

gtk-update-icon-cache -f -t /usr/share/icons/hicolor &>/dev/null || true
success "Icon installed."

# ─────────────────────────────────────────────────────────────────────────────
#  5. Update desktop database
# ─────────────────────────────────────────────────────────────────────────────
update-desktop-database "$DESKTOP_DIR" &>/dev/null || true

# ─────────────────────────────────────────────────────────────────────────────
#  Done
# ─────────────────────────────────────────────────────────────────────────────
echo
echo -e "${GREEN}${BOLD}  PacHub installed successfully!${RESET}"
echo -e "  Run from terminal : ${BOLD}pachub${RESET}"
echo -e "  Or launch from    : ${BOLD}Applications → System → PacHub${RESET}"
echo
