import yaml
import sys

def generate_docker_compose(num_nodes):
    # Define the base networks configuration
    docker_compose = {
        "version": "3.7",
        "networks": {
            "dlt_network": {
                "name": "dlt_network",
                "driver": "bridge",
                "ipam": {
                    "config": [
                        {"subnet": "172.18.0.0/24"}
                    ]
                }
            }
        },
        "services": {}
    }

    # Add base services (InfluxDB and Grafana)
    docker_compose["services"]["influxdb"] = {
        "image": "influxdb:1.8",
        "container_name": "influxdb",
        "ports": ["8086:8086"],
        "environment": {
            "INFLUXDB_HTTP_FLUX_ENABLED": "false",
            "INFLUXDB_HTTP_AUTH_ENABLED": "false",
            "INFLUXDB_DB": "geth"
        },
        "networks": {
            "dlt_network": {"ipv4_address": "172.18.0.2"}
        },
        "restart": "always"
    }

    docker_compose["services"]["grafana"] = {
        "image": "grafana/grafana:latest",
        "container_name": "grafana",
        "ports": ["3000:3000"],
        "volumes": [
            "./grafana/datasources:/etc/grafana/provisioning/datasources",
            "./grafana/dashboards:/etc/grafana/provisioning/dashboards"
        ],
        "environment": {
            "GF_SECURITY_ADMIN_USER": "desire6g",
            "GF_SECURITY_ADMIN_PASSWORD": "desire6g2024;"
        },
        "depends_on": ["influxdb"],
        "networks": {
            "dlt_network": {"ipv4_address": "172.18.0.3"}
        },
        "restart": "always"
    }

    # Add the bootnode service
    docker_compose["services"]["bootnode"] = {
        "image": "dlt-node",
        "container_name": "bootnode",
        "hostname": "bootnode",
        "volumes": ["../config/dlt-local/bootnode.env:/dlt-network/.env"],
        "command": "./bootnode_start.sh",
        "networks": {
            "dlt_network": {"ipv4_address": "172.18.0.4"}
        },
        "restart": "always"
    }

    # Add dynamically created nodes based on the user input
    for i in range(1, num_nodes + 1):
        node_service = {
            f"node{i}": {
                "image": "dlt-node",
                "container_name": f"node{i}",
                "hostname": f"node{i}",
                "depends_on": ["bootnode"],
                "volumes": [
                    f"../config/dlt-local/node{i}.env:/dlt-network/.env",
                    f"../config/dlt/genesis/genesis_{num_nodes}_validators.json:/dlt-network/genesis.json"
                ],
                "command": "./node_start.sh",
                "ports": [f"{3333 + i}:{3333 + i}"],
                "networks": {
                    "dlt_network": {
                        "ipv4_address": f"172.18.0.{4 + i}"
                    }
                },
                "restart": "always"
            }
        }
        docker_compose["services"].update(node_service)

    # Save the final Docker Compose file
    with open("docker-compose.yml", "w") as compose_file:
        yaml.dump(docker_compose, compose_file, default_flow_style=False)

    print(f"docker-compose.yml generated successfully with {num_nodes} nodes.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 generate_local_docker_compose.py <number_of_nodes>")
        sys.exit(1)

    num_nodes = int(sys.argv[1])
    generate_docker_compose(num_nodes)
