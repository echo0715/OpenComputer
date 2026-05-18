# Docker Desktop Image

Build the Linux desktop image from the repository root:

```bash
bash computer_env/provision/docker/build_image.sh
```

This image is intended for the `docker` environment backend in `computer_env/backends/docker/`.

The runtime mounts `/tmp` and `/home/user` as `tmpfs` so desktop-session writes
do not exhaust the Docker Desktop writable layer during local eval runs.

Notes:

- The image exposes noVNC on container port `6080`. The backend publishes it to a random localhost port.
- `linux/amd64` is the default target platform. On Apple Silicon hosts Docker Desktop will emulate it unless you build a native arm64 variant.
- The host only needs the Docker CLI; the Python backend uses the standard library rather than the Docker SDK.
