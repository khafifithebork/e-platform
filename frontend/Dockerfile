# syntax=docker/dockerfile:1

# Frontend image. Two runnable targets:
#
#   --target dev      next dev, for docker compose
#   --target runtime  standalone server bundle, for deployment
#
# ADR-002 recommends running Next.js on Cloudflare Workers, which needs no
# container at all. ADR-001 section 2.3 keeps that decision until M13, so this
# image exists to keep the Render and Dokploy paths open.

# ---------------------------------------------------------------------------
# Dependencies
#
# Keyed on the lockfiles alone so editing a component is a cache hit rather
# than a reinstall. `npm ci` rather than `npm install`: it installs exactly the
# locked tree and fails if package.json and the lockfile disagree.
# ---------------------------------------------------------------------------
FROM node:22-slim AS deps

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---------------------------------------------------------------------------
# Development
#
# The compose file bind-mounts the source over /app, so this stage exists to
# provide node_modules and the toolchain rather than a fixed copy of the code.
# ---------------------------------------------------------------------------
FROM node:22-slim AS dev

ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

USER node
EXPOSE 3000
CMD ["npm", "run", "dev"]

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
FROM node:22-slim AS builder

ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ---------------------------------------------------------------------------
# Runtime
#
# Copies the standalone bundle rather than node_modules. `node server.js`
# directly, not `npm start` — npm adds a process that forwards signals
# imperfectly, and a container that ignores SIGTERM is a container that gets
# killed hard on every deploy.
# ---------------------------------------------------------------------------
FROM node:22-slim AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

WORKDIR /app

# `node` is a non-root user the base image already provides.
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public

USER node
EXPOSE 3000
CMD ["node", "server.js"]
