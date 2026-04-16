FROM node:20-slim

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Non-root user
RUN groupadd -r claude -g 2000 && useradd -r -g claude -u 2000 -m -d /home/claude claude

# Project workspace volume
RUN mkdir -p /workspace && chown claude:claude /workspace

USER claude
WORKDIR /workspace

ENV TERM=xterm-256color
ENV HOME=/home/claude
# ANTHROPIC_API_KEY must be injected via docker exec environment at runtime

CMD ["/bin/bash"]
