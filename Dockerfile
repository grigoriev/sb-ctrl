# sb-ctrl REST API + transfer agent.
#
# The container runs as root on purpose: the worker chowns delivered media to
# the Plex user, which needs CAP_CHOWN. Mount the config and the SSH key at
# runtime (see sb-stack/docker-compose.yml).

# uv installs the exact versions and hashes of uv.lock. It is only mounted
# during the build, so the final image does not carry it.
FROM ghcr.io/astral-sh/uv:0.12.19@sha256:04d046b13e60d6bcec73cbc5e1cad25d680dea90c8573340950a0ac2d1aef424 AS uv

FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d

# lftp performs the mirror/get transfers; openssh-client backs lftp's sftp.
# The versions follow the pinned base image, so they are not pinned here.
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends lftp openssh-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY sb_ctrl ./sb_ctrl
# Installs into the system Python, then removes the pip of the base image and
# its dangling pip symlink. Nothing needs pip at runtime, and its vendored
# msgpack and setuptools carry HIGH findings.
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    UV_PROJECT_ENVIRONMENT=/usr/local UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1 \
    uv sync --frozen --no-dev --no-editable --inexact --no-cache \
    && uv pip uninstall --system pip \
    && rm -f /usr/local/bin/pip

# Default config location; override with a bind mount or SB_CTRL_CONFIG.
# The mounted config must set [api] host = "0.0.0.0" to be reachable.
ENV SB_CTRL_CONFIG=/config/config.toml

EXPOSE 8765
CMD ["sb-ctrl", "serve"]
