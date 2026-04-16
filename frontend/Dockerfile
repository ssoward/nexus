FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# Production stage — just the static files
FROM scratch AS dist
COPY --from=builder /app/dist /dist
