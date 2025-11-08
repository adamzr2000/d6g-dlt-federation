# Kubernetes orchestrator

1. Build the Docker image
```shell
./build.sh
```

2. Deploy
```shell
./run.sh
```

## Endpoints

### Health check
```shell
curl -s http://localhost:6665/health | jq
```
---
### Apply manifest:
```shell
curl -s -X POST "http://localhost:6665/apply?wait=true" -F "file=@alpine-service.yaml" | jq
```
---
### List deployments:
```shell
curl -s http://localhost:6665/deployments | jq
```
---
### Delete manifest:
```shell
curl -s -X POST "http://localhost:6665/delete?wait=true&timeout=60" -F "file=@alpine-service.yaml" | jq
```
---
### Delete all:
```shell
curl -s -X POST "http://localhost:6665/deployments/delete_all?wait=true&timeout=60" | jq
```


