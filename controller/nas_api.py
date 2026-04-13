import subprocess
import re
import time
from controller.config import NAS_IP, NAS_USER


class QNAPManager:
    def __init__(self, ip):
        self.ip = ip
        self.community = "public"  # 必须定义 SNMP 团体名
        self._cache_data = None
        self._last_sync = 0
        self._cache_duration = 4  # 缓存 4 秒

    def _get_snmp_value(self, oid):
        """执行 snmpget 并精准提取值"""
        try:
            # 使用 -Ov 参数只输出值
            cmd = f"snmpget -v 2c -c {self.community} -Ov {self.ip} {oid}"
            result = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, timeout=3).decode().strip()

            # 解析 Timeticks
            if "Timeticks:" in result:
                match = re.search(r'\((\d+)\)', result)
                return match.group(1) if match else None

            # 解析 STRING
            if "STRING:" in result:
                match = re.search(r'STRING: "(.*?)"', result)
                if match: return match.group(1)
                return result.split("STRING:")[-1].strip().strip('"')

            # 解析 INTEGER 或 Gauge32
            if "INTEGER:" in result or "Gauge32:" in result:
                return result.split(":")[-1].strip()

            return result.split(":")[-1].strip()
        except:
            return None

    def _parse_size_to_gb(self, size_str):
        if not size_str: return 0.0
        num_match = re.search(r"[\d\.]+", str(size_str))
        if not num_match: return 0.0
        num = float(num_match.group())
        if "TB" in str(size_str).upper(): return num * 1024
        return num

    def get_stats(self):
        now = time.time()
        if self._cache_data and (now - self._last_sync) < self._cache_duration:
            return self._cache_data

        uptime_ticks = self._get_snmp_value(".1.3.6.1.2.1.25.1.1.0")
        if uptime_ticks is None:
            return {"online": False}

        data = {"online": True}

        # 运行时间
        if str(uptime_ticks).isdigit():
            seconds = int(uptime_ticks) // 100
            d, h = divmod(seconds // 3600, 24)
            data["uptime"] = f"{d}天 {h:02d}小时"
        else:
            data["uptime"] = "N/A"

        # 硬件信息
        data["sys_desc"] = self._get_snmp_value(".1.3.6.1.2.1.1.1.0") or "QNAP NAS"
        data["cpu_temp"] = self._get_snmp_value(".1.3.6.1.4.1.24681.1.2.5.0") or "--"
        data["sys_temp"] = self._get_snmp_value(".1.3.6.1.4.1.24681.1.2.6.0") or "--"
        data["fan_speed"] = self._get_snmp_value(".1.3.6.1.4.1.24681.1.2.15.1.3.1") or "--"

        # 负载
        cpu = self._get_snmp_value(".1.3.6.1.4.1.24681.1.3.1.0")
        data["cpu"] = f"{cpu}%" if cpu else "0%"

        t_kb = self._get_snmp_value(".1.3.6.1.4.1.24681.1.3.2.0")
        f_kb = self._get_snmp_value(".1.3.6.1.4.1.24681.1.3.3.0")
        if t_kb and f_kb:
            try:
                data["mem"] = f"{int((float(t_kb) - float(f_kb)) / float(t_kb) * 100)}%"
            except:
                data["mem"] = "0%"
        else:
            data["mem"] = "0%"

        # 磁盘明细
        data["disks"] = []
        for i in range(1, 5):
            name = self._get_snmp_value(f".1.3.6.1.4.1.24681.1.2.17.1.2.{i}")
            if name:
                total_str = self._get_snmp_value(f".1.3.6.1.4.1.24681.1.2.17.1.4.{i}")
                free_str = self._get_snmp_value(f".1.3.6.1.4.1.24681.1.2.17.1.5.{i}")
                status = self._get_snmp_value(f".1.3.6.1.4.1.24681.1.3.17.1.6.{i}")

                total_gb = self._parse_size_to_gb(total_str)
                free_gb = self._parse_size_to_gb(free_str)
                used_gb = total_gb - free_gb
                pct = int((used_gb / total_gb * 100)) if total_gb > 0 else 0

                data["disks"].append({
                    "name": name.replace("[Volume ", "").replace("]", ""),
                    "total": f"{total_gb / 1024:.2f} TB" if total_gb > 1000 else f"{total_gb:.0f} GB",
                    "used": f"{used_gb / 1024:.2f} TB" if used_gb > 1024 else f"{used_gb:.0f} GB",
                    "free": f"{free_gb / 1024:.2f} TB" if free_gb > 1024 else f"{free_gb:.0f} GB",
                    "pct": f"{pct}%",
                    "status": status or "Ready"
                })

        self._cache_data = data
        self._last_sync = now
        return data

    def shutdown(self):
        """SSH 密钥安全关机"""
        try:
            cmd = f"ssh -o BatchMode=yes -o StrictHostKeyChecking=no {NAS_USER}@{self.ip} 'poweroff'"
            result = subprocess.run(cmd, shell=True, capture_output=True, timeout=10)
            return result.returncode == 0
        except:
            return False


# 实例化时必须传入 NAS_IP
nas_manager = QNAPManager(NAS_IP)