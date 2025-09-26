FROM python:3.11-slim
WORKDIR /app
COPY echo-bridge/ ./echo-bridge/
RUN python -m venv /opt/venv \
  && /opt/venv/bin/pip install --upgrade pip \
  && /opt/venv/bin/pip install -r echo-bridge/requirements.txt
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app/echo-bridge"
EXPOSE 3333 3337
# Start both bridge (uvicorn) and mcp in background using a simple shell wrapper
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh
CMD ["/app/docker-entrypoint.sh"]
