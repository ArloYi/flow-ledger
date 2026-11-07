"""Identify physical networks without guessing whether Wi-Fi is a hotspot."""
import hashlib
import re
import subprocess


def command(args, input_text=None):
    try:
        result = subprocess.run(args, input=input_text, capture_output=True, text=True, timeout=2)
        return result.stdout.strip() if result.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''


def probe_networks(interfaces):
    found = {}
    for interface in interfaces:
        address = command(['/usr/sbin/ipconfig', 'getifaddr', interface])
        if not address:
            continue
        router = command(['/usr/sbin/ipconfig', 'getoption', interface, 'router'])
        if not re.fullmatch(r'\d+\.\d+\.\d+\.\d+', router):
            found[interface] = {'id': 'unknown', 'name': '无法识别的网络'}
            continue
        arp = command(['/usr/sbin/arp', '-n', router])
        match = re.search(r' at ([0-9a-f:]+) on ' + re.escape(interface) + r'\b', arp, re.I)
        hardware = match.group(1).lower() if match else None
        if not hardware:
            summary = command(['/usr/sbin/ipconfig', 'getsummary', interface])
            service = re.search(r'\bServiceID\s*:\s*([A-Fa-f0-9-]{36})\b', summary)
            if service:
                state = command(['/usr/sbin/scutil'], 'show State:/Network/Service/' + service.group(1) + '/IPv4\n')
                confirmed = re.search(r'\bInterfaceName\s*:\s*' + re.escape(interface) + r'\b', state)
                cached = re.search(r'ARPResolvedHardwareAddress\s*:\s*([0-9a-f:]+)', state, re.I)
                if confirmed and cached:
                    hardware = cached.group(1).lower()
        if not hardware:
            found[interface] = {'id': 'unknown', 'name': '无法识别的网络'}
            continue
        fingerprint = hashlib.sha256((interface + '|' + hardware).encode()).hexdigest()[:16]
        found[interface] = {'id': fingerprint, 'name': '网络 ' + fingerprint[:4].upper()}
    return found


def attribution(previous, current, interface):
    before = previous.get(interface, {}).get('id', 'unknown')
    after = current.get(interface, {}).get('id', 'unknown')
    return after if before == after else 'switch'
