# Multus and VXLAN Setup Script

## Prerequisites

- Kubernetes cluster (e.g., [K3s distribution](https://docs.k3s.io/)) with [Multus CNI](https://docs.k3s.io/networking/multus-ipams) installed

## Execute the Setup Script

Run the script with the required parameters:

```sh
./multus_and_vxlan_setup.sh -l <local_ip> -r <remote_ip> -i <interface_name> -v <vxlan_id> -p <dst_port> -s <subnet> -d <ip_range> [-n <network_name> (default: federation-net)]
```

```sh
./multus_and_vxlan_setup.sh -l 10.5.99.1 -r 10.5.99.2 -i ens3 -v 200 -p 4789 -s 10.0.0.0/16 -d 10.0.1.2-10.0.1.10
```

```sh
./multus_and_vxlan_setup.sh -l 10.5.99.2 -r 10.5.99.1 -i ens3 -v 200 -p 4789 -s 10.0.0.0/16 -d 10.0.2.2-10.0.2.10
```

```sh
kubectl apply -f alpine-pod.yaml
```

## Clean the Setup

Run the cleanup script:

```sh
./clean_multus_and_vxlan_setup.sh -n <network_name> -v <vxlan_id>
```

## Cluster Installation

To effortlessly set up a fully-functional, single-node Kubernetes cluster, execute the following command:
```bash
curl -sfL https://get.k3s.io | sh -
```

This single-node will function as a server, including all the `datastore`, `control-plane`, `kubelet`, and `container runtime` components necessary to host workload pods. 

After installing k3s, use the `export KUBECONFIG="/etc/rancher/k3s/k3s.yaml"` environment variable to specify to `kubectl` the location of the [kubeconfig](https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/) file required for cluster configuration.

To ensure permanent application of this environment variable during startup, add it to either `~/.bash_profile` or `~/.bashrc` files:
```bash
echo 'export KUBECONFIG="/etc/rancher/k3s/k3s.yaml"' >> ~/.bashrc
```


## Multus Installation

Multus is a CNI (Container Network Interface) plugin for Kubernetes that allows pods to connect to multiple networks. This is particularly useful for advanced networking configurations where pods need to interact with multiple interfaces, such as overlay networks or external systems.

In lightweight Kubernetes distributions like K3s, you can easily install Multus using Helm. If you don’t have Helm installed, you can install it using: `sudo snap install helm --classic`

For more details, visit the [Helm documentation](https://helm.sh/docs/intro/install/).


Add the Helm repository for RKE2 charts and update it:
```bash
helm repo add rke2-charts https://rke2-charts.rancher.io
helm repo update
```

Install Multus CNI using Helm in the `kube-system` namespace:
```bash
helm install multus rke2-charts/rke2-multus -n kube-system --kubeconfig /etc/rancher/k3s/k3s.yaml --values multus-values.yaml
```

Check the Multus installation:
```bash
kubectl get pods --all-namespaces | grep -i multus
```

## Utilities

Reset IPAM IP address allocation for a specific network:
```bash
sudo rm /var/lib/cni/networks/federation-net/*
```

To access the terminal of a running Alpine pod, use:
```bash
kubectl exec -it <pod-name> -- sh
```

To inspect detailed information about a Multus network configuration:
```bash
kubectl describe network-attachment-definitions.k8s.cni.cncf.io
```


