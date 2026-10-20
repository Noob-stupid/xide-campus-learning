FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    ZX_HOST=0.0.0.0 \
    ZX_PORT=5820 \
    ZX_ENABLE_SWEEPER=1

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 fonts-noto-cjk && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .
RUN python seed.py --reset

EXPOSE 5820
CMD ["gunicorn", "-b", "0.0.0.0:5820", "-w", "1", "--threads", "4", "app:app"]
