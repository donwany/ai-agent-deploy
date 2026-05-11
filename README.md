## Deploy
```bash

# build command
pip install uv && uv sync

# start command
# uv run uvicorn app:app --host 0.0.0.0 --port $PORT
uv run app.py


# Render environment variable
LOGFIRE_TOKEN=
WEATHER_API_KEY=
OPENAI_API_KEY=
TAVILY_API_KEY=
PORT=8000

```