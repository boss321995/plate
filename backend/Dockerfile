FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 3003
CMD ["npx", "ts-node", "src/index.ts"]
# Cache bust 1
