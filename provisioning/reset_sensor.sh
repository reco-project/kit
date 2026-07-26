#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Stop nvargus-daemon so /dev/video* becomes usable by v4l2-ctl.
# Runs on the target host via SSH; sudo prompts interactively in your terminal.
#
# Usage: reset_sensor.sh [hostname]
#
# Set RECO_SSH_USER to override the SSH user (default: same as host).
set -euo pipefail

HOST="${1:-reco-jetson}"
USER="${RECO_SSH_USER:-${HOST}}"

ssh -t "${USER}@${HOST}" 'sudo systemctl stop nvargus-daemon && echo "nvargus stopped"'
