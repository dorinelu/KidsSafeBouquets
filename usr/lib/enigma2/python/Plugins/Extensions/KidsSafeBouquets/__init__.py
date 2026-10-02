# -*- coding: utf-8 -*-
from __future__ import print_function

import gettext

DOMAIN = "KidsSafeBouquets"
LOCALE_PATH = "Extensions/KidsSafeBouquets/locale"

try:
    from Components.Language import language
    from Tools.Directories import resolveFilename, SCOPE_PLUGINS

    def localeInit():
        gettext.bindtextdomain(DOMAIN, resolveFilename(SCOPE_PLUGINS, LOCALE_PATH))

    localeInit()
    language.addCallback(localeInit)
except Exception:
    pass


def _(txt):
    try:
        translated = gettext.dgettext(DOMAIN, txt)
        if translated:
            return translated
    except Exception:
        pass
    return txt
