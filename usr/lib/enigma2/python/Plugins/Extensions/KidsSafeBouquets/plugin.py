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

from . import _

PLUGIN_NAME = "KidsSafe Bouquets"
PLUGIN_VERSION = "1.6"
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


def scan_all_services():
    """Scan the same global TV service namespace used by Enigma2's All view."""
    service_center = eServiceCenter.getInstance()
    result = {"services": [], "errors": []}
    _, channel_words, whitelist = build_rule_sets()
    root = all_tv_root()
    try:
        listing = service_center.list(root)
        services = listing.getContent("R", True) if listing else []
    except Exception as err:
        result["errors"].append("Could not scan All services: %s" % err)
        return result

    seen = set()
    for sref in services or []:
        if is_marker(sref):
            continue
        sname = service_name(service_center, sref)
        white, _ = contains_any(sname, whitelist)
        if white:
            continue
        bad, matched = contains_any(sname, channel_words)
        if not bad:
            continue
        compare = compare_ref_string(sref)
        if compare in seen:
            continue
        seen.add(compare)
        result["services"].append({
            "service_ref": ref_string(sref),
            "compare_ref": compare,
            "service_name": sname,
            "rule": matched,
        })
    return result


def services_from_adult_containers(bouquets, sections):
    """Return every service inside a matched adult bouquet/section for global hiding.

    This is intentionally stronger than name matching: a harmless-looking channel name
    inside an Adult/Erotic/XXX section is still treated as adult content.
    """
    service_center = eServiceCenter.getInstance()
    result = []
    seen = set()
    containers = []
    for item in bouquets:
        containers.append((item.get("name", "adult bouquet"), item.get("rule", "container"), item.get("service_refs", [])))
    for item in sections:
        containers.append((item.get("title", "adult section"), item.get("rule", "container"), item.get("service_refs", [])))

    for title, rule, refs in containers:
        for value in refs:
            try:
                ref = eServiceReference(value)
                compare = compare_ref_string(ref)
            except Exception:
                compare = value
                ref = None
            if not compare or compare in seen:
                continue
            seen.add(compare)
            name = service_name(service_center, ref) if ref is not None else value
            result.append({
                "service_ref": value,
                "compare_ref": compare,
                "service_name": name,
                "rule": "section/bouquet: %s" % rule,
                "container": title,
            })
    return result


def merge_global_services(*groups):
    result = []
    seen = set()
    for group in groups:
        for item in group or []:
            key = item.get("compare_ref") or item.get("service_ref")
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(item)
    return result


def scan_everything():
    bouquets = scan_bouquets()
    if config.plugins.kidssafebouquets.strict_hide.value:
        global_scan = scan_all_services()
        container_services = services_from_adult_containers(bouquets["bouquets"], bouquets["sections"])
        global_services = merge_global_services(global_scan["services"], container_services)
    else:
        global_scan = {"services": [], "errors": []}
        global_services = []
    return {
        "bouquets": bouquets["bouquets"],
        "sections": bouquets["sections"],
        "channels": bouquets["channels"],
        "global_services": global_services,
        "errors": bouquets["errors"] + global_scan["errors"],
    }


def create_backup():
    if not os.path.isdir(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = os.path.join(BACKUP_DIR, "kidssafe-%s.tar.gz" % stamp)
    patterns = [
        "bouquets.tv", "bouquets.radio", "userbouquet.*.tv", "userbouquet.*.radio",
        "kidssafe_hidden_refs.txt",
        "blacklist",
    ]
    files = []
    for pattern in patterns:
        files.extend(glob.glob(os.path.join(ENIGMA2_DIR, pattern)))
    with tarfile.open(target, "w:gz") as archive:
        for path in sorted(set(files)):
            if os.path.isfile(path):
                archive.add(path, arcname=os.path.basename(path))
    return target


def latest_backup():
    files = sorted(glob.glob(os.path.join(BACKUP_DIR, "kidssafe-*.tar.gz")), reverse=True)
    return files[0] if files else None


def remove_hidden_flags(refs):
    db = eDVBDB.getInstance()
    for value in refs:
        try:
            db.removeFlag(eServiceReference(value), 2)
        except Exception:
            pass


def apply_hidden_flags(refs):
    db = eDVBDB.getInstance()
    count = 0
    for value in refs:
        try:
            db.addFlag(eServiceReference(value), 2)
            count += 1
        except Exception as err:
            log("Could not hide %s: %s" % (value, err))
    try:
        from Components.ServiceList import refreshServiceList
        refreshServiceList()
    except Exception:
        pass
    return count


def restore_backup(path):
    if not path or not os.path.isfile(path):
        raise IOError("Backup not found")
    old_refs = read_terms(HIDDEN_REFS_FILE)
    remove_hidden_flags(old_refs)
    with tarfile.open(path, "r:gz") as archive:
        members = {os.path.basename(m.name): m for m in archive.getmembers() if m.isfile()}
        for name, member in members.items():
            if not name or name != member.name:
                continue
            source = archive.extractfile(member)
            if source is None:
                continue
            target = os.path.join(ENIGMA2_DIR, name)
            with open(target, "wb") as out:
                out.write(source.read())
    eDVBDB.getInstance().reloadBouquets()
    apply_hidden_flags(read_terms(HIDDEN_REFS_FILE))


def protect_with_native_parental_control(compare_refs):
    protected = 0
    warnings = []
    if not config.plugins.kidssafebouquets.use_parental_control.value:
        return protected, warnings
    try:
        from Components.ParentalControl import parentalControl
        # Do not change the user's PIN/settings. If parental control is configured,
        # also add services to its blacklist. KidsSafe's own hide flag works anyway.
        for value in compare_refs:
            try:
                parentalControl.protectService(value)
                protected += 1
            except Exception as err:
                warnings.append("Parental control %s: %s" % (value, err))
        try:
            parentalControl.save()
        except Exception as err:
            warnings.append("Could not save parental-control blacklist: %s" % err)
    except Exception as err:
        warnings.append("Native parental control unavailable: %s" % err)
    return protected, warnings


def strict_hide(global_services):
    new_refs = []
    compare_refs = []
    for item in global_services:
        new_refs.append(item["service_ref"])
        compare_refs.append(item["compare_ref"])

    old_refs = read_terms(HIDDEN_REFS_FILE)
    # Unhide stale refs from previous settings before applying the new scan.
    remove_hidden_flags([x for x in old_refs if x not in new_refs])
    write_terms(HIDDEN_REFS_FILE, new_refs)
    hidden = apply_hidden_flags(new_refs)
    protected, warnings = protect_with_native_parental_control(compare_refs)
    return hidden, protected, warnings


def apply_clean(scan_result):
    """Apply a scan result without doing expensive full rescans.

    V1.3 intentionally reuses the already computed scan. Adult sections are
    removed first, then individual channel matches outside those sections,
    then the precomputed global hide list is applied. This makes Clean much
    faster after Preview and avoids scanning ALL services several times.
    """
    service_center = eServiceCenter.getInstance()
    removed_bouquets = 0
    removed_sections = 0
    removed_section_services = 0
    removed_channels = 0
    failures = []

    removed_bouquet_refs = set()
    if scan_result["bouquets"]:
        try:
            root_mutable = service_center.list(bouquet_root()).startEdit()
        except Exception:
            root_mutable = None
        if root_mutable:
            for item in scan_result["bouquets"]:
                try:
                    rc = root_mutable.removeService(eServiceReference(item["ref"]))
                    if rc == 0:
                        removed_bouquets += 1
                        removed_bouquet_refs.add(item["ref"])
                    else:
                        failures.append("Bouquet: %s" % item["name"])
                except Exception as err:
                    failures.append("Bouquet %s: %s" % (item["name"], err))
            try:
                root_mutable.flushChanges()
            except Exception as err:
                failures.append("Saving bouquets.tv: %s" % err)
        else:
            failures.append("bouquets.tv is not editable")

    rs, rss, section_failures = remove_sections_from_files(
        scan_result.get("sections", []), skip_bouquet_refs=removed_bouquet_refs
    )
    removed_sections += rs
    removed_section_services += rss
    failures.extend(section_failures)

    try:
        eDVBDB.getInstance().reloadBouquets()
    except Exception as err:
        failures.append("Reload after section cleanup: %s" % err)

    # V1.3: use the original channel list. scan_bouquets() already excludes
    # individual matches that are inside a section scheduled for full removal.
    grouped = {}
    for item in scan_result.get("channels", []):
        if item.get("bouquet_ref") in removed_bouquet_refs:
            continue
        grouped.setdefault(item["bouquet_ref"], []).append(item)

    for bref, items in grouped.items():
        try:
            mutable = service_center.list(eServiceReference(bref)).startEdit()
        except Exception:
            mutable = None
        if not mutable:
            failures.append("Not editable: %s" % items[0]["bouquet_name"])
            continue
        for item in items:
            try:
                rc = mutable.removeService(eServiceReference(item["service_ref"]))
                if rc == 0:
                    removed_channels += 1
                else:
                    failures.append("Channel: %s" % item["service_name"])
            except Exception as err:
                failures.append("Channel %s: %s" % (item["service_name"], err))
        try:
            mutable.flushChanges()
        except Exception as err:
            failures.append("Saving %s: %s" % (items[0]["bouquet_name"], err))

    hidden = 0
    protected = 0
    if config.plugins.kidssafebouquets.strict_hide.value:
        # Reuse the precomputed global list from Preview/scan. Service refs stay
        # valid even after their bouquet entries have been removed.
        try:
            hidden, protected, warnings = strict_hide(scan_result.get("global_services", []))
            failures.extend(warnings)
        except Exception as err:
            failures.append("Strict Kids Mode: %s" % err)

    try:
        eDVBDB.getInstance().reloadBouquets()
    except Exception as err:
        failures.append("Final bouquet reload: %s" % err)
    if config.plugins.kidssafebouquets.strict_hide.value:
        apply_hidden_flags(read_terms(HIDDEN_REFS_FILE))
    return (removed_bouquets, removed_sections, removed_section_services,
            removed_channels, hidden, protected, failures)

def format_scan(result, title="Preview"):
    lines = ["%s - %s v%s" % (title, PLUGIN_NAME, PLUGIN_VERSION), ""]
    lines.append(_("Adult bouquets found: %d") % len(result["bouquets"]))
    for item in result["bouquets"]:
        lines.append("  [BOUQUET] %s  (%d services; rule: %s)" % (item["name"], item["count"], item["rule"]))
    lines.append("")
    lines.append(_("Adult sections found (FULL SECTION WILL BE REMOVED): %d") % len(result.get("sections", [])))
    for item in result.get("sections", []):
        lines.append("  [SECTION] %s -> %s  (%d services; rule: %s)" % (
            item["bouquet_name"], item["title"], item["count"], item["rule"]))
    lines.append("")
    lines.append(_("Adult channels found outside those sections: %d") % len(result["channels"]))
    for item in result["channels"]:
        lines.append("  %s  ->  %s  (rule: %s)" % (item["bouquet_name"], item["service_name"], item["rule"]))
    lines.append("")
    lines.append(_("Adult services found in global ALL list: %d") % len(result["global_services"]))
    for item in result["global_services"]:
        lines.append("  [ALL] %s  (rule: %s)" % (item["service_name"], item["rule"]))
    if result["errors"]:
        lines.append("")
        lines.append(_(_("Warnings:")))
        for err in result["errors"]:
            lines.append("  - %s" % err)
    if not result["bouquets"] and not result.get("sections") and not result["channels"] and not result["global_services"]:
        lines.extend(["", _("No matching adult bouquets/sections/channels were detected.")])
    return "\n".join(lines)


class KidsSafeResults(Screen):
    skin = """
        <screen name="KidsSafeResults" position="center,center" size="1120,630" title="KidsSafe Bouquets" backgroundColor="#101820">
            <widget name="header" position="25,18" size="1070,44" font="Regular;30" foregroundColor="#F5F7FA" backgroundColor="#101820" />
            <widget name="text" position="25,78" size="1070,470" font="Regular;23" scrollbarMode="showOnDemand" foregroundColor="#E6EAF0" backgroundColor="#101820" />
            <widget source="key_red" render="Label" position="25,570" size="240,40" font="Regular;24" foregroundColor="#FF4040" backgroundColor="#101820" />
        </screen>
    """

    def __init__(self, session, text, header="KidsSafe Bouquets"):
        Screen.__init__(self, session)
        self["header"] = Label(header)
        self["text"] = ScrollLabel(text)
        self["key_red"] = StaticText(_("RED  Close"))
        self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions"], {
            "cancel": self.close, "ok": self.close, "red": self.close,
            "up": self["text"].pageUp, "down": self["text"].pageDown,
            "left": self["text"].pageUp, "right": self["text"].pageDown,
        }, -1)


class KidsSafeSettings(Screen, ConfigListScreen):
    skin = """
        <screen name="KidsSafeSettings" position="center,center" size="1040,560" title="KidsSafe Bouquets - Settings" backgroundColor="#08111C">
            <widget name="header" position="35,28" size="970,50" font="Regular;34" foregroundColor="#FFFFFF" backgroundColor="#08111C" />
            <widget name="sub" position="35,78" size="970,34" font="Regular;22" foregroundColor="#55A8FF" backgroundColor="#08111C" />
            <widget name="config" position="35,145" size="970,270" scrollbarMode="showOnDemand" />
            <widget source="key_red" render="Label" position="45,465" size="360,46" font="Regular;25" foregroundColor="#FF5050" backgroundColor="#08111C" />
            <widget source="key_green" render="Label" position="440,465" size="360,46" font="Regular;25" foregroundColor="#4FE066" backgroundColor="#08111C" />
            <widget name="hint" position="35,520" size="970,28" font="Regular;19" foregroundColor="#B6C7D8" backgroundColor="#08111C" />
        </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        entries = [
            getConfigListEntry(_("Strict Kids Mode: hide matches from ALL / Satellites / Providers"), config.plugins.kidssafebouquets.strict_hide),
            getConfigListEntry(_("Also add matches to native parental blacklist"), config.plugins.kidssafebouquets.use_parental_control),
            getConfigListEntry(_("Create backup before cleaning"), config.plugins.kidssafebouquets.make_backup),
        ]
        ConfigListScreen.__init__(self, entries, session=session)
        self["header"] = Label(_("KidsSafe Bouquets v%s") % PLUGIN_VERSION)
        self["sub"] = Label(_("Simple settings - the adult filter itself is always enabled"))
        self["key_red"] = StaticText(_("RED   Cancel"))
        self["key_green"] = StaticText(_("GREEN   Save"))
        self["hint"] = Label(_("Adult / Erotic / XXX bouquets, sections and matching channels are always filtered aggressively."))
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
            "cancel": self.keyCancel, "red": self.keyCancel, "green": self.saveSettings,
        }, -1)

    def saveSettings(self):
        for entry in self["config"].list:
            entry[1].save()
        configfile.save()
        self.close(True)


class KidsSafeMain(Screen):
    skin = """
        <screen name="KidsSafeMain" position="center,center" size="1200,650" title="KidsSafe Bouquets" backgroundColor="#06101B">
            <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/KidsSafeBouquets/main_bg.png" position="0,0" size="1200,650" zPosition="-5" alphatest="blend" />
            <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/KidsSafeBouquets/logo.png" position="28,24" size="150,112" alphatest="blend" />
            <widget name="title" position="205,24" size="570,54" font="Regular;42" foregroundColor="#FFFFFF" transparent="1" />
            <widget name="subtitle" position="205,80" size="570,38" font="Regular;27" foregroundColor="#58AFFF" transparent="1" />
            <widget name="list" position="32,175" size="570,300" font="Regular;29" itemHeight="56" scrollbarMode="showNever" transparent="1" />
            <widget name="panelTitle" position="675,115" size="470,45" font="Regular;33" foregroundColor="#FFFFFF" transparent="1" />
            <widget name="version" position="675,162" size="470,38" font="Regular;28" foregroundColor="#58AFFF" transparent="1" />
            <widget name="panelText" position="675,214" size="470,245" font="Regular;22" foregroundColor="#E3EDF7" transparent="1" />
            <widget name="credit" position="695,482" size="430,70" font="Regular;20" halign="center" valign="center" foregroundColor="#EAF2FA" transparent="1" />
            <widget name="status" position="40,555" size="1120,32" font="Regular;20" foregroundColor="#BFD0E0" transparent="1" />
            <widget source="key_red" render="Label" position="38,604" size="245,36" font="Regular;23" foregroundColor="#FFFFFF" transparent="1" />
            <widget source="key_green" render="Label" position="325,604" size="245,36" font="Regular;23" foregroundColor="#FFFFFF" transparent="1" />
            <widget source="key_yellow" render="Label" position="610,604" size="245,36" font="Regular;23" foregroundColor="#FFFFFF" transparent="1" />
            <widget source="key_blue" render="Label" position="895,604" size="245,36" font="Regular;23" foregroundColor="#FFFFFF" transparent="1" />
        </screen>
    """

    SCAN_WARNING = _(
        "KidsSafe must scan all bouquets and, in Strict Kids Mode, the global TV service list.\n\n"
        "Large settings can take some time and Enigma2 may react slowly during the scan. "
        "Please wait until the scan finishes and do not restart the GUI.\n\nContinue?"
    )
    def __init__(self, session):
        Screen.__init__(self, session)
        self.last_scan = None
        self.last_scan_fingerprint = None
        self["title"] = Label("KidsSafe Bouquets")
        self["subtitle"] = Label(_("A safer TV for your family"))
        self.menu = [
            (_("1   Clean now (Strict Kids Mode)"), "clean"),
            (_("2   Preview scan"), "preview"),
            (_("3   Settings"), "settings"),
            (_("4   Restore last backup"), "restore"),
            (_("5   About"), "about"),
        ]
        self["list"] = MenuList([x[0] for x in self.menu])
        self["panelTitle"] = Label("KidsSafe Bouquets")
        self["version"] = Label(_("Version %s") % PLUGIN_VERSION)
        self["panelText"] = Label(_(
            "Aggressive family-safety cleaning:\n\n"
            "• removes Adult / Erotic / XXX categories in many languages\n"
            "• deletes the complete section and every channel inside it\n"
            "• removes individually matched adult channels\n"
            "• can hide matches from All / Satellites / Providers\n"
            "• backup and restore included\n\n"
            "If in doubt, KidsSafe removes it."
        ))
        self["credit"] = Label(_("Created by Dorinelu\nwith AI assistance by ChatGPT\nDG Labs"))
        self["key_red"] = StaticText(_("Close"))
        self["key_green"] = StaticText(_("Clean"))
        self["key_yellow"] = StaticText(_("Preview"))
        self["key_blue"] = StaticText(_("Settings"))
        self["status"] = Label(_("Ready. First scan can take a while on very large settings."))
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
            "cancel": self.close, "red": self.close, "ok": self.runSelected,
            "green": self.clean, "yellow": self.preview, "blue": self.openSettings,
            "up": self["list"].up, "down": self["list"].down,
            "left": self["list"].pageUp, "right": self["list"].pageDown,
        }, -1)

    def settingsFingerprint(self):
        parts = []
        paths = [os.path.join(ENIGMA2_DIR, "bouquets.tv")]
        paths.extend(glob.glob(os.path.join(ENIGMA2_DIR, "userbouquet.*.tv")))
        for path in sorted(set(paths)):
            try:
                st = os.stat(path)
                parts.append((path, int(st.st_mtime), int(st.st_size)))
            except Exception:
                parts.append((path, 0, 0))
        parts.append(("cfg", int(config.plugins.kidssafebouquets.strict_hide.value),
                      int(config.plugins.kidssafebouquets.use_parental_control.value),
                      int(config.plugins.kidssafebouquets.make_backup.value)))
        return tuple(parts)

    def cacheIsValid(self):
        return self.last_scan is not None and self.last_scan_fingerprint == self.settingsFingerprint()

    def invalidateScan(self, *args):
        self.last_scan = None
        self.last_scan_fingerprint = None
        self["status"].setText(_("Settings changed. A new scan will be required."))

    def runSelected(self):
        index = self["list"].getSelectedIndex()
        if index < 0 or index >= len(self.menu):
            return
        action = self.menu[index][1]
        if action == "clean":
            self.clean()
        elif action == "preview":
            self.preview()
        elif action == "settings":
            self.openSettings()
        elif action == "restore":
            self.restoreLatest()
        elif action == "about":
            self.showAbout()

    def askScanWarning(self, callback):
        self.session.openWithCallback(callback, MessageBox, self.SCAN_WARNING, MessageBox.TYPE_YESNO, default=True)

    def doScan(self):
        self["status"].setText(_("Scanning... please wait. Do not restart Enigma2."))
        result = scan_everything()
        self.last_scan = result
        self.last_scan_fingerprint = self.settingsFingerprint()
        return result

    def preview(self):
        if self.cacheIsValid():
            self["status"].setText(_("Cached preview ready. Clean can reuse it without another full scan."))
            self.session.open(KidsSafeResults, format_scan(self.last_scan, _("Preview")), _("Preview - cached result"))
            return
        self.askScanWarning(self.previewConfirmed)

    def previewConfirmed(self, answer):
        if not answer:
            return
        try:
            result = self.doScan()
            self["status"].setText(_("Preview complete. GREEN Clean will reuse this scan."))
            self.session.open(KidsSafeResults, format_scan(result, _("Preview")), _("Preview scan complete"))
        except Exception as err:
            log("Preview failed: %s" % err)
            self["status"].setText(_("Preview failed."))
            self.session.open(MessageBox, _("Preview failed:\n%s") % err, MessageBox.TYPE_ERROR)

    def clean(self):
        if self.cacheIsValid():
            self["status"].setText(_("Using cached Preview - no second full scan needed."))
            self.confirmCleanFromResult(self.last_scan)
            return
        self.askScanWarning(self.cleanScanConfirmed)

    def cleanScanConfirmed(self, answer):
        if not answer:
            return
        try:
            result = self.doScan()
            self.confirmCleanFromResult(result)
        except Exception as err:
            self["status"].setText(_("Scan failed."))
            self.session.open(MessageBox, _("Scan failed:\n%s") % err, MessageBox.TYPE_ERROR)

    def confirmCleanFromResult(self, result):
        total = len(result["bouquets"]) + len(result.get("sections", [])) + len(result["channels"]) + len(result["global_services"])
        if total == 0:
            self.session.open(KidsSafeResults, format_scan(result, _("Clean")), _("Nothing to clean"))
            return
        message = _(
            "Found:\n%d adult bouquet(s)\n%d adult section(s) to remove COMPLETELY\n"
            "%d adult channel entries outside sections\n%d matching services in ALL\n\n"
            "Clean everything matched?"
        ) % (len(result["bouquets"]), len(result.get("sections", [])),
             len(result["channels"]), len(result["global_services"]))
        self.session.openWithCallback(lambda answer: self.cleanConfirmed(answer, result), MessageBox, message, MessageBox.TYPE_YESNO)

    def cleanConfirmed(self, answer, result):
        if not answer:
            return
        backup = None
        try:
            self["status"].setText(_("Cleaning... please wait."))
            if config.plugins.kidssafebouquets.make_backup.value:
                backup = create_backup()
            rb, rs, rss, rc, hidden, protected, failures = apply_clean(result)
            lines = [
                _("Cleaning completed."), "",
                _("Bouquets removed: %d") % rb,
                _("Adult sections removed: %d") % rs,
                _("Services removed with those sections: %d") % rss,
                _("Individual bouquet channel entries removed: %d") % rc,
                _("Services hidden from ALL/Satellites/Providers: %d") % hidden,
                _("Added to native parental blacklist: %d") % protected,
            ]
            if backup:
                lines.extend(["", _("Backup:"), backup])
            if failures:
                lines.extend(["", _("Warnings:")] + ["  - %s" % x for x in failures])
            lines.extend(["", _("lamedb was not directly edited.")])
            self.last_scan = None
            self.last_scan_fingerprint = None
            self["status"].setText(_("Cleaning complete."))
            self.session.open(KidsSafeResults, "\n".join(lines), _("Cleaning complete"))
        except Exception as err:
            log("Clean failed: %s" % err)
            self["status"].setText(_("Cleaning failed."))
            self.session.open(MessageBox, _("Cleaning failed:\n%s") % err, MessageBox.TYPE_ERROR)

    def openSettings(self):
        self.session.openWithCallback(self.invalidateScan, KidsSafeSettings)

    def showAbout(self):
        text = _(
            "KidsSafe Bouquets v%s\n\n"
            "Family-safety cleaner for Enigma2.\n\n"
            "• Removes complete Adult / Erotic / XXX categories and every channel inside them.\n"
            "• Uses multilingual category detection.\n"
            "• Removes individually matched adult channels.\n"
            "• Can hide matches from All / Satellites / Providers.\n"
            "• Backup and restore are included.\n\n"
            "Created by Dorinelu\n"
            "with AI assistance by ChatGPT\n\n"
            "DG Labs\n"
            "Plugins • Tools • Solutions"
        ) % PLUGIN_VERSION
        self.session.open(KidsSafeResults, text, _("About KidsSafe Bouquets"))

    def restoreLatest(self):
        backup = latest_backup()
        if not backup:
            self.session.open(MessageBox, _("No KidsSafe backup found."), MessageBox.TYPE_INFO)
            return
        msg = _("Restore this backup?\n\n%s") % backup
        self.session.openWithCallback(lambda answer: self.restoreConfirmed(answer, backup), MessageBox, msg, MessageBox.TYPE_YESNO)

    def restoreConfirmed(self, answer, backup):
        if not answer:
            return
        try:
            restore_backup(backup)
            self.invalidateScan()
            self.session.open(MessageBox, _("Backup restored. Hidden-service flags were refreshed."), MessageBox.TYPE_INFO)
        except Exception as err:
            self.session.open(MessageBox, _("Restore failed:\n%s") % err, MessageBox.TYPE_ERROR)


def session_start(reason, **kwargs):
    if reason == 0:
        try:
            if config.plugins.kidssafebouquets.strict_hide.value:
                apply_hidden_flags(read_terms(HIDDEN_REFS_FILE))
        except Exception as err:
            log("Session-start hide refresh failed: %s" % err)


def main(session, **kwargs):
    session.open(KidsSafeMain)


def Plugins(**kwargs):
    return [
        PluginDescriptor(
            name=PLUGIN_NAME,
            description=_("Simple family-safety cleaner for adult bouquets, sections and channels"),
            where=PluginDescriptor.WHERE_PLUGINMENU,
            icon="plugin.png",
            needsRestart=False,
            fnc=main,
        ),
        PluginDescriptor(
            where=PluginDescriptor.WHERE_SESSIONSTART,
            needsRestart=False,
            fnc=session_start,
        ),
    ]
