#!/bin/sh
## setup command=wget -q https://raw.githubusercontent.com/dorinelu/KidsSafeBouquets/main/installer.sh -O - | /bin/sh

version='1.7'
changelog="Fixed section detection with spacers and numbered markers\nSafer bouquet file rewriting\nRestore now fully undoes Strict Kids Mode\nLinuxsatPanel installer"

PLUGIN=KidsSafeBouquets
REPO=https://github.com/dorinelu/KidsSafeBouquets/archive/refs/heads/main.tar.gz
TMPPATH=/tmp/$PLUGIN-install
FILEPATH=/tmp/$PLUGIN-main.tar.gz
SRCDIR=$TMPPATH/$PLUGIN-main/usr/lib/enigma2/python/Plugins/Extensions/$PLUGIN

if [ -d /usr/lib64/enigma2/python/Plugins/Extensions ]; then
    PLUGINPATH=/usr/lib64/enigma2/python/Plugins/Extensions/$PLUGIN
else
    PLUGINPATH=/usr/lib/enigma2/python/Plugins/Extensions/$PLUGIN
fi

cleanup() {
    rm -rf "$TMPPATH" "$FILEPATH" 2>/dev/null
}

echo "======================================================="
echo "  KidsSafe Bouquets v$version installer"
echo "======================================================="

if [ -f /var/lib/dpkg/status ]; then
    OSTYPE=DreamOs
else
    OSTYPE=OE
fi
echo "Detected OS type: $OSTYPE"

if ! command -v wget >/dev/null 2>&1; then
    echo "Installing wget..."
    if [ "$OSTYPE" = "DreamOs" ]; then
        apt-get update >/dev/null 2>&1 && apt-get install -y wget
    else
        opkg update >/dev/null 2>&1 && opkg install wget
    fi
    if ! command -v wget >/dev/null 2>&1; then
        echo "wget is not available. Installation aborted."
        exit 1
    fi
fi

cleanup
mkdir -p "$TMPPATH"

echo "Downloading $PLUGIN..."
# Some BusyBox wget builds reject --no-check-certificate; fall back if needed.
if ! wget -q --no-check-certificate "$REPO" -O "$FILEPATH" 2>/dev/null &&
   ! wget -q "$REPO" -O "$FILEPATH" 2>/dev/null &&
   ! { command -v curl >/dev/null 2>&1 && curl -fsSL -k "$REPO" -o "$FILEPATH"; }; then
    echo "Download failed! Check the internet connection."
    cleanup
    exit 1
fi

echo "Extracting package..."
if ! tar -xzf "$FILEPATH" -C "$TMPPATH"; then
    echo "Failed to extract the package!"
    cleanup
    exit 1
fi

if [ ! -f "$SRCDIR/plugin.py" ]; then
    echo "Plugin files not found in the downloaded archive!"
    cleanup
    exit 1
fi

# A previous IPK install would otherwise keep owning (and later remove) these files.
if [ "$OSTYPE" = "OE" ] && opkg list-installed 2>/dev/null | grep -q "^enigma2-plugin-extensions-kidssafebouquets "; then
    echo "Removing previous IPK installation..."
    opkg remove --force-depends enigma2-plugin-extensions-kidssafebouquets >/dev/null 2>&1
fi

echo "Installing plugin files to $PLUGINPATH ..."
rm -rf "$PLUGINPATH"
mkdir -p "$PLUGINPATH"
if ! cp -rf "$SRCDIR"/. "$PLUGINPATH"/; then
    echo "Failed to copy plugin files!"
    cleanup
    exit 1
fi
find "$PLUGINPATH" -name "__pycache__" -type d -prune -exec rm -rf {} \; 2>/dev/null
find "$PLUGINPATH" -name "*.py[co]" -exec rm -f {} \; 2>/dev/null
chmod -R 755 "$PLUGINPATH" 2>/dev/null

cleanup
sync

if [ ! -f "$PLUGINPATH/plugin.py" ]; then
    echo "Installation failed: $PLUGINPATH/plugin.py is missing!"
    exit 1
fi

box_type=$(head -n 1 /etc/hostname 2>/dev/null || echo "Unknown")
python_vers=$(python --version 2>&1 || python3 --version 2>&1)

echo "======================================================="
echo "  KidsSafe Bouquets v$version installed successfully"
echo "-------------------------------------------------------"
printf "%b\n" "$changelog" | sed 's/^/  /'
echo "-------------------------------------------------------"
echo "  Box:    $box_type"
echo "  Python: $python_vers"
echo "  Path:   $PLUGINPATH"
echo "======================================================="
echo "  Please restart the Enigma2 GUI to load the plugin."
echo "======================================================="
exit 0
