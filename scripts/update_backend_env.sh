#!/bin/bash

# Define paths
ENV_FILE="backend/.env"
if [ ! -f "$ENV_FILE" ]; then
    ENV_FILE=".env"
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env file not found in backend/ or root"
    exit 1
fi

echo "Loading environment variables from $ENV_FILE..."
# Export variables from .env, ignoring comments and lines starting with #
export $(grep -v '^#' "$ENV_FILE" | xargs)

# Check if az CLI is installed
if ! command -v az &> /dev/null; then
    echo "Error: Azure CLI (az) is not installed."
    exit 1
fi

RESOURCE_GROUP="Dalle2"
APP_NAME="daom-backend"

echo "Updating environment variables for $APP_NAME in $RESOURCE_GROUP..."

# Construct the update command with key variables
# We use sensitive values from the loaded environment
az containerapp update \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --set-env-vars \
    AZURE_FORM_ENDPOINT="$AZURE_FORM_ENDPOINT" \
    AZURE_FORM_KEY="$AZURE_FORM_KEY" \
    AZURE_OPENAI_ENDPOINT="$AZURE_OPENAI_ENDPOINT" \
    AZURE_OPENAI_API_KEY="$AZURE_OPENAI_API_KEY" \
    AZURE_OPENAI_DEPLOYMENT_NAME="${AZURE_OPENAI_DEPLOYMENT_NAME:-gpt-5.1}" \
    AZURE_OPENAI_API_VERSION="${AZURE_OPENAI_API_VERSION:-2024-05-01-preview}" \
    COSMOS_ENDPOINT="$COSMOS_ENDPOINT" \
    COSMOS_KEY="$COSMOS_KEY" \
    COSMOS_DATABASE="${COSMOS_DATABASE:-daom}" \
    AZURE_STORAGE_CONNECTION_STRING="$AZURE_STORAGE_CONNECTION_STRING" \
    AZURE_CONTAINER_NAME="${AZURE_CONTAINER_NAME:-documents}" \
    AZURE_AD_CLIENT_ID="$AZURE_AD_CLIENT_ID" \
    AZURE_AD_TENANT_ID="${AZURE_AD_TENANT_ID:-common}"

if [ $? -eq 0 ]; then
    echo "✅ Successfully updated environment variables!"
    echo "The container app will now restart with new settings."
else
    echo "❌ Failed to update environment variables."
    echo "Please ensure you are logged in via 'az login'."
fi
