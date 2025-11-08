# main.py
import os
import sys
import tempfile
import logging
import uuid
import time
import yaml
from datetime import datetime
from threading import Lock
from typing import List, Tuple, Dict, Any, Set

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse

from kubernetes import client, config, utils
from kubernetes.client import ApiClient
from kubernetes.client.rest import ApiException
from kubernetes.client import V1DeleteOptions

# -------------------------
# Logging
# -------------------------
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("k8s-api")

# -------------------------
# Kubernetes API Initialization
# -------------------------
try:
    config.load_kube_config(config_file="/config/k8s-cluster-config.yaml")
    log.info("Successfully loaded kubeconfig from /config/k8s-cluster-config.yaml")
except Exception as e:
    log.error(f"Failed to load kubeconfig: {e}")
    sys.exit(1)

api_client = ApiClient()
core_api = client.CoreV1Api()
version_api = client.VersionApi()
apps_api = client.AppsV1Api()
custom_api = client.CustomObjectsApi()

# Delete options: foreground + quick termination
DELETE_OPTS = V1DeleteOptions(
    propagation_policy="Foreground",
    grace_period_seconds=0,
)

# -------------------------
# Simple in-memory registry
# -------------------------
# REGISTRY[deployment_id] = {
#   "filename": str,
#   "applied_at": iso8601 str,
#   "objects": List[Tuple[apiVersion, kind, name]],
#   "yaml_text": str,
# }
REGISTRY: Dict[str, Dict[str, Any]] = {}
REGISTRY_LOCK = Lock()

# -------------------------
# FastAPI app
# -------------------------
app = FastAPI(title="K8s Simple Apply/Delete API with Registry")

def _write_temp(upload: UploadFile) -> str:
    suffix = os.path.splitext(upload.filename or "manifest.yaml")[-1] or ".yaml"
    fd, path = tempfile.mkstemp(prefix="k8s-", suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(upload.file.read())
    return path

def _flatten(seq):
    for x in (seq or []):
        if isinstance(x, list):
            yield from _flatten(x)
        else:
            yield x

def _summarize(results: List) -> List[Tuple[str, str, str]]:
    """Extract (apiVersion, kind, metadata.name) from returned objects (handles nested lists)."""
    out = []
    for obj in _flatten(results):
        if isinstance(obj, dict):
            av = obj.get("apiVersion", "unknown")
            kd = obj.get("kind", "unknown")
            nm = (obj.get("metadata") or {}).get("name", "unknown")
            out.append((av, kd, nm))
            continue
        av = getattr(obj, "api_version", None) or "unknown"
        kd = getattr(obj, "kind", None) or obj.__class__.__name__
        md = getattr(obj, "metadata", None)
        nm = getattr(md, "name", None) if md else None
        out.append((av, kd, nm or "unknown"))
    return out

def _wait_ready(objects: List[Tuple[str, str, str]], namespace: str = "default", timeout: int = 120):
    """
    Wait for Pods to be Ready and Deployments to be Available.
    'objects' is the (apiVersion, kind, name) list from _summarize().
    """
    deadline = time.time() + timeout
    pod_names = [n for _, k, n in objects if k == "Pod"]
    dep_names = [n for _, k, n in objects if k == "Deployment"]

    # Pods → Ready
    for name in pod_names:
        while True:
            if time.time() > deadline:
                raise TimeoutError(f"Pod/{name} not Ready within {timeout}s (ns={namespace})")
            p = core_api.read_namespaced_pod(name=name, namespace=namespace)
            conds = p.status.conditions or []
            if any(c.type == "Ready" and c.status == "True" for c in conds):
                break
            time.sleep(1)

    # Deployments → Available and observedGeneration up-to-date
    for name in dep_names:
        while True:
            if time.time() > deadline:
                raise TimeoutError(f"Deployment/{name} not Available within {timeout}s (ns={namespace})")
            d = apps_api.read_namespaced_deployment_status(name=name, namespace=namespace)
            spec_repl = d.spec.replicas or 0
            avail = d.status.available_replicas or 0
            gen_ok = (d.status.observed_generation or 0) >= (d.metadata.generation or 0)
            if gen_ok and avail >= spec_repl:
                break
            time.sleep(1)

def _delete_one(doc: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Delete a single K8s object described by a dict and return (apiVersion, kind, name).
    Gracefully ignores 404 NotFound.
    """
    api_version = str(doc.get("apiVersion", "unknown"))
    kind        = str(doc.get("kind", "unknown"))
    meta        = doc.get("metadata") or {}
    name        = meta.get("name")
    namespace   = meta.get("namespace") or "default"

    if not name or kind == "unknown":
        return (api_version, kind, name or "unknown")

    try:
        # CoreV1 namespaced
        if kind == "Pod":
            core_api.delete_namespaced_pod(name, namespace, body=DELETE_OPTS)
        elif kind == "Service":
            core_api.delete_namespaced_service(name, namespace, body=DELETE_OPTS)
        elif kind == "ConfigMap":
            core_api.delete_namespaced_config_map(name, namespace, body=DELETE_OPTS)
        elif kind == "Secret":
            core_api.delete_namespaced_secret(name, namespace, body=DELETE_OPTS)
        elif kind == "PersistentVolumeClaim":
            core_api.delete_namespaced_persistent_volume_claim(name, namespace, body=DELETE_OPTS)

        # CoreV1 cluster-scoped
        elif kind == "Namespace":
            core_api.delete_namespace(name, body=DELETE_OPTS)

        # AppsV1 namespaced
        elif kind == "Deployment":
            apps_api.delete_namespaced_deployment(name, namespace, body=DELETE_OPTS)
        elif kind == "DaemonSet":
            apps_api.delete_namespaced_daemon_set(name, namespace, body=DELETE_OPTS)
        elif kind == "StatefulSet":
            apps_api.delete_namespaced_stateful_set(name, namespace, body=DELETE_OPTS)
        elif kind == "ReplicaSet":
            apps_api.delete_namespaced_replica_set(name, namespace, body=DELETE_OPTS)

        # Common CRD example: Multus NAD
        elif api_version.startswith("k8s.cni.cncf.io/") and kind == "NetworkAttachmentDefinition":
            # apiVersion: k8s.cni.cncf.io/v1
            _, ver = api_version.split("/", 1)
            custom_api.delete_namespaced_custom_object(
                group="k8s.cni.cncf.io", version=ver,
                namespace=namespace, plural="network-attachment-definitions", name=name,
                body=DELETE_OPTS,
            )

        # Fallback: generic custom object
        else:
            if "/" in api_version:
                group, ver = api_version.split("/", 1)
                plural = kind.lower() + "s"  # naive pluralization
                custom_api.delete_namespaced_custom_object(
                    group, ver, namespace, plural, name, body=DELETE_OPTS
                )
            else:
                pass

    except ApiException as e:
        if e.status != 404:  # ignore NotFound
            raise

    return (api_version, kind, name)

def delete_from_yaml_text(yaml_text: str) -> List[Tuple[str, str, str]]:
    """Delete all docs in a multi-doc YAML string and return a summary list."""
    docs = [d for d in yaml.safe_load_all(yaml_text) if isinstance(d, dict)]
    out: List[Tuple[str, str, str]] = []
    for d in docs:
        out.append(_delete_one(d))
    return out

def _wait_gone(objects: List[Tuple[str, str, str]], namespace: str = "default", timeout: int = 120):
    """
    Wait until each (kind,name) in 'objects' no longer exists in the cluster.
    """
    deadline = time.time() + timeout

    def still_exists(kind: str, name: str) -> bool:
        try:
            if kind == "Pod":
                core_api.read_namespaced_pod(name, namespace)
                return True
            if kind == "Service":
                core_api.read_namespaced_service(name, namespace)
                return True
            if kind == "Deployment":
                apps_api.read_namespaced_deployment(name, namespace)
                return True
            # best effort for unknown kinds: treat as gone
            return False
        except ApiException as e:
            return e.status != 404

    remaining: Set[Tuple[str, str]] = {(k, n) for _, k, n in objects if k and n}
    while remaining:
        if time.time() > deadline:
            still_there = [f"{k}/{n}" for (k, n) in remaining if still_exists(k, n)]
            raise TimeoutError(f"Timeout waiting deletion. Still present: {', '.join(still_there)}")
        for k, n in list(remaining):
            if not still_exists(k, n):
                remaining.discard((k, n))
        time.sleep(0.5)
def apply_from_yaml_text(yaml_text: str, default_namespace: str = "default") -> List[Dict[str, Any]]:
    """
    Apply multi-doc YAML. Handles core kinds via create_from_dict and
    CRDs (e.g., Multus NAD) via CustomObjectsApi. Returns list of created objects (dicts).
    """
    docs = [d for d in yaml.safe_load_all(yaml_text) if isinstance(d, dict)]
    # Ensure NADs go first so Pods referencing them don't fail
    def _order_key(d):
        av = str(d.get("apiVersion", ""))
        kd = str(d.get("kind", ""))
        return 0 if (av.startswith("k8s.cni.cncf.io/") and kd == "NetworkAttachmentDefinition") else 1
    docs.sort(key=_order_key)

    created = []
    for d in docs:
        api_version = str(d.get("apiVersion", ""))
        kind        = str(d.get("kind", ""))
        meta        = d.get("metadata") or {}
        name        = meta.get("name")
        namespace   = meta.get("namespace") or default_namespace

        if api_version.startswith("k8s.cni.cncf.io/") and kind == "NetworkAttachmentDefinition":
            # group/version/plural for Multus NAD
            _, ver = api_version.split("/", 1)
            try:
                obj = custom_api.create_namespaced_custom_object(
                    group="k8s.cni.cncf.io",
                    version=ver,
                    namespace=namespace,
                    plural="network-attachment-definitions",
                    body=d,
                )
            except ApiException as e:
                if e.status == 409:  # Already exists -> patch to be nice
                    obj = custom_api.patch_namespaced_custom_object(
                        group="k8s.cni.cncf.io",
                        version=ver,
                        namespace=namespace,
                        plural="network-attachment-definitions",
                        name=name,
                        body=d,
                    )
                else:
                    raise
            created.append(obj)
        else:
            # Core/standard resources (Pod, Service, Deployment, etc.)
            try:
                objs = utils.create_from_dict(api_client, data=d, namespace=namespace)
                # create_from_dict returns either a model or list; normalize to list
                if isinstance(objs, list):
                    created.extend(objs)
                else:
                    created.append(objs)
            except ApiException as e:
                if e.status == 409:  # Already exists -> best-effort patch
                    try:
                        # Patch via dynamic CustomObjectsApi for CRDs; for core kinds you’d need specific APIs.
                        if "/" in api_version and kind not in {"Pod","Service","ConfigMap","Secret","PersistentVolumeClaim","Deployment","DaemonSet","StatefulSet","ReplicaSet","Namespace"}:
                            group, ver = api_version.split("/", 1)
                            plural = kind.lower() + "s"
                            created.append(custom_api.patch_namespaced_custom_object(
                                group, ver, namespace, plural, name, d
                            ))
                        else:
                            # For brevity, ignore patch for core kinds on 409; they already exist.
                            pass
                    except Exception:
                        pass
                else:
                    raise
    return created


@app.get("/health")
def health():
    """Very basic health check against the cluster."""
    try:
        ver = version_api.get_code()
        nodes = core_api.list_node()
        return {
            "status": "ok",
            "kubernetes_version": {
                "major": ver.major,
                "minor": ver.minor,
                "gitVersion": ver.git_version,
                "platform": ver.platform,
            },
            "nodes_count": len(nodes.items or []),
        }
    except ApiException as e:
        raise HTTPException(status_code=503, detail=f"Kubernetes API error: {e.reason}")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Health check failed: {e}")

@app.post("/apply")
def apply_manifest(
    file: UploadFile = File(...),
    wait: bool = Query(False, description="Wait for Pods/Deployments to become Ready/Available"),
    namespace: str = Query("default", description="Namespace to check readiness in"),
    timeout: int = Query(120, ge=1, le=3600, description="Wait timeout in seconds"),
):
    """
    Apply a single YAML file (multi-doc supported) and track it in the registry.
    Returns a deployment_id for later listing/deletion.
    """
    path = None
    try:
        raw_bytes = file.file.read()
        yaml_text = raw_bytes.decode("utf-8", errors="replace")
        path = tempfile.mkstemp(prefix="k8s-", suffix=".yaml")[1]
        with open(path, "wb") as f:
            f.write(raw_bytes)

        results = apply_from_yaml_text(yaml_text, default_namespace=namespace)
        summary = _summarize(results)

        if wait:
            try:
                _wait_ready(summary, namespace=namespace, timeout=timeout)
            except TimeoutError as te:
                raise HTTPException(status_code=504, detail=str(te))

        deployment_id = str(uuid.uuid4())
        with REGISTRY_LOCK:
            REGISTRY[deployment_id] = {
                "filename": file.filename,
                "applied_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "objects": summary,
                "yaml_text": yaml_text,
            }

        return JSONResponse({
            "status": "applied" if not wait else "applied_and_ready",
            "deployment_id": deployment_id,
            "file": file.filename,
            "objects": [{"apiVersion": a, "kind": k, "name": n} for a, k, n in summary],
            "count": len(summary),
            "wait": wait,
            "namespace": namespace,
            "timeout": timeout,
        })
    except ApiException as e:
        raise HTTPException(status_code=400, detail=f"Apply failed: {e.reason}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Apply failed: {e}")
    finally:
        if path:
            try:
                os.remove(path)
            except Exception:
                pass

@app.post("/delete")
def delete_manifest(
    file: UploadFile = File(...),
    wait: bool = Query(False),
    namespace: str = Query("default"),
    timeout: int = Query(120, ge=1, le=3600),
):
    """
    Delete resources described in the uploaded YAML.
    If wait=true, block until the resources are gone.
    """
    try:
        raw_bytes = file.file.read()
        yaml_text = raw_bytes.decode("utf-8", errors="replace")

        summary = delete_from_yaml_text(yaml_text)
        if wait:
            try:
                _wait_gone(summary, namespace=namespace, timeout=timeout)
            except TimeoutError as te:
                raise HTTPException(status_code=504, detail=str(te))

        return JSONResponse({
            "status": "deleted_and_gone" if wait else "deleted",
            "file": file.filename,
            "objects": [{"apiVersion": a, "kind": k, "name": n} for a, k, n in summary],
            "count": len(summary),
            "wait": wait,
            "namespace": namespace,
            "timeout": timeout,
        })
    except ApiException as e:
        raise HTTPException(status_code=400, detail=f"Delete failed: {e.reason}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Delete failed: {e}")

@app.get("/deployments")
def list_deployments():
    """List all deployments applied via /apply (in-memory registry)."""
    with REGISTRY_LOCK:
        data = [
            {
                "deployment_id": dep_id,
                "file": entry["filename"],
                "applied_at": entry["applied_at"],
                "count": len(entry["objects"]),
                "objects": [
                    {"apiVersion": a, "kind": k, "name": n}
                    for (a, k, n) in entry["objects"]
                ],
            }
            for dep_id, entry in REGISTRY.items()
        ]
    return {"deployments": data, "count": len(data)}

@app.post("/deployments/delete_all")
def delete_all_deployments(
    wait: bool = Query(False),
    namespace: str = Query("default"),
    timeout: int = Query(120, ge=1, le=3600),
):
    """
    Delete ONLY the resources that were applied via /apply (based on registry),
    then clear the registry. Idempotent: 404s are ignored in delete_from_yaml_text().
    If wait=true, block until all deleted resources are gone.
    """
    deleted: List[Dict[str, Any]] = []
    errors: List[str] = []
    to_wait: List[Tuple[str, str, str]] = []

    with REGISTRY_LOCK:
        snapshot = [(dep_id, entry["filename"], entry["yaml_text"])
                    for dep_id, entry in REGISTRY.items()]

    for dep_id, filename, yaml_text in snapshot:
        try:
            summary = delete_from_yaml_text(yaml_text)
            deleted.append({
                "deployment_id": dep_id,
                "file": filename,
                "objects": [{"apiVersion": a, "kind": k, "name": n} for a, k, n in summary],
                "count": len(summary),
            })
            to_wait.extend(summary)
        except ApiException as e:
            errors.append(f"{dep_id}: {e.reason}")
        except Exception as e:
            errors.append(f"{dep_id}: {e}")

    if wait and not errors:
        try:
            _wait_gone(to_wait, namespace=namespace, timeout=timeout)
        except TimeoutError as te:
            errors.append(str(te))

    with REGISTRY_LOCK:
        if not errors:
            REGISTRY.clear()
        else:
            for d in deleted:
                REGISTRY.pop(d["deployment_id"], None)

    status = "ok" if not errors else "partial"
    return {
        "status": status if not wait else ("ok_and_gone" if not errors else "partial"),
        "deleted": deleted,
        "deleted_count": len(deleted),
        "errors": errors,
        "remaining_in_registry": len(REGISTRY),
        "wait": wait,
        "namespace": namespace,
        "timeout": timeout,
    }

