docker run \
    -it \
    --name node1 \
    --hostname node1 \
    --rm \
    --net host \
    -v $(pwd)/../config/dlt/node1.env:/dlt-network/node1.env \
    dlt-node:latest
