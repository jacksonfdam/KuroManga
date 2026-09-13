# comick-source-api ships no Dockerfile of its own, so the recipe lives here.
# It is a plain Next.js app: fetch the pinned commit, install, build, serve.
FROM node:22-alpine

# Pinned on purpose. Without a ref, every rebuild would run whatever that third
# party pushed to its default branch, as a service on this host. To update,
# read what changed upstream and then move this SHA.
ARG COMICK_REF=ea168fc283466c403d057301df41fc177694c67c

RUN apk add --no-cache git

WORKDIR /app
# Fetching the single commit keeps the image free of the repository's history.
RUN git init -q . \
 && git remote add origin https://github.com/GooglyBlox/comick-source-api.git \
 && git fetch -q --depth 1 origin "${COMICK_REF}" \
 && git checkout -q FETCH_HEAD \
 && rm -rf .git

RUN npm ci && npm run build

ENV PORT=3000 HOSTNAME=0.0.0.0
EXPOSE 3000
CMD ["npm", "run", "start"]
