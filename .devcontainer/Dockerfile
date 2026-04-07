FROM mcr.microsoft.com/devcontainers/python:3

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    pipewire \
    libclang-dev \
    libpipewire-0.3-dev \
    gir1.2-wp-0.5 \
    libgirepository-2.0-dev \
    && rm -rf /var/lib/apt/lists/*

ENV DEBIAN_FRONTEND=dialog

USER vscode
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
RUN curl -fsSL https://claude.ai/install.sh | bash
USER root
