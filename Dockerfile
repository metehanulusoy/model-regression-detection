FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install build deps for any wheels that need them, then strip.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip \
    && pip install . \
    && apt-get purge -y build-essential \
    && apt-get autoremove -y

# Create a non-root runtime user.
RUN useradd -m -u 1001 mrd
USER mrd

VOLUME ["/data", "/work"]
WORKDIR /work

ENTRYPOINT ["mrd"]
CMD ["--help"]
