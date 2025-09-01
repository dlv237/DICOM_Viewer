FROM node:20-slim

WORKDIR /app

# Accept API base URL at build time
ARG VITE_API_URL=
ENV VITE_API_URL=${VITE_API_URL}

COPY frontend/package.json frontend/tsconfig.json frontend/vite.config.ts frontend/index.html ./
COPY frontend/src ./src

RUN npm install && npm run build

EXPOSE 5173

# Use a tiny static server
RUN npm install -g serve

CMD ["serve", "-s", "dist", "-l", "5173"]
