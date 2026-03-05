# CI/CD Playbook

- CI validates repo and builds manifests.
- CI runs content schema checks with dry-run content sync.
- CI does not run live deploy by default.
- Live deployment is gated and secret-backed.
