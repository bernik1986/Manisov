FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV OMP_THREAD_LIMIT=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-rus tesseract-ocr-ukr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements*.txt ./
RUN python -m pip install --no-cache-dir pip==26.2 \
    && python -m pip install --no-cache-dir --no-deps setuptools==79.0.1 wheel==0.46.3 packaging==26.3 \
    && python -m pip install --no-cache-dir --no-build-isolation --no-deps -r requirements.txt \
    && python -m pip check

RUN groupadd --gid 10001 manisov \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /tmp --shell /usr/sbin/nologin manisov
COPY app ./app
COPY parser ./parser
COPY models ./models
COPY migrations ./migrations
COPY synonyms.py alembic.ini ./
COPY scripts/deployment_data.py ./scripts/deployment_data.py
RUN find app parser models migrations scripts -type d -exec chmod 0755 {} + \
    && find app parser models migrations scripts -type f -exec chmod 0644 {} + \
    && chmod 0644 synonyms.py alembic.ini \
    && mkdir -p uploads generated templates/manager_files \
    && chown -R 10001:10001 uploads generated templates
ENV HOME=/tmp
USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
