# sb-ctrl REST API + transfer agent.
#
# The container runs as root on purpose: the worker chowns delivered media to
# the Plex user, which needs CAP_CHOWN. Mount the config and the SSH key at
# runtime (see sb-stack/docker-compose.yml).

# uv installs the exact versions and hashes of uv.lock. It is only mounted
# during the build, so the final image does not carry it.
FROM ghcr.io/astral-sh/uv:0.12.18@sha256:3adc3706091ce7c2fe595e669628caedd6d951551b92b258b7e7dbe06d9440bc AS uv

FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4

# lftp performs the mirror/get transfers; openssh-client backs lftp's sftp.
# The versions follow the pinned base image, so they are not pinned here.
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends lftp openssh-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY sb_ctrl ./sb_ctrl
# Installs into the system Python, as pip did. --inexact keeps pip itself.
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    UV_PROJECT_ENVIRONMENT=/usr/local UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1 \
    uv sync --frozen --no-dev --no-editable --inexact --no-cache

# Default config location; override with a bind mount or SB_CTRL_CONFIG.
# The mounted config must set [api] host = "0.0.0.0" to be reachable.
ENV SB_CTRL_CONFIG=/config/config.toml

EXPOSE 8765
CMD ["sb-ctrl", "serve"]
