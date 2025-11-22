# utils.py

import requests
import logging
import csv
import requests
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
import os
import json
import copy
from yaml.representer import SafeRepresenter

# Get the logger defined in main.py
logger = logging.getLogger(__name__)

def truncate_text(s: str, max_lines=50, max_chars=5000):
    lines = s.splitlines()
    if len(lines) > max_lines:
        s = "\n".join(lines[:max_lines]) + f"\n... (truncated, +{len(lines)-max_lines} lines)"
    if len(s) > max_chars:
        s = s[:max_chars] + f"\n... (truncated to {max_chars} chars)"
    return s

def extract_service_requirements(formatted_requirements: str) -> dict:
    requirements_dict = {}
    
    # Split the string by ';' and process each key-value pair
    for entry in formatted_requirements.split(";"):
        entry = entry.strip()
        if "=" in entry:  # Ensure valid key-value pairs
            key, value = entry.split("=", 1)
            key = key.strip()
            value = value.strip()
            
            # Convert numeric values from string to appropriate type
            if value.isdigit():
                value = int(value)
            elif value.replace(".", "", 1).isdigit():  # Handle float values
                value = float(value)
            elif value.lower() == "none":  # Convert 'None' string to Python None
                value = None
            
            requirements_dict[key] = value
    
    return requirements_dict

def create_csv_file(file_path, header, data):
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)  # ensure /experiments exists

    with open(file_path, 'w', encoding='UTF8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(data)
    logger.info(f"Data saved to {file_path}")

def _log_http_error(url: str, resp: Optional[requests.Response] = None, exc: Optional[Exception] = None):
    """Log server response body only on error."""
    if resp is not None:
        body = None
        try:
            body = resp.text
        except Exception:
            body = "<no body>"
        logger.error("HTTP error %s for %s\n%s", resp.status_code, url, body)
    elif exc is not None:
        logger.error("HTTP error calling %s: %s", url, exc)

def _request_json(method: str, url: str, *, timeout: int = 10, **kwargs):
    """Request expecting JSON; log error body on failure; raise on bad status."""
    try:
        r = requests.request(method, url, timeout=timeout, **kwargs)
        if not r.ok:
            _log_http_error(url, resp=r)
            r.raise_for_status()
        return r.json()
    except requests.HTTPError:
        raise
    except Exception as e:
        _log_http_error(url, exc=e)
        raise

def _request_bytes(method: str, url: str, *, timeout: int = 30, **kwargs) -> bytes:
    """Request expecting bytes; log error body on failure; raise on bad status."""
    try:
        r = requests.request(method, url, timeout=timeout, **kwargs)
        if not r.ok:
            _log_http_error(url, resp=r)
            r.raise_for_status()
        return r.content
    except requests.HTTPError:
        raise
    except Exception as e:
        _log_http_error(url, exc=e)
        raise

def ipfs_add(file_path: str, api_base: str, pin: bool = True, timeout: int = 30):
    url = f"{api_base}/add"
    params = {"pin": "true" if pin else "false"}
    basename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        files = {"file": (basename, f)}
        # returns NDJSON; we’ll parse manually but still get error-logging
        try:
            r = requests.post(url, params=params, files=files, timeout=timeout)
            if not r.ok:
                _log_http_error(url, resp=r)
                r.raise_for_status()
        except requests.HTTPError:
            raise
        except Exception as e:
            _log_http_error(url, exc=e)
            raise

    objs = [json.loads(line) for line in r.text.strip().splitlines() if line.strip()]
    obj = next((o for o in objs if o.get("Name") == basename), objs[-1])
    return obj  # { "Hash": ..., "Name": ..., "Size": ... }

def ipfs_cat(cid: str, api_base: str, timeout: int = 30, decode: bool = True) -> str:
    url = f"{api_base}/cat"
    content = _request_bytes("POST", url, timeout=timeout, params={"arg": cid})
    if decode:
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("latin-1", errors="replace")
    return content

def load_json_text(s: str) -> Dict[str, Any]:
    data = json.loads(s)
    if not isinstance(data, dict):
        raise ValueError("Top-level JSON must be an object")
    return data

def load_yaml_file(path: str) -> List[Dict[str, Any]]:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"YAML file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        docs = [doc for doc in yaml.safe_load_all(f) if isinstance(doc, dict)]
    if not docs:
        raise ValueError(f"No YAML documents found in: {path}")
    return docs

class _LiteralStr(str):
    """Marker to dump a Python str using YAML literal block style ('|')."""
    pass

def _literal_str_representer(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')

class _LiteralDumper(yaml.SafeDumper):
    pass

_LiteralDumper.add_representer(_LiteralStr, _literal_str_representer)


def _beautify_multus_nad_config(obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    If obj is a NetworkAttachmentDefinition and spec.config is a JSON string,
    dump it as a YAML literal block (|) and pretty-indent the JSON.
    """
    if not isinstance(obj, dict):
        return obj
    if obj.get("kind") != "NetworkAttachmentDefinition":
        return obj

    spec = obj.get("spec") or {}
    cfg = spec.get("config")
    if isinstance(cfg, str) and cfg.strip():
        pretty = cfg.strip()
        # Try to pretty-print JSON if valid; otherwise keep as-is
        try:
            pretty = json.dumps(json.loads(pretty), indent=2)
        except Exception:
            pass
        # Ensure trailing newline so the block prints cleanly
        spec["config"] = _LiteralStr(pretty + ("\n" if not pretty.endswith("\n") else ""))
        obj["spec"] = spec
    return obj

def get_vxlan_network_config(
    docs: List[Dict[str, Any]],
    overlay_name: Optional[str] = None,
) -> Dict[str, Any]:
    for doc in docs:
        if doc.get("kind") == "NetworkOverlayConfig":
            if overlay_name and doc.get("metadata", {}).get("name") != overlay_name:
                continue
            spec = doc.get("spec", {}) or {}
            net = spec.get("network", {}) or {}
            endpoints = spec.get("endpoints", []) or []
            return {
                "name": doc.get("metadata", {}).get("name"),
                "vni": net.get("vni"),
                "overlaySubnet": net.get("overlaySubnet"),
                "udpPort": net.get("udpPort"),
                "endpoints": [e.get("name") for e in endpoints if isinstance(e, dict)],
            }
    raise ValueError("No NetworkOverlayConfig found"
                     + (f" with name '{overlay_name}'" if overlay_name else ""))

def _find_overlay(
    docs: List[Dict[str, Any]],
    overlay_name: str
) -> Dict[str, Any]:
    for doc in docs:
        if doc.get("kind") == "NetworkOverlayConfig" and doc.get("metadata", {}).get("name") == overlay_name:
            spec = doc.get("spec", {}) or {}
            net = spec.get("network", {}) or {}
            endpoints = spec.get("endpoints", []) or []
            return {
                "name": overlay_name,
                "vni": net.get("vni"),
                "overlaySubnet": net.get("overlaySubnet"),
                "udpPort": net.get("udpPort"),
                "protocol": net.get("protocol"),
                "endpoints": [e.get("name") for e in endpoints if isinstance(e, dict)],
            }
    raise ValueError(f"No NetworkOverlayConfig found with name '{overlay_name}'")

def get_vtep_node_config(
    docs: List[Dict[str, Any]],
    node_name: str,
    overlay_name: Optional[str] = None,
    include_overlay: bool = True,
) -> Dict[str, Any]:
    # First locate the VTEP node
    match: Dict[str, Any] = {}
    for doc in docs:
        if doc.get("kind") == "VtepNodeConfig" and doc.get("metadata", {}).get("name") == node_name:
            spec = doc.get("spec", {}) or {}
            match = {
                "name": node_name,
                "overlayRef": spec.get("overlayRef"),
                "endpointRef": spec.get("endpointRef"),
                "vtepIP": spec.get("vtepIP"),
                "addressPool": spec.get("addressPool"),
            }
            break
    if not match:
        raise ValueError(f"No VtepNodeConfig found for node '{node_name}'")

    # If caller specified an overlay_name, ensure it matches the node's overlayRef
    if overlay_name is not None and match.get("overlayRef") != overlay_name:
        raise ValueError(
            f"VTEP '{node_name}' overlayRef='{match.get('overlayRef')}' "
            f"does not match requested overlay_name='{overlay_name}'"
        )

    # Optionally attach overlay details (resolve either requested overlay_name or node's overlayRef)
    if include_overlay:
        resolved_overlay_name = overlay_name or match.get("overlayRef")
        if resolved_overlay_name:
            match["overlay"] = _find_overlay(docs, resolved_overlay_name)

    return match

def get_k8s_manifest(
    docs: List[Dict[str, Any]],
    include_kinds: Optional[List[str]] = None,
    as_yaml: bool = False,
):
    """
    Collect a unified manifest of selected Kubernetes resource kinds.
    Defaults: Pod, Deployment, Service, NetworkAttachmentDefinition (Multus).
    Returns list[dict], or multi-doc YAML if as_yaml=True.
    """
    default_kinds = {"Pod", "Deployment", "Service", "NetworkAttachmentDefinition"}
    kinds = set(include_kinds) if include_kinds else default_kinds

    selected = [d for d in docs if isinstance(d, dict) and d.get("kind") in kinds]
    if not selected:
        raise ValueError(f"No Kubernetes manifests found for kinds: {sorted(kinds)}")

    # Work on a copy so we don’t mutate the original docs
    selected = [copy.deepcopy(d) for d in selected]
    # Beautify Multus NAD config so it prints as a literal block
    selected = [_beautify_multus_nad_config(d) for d in selected]

    if as_yaml:
        # Use our dumper that knows how to print _LiteralStr with '|'
        return "\n---\n".join(
            yaml.dump(d, Dumper=_LiteralDumper, sort_keys=False).strip() for d in selected
        )

    return selected


def vxlan_create(vni: int, iface: str, port: int, vxlan_ip: str,
                 remote_ips: List[str], base_url: str):
    url = f"{base_url}/vxlan"
    return _request_json("POST", url, timeout=20, json={
        "vni": vni, "iface": iface, "port": port,
        "vxlan_ip": vxlan_ip, "remote_ips": remote_ips
    })

def vxlan_add_peers(vxlan_iface: str, peers: List[str], base_url: str):
    url = f"{base_url}/vxlan/{vxlan_iface}/peers"
    return _request_json("POST", url, timeout=20, json={"peers": peers})

def vxlan_delete_peers(vxlan_iface: str, peers: List[str], base_url: str) -> Dict[str, Any]:
    url = f"{base_url}/vxlan/{vxlan_iface}/peers"
    return _request_json("DELETE", url, timeout=20, json={"peers": peers})

def vxlan_delete(vxlan_iface: str, base_url: str):
    url = f"{base_url}/vxlan/{vxlan_iface}"
    return _request_json("DELETE", url, timeout=20)

def vxlan_ping(dst: str, base_url: str, count: int = 4, interval: float = 1.0, timeout: int = 10) -> Dict[str, Any]:
    url = f"{base_url}/ping"
    return _request_json("GET", url, timeout=timeout, params={"dst": dst, "count": count, "interval": interval})


def k8s_apply_text(yaml_text: str, base_url: str, *, wait: bool = False,
                   namespace: str = "default", timeout: int = 120):
    url = f"{base_url}/apply"
    params = {
        "wait": "true" if wait else "false",
        "namespace": namespace,
        "timeout": str(timeout),
    }
    files = {"file": ("manifest.yaml", yaml_text.encode("utf-8"), "application/yaml")}
    return _request_json("POST", url, params=params, files=files, timeout=timeout)

def k8s_delete_all(base_url: str, *, wait: bool = False,
                   namespace: str = "default", timeout: int = 120) -> Dict[str, Any]:
    """
    POST /deployments/delete_all with query params.
    Mirrors: curl -X POST "{base_url}/deployments/delete_all?wait=true&timeout=60"
    """
    url = f"{base_url}/deployments/delete_all"
    params = {
        "wait": "true" if wait else "false",
        "namespace": namespace,
        "timeout": str(timeout),
    }
    return _request_json("POST", url, params=params, timeout=timeout)

def pretty(obj):  # tiny helper
    print(json.dumps(obj, indent=2))


def sdn_clear_all_tables(base_url: str, timeout: int = 120) -> Dict[str, Any]:
    """
    Call the SDN controller to clear all Tofino tables.

    Equivalent to:
      curl -X DELETE http://<host>:8080/d6g-controller-API
    """
    url = base_url.rstrip("/")
    # logger.info("SDN: clearing all Tofino tables via %s", url)
    return _request_json("DELETE", url, timeout=timeout)


def sdn_config_detnet_path(
    base_url: str,
    src_ip: str,
    dst_ip: str,
    tos_field: int,
    timeout: int = 120,
) -> Dict[str, Any]:
    """
    Configure DetNet/Tofino tables for a given (src_ip, dst_ip, tos_field).

    Equivalent to:
      curl -X POST $SDNc -H "Content-Type: application/json" -d '{
        "action":"config",
        "src_ip":"10.3.202.67",
        "dst_ip":"10.11.7.6",
        "tos_field":5
      }'
    """
    url = base_url.rstrip("/")
    payload = {
        "action": "config",
        "src_ip": src_ip,
        "dst_ip": dst_ip,
        "tos_field": tos_field,
    }
    # logger.info(
    #     "SDN: applying DetNet config via %s (src_ip=%s, dst_ip=%s, tos=%s)",
    #     url, src_ip, dst_ip, tos_field
    # )
    return _request_json("POST", url, timeout=timeout, json=payload)
