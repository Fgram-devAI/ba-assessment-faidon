FROM node:20-alpine

WORKDIR /app

# Copy package files and install dependencies
COPY typescript/package.json typescript/package-lock.json ./
RUN npm ci && npm install tsx

# Copy source code and shared files
COPY typescript/src ./src
COPY typescript/tsconfig.json ./
COPY samples ../samples

EXPOSE 3000

CMD ["npx", "tsx", "src/app.ts"]