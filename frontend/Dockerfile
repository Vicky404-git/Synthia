# Build stage
FROM node:20-alpine AS build
WORKDIR /app

# The API base URL is baked in at build time (Vite requirement).
ARG VITE_API_BASE_URL=""
ARG VITE_STT_PROVIDER="browser"
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_STT_PROVIDER=$VITE_STT_PROVIDER

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

# Serve stage
FROM nginx:1.27-alpine AS serve
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1
