# syntax=docker/dockerfile:1

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# In-app docs and agent-skill links point at this release's tag (A-197); release.yml sets both.
ARG DEPLOYER_REPO=nyx-ulrix/deployer
ARG DEPLOYER_REF=main
RUN VITE_DEPLOYER_REPO="$DEPLOYER_REPO" VITE_DEPLOYER_REF="$DEPLOYER_REF" npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
