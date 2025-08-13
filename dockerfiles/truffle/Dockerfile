FROM node:18-alpine

LABEL maintainer="azahir@pa.uc3m.es"

RUN apk add --no-cache --virtual .build-deps \
      python3 make g++ \
  && npm config set fund false \
  && npm config set audit false \
  && npm config set update-notifier false \
  && npm install -g truffle@5 \
  && npm cache clean --force \
  && apk del .build-deps

WORKDIR /smart-contracts

CMD ["sh"]
