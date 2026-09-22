# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Report them privately through GitHub: go to the repository's **Security** tab and choose
**Report a vulnerability** (GitHub private vulnerability reporting / security advisories). Include
the affected version, steps to reproduce and the impact you expect.

You should get an acknowledgement within a few days. We will work with you on a fix and credit you
in the advisory unless you prefer to stay anonymous.

## Supported versions

Security fixes are made for the latest release. Update with `deployer update`.

## Scope notes

- Each Deployer installation is self-hosted and independent; the project operates no servers and
  holds no user data or credentials.
- The default listener is plain HTTP intended for `localhost` or a trusted private network. Exposing
  it directly to the internet without a TLS tunnel or reverse proxy is not a supported configuration.
- **Worker trust** (push-to-deploy, [docs/DEPLOYMENTS.md](docs/DEPLOYMENTS.md)): the `worker` service
  mounts `/var/run/docker.sock` and runs as root so it can build app images and start app containers.
  Anyone who can run code in the worker is root on the Docker engine (and on the WSL2 VM). The API
  container has no socket and stays unprivileged; only project developers can create apps, and their
  build commands run inside BuildKit / the app container, never in the worker process. Deployed app
  containers get no volumes, no extra capabilities, `no-new-privileges`, memory / CPU / pid limits and
  are reachable only through Caddy's per-app port and the app's hostnames.
