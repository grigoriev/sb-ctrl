# sb-ctrl REST API + transfer agent.
#
# The container runs as root on purpose: the worker chowns delivered media to
# the Plex user, which needs CAP_CHOWN. Mount the config and the SSH key at
# runtime (see sb-stack/docker-compose.yml).
FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4

# lftp performs the mirror/get transfers; openssh-client backs lftp's sftp.
RUN apt-get update \
    && apt-get install -y --no-install-recommends lftp openssh-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY sb_ctrl ./sb_ctrl
RUN pip install --no-cache-dir .

# Default config location; override with a bind mount or SB_CTRL_CONFIG.
# The mounted config must set [api] host = "0.0.0.0" to be reachable.
ENV SB_CTRL_CONFIG=/config/config.toml

EXPOSE 8765
CMD ["sb-ctrl", "serve"]
