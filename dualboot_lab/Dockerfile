FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements*.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements-bootstrap.lock \
    && pip install --no-cache-dir --require-hashes --no-build-isolation -r requirements.lock
COPY lab ./lab
RUN python -c "import lab.server"
CMD ["python", "-m", "lab.server"]
