#!/bin/bash

# Configuration
RESOURCE_GROUP="Dalle2"
BACKEND_APP="daom-backend"
FRONTEND_APP="daom-frontend"
REGISTRY="ghcr.io"
REPO_NAME="jl-seo/daom" # Assuming repo name, adjust if needed

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Helper for loading .env
if [ -f .env ]; then
  export $(cat .env | xargs)
fi

echo -e "${YELLOW}Starting Manual Deployment...${NC}"

# Auth Check Function
check_auth() {
    echo "Checking authentication..."
    
    # Check Azure CLI login
    if ! az account show > /dev/null 2>&1; then
        echo -e "${RED}Error: You are NOT logged in to Azure CLI.${NC}"
        echo "Please run: az login"
        exit 1
    fi
    echo -e "${GREEN}✔ Azure CLI logged in${NC}"

    # Check Docker login (optional but recommended for push)
    # Just checking if docker is running first
    if ! docker info > /dev/null 2>&1; then
        echo -e "${RED}Error: Docker is not running.${NC}"
        echo "Please start Docker Desktop."
        exit 1
    fi
}

check_auth

# 1. Get Context
BRANCH=$(git rev-parse --abbrev-ref HEAD)
SHA=$(git rev-parse --short HEAD)
SAFE_BRANCH=$(echo "$BRANCH" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | cut -c 1-10)
TIMESTAMP=$(date +%s | cut -c 6-10)

SUFFIX="test-$SAFE_BRANCH-$TIMESTAMP"
LABEL="test-$SAFE_BRANCH"

echo -e "Branch: ${GREEN}$BRANCH${NC}"
echo -e "Revision Suffix: ${GREEN}$SUFFIX${NC}"
echo -e "Label: ${GREEN}$LABEL${NC}"

# Function to deploy a service
deploy_service() {
    SERVICE_NAME=$1
    APP_NAME=$2
    DOCKER_CONTEXT=$3

    echo -e "\n${YELLOW}Deploying $SERVICE_NAME ($APP_NAME)...${NC}"

    # Use 'latest' for manual deploy convenience, or specific SHA if strict
    # Using SHA to match CI behavior
    IMAGE_TAG="$REGISTRY/$REPO_NAME/$SERVICE_NAME:$SHA"
    
    echo "1. Building Docker Image..."
    if ! docker build -t $IMAGE_TAG $DOCKER_CONTEXT; then
        echo -e "${RED}Docker Build Failed${NC}"
        exit 1
    fi
    
    echo "2. Pushing Docker Image..."
    if ! docker push $IMAGE_TAG; then
         echo -e "${RED}Docker Push Failed. Please check 'docker login ghcr.io'${NC}"
         exit 1
    fi
    
    echo "3. Updating Container App (Revision: $SUFFIX)..."
    if ! az containerapp update \
      --name $APP_NAME \
      --resource-group $RESOURCE_GROUP \
      --image $IMAGE_TAG \
      --revision-suffix $SUFFIX \
      --query properties.configuration.activeRevisionsMode; then
        echo -e "${RED}Azure Container App Update Failed${NC}"
        exit 1
    fi

    echo "4. Labeling Revision..."
    REVISION_NAME="$APP_NAME--$SUFFIX"
    az containerapp revision label add \
      --resource-group $RESOURCE_GROUP \
      --name $APP_NAME \
      --label $LABEL \
      --revision $REVISION_NAME \
      --no-prompt

    echo -e "${GREEN}Success! Access '$SERVICE_NAME' at the new label URL in Azure Portal.${NC}"
}

# Check arguments
TARGET=$1
if [[ "$TARGET" == "backend" ]]; then
    deploy_service "backend" $BACKEND_APP "./backend"
elif [[ "$TARGET" == "frontend" ]]; then
    deploy_service "frontend" $FRONTEND_APP "./frontend"
elif [[ "$TARGET" == "all" ]]; then
    deploy_service "backend" $BACKEND_APP "./backend"
    deploy_service "frontend" $FRONTEND_APP "./frontend"
else
    echo "Usage: ./scripts/deploy_manual.sh [backend|frontend|all]"
    exit 1
fi
