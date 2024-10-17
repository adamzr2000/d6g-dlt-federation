#!/bin/bash

# Check if pod name and network name arguments are provided
if [ -z "$1" ] || [ -z "$2" ]; then
  echo "Usage: $0 <pod_name> <network_name>"
  exit 1
fi

POD_NAME=$1
NETWORK_NAME=$2

# Fetch the current pod configuration in JSON format
POD_CONFIG=$(kubectl get pod $POD_NAME -o json)

# Check if the pod exists
if [ $? -ne 0 ]; then
  echo "Pod '$POD_NAME' not found."
  exit 1
fi

# Extract the pod's image, command, and other relevant data from the existing configuration
IMAGE=$(echo $POD_CONFIG | jq -r '.spec.containers[0].image')

# Delete the existing pod
kubectl delete pod $POD_NAME

# Recreate the pod with the previous configuration and the new network annotation
kubectl run $POD_NAME \
  --image=$IMAGE \
  --restart=Never \
  --overrides='{
    "metadata": {
      "annotations": {
        "k8s.v1.cni.cncf.io/networks": "'$NETWORK_NAME'"
      }
    },
    "spec": {
      "containers": [
        {
          "name": "'$POD_NAME'",
          "image": "'$IMAGE'"
        }
      ]
    }
  }'

# Check if the operation was successful
if [ $? -eq 0 ]; then
  echo "Successfully recreated pod '$POD_NAME' with network '$NETWORK_NAME'."
else
  echo "Failed to recreate pod '$POD_NAME' with network '$NETWORK_NAME'."
fi
