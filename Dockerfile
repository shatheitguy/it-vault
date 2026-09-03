FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc default-libmysqlclient-dev pkg-config curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Runtime dirs the app writes to (invoices, backups, a generated logo
# placeholder) — created up front and owned by the non-root user below.
RUN mkdir -p invoices backups \
    && useradd -m -u 1000 itguy \
    && chown -R itguy:itguy /app
USER itguy

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=5 \
    CMD curl -f http://localhost:5000/ || exit 1

CMD ["sh", "-c", "python wait_for_db.py && python serve.py"]
