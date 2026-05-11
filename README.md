## Deploy
```bash

# build command
pip install uv && uv sync

# start command
uv run uvicorn app:app --host 0.0.0.0 --port $PORT


# Render environment variable
LOGFIRE_API_KEY=
WEATHER_API_KEY=
PORT=8000


```