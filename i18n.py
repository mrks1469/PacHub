"""Localisation support for PacHub."""

import gettext
import os

DOMAIN = "pachub"

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_LOCALEDIRS = (
    os.environ.get("PACHUB_LOCALEDIR"),
    os.path.join(_APP_DIR, "locale"),
    "/usr/local/share/locale",
    "/usr/share/locale",
)


def _load_translation():
    for localedir in _LOCALEDIRS:
        if not localedir:
            continue
        try:
            translation = gettext.translation(
                DOMAIN, localedir=localedir, fallback=True)
        except OSError:
            continue
        if isinstance(translation, gettext.GNUTranslations):
            return translation
    return gettext.NullTranslations()


_translation = _load_translation()
_ = _translation.gettext
ngettext = _translation.ngettext
