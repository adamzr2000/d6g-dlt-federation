

```bash
sudo ./start_app.sh
screen -XS dummy-orchestrator quit
```

```bash
curl http://localhost:9999/catalog/consumer-app.yaml
curl http://localhost:9999/topology/consumer-net.yaml

# Download with:
curl -O http://10.5.15.55:9999/catalog/consumer-app.yaml
```

```bash
curl -X POST http://10.5.15.16:9999/configure_router \
     -H "Content-Type: application/json" \
     -d '{
           "sudo_password": "netcom;",
           "local_ip": "10.5.15.16",
           "remote_ip": "10.5.98.105",
           "interface": "eno1",
           "vni": 100,
           "dst_port": 4789,
           "destination_network": "192.168.70.0/24",
           "tunnel_ip": "172.28.0.1/30",
           "gateway_ip": "172.28.0.2"
         }'
```

```bash
curl -X POST http://10.5.98.105:9999/configure_router \
     -H "Content-Type: application/json" \
     -d '{
           "sudo_password": "netcom;",
           "local_ip": "10.5.98.105",
           "remote_ip": "10.5.15.16",
           "interface": "enp7s0",
           "vni": 100,
           "dst_port": 4789,
           "destination_network": "10.11.7.0/24",
           "tunnel_ip": "172.28.0.2/30",
           "gateway_ip": "172.28.0.1"
         }'
```

```bash
curl -X POST http://10.5.15.16:9999/remove_vxlan \
     -H "Content-Type: application/json" \
     -d '{
           "sudo_password": "netcom;",
           "vni": 100,
           "destination_network": "192.168.70.0/24"
         }'

```

```bash
curl -X POST http://10.5.98.105:9999/remove_vxlan \
     -H "Content-Type: application/json" \
     -d '{
           "sudo_password": "netcom;",
           "vni": 100,
           "destination_network": "10.11.7.0/24"
         }'
```

```bash
curl -X POST http://10.5.15.16:9999/test_connectivity \
     -H "Content-Type: application/json" \
     -d '{
           "target": "8.8.8.8"
         }'
```

```bash
# groot (d6g-gw)
sudo ./vxlan_router_setup.sh -l 10.5.15.16 -r 10.5.98.105 -i eno1 -v 100 -p 4789 -n 192.168.70.0/24 -a 172.28.0.1/30 -g 172.28.0.2
sudo ./remove_vxlan.sh -v 100 -n 192.168.70.0/24

# predict-6g-gw
sudo ./vxlan_router_setup.sh -l 10.5.98.105 -r 10.5.15.16 -i enp7s0 -v 100 -p 4789 -n 10.11.7.0/24 -a 172.28.0.2/30 -g 172.28.0.1
sudo ./remove_vxlan.sh -v 100 -n 10.11.7.0/24
```
