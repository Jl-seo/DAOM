import logging
from typing import List, Union
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    PROJECT_NAME: str = "DAOM"
    API_V1_STR: str = "/api/v1"

    # CORS - Include Azure Container Apps URL and localhost for development
    BACKEND_CORS_ORIGINS: Union[List[AnyHttpUrl], str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "https://daom-frontend.greenpebble-00aa1dc4.koreacentral.azurecontainerapps.io"
    ]

    @property
    def cors_origins(self) -> List[str]:
        if isinstance(self.BACKEND_CORS_ORIGINS, str):
            import json
            try:
                parsed = json.loads(self.BACKEND_CORS_ORIGINS)
                return [str(origin) for origin in parsed]
            except (json.JSONDecodeError, TypeError):
                return []
        return [str(origin) for origin in self.BACKEND_CORS_ORIGINS]

    # Azure AI Document Intelligence
    AZURE_FORM_ENDPOINT: str = ""
    AZURE_FORM_KEY: str = ""

    # Azure AI Foundry Project
    AZURE_ENV_NAME: str = ""
    AZURE_LOCATION: str = ""
    AZURE_SUBSCRIPTION_ID: str = ""
    AZURE_AIPROJECT_ENDPOINT: str = ""
    AZURE_AIPROJECT_RESOURCE_ID: str = ""
    AZURE_RESOURCE_ID: str = ""

    # Azure OpenAI (Legacy - kept for backward compatibility)
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_API_VERSION: str = "2025-03-01-preview"
    AZURE_OPENAI_DEPLOYMENT_NAME: str = ""

    # Azure Storage
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_CONTAINER_NAME: str = "documents"

    # Azure Cosmos DB
    COSMOS_ENDPOINT: str = ""
    COSMOS_KEY: str = ""
    COSMOS_DATABASE: str = "daom"

    # Azure AD Authentication
    AZURE_AD_CLIENT_ID: str = ""
    AZURE_AD_TENANT_ID: str = "common"

    # OCR Defaults
    OCR_DEFAULT_MODEL: str = "prebuilt-layout"
    
    # Refiner Limits
    REFINER_MAX_REF_CHARS: int = 10000

    # LLM Settings
    # GPT-4.1: max output = 52K tokens. Table extraction needs more for many rows.
    LLM_TABLE_MAX_TOKENS: int = 50000
    LLM_DEFAULT_MAX_TOKENS: int = 8192
    LLM_DEFAULT_TEMPERATURE: float = 0.0
    # Max user prompt chars (~100K tokens, leave 28K for system + response)
    LLM_MAX_USER_PROMPT_CHARS: int = 400_000
    # Max tokens for image comparison responses
    LLM_COMPARISON_MAX_TOKENS: int = 2000

    # Chunking Settings
    # GPT-4o: 128K context. System ~2K, response ~4K → ~122K user = ~488K chars.
    # Target ~80K tokens = 320K chars with headroom.
    CHUNK_MAX_PROMPT_CHARS: int = 320_000
    # Threshold to trigger chunking: ~25K tokens — conservative.
    CHUNK_THRESHOLD_CHARS: int = 100_000

    # Chunking & Preview
    LLM_CHUNK_MAX_TOKENS: int = 8000
    PREVIEW_TEXT_CHARS: int = 5000

    # Validation / Fuzzy Matching
    FUZZY_MATCH_THRESHOLD_STRICT: int = 95
    FUZZY_MATCH_THRESHOLD_LENIENT: int = 85
    LLM_CONFIDENCE_THRESHOLD: float = 0.7
    SCHEMA_GENERATION_MAX_CHARS: int = 4000

    # External Service URLs
    GRAPH_API_BASE_URL: str = "https://graph.microsoft.com/v1.0"
    API_BASE_URL: str = "http://localhost:8000"

    # Initial Admin Setup
    # Comma-separated list of email addresses that will be added to System Admins group
    INITIAL_ADMIN_EMAILS: str = ""
    SYSTEM_USER_EMAIL: str = "system@daom.ai"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    def validate_setup(self):
        missing = []
        if not self.AZURE_FORM_ENDPOINT: missing.append("AZURE_FORM_ENDPOINT")
        if not self.AZURE_FORM_KEY: missing.append("AZURE_FORM_KEY")

        # Check AI Foundry OR legacy OpenAI settings
        has_foundry = bool(self.AZURE_AIPROJECT_ENDPOINT and self.AZURE_OPENAI_API_KEY)
        has_legacy = bool(self.AZURE_OPENAI_ENDPOINT and self.AZURE_OPENAI_API_KEY)

        if not (has_foundry or has_legacy):
            missing.append("AZURE_AIPROJECT_ENDPOINT or AZURE_OPENAI_ENDPOINT")
            missing.append("AZURE_OPENAI_API_KEY")

        if missing:
             logger.warning(f"CRITICAL WARNING: Missing configuration for {missing}. Document processing will fail.")
        else:
            mode = "AI Foundry" if has_foundry else "Legacy OpenAI"
            logger.info(f"[CONFIG] Mode: {mode}")
            logger.info(f"[CONFIG] CORS Origins: {self.cors_origins}")

settings = Settings()
settings.validate_setup()
