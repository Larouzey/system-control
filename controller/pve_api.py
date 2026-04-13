# /root/controller/pve_api.py
import subprocess
import json

def get_pve_status():
    """获取宿主机资源使用率"""
    try:
        res = subprocess.run("pvesh get /nodes/localhost/status --output-format json", 
                             shell=True, capture_output=True, text=True)
        data = json.loads(res.stdout)
        # 提取关键数据：CPU使用率、内存、运行时间
        cpu = f"{float(data.get('cpu', 0))*100:.1f}%"
        mem = f"{data.get('memory', {}).get('used', 0) / (1024**3):.1f}G / {data.get('memory', {}).get('total', 0) / (1024**3):.1f}G"
        uptime = f"{int(data.get('uptime', 0) / 3600)} 小时"
        return {"cpu": cpu, "mem": mem, "uptime": uptime}
    except:
        return {"cpu": "未知", "mem": "未知", "uptime": "未知"}

def get_vm_list():
    """获取所有虚拟机和容器列表 (增强版)"""
    try:
        res = subprocess.run("pvesh get /cluster/resources --type vm --output-format json", 
                             shell=True, capture_output=True, text=True)
        vms = json.loads(res.stdout)
        result = []
        
        for v in vms:
            status = v.get('status', 'unknown')
            
            # 1. 处理内存数据 (换算为 GB 并计算百分比)
            max_mem_bytes = v.get('maxmem', 0)
            used_mem_bytes = v.get('mem', 0)
            max_mem_gb = max_mem_bytes / (1024**3)
            used_mem_gb = used_mem_bytes / (1024**3)
            mem_pct = int((used_mem_bytes / max_mem_bytes) * 100) if max_mem_bytes > 0 else 0

            # 2. 处理 CPU 数据 (提取核心数与负载)
            max_cpu = v.get('maxcpu', 0)
            cpu_usage = v.get('cpu', 0)
            cpu_pct = int(cpu_usage * 100) if cpu_usage else 0

            # 3. 处理运行时间
            uptime_sec = v.get('uptime', 0)
            if uptime_sec > 0 and status == 'running':
                d, rem = divmod(uptime_sec, 86400)
                h, m = divmod(rem, 3600)[0], divmod(rem, 60)[0] % 60
                uptime_str = f"{d}天 {h:02d}:{m:02d}"
            else:
                uptime_str = "已关机"
                cpu_pct = 0
                mem_pct = 0
                used_mem_gb = 0

            result.append({
                "id": v.get('vmid'),
                "name": v.get('name', f"VM-{v.get('vmid')}"),
                "status": status,
                "cpu_cores": max_cpu,
                "cpu_pct": f"{cpu_pct}%",
                "mem_text": f"{used_mem_gb:.1f}G / {max_mem_gb:.1f}G",
                "mem_pct": f"{mem_pct}%",
                "uptime": uptime_str
            })
            
        # 按照 VMID 从小到大排序
        result.sort(key=lambda x: int(x['id']))
        return result
    except:
        return []
