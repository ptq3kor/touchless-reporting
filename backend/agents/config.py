"""Azure model configuration for the Microsoft Agent Framework (MAF) layer.

The model deployment is env-configurable and vendor-neutral: any chat deployment
reachable through Azure OpenAI / Azure AI Foundry works (a Claude deployment in
Foundry, a GPT deployment, ...). Swap models by changing MODEL_DEPLOYMENT_NAME only.
"""
import os
from pathlib import Path

# Load .env from the project root (two levels up from this file)
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
if _ENV_FILE.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_ENV_FILE, override=False)
    except ImportError:
        # dotenv not installed — parse the file manually
        with open(_ENV_FILE) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _, _v = _line.partition("=")
                    os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

NOT_CONFIGURED_MSG = ("AI layer not configured. Set AZURE_OPENAI_ENDPOINT, "
                      "AZURE_OPENAI_API_KEY, MODEL_DEPLOYMENT_NAME.")


def _env():
    return {
        "endpoint": os.getenv("AZURE_OPENAI_ENDPOINT") or os.getenv("AZURE_AI_PROJECT_ENDPOINT"),
        "api_key": os.getenv("MODEL_FARM_API_KEY"),
        "deployment": os.getenv("MODEL_DEPLOYMENT_NAME"),
        "api_version": os.getenv("AZURE_OPENAI_API_VERSION"),
    }


def is_configured() -> bool:
    cfg = _env()
    return bool(cfg["endpoint"] and cfg["deployment"])


def make_chat_client():
    """Build a MAF chat client against the Azure deployment.

    Uses OpenAIChatCompletionClient (classic Chat Completions API, deployment-based
    routing: /openai/deployments/{model}/chat/completions?api-version=...). This is
    the surface the Azure OpenAI / model-farm proxy exposes. OpenAIChatClient targets
    the newer Responses API (/openai/v1), which such proxies return 404 for.
    Takes `model` (= Azure deployment name), `azure_endpoint`, `api_key`/`credential`
    and optional `api_version`. Raises RuntimeError when unconfigured.
    """
    cfg = _env()
    if not (cfg["endpoint"] and cfg["deployment"]):
        raise RuntimeError(NOT_CONFIGURED_MSG)

    from agent_framework.openai import OpenAIChatCompletionClient

    kwargs = {"model": cfg["deployment"], "azure_endpoint": cfg["endpoint"]}
    if cfg["api_version"]:
        kwargs["api_version"] = cfg["api_version"]
    if cfg["api_key"]:
        kwargs["api_key"] = cfg["api_key"]
    else:
        from azure.identity import DefaultAzureCredential
        kwargs["credential"] = DefaultAzureCredential()
    return OpenAIChatCompletionClient(**kwargs)
