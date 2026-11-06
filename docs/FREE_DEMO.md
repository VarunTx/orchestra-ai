# Free public demo (retired)

Cloudflare Quick Tunnels are no longer used. The earlier temporary public URLs
stopped resolving, and the tunnel container exposed nothing after that.

The default deployment is now the local Docker Compose stack:

```sh
python3 scripts/setup_env.py
make up
```

Open `http://localhost:3000`. Only loopback ports are published; see the README
for the services and `docs/DEPLOYMENT.md` for the private-host preparation
notes.

For an optional always-on deployment that does not depend on this machine, see
`docs/DEPLOY_FREE.md`. That VM profile is optional and has never been verified
on a real host.

The history of the tunnel and hosted demos remains in `docs/PROGRESS.md` and is
not rewritten by this note.
