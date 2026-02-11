"""
K8sDeployment Skill
===================
Kubernetes deployment operations for WolfStrategyV1.
"""

import subprocess
import logging
import os
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class K8sConfig:
    """Kubernetes configuration."""
    kubeconfig: str = ""
    namespace: str = "default"
    nodeport_base: int = 30500
    image: str = "freqtradeorg/freqtrade:develop"
    resources: Dict = None
    
    def __post_init__(self):
        if self.resources is None:
            self.resources = {
                'cpu_request': '1000m',
                'cpu_limit': '2000m',
                'memory_request': '2Gi',
                'memory_limit': '4Gi',
            }


class K8sDeployment:
    """
    Kubernetes deployment operations.
    
    Capabilities:
    - Generate deployment manifests
    - Apply/remove deployments
    - Manage ConfigMaps and Secrets
    - Monitor pod status
    """
    
    def __init__(self, config: Optional[K8sConfig] = None):
        self.config = config or K8sConfig()
        self.kubectl_path = 'kubectl'
    
    def check_kubectl(self) -> bool:
        """Check if kubectl is available."""
        try:
            result = subprocess.run(
                [self.kubectl_path, 'version', '--client'],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False
    
    def run_kubectl(self, args: List[str]) -> subprocess.CompletedProcess:
        """Run kubectl command."""
        cmd = [self.kubectl_path] + args
        if self.config.kubeconfig:
            cmd.extend(['--kubeconfig', self.config.kubeconfig])
        
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
    
    def apply_manifest(self, manifest_path: str) -> bool:
        """Apply K8s manifest."""
        result = self.run_kubectl(['apply', '-f', manifest_path])
        
        if result.returncode == 0:
            logger.info(f"[K8S] Applied manifest: {manifest_path}")
            return True
        else:
            logger.error(f"[K8S] Failed to apply {manifest_path}: {result.stderr}")
            return False
    
    def delete_manifest(self, manifest_path: str) -> bool:
        """Delete K8s manifest."""
        result = self.run_kubectl(['delete', '-f', manifest_path])
        
        if result.returncode == 0:
            logger.info(f"[K8S] Deleted manifest: {manifest_path}")
            return True
        else:
            logger.warning(f"[K8S] Delete failed {manifest_path}: {result.stderr}")
            return False
    
    def get_pods(self, labels: Dict[str, str] = None) -> List[Dict]:
        """Get pods with optional label filter."""
        args = ['get', 'pods', '-o', 'json']
        
        if labels:
            label_selector = ','.join([f"{k}={v}" for k, v in labels.items()])
            args.extend(['-l', label_selector])
        
        result = self.run_kubectl(args)
        
        if result.returncode == 0:
            import json
            return json.loads(result.stdout).get('items', [])
        return []
    
    def get_pod_status(self, pod_name: str) -> Dict:
        """Get pod status."""
        result = self.run_kubectl(['get', 'pod', pod_name, '-o', 'json'])
        
        if result.returncode == 0:
            import json
            return json.loads(result.stdout)
        return {}
    
    def get_logs(
        self, 
        pod_name: str, 
        tail: int = 100,
        follow: bool = False
    ) -> subprocess.Popen:
        """Get pod logs."""
        args = ['logs', pod_name, f'--tail={tail}']
        if follow:
            args.append('-f')
        
        return subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
    
    def exec_command(
        self, 
        pod_name: str, 
        command: List[str],
        namespace: str = None
    ) -> subprocess.CompletedProcess:
        """Execute command in pod."""
        ns = namespace or self.config.namespace
        args = ['exec', '-n', ns, pod_name, '--'] + command
        
        return self.run_kubectl(args)
    
    def restart_pod(self, pod_name: str) -> bool:
        """Restart a pod."""
        result = self.run_kubectl(['delete', 'pod', pod_name])
        
        if result.returncode == 0:
            logger.info(f"[K8S] Pod restarted: {pod_name}")
            return True
        return False
    
    def scale_deployment(self, deployment_name: str, replicas: int) -> bool:
        """Scale deployment replicas."""
        result = self.run_kubectl([
            'scale', 
            'deployment', 
            deployment_name, 
            f'--replicas={replicas}'
        ])
        
        if result.returncode == 0:
            logger.info(f"[K8S] Scaled {deployment_name} to {replicas}")
            return True
        return False
    
    def create_secret(
        self, 
        secret_name: str, 
        data: Dict[str, str],
        namespace: str = None
    ) -> bool:
        """Create K8s secret."""
        import base64
        
        ns = namespace or self.config.namespace
        
        # Convert values to base64
        encoded_data = {
            k: base64.b64encode(v.encode()).decode() 
            for k, v in data.items()
        }
        
        manifest = {
            'apiVersion': 'v1',
            'kind': 'Secret',
            'metadata': {
                'name': secret_name,
                'namespace': ns
            },
            'type': 'Opaque',
            'data': encoded_data
        }
        
        import json
        import tempfile
        
        with tempfile.NamedTemporaryFile(
            mode='w', 
            suffix='.json', 
            delete=False
        ) as f:
            json.dump(manifest, f)
            temp_path = f.name
        
        try:
            return self.apply_manifest(temp_path)
        finally:
            os.unlink(temp_path)
    
    def create_configmap(
        self, 
        configmap_name: str, 
        data: Dict[str, str],
        namespace: str = None
    ) -> bool:
        """Create K8s ConfigMap."""
        ns = namespace or self.config.namespace
        
        manifest = {
            'apiVersion': 'v1',
            'kind': 'ConfigMap',
            'metadata': {
                'name': configmap_name,
                'namespace': ns
            },
            'data': data
        }
        
        import json
        import tempfile
        
        with tempfile.NamedTemporaryFile(
            mode='w', 
            suffix='.json', 
            delete=False
        ) as f:
            json.dump(manifest, f)
            temp_path = f.name
        
        try:
            return self.apply_manifest(temp_path)
        finally:
            os.unlink(temp_path)
