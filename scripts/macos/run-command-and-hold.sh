#!/usr/bin/env bash
# Keep a newly opened demo window visible when its command fails, so the real
# Python error is not lost in a flash.  --hold-on-success is used for finite
# informational commands such as illustrated help, which must remain readable.
set +e
hold_on_success=0
if [[ "${1:-}" == --hold-on-success ]]; then
    hold_on_success=1
    shift
fi
"$@"
status=$?
if [[ $status -eq 0 && $hold_on_success -eq 1 ]]; then
    printf '\nPress Return to close this help window. '
    IFS= read -r _
elif [[ $status -ne 0 && $status -ne 130 ]]; then
    printf '\nDemo failed with exit status %d.\n' "$status" >&2
    printf 'Press Return to close this window. ' >&2
    IFS= read -r _
fi
exit "$status"
