# Translations

PacHub uses gettext. `pachub.pot` is the source catalog and `es.po` holds the
Spanish translation.

## Update the catalog

From the repository root:

```sh
xgettext --language=Python --from-code=UTF-8 --add-comments=Translators: \
    --package-name=PacHub --package-version=1.0.0 \
    --msgid-bugs-address=https://github.com/mrks1469/PacHub/issues \
    --keyword=_ --keyword=ngettext:1,2 \
    -o po/pachub.pot app.py backend.py dialogs.py i18n.py models.py styles.py window.py
msgmerge --update po/es.po po/pachub.pot
```

## Compile a translation

```sh
msgfmt -c -o locale/es/LC_MESSAGES/pachub.mo po/es.po
```

Compiled `.mo` files are committed so that `python3 app.py` picks up the
translation without a build step. Run the command above after editing a `.po`
file.

`i18n.py` looks for catalogs in `PACHUB_LOCALEDIR`, the application directory,
`/usr/local/share/locale` and `/usr/share/locale`.
