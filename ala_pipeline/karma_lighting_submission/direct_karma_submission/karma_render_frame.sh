#!/usr/bin/env bash

set -Eeuo pipefail

# -----------------------------------------------------------------------------
# Logging / errors
# -----------------------------------------------------------------------------

log() {
    printf '[karma-helper] %s\n' "$*"
}

die() {
    log "ERROR: $*"
    exit 1
}

usage() {
    cat >&2 <<EOF
Usage:
    $(basename "$0") HIP_FILE LOP_NODE OUTPUT_EXR FRAME JID TID SLOTS

Arguments:
    HIP_FILE     Houdini scene file
    LOP_NODE     LOP node to export, e.g. /obj/lopnet1/env
    OUTPUT_EXR   Final render output
    FRAME        Frame to render
    JID          Tractor Job ID  (%j)
    TID          Tractor Task ID (%t)
    SLOTS        Tractor slots   (%n)

Example Tractor invocation:

    $(basename "$0") \
        /path/to/scene.hip \
        /obj/lopnet1/env \
        /path/to/output.exr \
        1001 \
        %j \
        %t \
        %n
EOF

    exit 2
}

# -----------------------------------------------------------------------------
# Arguments
# -----------------------------------------------------------------------------

[[ $# -eq 7 ]] || usage

HIP_FILE="$1"
LOP_NODE="$2"
OUTPUT="$3"
FRAME="$4"
JID="$5"
TID="$6"
SLOTS="$7"

# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------

[[ -f "$HIP_FILE" ]] ||
    die "HIP file does not exist: $HIP_FILE"

[[ "$FRAME" =~ ^-?[0-9]+([.][0-9]+)?$ ]] ||
    die "Invalid frame: $FRAME"

[[ "$JID" =~ ^[0-9]+$ ]] ||
    die "Invalid Tractor JID: $JID"

[[ "$TID" =~ ^[0-9]+$ ]] ||
    die "Invalid Tractor TID: $TID"

[[ "$SLOTS" =~ ^[1-9][0-9]*$ ]] ||
    die "Invalid Tractor slot count: $SLOTS"

# -----------------------------------------------------------------------------
# Resolve software from active Rez environment
# -----------------------------------------------------------------------------

HYTHON="$(command -v hython)" ||
    die "hython not found in active Rez environment"

HUSK="$(command -v husk)" ||
    die "husk not found in active Rez environment"

# CREATE_USD_STAGE="$(command -v python/houdini_pipeline/direct_karma_submission/create_usd_stage.py)" ||
#     die "create_usd_stage.py not found in active Rez environment"

CREATE_USD_STAGE="$REZ_HOUDINI_PIPELINE_ROOT/python/houdini_pipeline/direct_karma_submission/create_usd_stage.py"

[[ -f "$CREATE_USD_STAGE" ]] ||
    die "create_usd_stage.py not found: $CREATE_USD_STAGE"

# -----------------------------------------------------------------------------
# Idempotency
#
# If the final render already exists and is non-empty, there is nothing to do.
# Check this before creating any temporary state.
# -----------------------------------------------------------------------------

if [[ -s "$OUTPUT" ]]; then
    log "Output already exists; nothing to do:"
    log "  $OUTPUT"
    exit 0
fi

# -----------------------------------------------------------------------------
# Local temporary task workspace
# -----------------------------------------------------------------------------

TMP_BASE="${HOUDINI_TEMP_DIR:-/tmp}"
WORK_DIR="${TMP_BASE}/tractor_${JID}_${TID}"

USD_FILE="${WORK_DIR}/stage.usd"
USD_TMP="${WORK_DIR}/stage.tmp.$$.usd"

EXT="${OUTPUT##*.}"
HUSK_TMP="${WORK_DIR}/render.tmp.$$.${EXT}"

mkdir -p "$WORK_DIR"
mkdir -p "$(dirname "$OUTPUT")"

# -----------------------------------------------------------------------------
# Cleanup
#
# EXIT is invoked for both normal and error exits.
#
# Preserve the original return code so failures continue to propagate back to
# Tractor after cleanup has completed.
# -----------------------------------------------------------------------------

cleanup() {
    local rc=$?

    log "Cleaning temporary workspace: $WORK_DIR"

    rm -rf -- "$WORK_DIR"

    exit "$rc"
}

trap cleanup EXIT

# Convert termination signals into normal shell exits. The EXIT trap above
# then performs cleanup while preserving a meaningful status for Tractor.
trap 'exit 130' INT
trap 'exit 143' TERM

# -----------------------------------------------------------------------------
# Diagnostics
# -----------------------------------------------------------------------------

log "Starting Karma render"
log "  JID:        $JID"
log "  TID:        $TID"
log "  Slots:      $SLOTS"
log "  Frame:      $FRAME"
log "  HIP:        $HIP_FILE"
log "  LOP:        $LOP_NODE"
log "  Output Tmp: $HUSK_TMP"
log "  Output:     $OUTPUT"
log "  Workspace:  $WORK_DIR"
log "  USD Tmp:    $USD_TMP"
log "  USD:        $USD_FILE"

log "Resolved Rez environment:"
log "  hython:     $HYTHON"
log "  husk:       $HUSK"
log "  USD helper: $CREATE_USD_STAGE"

# -----------------------------------------------------------------------------
# Generate USD
#
# Write to a temporary file first, then rename it into place. A failed or
# interrupted export therefore cannot leave stage.usd looking valid.
# -----------------------------------------------------------------------------

if [[ -s "$USD_FILE" ]]; then

    log "Reusing existing USD stage:"
    log "  $USD_FILE"

else

    log "Generating USD stage"

    rm -f -- "$USD_TMP"

    "$HYTHON" "$CREATE_USD_STAGE" \
        -f "$HIP_FILE" \
        -n "$LOP_NODE" \
        -o "$USD_TMP" \
        -F "$FRAME"

    [[ -s "$USD_TMP" ]] ||
        die "USD generation completed without producing a valid USD"

    mv -f -- "$USD_TMP" "$USD_FILE"

    log "USD generation complete:"
    log "  $USD_FILE"

fi

# -----------------------------------------------------------------------------
# Render
#
# Husk thread count follows Tractor's allocated slot count rather than using
# -j 0 and potentially consuming all CPUs available on the blade.
# -----------------------------------------------------------------------------

log "Starting Husk"
log "  Threads: $SLOTS"

rm -f -- "$HUSK_TMP"

"$HUSK" \
    -VaT3 \
    --windows-console none \
    -s /Render/rendersettings \
    --make-output-path \
    -o "$HUSK_TMP" \
    -f "$FRAME" \
    -R BRAY_HdKarma \
    --threads "$SLOTS" \
    --ocio 1 \
    --purpose geometry,render \
    --complexity veryhigh \
    "$USD_FILE"

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

[[ -s "$HUSK_TMP" ]] ||
    die "Husk exited successfully but expected output was not created: $OUTPUT"

mv -f -- "$HUSK_TMP" "$OUTPUT"

log "Render completed successfully:"
log "  $OUTPUT"