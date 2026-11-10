FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPENCV_IO_MAX_IMAGE_PIXELS=60000000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# La API corre con un usuario sin privilegios. El entrypoint arranca como root solo para dejarle
# permisos sobre el volumen de archivos (que puede venir de versiones anteriores, creado por root).
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin app

COPY . .

EXPOSE 8000
ENTRYPOINT ["sh", "/app/scripts/entrypoint.sh"]
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
