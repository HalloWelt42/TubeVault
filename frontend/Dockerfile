FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install --prefer-offline --no-audit
COPY . .
RUN npm run build

FROM nginx:alpine
LABEL maintainer="HalloWelt42"
LABEL version="1.1.0"
LABEL description="TubeVault Frontend – Svelte 5 SPA"

# curl für Healthcheck
RUN apk add --no-cache curl

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
