#!/usr/bin/env bash
# Install flatpak and flatpak-builder on a Debian/Ubuntu runner and add the Flathub remote.
# Inputs arrive as environment variables so the action and the unit tests share one path:
#   RUNTIME_REPO (a .flatpakrepo URL for Flathub; default below)
#   DRY_RUN=1 prints the commands instead of running them.
# Both tools come from the runner image's distribution, so their versions follow the runner label
# (pin ubuntu-22.04 / ubuntu-24.04 in the caller if that matters). The remote is added to the
# user installation, which is where package.sh builds.
set -euo pipefail

: "${RUNTIME_REPO:=https://dl.flathub.org/repo/flathub.flatpakrepo}"
: "${DRY_RUN:=0}"

run() {
    if [ "$DRY_RUN" = 1 ]; then
        echo "+ $*"
    else
        "$@"
    fi
}

run sudo apt-get update
run sudo apt-get install -y flatpak flatpak-builder

# Ubuntu 24.04 runners restrict unprivileged user namespaces through AppArmor, which breaks the
# bubblewrap sandbox flatpak-builder builds in. Lift it for this job's VM.
if [ "$DRY_RUN" = 1 ] || [ -e /proc/sys/kernel/apparmor_restrict_unprivileged_userns ]; then
    run sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0
fi

run flatpak remote-add --user --if-not-exists flathub "$RUNTIME_REPO"
