#!/bin/bash

# Configuration
RESOURCE_GROUP="Dalle2"
BACKEND_APP="daom-backend"
FRONTEND_APP="daom-frontend"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}Syncing .env to Azure Container Apps...${NC}"

# 1. Check Auth
if ! az account show > /dev/null 2>&1; then
    echo -e "${RED}Error: Not logged in to Azure CLI.${NC}"
    echo "Please run: az login"
    exit 1
fi

# 2. Check .env
if [ ! -f .env ]; then
    echo -e "${RED}Error: .env file not found in current directory.${NC}"
    exit 1
fi

# 3. Parse .env and build argument list
# Filter out comments and empty lines
ENV_VARS=""
while IFS= read -r line || [[ -n "$line" ]]; do
    # Skip comments and empty lines
    if [[ $line =~ ^#.* ]] || [[ -z $line ]]; then
        continue
    fi
    # Append to list (space separated key=value)
    # Quote the value part to handle spaces if any (though env vars usually don't have spaces)
    # Actually az cli expects space separated KEY=VAL
    ENV_VARS+="$line "
done < .env

echo -e "Found $(echo $ENV_VARS | wc -w) variables to sync."

# 4. Update Backend
echo -e "\n${YELLOW}Updating Backend ($BACKEND_APP)...${NC}"
az containerapp update \
    --name $BACKEND_APP \
    --resource-group $RESOURCE_GROUP \
    --set-env-vars $ENV_VARS \
    --no-prompt

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Backend Updated Successfully!${NC}"
else
    echo -e "${RED}Backend Update Failed${NC}"
fi

# 5. Update Frontend (Optional, usually frontend env vars are build-time, but verify)
# Frontend main env var is VITE_API_BASE_URL which is build-time.
# Runtime env vars for frontend container are usually not used unless for server-side serving (which nginx might check?)
# But safe to skip if not needed.
# However, if your frontend node server needs something, add here.
# For now, we only sync to Backend as per config.py needs.

echo -e "\n${GREEN}Done! Container Apps will restart automatically with new settings.${NC}"
