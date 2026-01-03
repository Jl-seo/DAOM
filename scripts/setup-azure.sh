#!/bin/bash
# Azure Container Apps Infrastructure Setup Script
# Run this once to create all required Azure resources

set -e

# Configuration - UPDATE THESE VALUES
RESOURCE_GROUP="daom-rg"
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

log_info "=== Creating Azure Resources ==="

# 1. Create Resource Group
log_info "Creating Resource Group: $RESOURCE_GROUP"
az group create --name $RESOURCE_GROUP --location $LOCATION

# 2. Create Container Apps Environment
log_info "Creating Container Apps Environment: $CONTAINER_APP_ENV"
az containerapp env create \
    --name $CONTAINER_APP_ENV \
    --resource-group $RESOURCE_GROUP \
    --location $LOCATION

# 3. Create Backend Container App (placeholder - will be replaced by CI/CD)
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

# 4. Create Frontend Container App (placeholder - will be replaced by CI/CD)
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

# 5. Get URLs
log_info "=== Deployment URLs ==="
BACKEND_URL=$(az containerapp show --name $BACKEND_APP_NAME --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv)
FRONTEND_URL=$(az containerapp show --name $FRONTEND_APP_NAME --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv)

echo ""
echo "Backend URL:  https://$BACKEND_URL"
echo "Frontend URL: https://$FRONTEND_URL"
echo ""

# 6. Create Service Principal for GitHub Actions
log_info "Creating Service Principal for GitHub Actions..."
SP_OUTPUT=$(az ad sp create-for-rbac \
    --name "daom-github-actions" \
    --role contributor \
    --scopes /subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP \
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
