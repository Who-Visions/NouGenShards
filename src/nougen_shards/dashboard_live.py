"""Read-only dashboard discovery. Missing evidence remains null."""
from __future__ import annotations
import concurrent.futures
import datetime
import json
import os
import platform
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

def read_json(path, fallback=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return fallback

def get_json(url):
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=2) as response:
            return json.load(response)
    except Exception:
        return None

def local_hardware():
    result = {'gpu': None, 'ram': None, 'temperature': None, 'vram_used_pct': None}
    try:
        import psutil
        result['ram'] = f'{psutil.virtual_memory().total / 1024**3:.1f} GB'
    except ImportError:
        pass
    try:
        raw = subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.total,memory.used,temperature.gpu', '--format=csv,noheader,nounits'], timeout=3, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).decode().strip().splitlines()
        gpus = [row.split(',') for row in raw]
        result['gpu'] = ', '.join(f'{g[0].strip()} ({float(g[1])/1024:.1f} GB)' for g in gpus)
        total = sum(float(g[1]) for g in gpus)
        result['vram_used_pct'] = round(sum(float(g[2]) for g in gpus) / total * 100, 1) if total else None
        result['temperature'] = ', '.join(f'{g[3].strip()}°C' for g in gpus)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return result

def fleet_nodes(home=None):
    home = Path(home or os.environ.get('NOUGEN_HOME', str(Path.home() / '.nougen')))
    config = read_json(home / 'nodes.json', {})
    config = {key: node for key, node in config.items() if isinstance(key, str) and isinstance(node, dict)} if isinstance(config, dict) else {}
    hosts_doc = read_json(home / 'fleet_hosts.json', {})
    hosts = hosts_doc.get('nodes', {}) if isinstance(hosts_doc, dict) else {}
    hosts = hosts if isinstance(hosts, dict) else {}
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except OSError:
        local_ip = None
    hardware = local_hardware()
    def probe(item):
        key, node = item
        transport = hosts.get(node.get('transport_node'))
        transport = transport if isinstance(transport, dict) else {}
        address = transport.get('ip') or node.get('ip') or node.get('host')
        aliases = node.get('aliases', [])
        aliases = aliases if isinstance(aliases, list) else []
        is_local = address in ('127.0.0.1', 'localhost', local_ip, hostname) or hostname.lower() in [str(a).lower() for a in aliases]
        target = '127.0.0.1' if is_local else address
        ports = node.get('ports', [])
        ports = ports if isinstance(ports, list) else []
        health = None
        for port in [p for p in ports if p in (4444, 8766)]:
            health = get_json(f'http://{target}:{port}/health')
            if isinstance(health, dict):
                break
        ollama_url = os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434') if is_local else (f'http://{target}:11434' if 11434 in ports else None)
        models = get_json(ollama_url.rstrip('/') + '/api/ps') if ollama_url else None
        running = models.get('models', []) if isinstance(models, dict) else None
        measured = hardware if is_local else {'gpu': None, 'ram': None, 'temperature': None, 'vram_used_pct': None}
        if not is_local and isinstance(health, dict):
            remote = health.get('hardware', {})
            if isinstance(remote, dict):
                measured.update({k: remote[k] for k in measured if k in remote})
        observed = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return {'name': node.get('name') or key, 'host': hostname if is_local else node.get('stadium') or node.get('machine'),
                'ip': local_ip if is_local else address, 'coach': node.get('coach'), 'role': node.get('role'),
                'player': ', '.join(m.get('name') or m.get('model', '') for m in running) if running else ('No resident models' if running == [] else None),
                'status': 'active-node' if is_local else ('online' if health or models is not None else 'unreachable'),
                'health_status': 'responding' if health or models is not None else 'unreachable',
                'is_local': is_local, 'observed_at': observed, 'fps_heartbeat': 'Observed ' + observed,
                'source': 'nodes.json + live health/Ollama probes' if not is_local else 'OS + nodes.json + nvidia-smi + Ollama', **measured}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        nodes = list(pool.map(probe, config.items()))
    if not any(n['is_local'] for n in nodes):
        nodes.append({'name': hostname, 'host': hostname, 'ip': local_ip, 'coach': None, 'role': None, 'player': None, 'status': 'active-node', 'is_local': True, **hardware})
    return nodes

def identity():
    home = Path(os.environ.get('NOUGEN_HOME', str(Path.home() / '.nougen')))
    nodes = read_json(home / 'nodes.json', {})
    hostname = socket.gethostname()
    return {'hostname': hostname, 'user': os.environ.get('USERNAME') or os.environ.get('USER'),
            'vault_path': os.environ.get('NOUGEN_VAULT_DIR', str(home / 'shards')),
            'platform': platform.system(), 'registered_nodes': len(nodes)}

def relay_feed():
    directory = Path(os.environ.get('NOUGEN_HANDOFFS_DIR', str(Path.home() / 'Outpost/NouGenRelay/.handoffs')))
    records = []
    for path in sorted(directory.glob('*.json'), key=lambda p:p.stat().st_mtime, reverse=True)[:15]:
        data = read_json(path, {})
        records.append({'id': path.stem, 'timestamp': data.get('created_utc') or data.get('when') or datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.timezone.utc).isoformat(),
                        'machine': data.get('machine') or data.get('host'), 'agent': data.get('agent'), 'branch': data.get('branch'),
                        'goal': data.get('goal'), 'tasks_done': data.get('tasks_done'), 'tasks_total': data.get('tasks_total'),
                        'status': data.get('state') or data.get('status') or 'unknown', 'live_status': data.get('state') or data.get('status') or 'unknown', 'acknowledged_by': data.get('acknowledged_by')})
    return records

def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {'fleet_nodes', 'identity', 'relay_feed'}:
        raise SystemExit('Expected one of: fleet_nodes, identity, relay_feed')
    command = sys.argv[1]
    try:
        value = {'fleet_nodes': fleet_nodes, 'identity': identity, 'relay_feed': relay_feed}[command]()
    except Exception as exc:
        print(f'dashboard command failed: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(value))
    return 0


if __name__ == '__main__':
    main()
