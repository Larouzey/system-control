/**
 * NAS 状态监控核心脚本
 * 支持：自动定时刷新、硬件温度显示、风扇转速监控、磁盘健康状态渲染
 */

function updateNASDisplay() {
    fetch('/api/nas_stats')
        .then(response => response.json())
        .then(data => {
            // 1. 处理离线状态
            if (!data.online) {
                const container = document.getElementById('disk_container');
                if (container) {
                    container.innerHTML = `
                        <div style="grid-column: 1/-1; text-align: center; padding: 40px; background: rgba(231, 76, 60, 0.1); border-radius: 8px; border: 1px dashed #e74c3c;">
                            <h3 style="color: #e74c3c; margin: 0;">⚠️ NAS 设备离线</h3>
                            <p style="color: #95a5a6; margin: 10px 0 0 0;">请检查设备电源、网络连接或 SNMP 服务状态</p>
                        </div>
                    `;
                }
                // 更新顶部状态指示器（如果存在）
                const statusIndicator = document.querySelector('.status-indicator');
                if (statusIndicator) {
                    statusIndicator.innerText = "● 设备离线";
                    statusIndicator.style.color = "#95a5a6";
                }
                return;
            }

            // 2. 更新基础运行负载 (增加容错判断)
            const updateText = (id, value) => {
                const el = document.getElementById(id);
                if (el) el.innerText = value || "--";
            };

            const updateWidth = (id, value) => {
                const el = document.getElementById(id);
                if (el) el.style.width = value || "0%";
            };

            // 基础信息
            updateText('nas_uptime', data.uptime);
            updateText('nas_cpu', data.cpu);
            updateWidth('nas_cpu_bar', data.cpu);
            updateText('nas_mem', data.mem);
            updateWidth('nas_mem_bar', data.mem);

            // 3. 更新新增的硬件环境信息 (对应 result.txt 中的新字段)
            updateText('nas_sys_desc', data.sys_desc);
            updateText('nas_cpu_temp', data.cpu_temp);
            updateText('nas_sys_temp', data.sys_temp);
            updateText('nas_fan_speed', data.fan_speed);

            // 4. 动态构建磁盘网格 (包含健康状态显示)
            const container = document.getElementById('disk_container');
            if (container && data.disks && data.disks.length > 0) {
                container.innerHTML = data.disks.map(disk => {
                    // 根据状态设置颜色：Ready 为绿色，其他（如 Warning/Error）为红色
                    const isReady = disk.status && disk.status.toLowerCase() === 'ready';
                    const statusStyle = isReady ? 'color: #2ecc71;' : 'color: #e74c3c; font-weight: bold;';

                    return `
                    <div class="storage-card">
                        <div class="card-head">
                            <span class="disk-name">💽 ${disk.name}</span>
                            <span class="usage-tag">${disk.pct}</span>
                        </div>
                        <div class="usage-track">
                            <div class="usage-fill" style="width: ${disk.pct}"></div>
                        </div>
                        <div class="cap-info">
                            <div class="cap-box">
                                <span>健康状态</span>
                                <b style="${statusStyle}">${disk.status || '未知'}</b>
                            </div>
                            <div class="cap-box">
                                <span>总容量</span>
                                <b>${disk.total}</b>
                            </div>
                            <div class="cap-box">
                                <span>已用/可用</span>
                                <b>${disk.used} / ${disk.free}</b>
                            </div>
                        </div>
                    </div>
                `}).join('');
            }
        })
        .catch(e => {
            console.error("NAS Data Sync Error:", e);
        });
}

// ... 原有的 updateNASDisplay 函数等代码保持不变 ...

// 增加：NAS 物理关机确认函数
function confirmNasShutdown() {
    if(confirm("⚠️ 危险操作：此指令将通过 SSH 强制关闭 NAS 设备！\n请确保数据已保存。确认执行物理关机吗？")) {
        fetch('/api/nas_shutdown', { 
            method: 'POST' 
        })
        .then(response => {
            if(response.ok) {
                alert("✅ 关机指令已成功发送至 NAS！设备即将断电。");
                // 强制将状态标红
                const statusIndicator = document.querySelector('.status-indicator');
                if (statusIndicator) {
                    statusIndicator.innerText = "● 正在关机";
                    statusIndicator.style.color = "#e74c3c";
                }
            } else {
                alert("❌ 关机指令发送失败，请检查权限。");
            }
        })
        .catch(e => {
            console.error("Shutdown Error:", e);
            alert("网络错误，无法连接控制面板后台。");
        });
    }
}

// 设定 5 秒心跳刷新
setInterval(updateNASDisplay, 5000);

// 页面加载完成后立即执行一次
document.addEventListener('DOMContentLoaded', updateNASDisplay);
