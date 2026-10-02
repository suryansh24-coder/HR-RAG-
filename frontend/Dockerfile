# syntax=docker/dockerfile:1
#
# HR Nexus web image: build the Vite bundle, then serve it from nginx.
#
# The API is a separate service, so the bundle is built with VITE_API_ORIGIN
# pointing at the public API origin. Leave it empty to keep every call
# same-origin, which is what nginx proxies below.

FROM node:20-alpine AS build

WORKDIR /app

# Dependencies are installed from the lockfile alone so this layer is only
# rebuilt when the dependencies actually change.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ARG VITE_API_ORIGIN=""
ENV VITE_API_ORIGIN=$VITE_API_ORIGIN
RUN npm run build


FROM nginx:1.27-alpine AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
