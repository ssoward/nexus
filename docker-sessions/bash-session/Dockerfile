FROM debian:12-slim

# Minimal shell environment — no network tools, no package manager access
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    coreutils \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -r terminal -g 2000 && useradd -r -g terminal -u 2000 -m -d /home/terminal terminal

WORKDIR /home/terminal

USER terminal

ENV TERM=xterm-256color
ENV HOME=/home/terminal

CMD ["/bin/bash"]
