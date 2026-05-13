import datetime
import os

import httpx
import logfire
import uvicorn
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.builtin_tools import CodeExecutionTool, WebSearchTool
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai_shields import (
    AsyncGuardrail,
    BlockedKeywords,
    BudgetExceededError,
    CostTracking,
    GuardrailError,
    InputBlocked,
    InputGuard,
    NoRefusals,
    OutputBlocked,
    OutputGuard,
    PiiDetector,
    PromptInjection,
    SecretRedaction,
    ToolBlocked,
    ToolGuard,
)

from utils import INSTRUCTIONS, KEYWORDS

load_dotenv(".env", override=True)
logfire.configure(token=os.getenv("LOGFIRE_TOKEN"), send_to_logfire=True)
logfire.instrument_pydantic_ai()
logfire.instrument_httpx(capture_all=True)

# model
model_settings = OpenAIResponsesModelSettings(
    temperature=0.2,
    max_tokens=500,
    top_p=1,
    frequency_penalty=0,
    presence_penalty=0,
)

model = OpenAIResponsesModel("gpt-4o-mini", settings=model_settings)


class ResponseModel(BaseModel):
    """Structured response with metadata."""

    response: str = Field(description="The agent's response to the user's query")
    needs_escalation: bool = Field(
        description="Whether the issue needs to be escalated to a human agent"
    )
    follow_up_required: bool = Field(description="Whether a follow-up is required")
    sentiment: str = Field(
        description="The sentiment of the customer's message, e.g., positive, negative, neutral"
    )


def get_current_datetime():
    """Get the current date and time."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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


# Create the agent
agent = Agent(
    name="elbowpay_faq_agent",
    description="An agent that answers FAQ questions.",
    output_type=str,
    model=model,
    tools=[get_weather_weatherapi, get_current_datetime],
    instructions=f"{INSTRUCTIONS}",
    retries=5,
    output_retries=5,
    capabilities=[
        CostTracking(budget_usd=1.0),
        InputGuard(guard=lambda prompt: "jailbreak" not in prompt.lower()),
        InputGuard(
            guard=lambda prompt: "ignore all instructions" not in prompt.lower()
        ),
        # block and detect prompt injection
        PromptInjection(sensitivity="high"),  # "low" | "medium" | "high"
        # Detect PII (email, phone, SSN, credit card, IP) in user input:
        PiiDetector(
            detect=["email", "ssn", "credit_card", "phone", "ip"], action="block"
        ),
        # Block prompts containing forbidden words or phrases:
        BlockedKeywords(
            keywords=KEYWORDS,
            whole_words=True,
        ),
        NoRefusals(patterns=[r"I cannot", r"I'm not able to", r"outside my scope"]),
    ],
)


def main():
    try:
        app = agent.to_web(
            models=[
                "openai:gpt-4o-mini",
                "openai:gpt-4o",
                "openai:gpt-3.5-turbo",
                "openai:gpt-3.5-turbo-16k",
            ]
        )
    except InputGuard as e:
        print(f"Input blocked: {e}")
    except GuardrailError as e:
        print(f"Guardrail error: {e}")

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))


if __name__ == "__main__":
    main()
