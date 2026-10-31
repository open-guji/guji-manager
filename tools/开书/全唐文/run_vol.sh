#!/bin/bash
VOL=${1:?册号}
source /home/user/env.sh; cd $WS
guji pipeline keben_body_v2 $VOL -w $WS --pages all --from row_segment --to cell_shrink --no-pack; echo seg-exit $?
guji cache warm --book $VOL --pages all --jobs 4 -w $WS; echo warm-exit $?
guji pipeline keben_body_v2 $VOL -w $WS --pages all --from glyph_match --no-pack; echo run-exit $?
