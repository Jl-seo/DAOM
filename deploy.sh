#!/bin/bash
# DAOM Deployment Script for Azure Web App
# Usage: ./deploy.sh [frontend|backend|all]

set -e

# Configuration
RESOURCE_GROUP="daom-rg"
FRONTEND_APP_NAME="daom-frontend"
BACKEND_APP_NAME="daom-backend"
LOCATION="koreacentral"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check Azure CLI
check_azure_cli() {
    if ! command -v az &> /dev/null; then
        log_error "Azure CLI is not installed. Please install it first."
        exit 1
    fi
    
    # Check login
    if ! az account show &> /dev/null; then
        log_warn "Not logged in to Azure. Running 'az login'..."
        az login
    fi
}

# Deploy Frontend (Static Web App or Web App)
deploy_frontend() {
    log_info "Building frontend..."
    cd frontend
    npm ci
    npm run build
    
    log_info "Deploying frontend to Azure..."
    # Option 1: Using Azure Static Web Apps
    # az staticwebapp upload --app-name $FRONTEND_APP_NAME --output-location ./dist
    
    # Option 2: Using Azure Web App with zip deploy
    cd dist
    zip -r ../frontend.zip .
    cd ..
    az webapp deploy --resource-group $RESOURCE_GROUP --name $FRONTEND_APP_NAME --src-path frontend.zip --type zip
    rm frontend.zip
    
    cd ..
    log_info "Frontend deployed successfully!"
}

# Deploy Backend (Azure Web App)
deploy_backend() {
    log_info "Preparing backend..."
    cd backend
    
    # Create requirements.txt if not exists
    if [ ! -f "requirements.txt" ]; then
        log_warn "requirements.txt not found, generating from venv..."
        source venv/bin/activate
        pip freeze > requirements.txt
        deactivate
    fi
    
    log_info "Creating deployment package..."
    # Exclude venv and other unnecessary files
    zip -r ../backend.zip . -x "venv/*" -x "__pycache__/*" -x "*.pyc" -x ".env" -x "scripts/*"
    
    log_info "Deploying backend to Azure..."
    az webapp deploy --resource-group $RESOURCE_GROUP --name $BACKEND_APP_NAME --src-path ../backend.zip --type zip
    rm ../backend.zip
    
    cd ..
    log_info "Backend deployed successfully!"
}

# Create Azure Resources (one-time setup)
create_resources() {
    log_info "Creating Azure resources..."
    
    # Create Resource Group
    az group create --name $RESOURCE_GROUP --location $LOCATION
    
    # Create App Service Plan
    az appservice plan create \
        --name "${RESOURCE_GROUP}-plan" \
        --resource-group $RESOURCE_GROUP \
        --sku B1 \
        --is-linux
    
    # Create Backend Web App (Python)
    az webapp create \
        --resource-group $RESOURCE_GROUP \
        --plan "${RESOURCE_GROUP}-plan" \
        --name $BACKEND_APP_NAME \
        --runtime "PYTHON:3.11"
    
    # Create Frontend Web App (Node)
    az webapp create \
        --resource-group $RESOURCE_GROUP \
        --plan "${RESOURCE_GROUP}-plan" \
        --name $FRONTEND_APP_NAME \
        --runtime "NODE:20-lts"
    
    log_info "Azure resources created successfully!"
}

# Configure Backend Environment Variables
configure_backend() {
    log_info "Configuring backend environment variables..."
    
    # Read from backend/.env and set as app settings
    if [ -f "backend/.env" ]; then
        while IFS='=' read -r key value; do
            # Skip comments and empty lines
            [[ $key =~ ^#.*$ ]] && continue
            [[ -z $key ]] && continue
            
            log_info "Setting $key..."
            az webapp config appsettings set \
                --resource-group $RESOURCE_GROUP \
                --name $BACKEND_APP_NAME \
                --settings "$key=$value" > /dev/null
        done < backend/.env
        
        log_info "Backend configured successfully!"
    else
        log_error "backend/.env not found. Please create it first."
        exit 1
    fi
}

# Main
case "$1" in
    frontend)
        check_azure_cli
        deploy_frontend
        ;;
    backend)
        check_azure_cli
        deploy_backend
        ;;
    all)
        check_azure_cli
        deploy_backend
        deploy_frontend
        ;;
    setup)
        check_azure_cli
        create_resources
        configure_backend
        ;;
    config)
        check_azure_cli
        configure_backend
        ;;
    *)
        echo "DAOM Deployment Script"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  frontend    Deploy frontend only"
        echo "  backend     Deploy backend only"
        echo "  all         Deploy both frontend and backend"
        echo "  setup       Create Azure resources (one-time)"
        echo "  config      Update backend environment variables"
        echo ""
        ;;
esac
