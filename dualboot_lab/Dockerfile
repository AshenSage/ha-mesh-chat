FROM python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements*.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements-bootstrap.lock \
    && pip install --no-cache-dir --require-hashes --no-build-isolation -r requirements.lock
COPY lab ./lab
RUN python -c "import lab.server"
CMD ["python", "-m", "lab.server"]
