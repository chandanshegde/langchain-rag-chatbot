FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# Setting vite to listen on all interfaces
ENV HOST=0.0.0.0
# The port we mapped in docker-compose
EXPOSE 5173

CMD ["npm", "run", "dev"]
