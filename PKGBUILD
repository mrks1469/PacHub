pkgname=pachub
pkgver=1.0.0
pkgrel=1
pkgdesc="Pacman and AUR front end built with GTK4 and libadwaita"
arch=('any')
url="https://github.com/mrks1469/PacHub"
license=('GPL2')
depends=('python' 'gtk4' 'libadwaita' 'python-gobject')
optdepends=(
  'yay: AUR helper support'
  'paru: AUR helper support'
)
source=(
  'app.py'
  'backend.py'
  'dialogs.py'
  'models.py'
  'styles.py'
  'window.py'
  'io.github.mrks1469.pachub.svg'
  'LICENSE'
)
sha256sums=('SKIP'
            'SKIP'
            'SKIP'
            'SKIP'
            'SKIP'
            'SKIP'
            'SKIP'
            'SKIP')

package() {
  local appdir="$pkgdir/usr/share/pachub"
  local desktop="$pkgdir/usr/share/applications/io.github.mrks1469.pachub.desktop"
  local launcher="$pkgdir/usr/bin/pachub"

  install -d "$appdir" \
             "$pkgdir/usr/bin" \
             "$pkgdir/usr/share/applications" \
             "$pkgdir/usr/share/icons/hicolor/scalable/apps" \
             "$pkgdir/usr/share/licenses/$pkgname"

  for file in app.py backend.py dialogs.py models.py styles.py window.py; do
    install -m 644 "$srcdir/$file" "$appdir/$file"
  done

  cat > "$launcher" <<'EOF'
#!/usr/bin/env bash
export PYTHONPATH="/usr/share/pachub:${PYTHONPATH:-}"
exec python3 /usr/share/pachub/app.py "$@"
EOF
  chmod 755 "$launcher"

  cat > "$desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=PacHub
GenericName=Package Manager
Comment=A powerful Pacman/AUR front end
Exec=/usr/bin/pachub
Icon=io.github.mrks1469.pachub
Categories=System;PackageManager;
Keywords=pacman;aur;packages;arch;
Terminal=false
StartupWMClass=pachub
EOF

  install -m 644 "$srcdir/io.github.mrks1469.pachub.svg" \
    "$pkgdir/usr/share/icons/hicolor/scalable/apps/io.github.mrks1469.pachub.svg"
  install -m 644 "$srcdir/LICENSE" "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
