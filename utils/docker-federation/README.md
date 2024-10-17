# Docker Network and VXLAN Setup Script

## Prerequisites

- Docker installed
- `brctl` command available (`sudo apt-get install bridge-utils`)

## Execute the Setup Script

Run the script with the required parameters:

```sh
./docker_host_and_vxlan_setup.sh -l <local_ip> -r <remote_ip> -i <interface_name> -v <vxlan_id> -p <dst_port> -s <subnet> -d <ip_range> [-n <network_name> (default: federation-net)]
```


```sh
./docker_host_and_vxlan_setup.sh -l 10.5.99.1 -r 10.5.99.2 -i ens3 -v 200 -p 4789 -s 10.0.0.0/16 -d 10.0.1.0/24
```

```sh
./docker_host_and_vxlan_setup.sh -l 10.5.99.2 -r 10.5.99.1 -i ens3 -v 200 -p 4789 -s 10.0.0.0/16 -d 10.0.2.0/24
```

```sh
sudo docker run --name alpine1 -it --rm --network federation-net alpine
```

```sh
sudo docker run --name alpine2 -it --rm --network federation-net alpine
```

## Clean the Setup

Run the cleanup script:

```sh
./clean_docker_host_and_vxlan_setup.sh -n <network_name> -v <vxlan_id>
```