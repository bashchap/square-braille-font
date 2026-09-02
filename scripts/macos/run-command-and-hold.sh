#!/usr/bin/env bash
# Keep a newly opened demo window visible when its command fails, so the real
# Python error is not lost in a flash.  Successful demos and user interrupts
# retain their normal close behaviour.
set +e
"$@"
status=$?
if [[ $status -ne 0 && $status -ne 130 ]]; then
    printf '\nDemo failed with exit status %d.\n' "$status" >&2
    printf 'Press Return to close this window. ' >&2
    IFS= read -r _
fi
exit "$status"
