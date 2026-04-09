FROM node:20-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev=false
COPY . .
RUN npx nest build
EXPOSE 3100
CMD ["node", "dist/src/main.js"]
