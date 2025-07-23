#!/bin/bash

set -e

# Read number of domain .env files
domain_envs=(domain*.env)
num_domains=${#domain_envs[@]}

if [[ $num_domains -eq 0 ]]; then
  echo "No domain .env files found. Nothing to delete."
  exit 0
fi

env_file="bootnode.env"
if [[ -f "$env_file" ]]; then
  echo "Removing $env_file..."
  rm -f "$env_file"
fi

echo "Detected $num_domains domain setups to delete."

# Remove generated files only
for (( i=1; i<=num_domains; i++ )); do
  compose_file="domain${i}-geth-network.yml"
  env_file="domain${i}.env"

  if [[ -f "$compose_file" ]]; then
    echo "Removing $compose_file..."
    rm -f "$compose_file"
  fi

  if [[ -f "$env_file" ]]; then
    echo "Removing $env_file..."
    rm -f "$env_file"
  fi

done



echo "Cleanup complete."
