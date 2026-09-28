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
    terms = []
    try:
        with open(path, "r") as handle:
            for raw in handle:
                item = raw.strip()
                if item and not item.startswith("#"):
                    terms.append(item)
    except IOError:
        pass
    return terms


def write_terms(path, items):
    unique = []
    seen = set()
    for item in items:
        item = item.strip()
        key = normalized(item)
        if item and key not in seen:
            unique.append(item)
            seen.add(key)
    with open(path, "w") as handle:
        for item in sorted(unique, key=lambda x: normalized(x)):
            handle.write(item + "\n")


def contains_any(name, terms):
    value = normalized(name)
    if not value:
        return False, None
    for term in terms:
        needle = normalized(term)
        if not needle:
            continue
        # Very short words (for example "sex" or "sct") are matched as tokens
        # to avoid accidental hits inside unrelated longer words.
        if len(needle) <= 3 and re.match(r"^[a-z0-9]+$", needle):
            if re.search(r"(^|[^a-z0-9])%s($|[^a-z0-9])" % re.escape(needle), value):
                return True, term
        elif needle in value:
            return True, term
    return False, None


def ref_string(ref):
    try:
        return ref.toString()
    except Exception:
        return str(ref)


def compare_ref_string(ref):
    try:
        return ref.toCompareString()
    except Exception:
        value = ref_string(ref)
        return value


def service_name(service_center, ref):
    try:
        info = service_center.info(ref)
        if info:
            name = info.getName(ref)
            if name:
                return name
    except Exception:
        pass
    return ref_string(ref)


def bouquet_root():
    return eServiceReference('1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "bouquets.tv" ORDER BY bouquet')


def all_tv_root():
    return eServiceReference(TV_SERVICE_ROOT)


def is_marker(ref):
    value = ref_string(ref)
    return value.startswith("1:64:") or value.startswith("1:832:")


def bouquet_filename_from_ref(ref):
    value = ref_string(ref)
    match = re.search(r'FROM BOUQUET "([^"]+)"', value, re.IGNORECASE)
    if not match:
        return None
    name = os.path.basename(match.group(1))
    if not name.startswith("userbouquet."):
        return None
    return os.path.join(ENIGMA2_DIR, name)


def marker_title_from_ref(ref, service_center=None):
    name = ""
    if service_center is not None:
        name = service_name(service_center, ref)
    value = ref_string(ref)
    # Marker labels are commonly stored after a double colon.
    if (not name or name == value) and "::" in value:
        name = value.split("::", 1)[1]
    return name or value


def is_marker_service_line(line):
    if not line.startswith("#SERVICE "):
        return False
    value = line[len("#SERVICE "):].strip()
    return value.startswith("1:64:") or value.startswith("1:832:")


def marker_title_from_lines(lines, index):
    line = lines[index].strip()
    value = line[len("#SERVICE "):].strip() if line.startswith("#SERVICE ") else line
    title = ""
    if "::" in value:
        title = value.split("::", 1)[1].strip()
    # Some settings keep the visible marker text only in #DESCRIPTION.
    if index + 1 < len(lines) and lines[index + 1].startswith("#DESCRIPTION "):
        desc = lines[index + 1][len("#DESCRIPTION "):].strip()
        if desc:
            title = desc
    return title


def scan_adult_sections_file(path, bouquet_ref, bouquet_name, bouquet_words, whitelist):
    sections = []
    if not path or not os.path.isfile(path):
        return sections
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            lines = handle.readlines()
    except TypeError:
        # Python 2 fallback for older Enigma2 images.
        with open(path, "r") as handle:
            lines = handle.readlines()
    except Exception as err:
        log("Could not read %s: %s" % (path, err))
        return sections

    markers = [idx for idx, line in enumerate(lines) if is_marker_service_line(line)]
    for pos, start in enumerate(markers):
        end = markers[pos + 1] if pos + 1 < len(markers) else len(lines)
        title = marker_title_from_lines(lines, start)
        white, _ = contains_any(title, whitelist)
        bad, matched = contains_any(title, bouquet_words)
        if not bad or white:
            continue
        service_refs = []
        for line in lines[start:end]:
            if line.startswith("#SERVICE ") and not is_marker_service_line(line):
                raw_ref = line[len("#SERVICE "):].strip()
                if raw_ref:
                    service_refs.append(raw_ref)
        sections.append({
            "bouquet_ref": bouquet_ref,
            "bouquet_name": bouquet_name,
            "file": path,
            "start": start,
            "end": end,
            "title": title,
            "rule": matched,
            "count": len(service_refs),
            "service_refs": service_refs,
        })
    return sections


def remove_sections_from_files(sections, skip_bouquet_refs=None):
    skip_bouquet_refs = set(skip_bouquet_refs or [])
    grouped = {}
    for item in sections:
        if item.get("bouquet_ref") in skip_bouquet_refs:
            continue
        grouped.setdefault(item["file"], []).append(item)

    removed_sections = 0
    removed_services = 0
    failures = []
    for path, items in grouped.items():
        try:
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                    lines = handle.readlines()
            except TypeError:
                with open(path, "r") as handle:
                    lines = handle.readlines()

            # Delete from bottom to top so stored line ranges stay valid.
            for item in sorted(items, key=lambda x: x["start"], reverse=True):
                start = max(0, int(item["start"]))
                end = min(len(lines), int(item["end"]))
                if start >= end:
                    continue
                del lines[start:end]
                removed_sections += 1
                removed_services += int(item.get("count", 0))

            tmp = path + ".kidssafe.tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as handle:
                    handle.writelines(lines)
            except TypeError:
                with open(tmp, "w") as handle:
                    handle.writelines(lines)
            os.rename(tmp, path)
        except Exception as err:
            failures.append("Section cleanup %s: %s" % (os.path.basename(path), err))
            try:
                tmp = path + ".kidssafe.tmp"
                if os.path.exists(tmp):
                    os.unlink(tmp)
            except Exception:
                pass
    return removed_sections, removed_services, failures


def build_rule_sets():
    # V1.5 intentionally uses only the built-in aggressive family-safety rules.
    # Custom blacklist/whitelist editors were removed for maximum stability and simplicity.
    return list(BUILTIN_BOUQUET_WORDS), list(BUILTIN_CHANNEL_WORDS), []


def scan_bouquets():
    service_center = eServiceCenter.getInstance()
    root_list = service_center.list(bouquet_root())
    if not root_list:
        return {"bouquets": [], "sections": [], "channels": [], "errors": ["Could not open bouquets.tv"]}

    try:
        bouquet_refs = root_list.getContent("R", True) or []
    except Exception as err:
        return {"bouquets": [], "sections": [], "channels": [], "errors": ["Could not enumerate bouquets: %s" % err]}

    bouquet_words, channel_words, whitelist = build_rule_sets()
    result = {"bouquets": [], "sections": [], "channels": [], "errors": []}

    for bref in bouquet_refs:
        bref_value = ref_string(bref)
        bname = service_name(service_center, bref)
        white, _ = contains_any(bname, whitelist)
        bad_bouquet, matched = contains_any(bname, bouquet_words)

        if bad_bouquet and not white:
            service_refs = []
            try:
                blist = service_center.list(bref)
                if blist:
                    items = blist.getContent("R", True) or []
                    service_refs = [ref_string(x) for x in items if not is_marker(x)]
            except Exception:
                pass
            result["bouquets"].append({
                "ref": bref_value, "name": bname, "rule": matched,
                "count": len(service_refs), "service_refs": service_refs,
            })
            continue

        # V1.2: inspect marker/section headings in the actual userbouquet file.
        # If a heading is adult/erotic, the whole block is removed up to the next marker.
        bpath = bouquet_filename_from_ref(bref)
        sections = scan_adult_sections_file(bpath, bref_value, bname, bouquet_words, whitelist)
        result["sections"].extend(sections)

        try:
            blist = service_center.list(bref)
            services = blist.getContent("R", True) if blist else []
        except Exception as err:
            result["errors"].append("%s: %s" % (bname, err))
            continue

        # Avoid listing individual matches from inside a section that will be removed wholesale.
        in_bad_section = False
        for sref in services or []:
            if is_marker(sref):
                marker_name = marker_title_from_ref(sref, service_center)
                mwhite, _ = contains_any(marker_name, whitelist)
                mbad, _ = contains_any(marker_name, bouquet_words)
                in_bad_section = bool(mbad and not mwhite)
                continue
            if in_bad_section:
                continue
            sname = service_name(service_center, sref)
            white, _ = contains_any(sname, whitelist)
            if white:
                continue
            bad_channel, matched = contains_any(sname, channel_words)
            if bad_channel:
                result["channels"].append({
                    "bouquet_ref": bref_value,
                    "bouquet_name": bname,
                    "service_ref": ref_string(sref),
                    "service_name": sname,
                    "rule": matched,
                })
    return result


