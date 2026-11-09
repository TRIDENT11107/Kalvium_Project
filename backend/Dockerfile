FROM python:3.12-slim
WORKDIR /srv
COPY backend/requirements.txt /srv/backend/requirements.txt
RUN pip install --no-cache-dir -r /srv/backend/requirements.txt
COPY backend /srv/backend
COPY modules /srv/modules
COPY utils /srv/utils
COPY config.py /srv/config.py
ENV PYTHONPATH=/srv:/srv/backend
WORKDIR /srv/backend
EXPOSE 8000
CMD ["sh","-c","alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
