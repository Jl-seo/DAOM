# Build Stage
FROM node:20-slim as build

WORKDIR /app

# Set API URL at build time - this MUST be https for production
ENV VITE_API_BASE_URL=https://daom-backend.greenpebble-00aa1dc4.koreacentral.azurecontainerapps.io/api/v1

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

# Production Stage
FROM nginx:alpine

# Copy built assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Expose port
EXPOSE 80

# Start Nginx
CMD ["nginx", "-g", "daemon off;"]
