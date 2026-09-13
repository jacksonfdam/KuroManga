FROM node:22-alpine AS build
WORKDIR /app
# The image ships npm 10, which ignores the `libc` field newer npm writes for
# platform-specific optional dependencies — it then skips the musl build of
# Rolldown's native binding and the build dies claiming the package is missing.
# Matching the npm that writes the lockfile keeps that from depending on whose
# machine ran the install.
RUN npm install -g npm@11
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile
