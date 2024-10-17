#!/bin/bash

# Function to prompt the user for input and validate it
prompt_and_validate_input() {
  local prompt_message="$1"
  local variable_name="$2"
  local validation_pattern="$3"

  while true; do
    echo "$prompt_message"
    read -r $variable_name  # Remove the double quotes
    if [[ ! ${!variable_name} =~ $validation_pattern ]]; then  # Use ${!variable_name} to access the variable's value
      echo "Invalid input. Please try again."
    else
      break
    fi
  done
}

# Prompt for the number of geth nodes to add (>0 and <=50)
prompt_and_validate_input "Please enter the number of geth nodes to add [>0]:" numNodesToAdd '^[1-9][0-9]*$'

# Read the current number of nodes from .env file
source .env
currentNumNodes=$NUM_NODES

# Calculate the new total number of nodes
newNumNodes=$((currentNumNodes + numNodesToAdd))

echo "Adding $numNodesToAdd new nodes to the network."

# Update the .env file with the new total number of nodes
sed -i "s/NUM_NODES=$currentNumNodes/NUM_NODES=$newNumNodes/g" .env

# Node creation and account generation for the new nodes
for (( i=currentNumNodes+1; i<=$newNumNodes; i++ ))
do
  mkdir "node$i"
  # Generate new account. Assumes password.txt is in the current directory.
  addr=$(geth --datadir node$i account new --password password.txt 2>&1 | grep "Public address of the key" | awk '{print $NF}')

  # Update .env file with node configuration
  echo "# node$i config" >> .env
  echo "IP_NODE_$i=127.0.0.1" >> .env
  echo "ETHERBASE_NODE_$i=$addr" >> .env
  echo "WS_PORT_NODE_$i=$((3333 + $i))" >> .env
  echo "RPC_PORT_NODE_$i=$((8550 + $i))" >> .env
  echo "ETH_PORT_NODE_$i=$((30302 + $i))" >> .env

  # Prepare node$i_start.sh
  cat << EOF > "node${i}_start.sh"
#!/bin/bash

# Execute the geth init command to initialize the data directory with genesis.json
output=\$(geth init --datadir node$i genesis.json)
echo "\$output"

# Read environment variables from .env file
source .env

# Define the command
command="geth --identity 'node$i' --datadir node$i --syncmode 'full' --ws --ws.addr \$IP_NODE_$i --ws.port \$WS_PORT_NODE_$i --port \$ETH_PORT_NODE_$i --bootnodes \$BOOTNODE_URL --ws.api 'eth,net,web3,personal,miner,admin,clique' --networkid \$NETWORK_ID --nat 'any' --allow-insecure-unlock --authrpc.port \$RPC_PORT_NODE_$i --ipcdisable --unlock \$ETHERBASE_NODE_$i --password password.txt --mine --snapshot=false --miner.etherbase \$ETHERBASE_NODE_$i"

# Add verbosity option to the command if logs need to be saved
if [ "\$SAVE_LOGS" == "y" ] || [ "\$SAVE_LOGS" == "Y" ]; then
  command="\$command --verbosity 3 >> ./logs/node$i.log 2>&1"
else
  command="\$command"
fi

# Execute the command
eval \$command
EOF

  # Make node$i_start.sh executable
  chmod +x "node${i}_start.sh"

  echo "node$i created and configured."
done

# Update the .env file with the new total number of nodes
sed -i "s/NUM_NODES=$currentNumNodes/NUM_NODES=$newNumNodes/g" .env