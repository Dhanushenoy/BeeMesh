# Public Hive Deployment

BeeMesh bees are already NAT-friendly because they only make outbound requests
to the Hive. The practical deployment problem is therefore the Hive endpoint:
it must be reachable by all bees and launch clients.

For a stable cross-network setup, run the Hive on a public machine and expose
it through HTTPS on port `443`. This avoids reverse-tunnel fragility and works
better on restricted networks than a random high-numbered port.

## Recommended topology

```text
[ Bee worker ] ----\
[ Bee worker ] ----- HTTPS ---> [ Reverse proxy ] ---> [ BeeMesh Hive ]
[ Launch client ] --/
```

- The Hive runs on a public machine.
- Bees and clients only make outbound requests.
- The reverse proxy terminates TLS and forwards to the local Hive.

## 1. Run the Hive

On the public host:

```bash
export BEEMESH_WORKER_TOKEN="shared-worker-token"
export BEEMESH_CLIENT_TOKEN="shared-client-token"
beemesh hive --host 127.0.0.1 --port 8000
```

Binding the Hive to `127.0.0.1` is preferable when a reverse proxy is used,
because the proxy becomes the public entry point instead of the FastAPI server
itself.

## 2. Put a reverse proxy in front

BeeMesh does not require any Bee-to-Bee traffic, so a standard HTTPS reverse
proxy is sufficient. Caddy is the simplest option because it manages TLS
automatically.

Example `Caddyfile`:

```text
beemesh.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

After the proxy is active, bees and clients should use:

```text
https://beemesh.example.com
```

## 3. Start remote bees

On each remote machine:

```bash
export BEEMESH_AUTH_TOKEN="shared-worker-token"
beemesh bee \
  --hostname remote-bee \
  --hive-url https://beemesh.example.com \
  --heartbeat-interval 10 \
  --task-poll-interval 1.5 \
  --request-timeout 30 \
  --reconnect-interval 5
```

The extra Bee arguments are useful for less stable links:

- `--task-poll-interval`: reduces idle polling frequency.
- `--request-timeout`: bounds each HTTP operation.
- `--reconnect-interval`: controls retry delay after a lost connection.

## 4. Launch jobs remotely

From any authorized client:

```bash
beemesh launch examples/mandelbrot_test/launch.py \
  --hive-url https://beemesh.example.com \
  --auth-token shared-client-token
```

## Notes

- If a Bee loses connectivity after registration, it now retries instead of
  exiting immediately.
- If your network blocks arbitrary outbound ports, exposing the Hive via HTTPS
  on `443` is usually more reliable than tunneling a local port with a free
  relay service.
- For trusted private connectivity, Tailscale remains a good alternative to a
  public-host deployment.
