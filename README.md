# KidsSafe Bouquets

**KidsSafe Bouquets** is an Enigma2 plugin for parents and families who want to keep their channel settings up to date without leaving Adult / Erotic / XXX content visible in the channel lists.

The plugin was created from a very practical problem: updated Enigma2 settings are useful, but many of them contain complete adult sections. Manually cleaning those lists after every update quickly becomes tedious. KidsSafe Bouquets automates that job.

## Current version

**v1.5**

Designed for **OpenATV**, **OpenBH** and similar Enigma2 images.

## Why this plugin exists

I wanted to use frequently updated channel settings, but I also have small children at home and did not want them to accidentally discover adult channels while browsing TV.

PIN protection alone was not the solution I wanted. A PIN can be seen, guessed, shared or discovered. My preferred approach is more direct:

> If adult content is detected, remove it from the channel lists.

That is the idea behind KidsSafe Bouquets.

## Main features

- Detects Adult / Erotic / XXX categories in multiple languages.
- Removes the **complete detected section**, including every channel inside it, until the next section marker.
- Removes complete adult bouquets.
- Removes known adult channels that appear outside a dedicated adult section.
- **Strict Kids Mode** can hide detected services from the global Enigma2 **All / Satellites / Providers** views.
- Optional integration with the native Enigma2 parental blacklist.
- Preview before cleaning.
- Backup before cleaning.
- Restore the last backup.
- Cached **Preview -> Clean** workflow to avoid an unnecessary second full scan.
- Does **not** directly edit `lamedb`.
- TV + shield interface and plugin icon.

## Aggressive filtering

KidsSafe Bouquets is intentionally conservative from a family-safety point of view.

If a complete section is identified as Adult / Erotic / XXX or an equivalent term in another supported language, the plugin removes the section header **and all services inside that section**.

The philosophy is simple:

> If in doubt, KidsSafe removes it.

This can produce false positives. Review the Preview result when using a new settings package.

## Multilingual detection

The built-in rules currently include common adult-category terms in English, German, Polish, French, Italian, Spanish, Portuguese, Dutch, Romanian, Hungarian, Czech, Slovak, Croatian, Serbian, Bosnian, Slovenian, Turkish, Greek, Russian, Ukrainian, Bulgarian and Scandinavian languages.

Examples include:

`Adult`, `Adults`, `XXX`, `Erotic`, `Erotik`, `Erotyczny`, `Erotyka`, `Dla dorosłych`, `Adulte`, `Adultos`, `Adulti`, `Felnőtt`, `Yetişkin` and others.

## Installation

### IPK

Copy the package to `/tmp` on the receiver and install it with:

```sh
opkg install /tmp/enigma2-plugin-extensions-kidssafebouquets_1.5-r0_all.ipk
```

Then restart the Enigma2 GUI.

A fresh installation can install v1.5 directly. Earlier versions are not required.

### Manual source installation

Copy:

```text
usr/lib/enigma2/python/Plugins/Extensions/KidsSafeBouquets/
```

to:

```text
/usr/lib/enigma2/python/Plugins/Extensions/KidsSafeBouquets/
```

on the receiver, then restart Enigma2.

## Usage

Open:

```text
Plugins -> KidsSafe Bouquets
```

Main actions:

- **GREEN** - Clean
- **YELLOW** - Preview
- **BLUE** - Settings
- **RED** - Close

On large settings packages the first scan can take some time. The plugin displays a warning before scanning. If you run **Preview** first, **Clean** can reuse the cached result instead of repeating the complete scan.

## Safety / backup

Before cleaning, the plugin can create a backup under:

```text
/etc/enigma2/kidssafe_backup/
```

The last backup can be restored from the plugin menu.

KidsSafe Bouquets does not directly modify `lamedb`.

## Feedback

Reports are welcome, especially if you find:

- an adult category name in another language that is not detected;
- an adult channel that remains outside an adult category;
- an OpenATV / OpenBH compatibility issue;
- a false positive that should be investigated.

Please open a GitHub issue with the exact category/channel name and, if possible, the Enigma2 image/version.

## Credits

**Plugin done by dorinelu with a lot of help from GPT-5.6 Sol.**

Created for the Enigma2 community and for families who want current channel settings without manually cleaning adult content after every update.
