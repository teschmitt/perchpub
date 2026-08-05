# syntax=docker/dockerfile:1

# PerchPub frontend — SvelteKit (adapter-node) SSR server. Replaces the prior
# nginx-static image: build once, run the Node server on :3000.

# --- build: install deps and compile the adapter-node server ---
FROM node:25-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# --- dev: source + deps for the Vite dev server (docker-compose.override.yml) ---
FROM node:25-slim AS dev
WORKDIR /app
ENV NODE_ENV=development
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# --- runtime: only the built server + its modules (default target) ---
FROM node:25-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
ENV HOST=0.0.0.0
COPY --from=build /app/package.json ./package.json
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/build ./build
EXPOSE 3000
CMD ["node", "build"]
