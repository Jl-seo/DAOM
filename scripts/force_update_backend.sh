#!/bin/bash

# Define paths
ENV_FILE="backend/.env"
if [ ! -f "$ENV_FILE" ]; then
    ENV_FILE=".env"
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env file not found"
    exit 1
fi

echo "Reading environment variables safely from $ENV_FILE..."

# Helper function to extract value safely
get_env_val() {
    grep "^$1=" "$ENV_FILE" | head -n 1 | cut -d'=' -f2- | sed 's/^"//;s/"$//'
}

# Extract key variables explicitly
AZURE_FORM_ENDPOINT=$(get_env_val "AZURE_FORM_ENDPOINT")
AZURE_FORM_KEY=$(get_env_val "AZURE_FORM_KEY")
AZURE_OPENAI_ENDPOINT=$(get_env_val "AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY=$(get_env_val "AZURE_OPENAI_API_KEY")
AZURE_OPENAI_DEPLOYMENT_NAME=$(get_env_val "AZURE_OPENAI_DEPLOYMENT_NAME")
AZURE_OPENAI_API_VERSION=$(get_env_val "AZURE_OPENAI_API_VERSION")
COSMOS_ENDPOINT=$(get_env_val "COSMOS_ENDPOINT")
COSMOS_KEY=$(get_env_val "COSMOS_KEY")
AZURE_STORAGE_CONNECTION_STRING=$(get_env_val "AZURE_STORAGE_CONNECTION_STRING")
AZURE_AD_CLIENT_ID=$(get_env_val "AZURE_AD_CLIENT_ID")
AZURE_AD_TENANT_ID=$(get_env_val "AZURE_AD_TENANT_ID")
AZURE_AIPROJECT_ENDPOINT=$(get_env_val "AZURE_AIPROJECT_ENDPOINT")

# Set defaults if missing
AZURE_OPENAI_DEPLOYMENT_NAME=${AZURE_OPENAI_DEPLOYMENT_NAME:-"gpt-5.1"}
AZURE_OPENAI_API_VERSION=${AZURE_OPENAI_API_VERSION:-"2024-05-01-preview"}
AZURE_AD_TENANT_ID=${AZURE_AD_TENANT_ID:-"common"}

echo "Using Azure OpenAI Endpoint: $AZURE_OPENAI_ENDPOINT"

echo "Force updating backend container..."

az containerapp update \
  --name daom-backend \
  --resource-group Dalle2 \
  --set-env-vars \
    AZURE_FORM_ENDPOINT="$AZURE_FORM_ENDPOINT" \
    AZURE_FORM_KEY="$AZURE_FORM_KEY" \
    AZURE_OPENAI_ENDPOINT="$AZURE_OPENAI_ENDPOINT" \
    AZURE_OPENAI_API_KEY="$AZURE_OPENAI_API_KEY" \
    AZURE_OPENAI_DEPLOYMENT_NAME="$AZURE_OPENAI_DEPLOYMENT_NAME" \
    AZURE_OPENAI_API_VERSION="$AZURE_OPENAI_API_VERSION" \
    COSMOS_ENDPOINT="$COSMOS_ENDPOINT" \
    COSMOS_KEY="$COSMOS_KEY" \
    AZURE_STORAGE_CONNECTION_STRING="$AZURE_STORAGE_CONNECTION_STRING" \
    AZURE_AD_CLIENT_ID="$AZURE_AD_CLIENT_ID" \
    AZURE_AD_TENANT_ID="$AZURE_AD_TENANT_ID" \
    AZURE_AIPROJECT_ENDPOINT="$AZURE_AIPROJECT_ENDPOINT"

if [ $? -eq 0 ]; then
    echo "✅ Backend updated successfully. A new revision should start now."
else
    echo "❌ Failed to update backend."
fi
