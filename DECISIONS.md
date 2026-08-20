
## D6 — Compose publishes Postgres on host `5433` and Redis on `6380`
A local Postgres and Redis already own `5432`/`6379` on the development machine, and
they shadow the published container ports, so host-side tooling (Alembic autogenerate,
`pytest`) silently connects to the wrong server. **Choice:** publish `5433:5432` and
`6380:6379`. Inside the Compose network the services still talk on `db:5432` and
`redis:6379`, so nothing about the deployed configuration changes.
