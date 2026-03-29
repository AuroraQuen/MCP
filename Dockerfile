FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "mcp[cli]" fastmcp pydantic starlette

COPY main.py .

# Data lives in a mounted volume so moments persist across container restarts
ENV DATA_DIR=/data
ENV PORT=3000

# Set MCP_AUTH_TOKEN at runtime — do not bake it into the image
# e.g. docker run -e MCP_AUTH_TOKEN=your-secret-token -v /your/data:/data -p 3000:3000 personal-growth

VOLUME ["/data"]

EXPOSE 3000

CMD ["python", "main.py"]
