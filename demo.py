from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio, MCPServerStreamableHTTP, MCPServerSSE
from pydantic_ai.models.openai import OpenAIResponsesModel
import json
import logfire
from dotenv import load_dotenv
import os
import httpx


load_dotenv(".env", override=True)
logfire.configure()
logfire.instrument_pydantic_ai()
logfire.instrument_httpx(capture_all=True)

# model
model = OpenAIResponsesModel("gpt-4o-mini")


# Remote MCP server - DISABLED (invalid token)
# The FASTMCP_TOKEN is not valid for this server (401 Unauthorized)
# To enable: get a valid token from federal-chocolate-dove.fastmcp.app and update .env

# students_mcp = MCPServerStdio(
#     command="uvx",
#     args=["--from", "prefect-mcp", "prefect-mcp-server"],
#     env={
#         "PREFECT_API_URL": os.getenv("PREFECT_API_URL"),
#         "PREFECT_API_KEY": os.getenv("PREFECT_API_KEY"),
#     },
# )


# local student mcp server
# student_mcp = MCPServerStreamableHTTP("http://localhost:8000/mcp")


# students_mcp = MCPServerStdio(
#     command="uvx",
#     args=["agentic_terminal"],
#     tool_prefix="agentic_terminal",
# )

# Initialize postgres mcp server
postgres_server = MCPServerStdio(
    "npx",
    ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/netflix"],
)

# Initialize fetch mcp server
fetch_server = MCPServerStdio("python", ["-m", "mcp_server_fetch"])

# Initialize mysql mcp server
mysql_server = MCPServerStdio(
    command="npx",
    args=["-y", "@benborla29/mcp-server-mysql"],
    env={
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": "3306",
        "MYSQL_USER": os.getenv("MYSQL_USER"),
        "MYSQL_PASS": os.getenv("MYSQL_PASS"),
        "MYSQL_DB": os.getenv("MYSQL_DB"),
        "ALLOW_INSERT": "true",
        "ALLOW_UPDATE": "true",
        "ALLOW_DELETE": "true",
        "ALLOW_DDL":    "true",   # CREATE, DROP, ALTER tables
        
        # Per-schema permissions — this is what the server actually checks
        "SCHEMA_DDL_PERMISSIONS":    json.dumps({"*": "true"}),
        "SCHEMA_INSERT_PERMISSIONS": json.dumps({"*": "true"}),
        "SCHEMA_UPDATE_PERMISSIONS": json.dumps({"*": "true"}),
        "SCHEMA_DELETE_PERMISSIONS": json.dumps({"*": "true"}),
        
        # Per-table permissions
        "TABLE_DDL_PERMISSIONS":    json.dumps({"*": "true"}),
        "TABLE_INSERT_PERMISSIONS": json.dumps({"*": "true"}),
        "TABLE_UPDATE_PERMISSIONS": json.dumps({"*": "true"}),
        "TABLE_DELETE_PERMISSIONS": json.dumps({"*": "true"}),
    }
)

# Initialize filesystem mcp server
filesystem_server = MCPServerStdio(
    command="npx",
    args=[
        "-y",
        "@modelcontextprotocol/server-filesystem",
        os.getenv("FILESYSTEM_DIRECTORY"),  # directory you want to expose
    ]
)

# search mcp server

tavily_server = MCPServerStdio(
    command="npx",
    args=["-y", "tavily-mcp@latest"],
    env={
        "TAVILY_API_KEY": os.getenv("TAVILY_API_KEY"),
        "DEFAULT_PARAMETERS": json.dumps({
            "include_images": True,
            "max_results": 15,
            "search_depth": "advanced"
        })
    }
)

# weather tool
def get_weather(city: str) -> str:
    """Get current weather for a city using OpenWeatherMap API."""
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        return "Error: OPENWEATHER_API_KEY not found in environment variables."
    
    base_url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": api_key,
        "units": "imperial"  # Use Celsius
    }
    
    try:
        with httpx.Client() as client:
            response = client.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Extract relevant weather info
            temp = data["main"]["temp"]
            feels_like = data["main"]["feels_like"]
            humidity = data["main"]["humidity"]
            description = data["weather"][0]["description"]
            wind_speed = data["wind"]["speed"]
            
            return f"Weather in {data['name']}, {data['sys']['country']}: {description.title()}, Temp: {temp}°C (feels like {feels_like}°C), Humidity: {humidity}%, Wind: {wind_speed} m/s"
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Error: City '{city}' not found."
        return f"Error: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Error fetching weather: {str(e)}"


def get_weather_weatherapi(city: str) -> str:
    """Get current weather for a city using WeatherAPI.com."""
    api_key = os.getenv("WEATHER_API_KEY")
    if not api_key:
        return "Error: WEATHER_API_KEY not found in environment variables."
    
    base_url = "https://api.weatherapi.com/v1/current.json"
    params = {
        "key": api_key,
        "q": city,
        "aqi": "yes"  # Include air quality data
    }
    
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



# Create the agent
agent = Agent(
    name="world_boss_agent",
    description="An agent that answers RANDOM questions.",
    output_type=str,
    model=model,
    tools=[get_weather_weatherapi],
    instructions="Be concise, reply with one sentence. "
    "You have access to: Fetch (web requests), MySQL database, Filesystem, Web Search (Tavily), and Weather lookup. "
    "Use these tools to answer questions and retrieve information.",
    retries=5,
    output_retries=5,
    toolsets=[fetch_server, mysql_server, filesystem_server, tavily_server],
    tool_timeout=300,
)

# Run the agent
async def main():
    result = await agent.run("Hello!")
    while True:
        print(f"\n{result.output}")
        user_input = input("\n> ")
        result = await agent.run(user_input, message_history=result.all_messages())


if __name__ == "__main__":
    import asyncio
    
    asyncio.run(main())
