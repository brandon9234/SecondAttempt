# Troubleshooting Playbook

- Auth failures: verify `.env` domain/token/version.
- Validation failures: fix schema, handles/SKUs, or image numbering.
- Rate limits: rely on retries, reduce deployment cadence.
- Drift: rerun dry-run and inspect planned mutations before live sync.
