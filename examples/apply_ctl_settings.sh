#!/bin/sh
# Apply the sweep range and trace calc setup matching controller.yaml in
# this directory. controller.yaml itself only carries network/security
# settings (tsanet has no config field for sweep/trace defaults yet), so
# this script issues the equivalent tsanet-ctl commands instead.
#
# Usage: ./apply_ctl_settings.sh
# (run from this directory, or pass a different --config to override)

set -e

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CONFIG="$SCRIPT_DIR/controller.yaml"
CTL="tsanet-ctl --config $CONFIG"

$CTL sweep range 2400mhz 2490mhz 180

$CTL trace view 1 on
$CTL trace calc 1 minh

$CTL trace view 2 on
$CTL trace calc 2 maxh

$CTL trace view 3 on
$CTL trace calc 3 aver4
