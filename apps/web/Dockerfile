# Imagem usada no docker-compose (desenvolvimento com hot reload).
FROM node:20-slim

WORKDIR /app

RUN corepack enable

COPY package.json ./
RUN corepack pnpm install

COPY . .

EXPOSE 3000

CMD ["corepack", "pnpm", "dev"]
