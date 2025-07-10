# Operations and recovery

## Start and stop

Build the frontend, configure a strong local `WORKBENCH_KEY`, and start `python -m workbench.server`. The default bind is loopback port 18120. Do not expose the reference service to the public internet. Keep the database, credentials, browser profiles and model weights outside version control.

Stop the API with Ctrl-C. A fresh process can open the same database. Browser dispatch already recorded in the journal may be uncertain after a worker stops; reconcile that action before considering any new operation. Never delete a receipt to make a retry pass.

## Investigate a failure

| Visible state | Operator action |
| --- | --- |
| Needs approval | Inspect arguments and resource version; approve or cancel |
| Ready to run, but approval expired | Cancel the old proposal and create a fresh proposal |
| Resource version changed | Refresh resource data and propose the intended change again |
| Running after a restart | Find the application receipt |
| Needs reconciliation | Check the authoritative owned-portal transaction record; do not replay |
| Receipt confirmed | Download the evidence record; do not submit the same action again |
| Browser lane busy | Wait for the existing run; approval was retained |

If receipt lookup is unavailable, preserve `outcome_unknown`. This implementation intentionally does not offer a force-retry button. Extending it to a third-party portal without receipts would weaken the guarantee and needs a different operating procedure.

## Backup and restore PostgreSQL

Use a dedicated database and PostgreSQL's supported dump tooling. Example for the compose database:

```sh
docker compose exec -T database pg_dump -U browser -d workbench -Fc > journal.dump
# Restore into a separate empty database first, then verify receipts and resource totals.
docker compose exec -T database createdb -U browser workbench_restore
docker compose exec -T database pg_restore -U browser -d workbench_restore < journal.dump
```

Compare action, receipt and event counts, and verify resource quantities before switching the API to the restored database. Keep the original database until verification completes. Use native SQLite's backup API for an online SQLite backup, or stop all writers before copying its database and WAL files together. Copying only a live main database file can lose committed work.

## Test profiles and limits

Core unit/HTTP tests need no model service. Browser, Browser Use, MCP, UI and PostgreSQL tests are explicitly enabled by environment variables shown in the README. Model evaluation is a separate command because actual inference availability and quality are not implied by unit test results. Every benchmark case gets an isolated journal and browser; all failure cases remain in the denominator.

Run one heavy integration stack at a time on small machines. The application permits one browser run at a time per process. Do not infer production capacity from the tiny fixture evaluation. Logs intentionally omit capabilities and operator secrets; evidence exports omit approval and dispatch fields.

## Compatibility container

The compose service uses `WORKBENCH_UNSANDBOXED_CONTAINER=1` explicitly, drops Linux capabilities and retains `no-new-privileges`. That profile is restricted to the owned fixture portal. It is not an operating-system network sandbox and is unsuitable for arbitrary untrusted browsing. Native Chromium runs without that override. Container OS packages reflect the build environment; the dependency profile's historical package dates do not establish a historical container image.
