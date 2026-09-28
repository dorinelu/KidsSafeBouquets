# -*- coding: utf-8 -*-
from __future__ import print_function

import glob
import os
import re
import tarfile
import time
import unicodedata

from enigma import eDVBDB, eServiceCenter, eServiceReference, getPrevAsciiCode
from Components.ActionMap import ActionMap, NumberActionMap
from Components.ConfigList import ConfigListScreen
from Components.Label import Label
from Components.Input import Input
from Components.MenuList import MenuList
from Components.ScrollLabel import ScrollLabel
from Components.Sources.StaticText import StaticText
from Components.config import config, configfile, ConfigSubsection, ConfigYesNo, getConfigListEntry
from Plugins.Plugin import PluginDescriptor
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen

PLUGIN_NAME = "KidsSafe Bouquets"
PLUGIN_VERSION = "1.5"
ENIGMA2_DIR = "/etc/enigma2"
CUSTOM_BLACKLIST = os.path.join(ENIGMA2_DIR, "kidssafe_blacklist.txt")
CUSTOM_WHITELIST = os.path.join(ENIGMA2_DIR, "kidssafe_whitelist.txt")
HIDDEN_REFS_FILE = os.path.join(ENIGMA2_DIR, "kidssafe_hidden_refs.txt")
BACKUP_DIR = os.path.join(ENIGMA2_DIR, "kidssafe_backup")

# Aggressive family-safety rules. Whitelist always wins.
# These terms are used for complete bouquets AND for section/marker headings.
# The goal is intentionally strict: explicit adult/erotic headings in many languages
# cause the whole section to be removed, not only individually matched channels.
BUILTIN_BOUQUET_WORDS = [
    # Generic / English
    "xxx", "adult", "adults", "adult only", "adults only", "18+", "18 +",
    "21+", "21 +", "erotic", "erotica", "erotics", "porn", "porno",
    "pornography", "x-rated", "x rated", "hardcore", "sex", "sexy",
    "sex channels", "sex tv", "mature", "nude", "nudes", "naked",

    # German
    "erotik", "erotische", "erwachsene", "erwachsenen", "nackt",
    "nur fur erwachsene", "nur für erwachsene",

    # Polish
    "erotyczny", "erotyczne", "erotyczna", "erotyka",
    "dla doroslych", "dla dorosłych",

    # French
    "adulte", "adultes", "erotique", "érotique", "erotiques", "érotiques",
    "pour adultes",

    # Italian
    "adulti", "erotico", "erotici", "erotica",

    # Spanish / Portuguese
    "adultos", "adultas", "erotico", "erótico", "erotica", "erótica",
    "para adultos", "conteudo adulto", "conteúdo adulto",

    # Dutch / Flemish
    "volwassen", "volwassenen", "erotiek",

    # Romanian
    "adulti", "adulți", "erotic", "erotice",

    # Hungarian
    "felnott", "felnőtt", "erotika",

    # Czech / Slovak
    "dospeli", "dospělí", "dospeli", "dospelí", "erotika",

    # Croatian / Serbian / Bosnian / Slovenian
    "odrasli", "erotski", "erotika",

    # Turkish
    "yetiskin", "yetişkin", "erotik",

    # Greek
    "ενηλικ", "ερωτικ",

    # Russian / Ukrainian / Bulgarian
    "для взрослых", "эротика", "эротические", "для дорослих", "еротика",
    "възрастни", "еротика",

    # Scandinavian
    "vuxen", "vuxna", "erotik", "voksen", "voksne", "aikuis",

    # Other common labels
    "playboy", "brazzers", "dorcel", "hustler", "penthouse", "redlight",
]

BUILTIN_CHANNEL_WORDS = [
    "brazzers", "dorcel", "hustler", "penthouse", "redlight",
    "playboy", "vivid", "private spice", "private tv", "passionxxx",
    "passion xxx", "erox", "erox hd", "erotic tv", "xxx tv",
    "adult channel", "hot club", "hot tv", "lust", "extasy",
    "exxxotica", "vixen", "superone", "super one", "sct",
    "pink x", "pink erotic", "leo tv", "dusk", "blue hustler",
    "hustler tv", "dorcel xxx", "penthouse gold", "penthouse quickies",
    "babes tv", "babestation", "xpanded", "television x", "tvx",
    "free x", "freex", "sexysat", "sexy sat", "desire tv",
]

# OpenATV/OpenBH TV service filter used by the native "All" view.
TV_SERVICE_ROOT = (
    "1:7:1:0:0:0:0:0:0:0:(type == 1) || (type == 17) || "
    "(type == 22) || (type == 25) || (type == 134) || (type == 195) ORDER BY name"
)

if not hasattr(config.plugins, "kidssafebouquets"):
    config.plugins.kidssafebouquets = ConfigSubsection()

config.plugins.kidssafebouquets.use_builtin = ConfigYesNo(default=True)
config.plugins.kidssafebouquets.remove_adult_bouquets = ConfigYesNo(default=True)
config.plugins.kidssafebouquets.scan_channels = ConfigYesNo(default=True)
config.plugins.kidssafebouquets.strict_hide = ConfigYesNo(default=True)
config.plugins.kidssafebouquets.use_parental_control = ConfigYesNo(default=True)
config.plugins.kidssafebouquets.make_backup = ConfigYesNo(default=True)


def log(msg):
    print("[KidsSafeBouquets] %s" % msg)


def normalized(text):
    if text is None:
        return ""
    try:
        text = str(text)
    except Exception:
        return ""
    text = text.replace("\u0086", "").replace("\u0087", "")
    text = text.lower()
    # Accent-insensitive matching helps with Polish/French/Romanian/etc. settings.
    try:
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
    except Exception:
        pass
    # Characters that are not decomposed by NFKD.
    text = (text.replace("ł", "l").replace("ø", "o").replace("đ", "d")
                .replace("ð", "d").replace("þ", "th").replace("ı", "i"))
    text = re.sub(r"[\t\r\n]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def read_terms(path):
