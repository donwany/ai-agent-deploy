from pydantic_ai import Agent
from pydantic_ai.builtin_tools import CodeExecutionTool, WebSearchTool
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.openai import OpenAIResponsesModel
import json
import logfire
from dotenv import load_dotenv
import os
import httpx


load_dotenv(".env", override=True)
logfire.configure(token=os.getenv('LOGFIRE_TOKEN'), send_to_logfire=True)
logfire.instrument_pydantic_ai()
logfire.instrument_httpx(capture_all=True)

# model
model = OpenAIResponsesModel("gpt-4o-mini")


def get_weather_weatherapi(city: str) -> str:
    """Get current weather for a city using WeatherAPI.com."""
    api_key = os.getenv("WEATHER_API_KEY")
    if not api_key:
        return "Error: WEATHER_API_KEY not found in environment variables."

    base_url = "https://api.weatherapi.com/v1/current.json"
    params = {"key": api_key, "q": city, "aqi": "yes"}  # Include air quality data

    try:
        with httpx.Client() as client:
            response = client.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Extract relevant weather info
            location = data["location"]
            current = data["current"]

            return f"Weather in {location['name']}, {location['country']}: {current['condition']['text']}, Temp: {current['temp_c']}°C (feels like {current['feelslike_c']}°C), Humidity: {current['humidity']}%, Wind: {current['wind_kph']} km/h"
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            return f"Error: City '{city}' not found."
        return f"Error: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error fetching weather: {str(e)}"


# Initialize fetch mcp server
fetch_server = MCPServerStdio("python", ["-m", "mcp_server_fetch"])


# Initialize filesystem mcp server
filesystem_server = MCPServerStdio(
    command="npx",
    args=[
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/mnt/",  # directory you want to expose
    ],
)

# search mcp server
tavily_server = MCPServerStdio(
    command="npx",
    args=["-y", "tavily-mcp@latest"],
    env={
        "TAVILY_API_KEY": os.getenv("TAVILY_API_KEY"),
        "DEFAULT_PARAMETERS": json.dumps(
            {"include_images": True, "max_results": 15, "search_depth": "advanced"}
        ),
    },
)


# Create the agent
agent = Agent(
    name="world_boss_agent",
    description="An agent that answers RANDOM questions.",
    output_type=str,
    model=model,
    tools=[get_weather_weatherapi],
    instructions="Be concise, reply with one sentence. "
    "You have access to: Fetch (web requests), Filesystem, Web Search (Tavily), and Weather lookup. "
    "Use these tools to answer questions and retrieve information.",
    retries=5,
    output_retries=5,
    toolsets=[fetch_server, filesystem_server, tavily_server],
    tool_timeout=300,
    builtin_tools=[CodeExecutionTool(), WebSearchTool()],
)


def main():
    app = agent.to_web(
        models=[
            "openai:gpt-4o-mini",
            "openai:gpt-4o",
            "openai:gpt-3.5-turbo",
            "openai:gpt-3.5-turbo-16k",
        ]
    )

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))


if __name__ == "__main__":
    main()
