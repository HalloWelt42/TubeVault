# Nachvertoner für TubeVault (nachvertoner/README.md), als Container neben TubeVault auf dem Pi.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# ffmpeg kommt nicht ins Abbild: es läuft das des Pi (ffmpeg-vom-pi, eingehängt in docker-compose.yml)
COPY ffmpeg-vom-pi /usr/local/bin/ffmpeg
COPY ffmpeg-vom-pi /usr/local/bin/ffprobe
COPY nachvertoner.py .
USER 1000:1000
CMD ["python", "nachvertoner.py"]
