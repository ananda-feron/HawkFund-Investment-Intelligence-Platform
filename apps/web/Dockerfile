FROM node:24-alpine AS dependencies
WORKDIR /workspace
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci

FROM node:24-alpine AS development
WORKDIR /workspace
COPY --from=dependencies /workspace/node_modules ./node_modules
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev:web"]

FROM development AS build
RUN npm run build:web

FROM node:24-alpine AS production
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --chown=node:node --from=build /workspace/apps/web/.next/standalone ./
COPY --chown=node:node --from=build /workspace/apps/web/.next/static ./apps/web/.next/static
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["wget", "--spider", "-q", "http://127.0.0.1:3000"]
CMD ["node", "apps/web/server.js"]
