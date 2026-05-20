# pilot.Dockerfile — T113 Phase 1 FEM-solver pilot (ONE-SHOT, не production!)
#
# Цель: прогнать PyOpenMagnetics analytical + advisor + Elmer FEM +
# GetDP+Gmsh FEM на фикстуре OPT 6П14П SE, собрать сравнительные данные
# и выбрать FEM-solver для Phase 2 integration (ADR).
#
# Build:
#   docker build -f pilot.Dockerfile -t efactory-pilot:linux .
#
# Run (memory-limited — см. ADR PyOM advisor host-OOM):
#   docker run --rm --memory=4g \
#     -v $PWD/pilot-out:/work \
#     -v $PWD/tests/fixtures/magnetic:/pilot/fixtures \
#     efactory-pilot:linux
#
# Не наследуется от efactory:linux — pilot одноразовый, не тащим KiCad
# 2.5 GB и связанные deps. Свежий ubuntu:24.04 + apt FEM stack.

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    UV_LINK_MODE=copy

# apt-deps:
#   - GetDP, Gmsh — есть в Ubuntu 24.04 universe;
#   - Elmer FEM CSC — PPA ppa:elmer-csc-ubuntu/elmer-csc-ppa
#     (Ubuntu 24.04 noble не имеет elmerfem-csc в стандартных репах);
#   - time (GNU /usr/bin/time -v для peak-RAM measurement);
#   - curl + ca-certificates для uv installer.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        software-properties-common \
        xz-utils \
        gmsh \
        getdp \
        ngspice \
        time \
    && add-apt-repository -y ppa:elmer-csc-ubuntu/elmer-csc-ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
        elmerfem-csc \
    && rm -rf /var/lib/apt/lists/*

# uv (та же команда что в efactory:linux Phase 0; Astral)
RUN curl -LsSf https://astral.sh/uv/install.sh \
    | env UV_INSTALL_DIR=/usr/local/bin sh

# Python 3.13 (consistency с pyproject.toml requires-python)
RUN uv python install 3.13

WORKDIR /pilot

# venv с PyOpenMagnetics (та же версия что pinned в проекте).
# uv venv не ставит pip — используем `uv pip install` с активным VIRTUAL_ENV.
RUN uv venv --python 3.13 /pilot/.venv \
    && VIRTUAL_ENV=/pilot/.venv uv pip install --no-cache-dir \
        'PyOpenMagnetics==1.3.10'

ENV PATH="/pilot/.venv/bin:${PATH}"

# Pilot scripts (entrypoint + helpers). Фикстура mount-ится при run
# на /pilot/fixtures — НЕ COPY в образ (быстрее iteration без rebuild).
COPY scripts/pilot/ /pilot/scripts/pilot/

# Sanity-check: tools available
RUN python --version && \
    gmsh --version 2>&1 | head -1 && \
    ElmerSolver -v 2>&1 | head -3 && \
    getdp --version 2>&1 | head -1

VOLUME /work
ENTRYPOINT ["python", "/pilot/scripts/pilot/run_pilot.py"]
CMD ["/work"]
