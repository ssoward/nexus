FROM python:3.12-slim

RUN pip install --no-cache-dir ipython requests numpy pandas

# Non-root user
RUN groupadd -r pyuser -g 2000 && useradd -r -g pyuser -u 2000 -m -d /home/pyuser pyuser

WORKDIR /home/pyuser

USER pyuser

ENV TERM=xterm-256color
ENV HOME=/home/pyuser
ENV PYTHONUNBUFFERED=1

CMD ["/bin/bash"]
