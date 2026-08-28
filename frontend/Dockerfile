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

# Where Django is *while this image is being built*.
#
# Not a runtime setting. M15 made the public catalogue statically generated
# (invariant 15), so `next build` reads every published course and bakes it
# into the HTML — which means the build needs a reachable API, and this image's
# build is a build like any other. Without this the builder inherits the
# localhost default, finds nothing listening inside the container, and
# `CatalogueUnavailable` stops it. That is abuse case 6 behaving exactly as
# designed, in a context that had not been given an API.
#
# Supplied by CI with `--network=host`, so `localhost` here is the runner's
# localhost, where the job has already started Django.
#
# **This is a deployment constraint, not just a CI one.** Whatever builds the
# release image — Render, a Workers pipeline, a laptop — must be able to reach
# the API at build time. There is no fallback by design: a build that cannot
# read the catalogue must fail rather than ship a site where every course
# silently disappeared.
ARG API_ORIGIN
ENV API_ORIGIN=${API_ORIGIN}

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
