#!/usr/bin/env bash
# Re-runs every experiment in REPORT.md. Results land in eval_results/<tag>.md|json.
# Uses the response cache, so a second run is free.
set -u
PY=${PY:-.venv/Scripts/python}
[ -x "$PY" ] || PY=python
run() { tag=$1; shift; echo "=== $tag"; "$PY" evaluate.py --tag "$tag" "$@" > /dev/null || echo "FAILED $tag"; }

# input ablation (labelled set)
run ablation_image_only            --input-mode image
run ablation_text_only             --input-mode text      # scans fall back to image
# robustness: degraded copies of the labelled docs (scripts/make_stress_set.py)
for v in lowres tiny blur_noise rot90 rot180 phone; do
  run "stress_${v}" --labelled "data/stress/${v}"
done
# repeatability: fresh API calls, same settings as baseline
run repeat_1 --no-cache
run repeat_2 --no-cache
# model comparison
run model_gemini-3.1-flash-lite --model gemini-3.1-flash-lite
run model_gemini-3.8-flash      --model gemini-3.8-flash
echo ALL DONE
