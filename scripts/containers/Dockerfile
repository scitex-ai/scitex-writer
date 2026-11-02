# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# SciTeX Writer - Docker Container
# Complete LaTeX environment for reproducible manuscript compilation
# Build: docker build -t scitex-writer .
# Run:   docker run --rm -v $(pwd):/workspace scitex-writer ./compile.sh manuscript

FROM ubuntu:24.04

LABEL maintainer="SciTeX Writer Project"
LABEL description="Complete LaTeX environment for scientific manuscript writing"
LABEL version="1.0.0"

# Prevent interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # LaTeX distribution
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    lmodern \
    texlive-fonts-extra \
    texlive-science \
    texlive-bibtex-extra \
    texlive-publishers \
    texlive-luatex \
    texlive-xetex \
    texlive-lang-european \
    texlive-lang-english \
    # LaTeX utilities
    latexdiff \
    chktex \
    # Document processing
    ghostscript \
    imagemagick \
    # Scripting and utilities
    perl \
    parallel \
    make \
    wget \
    curl \
    git \
    # Python
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Install yq (Go version)
RUN wget -qO /usr/local/bin/yq \
    https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 \
    && chmod +x /usr/local/bin/yq

# Upgrade pip
RUN python3 -m pip install --upgrade pip

# Copy Python requirements and install
COPY requirements/python.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Set working directory
WORKDIR /workspace

# Create a non-root user for running commands
RUN useradd -m -s /bin/bash scitex && \
    chown -R scitex:scitex /workspace

# Switch to non-root user
USER scitex

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=1 \
    CMD command -v pdflatex && command -v yq || exit 1

# Default command
CMD ["bash"]

# Build information
ARG BUILD_DATE
ARG VCS_REF
LABEL org.label-schema.build-date=$BUILD_DATE
LABEL org.label-schema.vcs-ref=$VCS_REF
LABEL org.label-schema.vcs-url="https://github.com/ywatanabe1989/scitex-writer"
LABEL org.label-schema.schema-version="1.0"
