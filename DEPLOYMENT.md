# Deployment

Daily Learner runs as two server-backed environments on the droplet:

- Production: `https://apps.thezdev.com/learn`
- Development: `https://apps.thezdev.com/learn-dev`

They are intentionally separate in three ways:

- Separate git worktrees:
  - prod: `/root/daily-learner` on `main`
  - dev: `/root/daily-learner-dev` on `learn-dev`
- Separate systemd services:
  - prod: `daily-learner-web.service`
  - dev: `daily-learner-web-dev.service`
- Separate runtime data/config:
  - prod: `DAILY_LEARNER_DATA_DIR=/root/.daily-learner`
  - dev: `DAILY_LEARNER_DATA_DIR=/root/.daily-learner-dev`

## Branch flow

1. Make and test changes on `learn-dev`
2. Deploy preview with:
   `sudo /root/daily-learner/bin/deploy-web.sh dev`
3. Promote to production by merging `learn-dev` into `main`
4. Deploy production with:
   `sudo /root/daily-learner/bin/deploy-web.sh prod`

## Status

To see both environments:

```bash
sudo /root/daily-learner/bin/deploy-web.sh status
```

## Notes

- This app is not a GitHub Pages app. It depends on Flask API routes.
- Caddy proxies `/learn` to port `8090` and `/learn-dev` to port `8091`.
- The app reads optional env overrides:
  - `DAILY_LEARNER_CONFIG`
  - `DAILY_LEARNER_DATA_DIR`
  - `DAILY_LEARNER_BASE_PATH`
  - `DAILY_LEARNER_PORT`
