#!/bin/bash
# Azure Container Apps Infrastructure Setup Script
# Uses existing resource group - creates Container Apps only

set -e

# Configuration - Using existing resource group
SUBSCRIPTION_ID="7b1417d8-833d-4ba9-a5cd-d27c91a28b83"
RESOURCE_GROUP="Dalle2"
LOCATION="koreacentral"
CONTAINER_APP_ENV="daom-env"
BACKEND_APP_NAME="daom-backend"
FRONTEND_APP_NAME="daom-frontend"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

# Check Azure CLI login
if ! az account show &> /dev/null; then
    log_warn "Not logged in to Azure. Running 'az login'..."
    az login
fi

# Set subscription
az account set --subscription $SUBSCRIPTION_ID

log_info "=== Setting up Azure Container Apps in existing Resource Group: $RESOURCE_GROUP ==="

# 1. Create Container Apps Environment
log_info "Creating Container Apps Environment: $CONTAINER_APP_ENV"
az containerapp env create \
    --name $CONTAINER_APP_ENV \
    --resource-group $RESOURCE_GROUP \
    --location $LOCATION

# 2. Create Backend Container App (placeholder - will be replaced by CI/CD)
log_info "Creating Backend Container App: $BACKEND_APP_NAME"
az containerapp create \
    --name $BACKEND_APP_NAME \
    --resource-group $RESOURCE_GROUP \
    --environment $CONTAINER_APP_ENV \
    --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest \
    --target-port 8000 \
    --ingress external \
    --min-replicas 0 \
    --max-replicas 3 \
    --cpu 0.5 \
    --memory 1.0Gi

# 3. Create Frontend Container App (placeholder - will be replaced by CI/CD)
log_info "Creating Frontend Container App: $FRONTEND_APP_NAME"
az containerapp create \
    --name $FRONTEND_APP_NAME \
    --resource-group $RESOURCE_GROUP \
    --environment $CONTAINER_APP_ENV \
    --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest \
    --target-port 80 \
    --ingress external \
    --min-replicas 0 \
    --max-replicas 3 \
    --cpu 0.25 \
    --memory 0.5Gi

# 4. Get URLs
log_info "=== Deployment URLs ==="
BACKEND_URL=$(az containerapp show --name $BACKEND_APP_NAME --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv)
FRONTEND_URL=$(az containerapp show --name $FRONTEND_APP_NAME --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv)

echo ""
echo "Backend URL:  https://$BACKEND_URL"
echo "Frontend URL: https://$FRONTEND_URL"
echo ""

# 5. Create Service Principal for GitHub Actions
log_info "Creating Service Principal for GitHub Actions..."
SP_OUTPUT=$(az ad sp create-for-rbac \
    --name "daom-github-actions" \
    --role contributor \
    --scopes /subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP \
    --sdk-auth)

echo ""
log_warn "=== IMPORTANT: Save this JSON as GitHub Secret 'AZURE_CREDENTIALS' ==="
echo "$SP_OUTPUT"
echo ""

log_info "=== Setup Complete! ==="
echo ""
echo "Next steps:"
echo "1. Copy the JSON above and add it as a GitHub Secret named 'AZURE_CREDENTIALS'"
echo "2. Add 'VITE_API_BASE_URL' secret with value: https://$BACKEND_URL/api/v1"
echo "3. Push code to main branch to trigger deployment"
