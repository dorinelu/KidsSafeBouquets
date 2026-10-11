# Changelog

## v1.7

- Added `installer.sh` for LinuxSat Panel and one-line installation (OE and DreamOS, `/usr/lib` and `/usr/lib64`).
- Fixed: untitled spacer markers inside an adult section no longer end the section early, leaving its remaining channels in place.
- Fixed: numbered and hidden markers (for example `1:320`) are now recognised as section headers.
- Fixed: Clean re-detects sections on the current file content instead of reusing line numbers from an earlier scan.
- Fixed: bouquet files are rewritten byte-for-byte (CRLF line endings and non-UTF-8 names are preserved).
- Fixed: Restore of a backup taken before Strict Kids Mode now un-hides the services again and reloads the parental-control lists.
- Fixed: Latin rule terms must start a word, so names such as "Sussex TV" or "Illustrated" are no longer removed by mistake.
- Fixed: Python 2 text normalisation for non-ASCII channel and category names.
- Fixed: the status text is shown before long scans and cleaning start.
- Fixed: skin images are loaded from the actual plugin path (works on `/usr/lib64` images).
- Added the missing `plugin.png`, `logo.png` and `main_bg.png` graphics.
- Removed unused imports (`getPrevAsciiCode` is missing on some images).
- Added IPK `postrm` script.
- Added update check: when the plugin opens it checks for a newer release and offers to install it (can be disabled in Settings, or run from the menu with "Check for updates").

## v1.6

- Added gettext-based multilingual user interface.
- Initial interface languages: EN, DE, RO, IT, ES, FR, NL, PL, PT, TR, RU and AR.
- Added English fallback when the receiver language is not available.
- Updated About screen with DG Labs branding and credits.
- Updated buttons, settings, status messages and dialogs to use translatable strings.
- Filtering logic and Strict Kids Mode remain unchanged.

## v1.5

- Removed the custom blacklist/whitelist editors for stability and simplicity.
- Kept aggressive built-in Adult / Erotic / XXX filtering always active.
- Kept multilingual full-section removal: when an adult/erotic section header is found, the header and every channel until the next section are removed.
- Kept Strict Kids Mode.
- Kept optional native parental blacklist integration.
- Kept backup / restore.
- Added cached Preview -> Clean workflow.
- Redesigned the main interface with TV + shield graphics.
- Simplified the menu to Clean, Preview, Settings, Restore and About.
- Color keys: RED Close, GREEN Clean, YELLOW Preview, BLUE Settings.
- Added a warning before a potentially long first scan.
- `lamedb` is not directly edited.

## v1.4

- Reworked the custom list editor in an attempt to avoid modal-screen crashes on some Enigma2 images.

## v1.3

- Improved scan workflow and reused Preview results for Clean.
- Added explicit scan warning.
- Reworked color-key mapping.

## v1.2

- Added aggressive full-section removal for Adult / Erotic / XXX-style markers.
- Expanded multilingual category matching.
- Added TV + shield plugin icon.

## v1.1

- Added Strict Kids Mode and global-service hiding.

## v1.0

- Initial KidsSafe Bouquets release.
