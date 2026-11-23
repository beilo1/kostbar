FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
LABEL org.opencontainers.image.title="KoSTbar" \
      org.opencontainers.image.version="38.0.0" \
      org.opencontainers.image.source="https://github.com/beilo1/kostbar" \
      org.opencontainers.image.licenses="MIT"
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py web.py configure.py store.py schema_migrations.py finance.py kiosk_state.py technical_docs.py api_reference.py check_api_reference.py privacy.md ./
COPY pi/card_types.py pi/versions.py ./pi/
COPY Dockerfile compose.common.yml ./
RUN python check_api_reference.py
COPY static/ ./static/
COPY LICENSE ./LICENSE
COPY licenses/fonts/ ./licenses/fonts/
USER 10001:10001
EXPOSE 8765
CMD ["python", "server.py", "serve"]
