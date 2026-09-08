FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc default-libmysqlclient-dev pkg-config curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Runtime dirs the app writes to (invoices, backups, and /app/data for the
# uploaded branding, the saved DB pointer and the session key) -- created up
# front and owned by the non-root user below.
#
# /app/data MUST exist in the image. Docker seeds a fresh named volume from
# the directory it shadows, ownership included; when that directory is
# absent it creates the volume empty and root-owned instead, and this
# container runs as uid 1000. That is why uploaded branding failed to save
# and the database pointer was forgotten on every update.
RUN mkdir -p invoices backups data \
    && useradd -m -u 1000 itguy \
    && chown -R itguy:itguy /app
USER itguy

# lets the app tell a container install from a source install, so "check for
# updates" advises pulling a new image rather than git pull
ENV ITVAULT_DOCKER=1

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=5 \
    CMD curl -f http://localhost:5000/ || exit 1

# serve.py waits for the database itself and, if there isn't one yet, still
# starts so the first-run setup wizard can ask for one. It must NOT be gated
# behind wait_for_db.py: that exits non-zero after its timeout, so with no
# DB_HOST configured the "&&" would stop the app from ever starting and the
# container would restart-loop with the wizard unreachable.
CMD ["python", "serve.py"]
