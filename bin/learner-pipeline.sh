#!/bin/bash
# Daily Learner nightly pipeline
# Cron: 30 5 * * * /root/daily-learner/bin/learner-pipeline.sh
# (05:30 UTC = 00:30 CDT)

set -euo pipefail

export PATH="/usr/local/bin:/usr/bin:$PATH"
cd /root/daily-learner

exec /usr/bin/python3 -m src.pipeline 2>&1 | tee -a "$HOME/.daily-learner/logs/pipeline.log"
