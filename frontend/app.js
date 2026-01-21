// Utilities
const fmtB = (b) => { if (!b) return '0 B'; const k = 1024, s = ['B','KB','MB','GB','TB'], i = Math.floor(Math.log(b)/Math.log(k)); return `${(b/Math.pow(k,i)).toFixed(1)} ${s[i]}`; };
const fmtSpd = (b) => `${fmtB(b)}/s`;
const fmtUp = (boot) => { if (!boot) return '-'; const s = Math.floor(Date.now()/1000 - boot), d = Math.floor(s/86400), h = Math.floor((s%86400)/3600), m = Math.floor((s%3600)/60); return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`; };
const getColor = (p) => p >= 90 ? '#ff3366' : p >= 70 ? '#ffaa00' : '#00ff41';

// State
let cpuChart, memChart, gpuChart, cpuHistoryChart, ws, killTarget = null;
let sysData = {}, infoData = {}, disksData = [], netData = {}, procsData = [], connsData = [], diskIoData = {};
let cpuHistory = [];
let maxReadSpeed = 1, maxWriteSpeed = 1;
const CPU_HISTORY_LENGTH = 60;

// BLE State
let connectedAddress = null;
let bleWs = null;
let rssiChart, rssiGaugeChart;
let rssiHistory = [];
const MAX_HISTORY = 60;
let bleInitialized = false;
let streamingAddress = null;

// Navigation
function showPage(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.add('hidden'));
  document.getElementById(`page-${page}`).classList.remove('hidden');
  document.querySelectorAll('.nav-link').forEach(n => n.classList.remove('active'));
  event.currentTarget.classList.add('active');
  if (page === 'processes') fetchProcesses();
  if (page === 'network') fetchConnections();
  if (page === 'storage') renderStoragePage();
}

// Charts
function initCharts() {
  const gaugeOpts = (color, label) => ({
    chart: { type: 'radialBar', height: 160, background: 'transparent', sparkline: { enabled: true } },
    plotOptions: { radialBar: { startAngle: -135, endAngle: 135, hollow: { size: '58%' }, track: { background: '#1a1a24' },
      dataLabels: { name: { show: true, fontSize: '10px', fontFamily: 'JetBrains Mono', color: '#a1a1aa', offsetY: 50 },
        value: { show: true, fontSize: '22px', fontFamily: 'JetBrains Mono', fontWeight: 'bold', color, offsetY: -8, formatter: v => `${v.toFixed(1)}%` } } } },
    fill: { type: 'gradient', gradient: { shade: 'dark', type: 'horizontal', gradientToColors: ['#00d4ff'] } },
    stroke: { lineCap: 'round' }, colors: [color], labels: [label], series: [0]
  });
  cpuChart = new ApexCharts(document.getElementById('cpuGauge'), gaugeOpts('#00ff41', 'USAGE'));
  memChart = new ApexCharts(document.getElementById('memGauge'), gaugeOpts('#00d4ff', 'RAM'));
  gpuChart = new ApexCharts(document.getElementById('gpuGauge'), gaugeOpts('#ff00ff', 'LOAD'));
  cpuChart.render(); memChart.render(); gpuChart.render();

  cpuHistoryChart = new ApexCharts(document.getElementById('cpuHistoryChart'), {
    chart: { type: 'area', height: 200, background: 'transparent', toolbar: { show: false }, animations: { enabled: true, easing: 'linear', dynamicAnimation: { speed: 1000 } }, zoom: { enabled: false } },
    series: [{ name: 'CPU %', data: [] }],
    colors: ['#00ff41'],
    fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.5, opacityTo: 0.1, stops: [0, 100] } },
    stroke: { curve: 'smooth', width: 2 },
    grid: { borderColor: '#27272a', strokeDashArray: 3 },
    xaxis: { type: 'numeric', labels: { show: false }, axisBorder: { show: false }, axisTicks: { show: false }, range: CPU_HISTORY_LENGTH },
    yaxis: { min: 0, max: 100, labels: { style: { colors: '#71717a', fontSize: '10px', fontFamily: 'JetBrains Mono' }, formatter: v => `${v}%` } },
    tooltip: { enabled: true, theme: 'dark', x: { show: false }, y: { formatter: v => `${v.toFixed(1)}%` } },
    dataLabels: { enabled: false }
  });
  cpuHistoryChart.render();
}

// WebSocket
function connectWS() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${protocol}//${location.host}/ws/system`);
  ws.onopen = () => {
    document.getElementById('connStatus').innerHTML = `<i class="codicon codicon-broadcast"></i><span class="text-[10px]">LIVE</span>`;
    document.getElementById('connStatus').className = 'flex items-center gap-1.5 text-[#00ff41]';
  };
  ws.onmessage = (e) => { const msg = JSON.parse(e.data); if (msg.type === 'system_stats') updateDashboard(msg.data); };
  ws.onclose = () => {
    document.getElementById('connStatus').innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 5.636a9 9 0 010 12.728m0 0l-2.829-2.829m2.829 2.829L21 21M15.536 8.464a5 5 0 010 7.072m0 0l-2.829-2.829m-4.243 2.829a4.978 4.978 0 01-1.414-2.83m-1.414 5.658a9 9 0 01-2.167-9.238m7.824 2.167a1 1 0 111.414 1.414m-1.414-1.414L3 3m8.293 8.293l1.414 1.414"></path></svg><span class="text-[10px]">OFFLINE</span>`;
    document.getElementById('connStatus').className = 'flex items-center gap-1.5 text-[#ff3366]';
    setTimeout(connectWS, 3000);
  };
}

// Dashboard Updates
function updateDashboard(data) {
  sysData = data;
  const cpuPercent = data.cpu?.percent || 0;
  
  cpuChart.updateSeries([cpuPercent]);
  const cores = data.cpu?.per_cpu || [];
  document.getElementById('cpuCores').innerHTML = cores.slice(0, 8).map((c, i) => `
    <div><div class="flex justify-between text-[10px] mb-1"><span class="text-[#a1a1aa]">C${i}</span></div>
    <div class="progress-bar"><div class="progress-fill" style="width:${c}%;background:${getColor(c)}"></div></div></div>
  `).join('');
  
  const freq = data.cpu?.freq_current;
  document.getElementById('cpuFreq').textContent = freq ? `${(freq/1000).toFixed(2)} GHz` : '-';
  
  cpuHistory.push({ x: cpuHistory.length, y: cpuPercent });
  if (cpuHistory.length > CPU_HISTORY_LENGTH) cpuHistory.shift();
  cpuHistoryChart.updateSeries([{ name: 'CPU %', data: cpuHistory.map((p, i) => ({ x: i, y: p.y })) }]);
  
  document.getElementById('cpuSpeed').textContent = freq ? `${(freq/1000).toFixed(2)} GHz` : '-';
  document.getElementById('cpuBaseSpeed').textContent = data.cpu?.freq_max ? `${(data.cpu.freq_max/1000).toFixed(2)} GHz` : '-';
  document.getElementById('cpuCoreCount').textContent = data.cpu?.count_physical || data.cpu?.count || '-';
  document.getElementById('cpuLogical').textContent = data.cpu?.count_logical || data.cpu?.count || '-';
  document.getElementById('procCount').textContent = data.cpu?.processes?.toLocaleString() || '-';
  document.getElementById('threadCount').textContent = data.cpu?.threads?.toLocaleString() || '-';
  document.getElementById('ctxSwitches').textContent = data.cpu?.ctx_switches?.toLocaleString() || '-';
  document.getElementById('interrupts').textContent = data.cpu?.interrupts?.toLocaleString() || '-';
  
  memChart.updateSeries([data.memory?.percent || 0]);
  document.getElementById('memUsed').textContent = `${fmtB(data.memory?.used)} / ${fmtB(data.memory?.total)}`;
  document.getElementById('swapBar').style.width = `${data.swap?.percent || 0}%`;
  document.getElementById('swapUsed').textContent = `${fmtB(data.swap?.used)} / ${fmtB(data.swap?.total)}`;
  
  const gpus = data.gpu || [];
  if (gpus.length > 0) {
    const gpu = gpus[0];
    document.getElementById('gpuContent').classList.remove('hidden');
    document.getElementById('gpuNoDevice').classList.add('hidden');
    document.getElementById('gpuName').textContent = gpu.name || 'GPU';
    
    if (gpu.load !== null && gpu.load !== undefined) {
      gpuChart.updateSeries([gpu.load]);
    } else {
      gpuChart.updateSeries([0]);
    }
    
    if (gpu.memory_used !== null && gpu.memory_total !== null) {
      document.getElementById('gpuVram').textContent = `${fmtB(gpu.memory_used * 1024 * 1024)} / ${fmtB(gpu.memory_total * 1024 * 1024)}`;
      document.getElementById('gpuVramBar').style.width = `${gpu.memory_percent || 0}%`;
    } else if (gpu.memory_total !== null) {
      document.getElementById('gpuVram').textContent = `${fmtB(gpu.memory_total * 1024 * 1024)} VRAM`;
      document.getElementById('gpuVramBar').style.width = '0%';
    } else {
      document.getElementById('gpuVram').textContent = '-';
      document.getElementById('gpuVramBar').style.width = '0%';
    }
    
    const tempEl = document.getElementById('gpuTemp');
    const temp = gpu.temperature;
    if (temp !== null && temp !== undefined) {
      tempEl.textContent = `${temp}°C`;
      tempEl.className = 'gpu-temp ' + (temp >= 80 ? 'hot' : temp >= 60 ? 'warm' : 'cool');
    } else {
      tempEl.textContent = '-';
      tempEl.className = 'gpu-temp cool';
    }
  } else {
    document.getElementById('gpuContent').classList.add('hidden');
    document.getElementById('gpuNoDevice').classList.remove('hidden');
    document.getElementById('gpuName').textContent = 'GPU';
  }
  
  netData = data.network || {};
  document.getElementById('netDown').textContent = fmtSpd(netData.bytes_recv_speed || 0);
  document.getElementById('netUp').textContent = fmtSpd(netData.bytes_sent_speed || 0);
  document.getElementById('netDownTotal').textContent = `${fmtB(netData.bytes_recv || 0)} total`;
  document.getElementById('netUpTotal').textContent = `${fmtB(netData.bytes_sent || 0)} total`;
  document.getElementById('packetsIn').textContent = (netData.packets_recv || 0).toLocaleString();
  document.getElementById('packetsOut').textContent = (netData.packets_sent || 0).toLocaleString();
  document.getElementById('netDownLg').textContent = fmtSpd(netData.bytes_recv_speed || 0);
  document.getElementById('netUpLg').textContent = fmtSpd(netData.bytes_sent_speed || 0);
  document.getElementById('netRecvTotal').textContent = fmtB(netData.bytes_recv || 0);
  document.getElementById('netSentTotal').textContent = fmtB(netData.bytes_sent || 0);
  
  if (data.disk_io) {
    diskIoData = data.disk_io;
    Object.values(diskIoData).forEach(io => {
      if (io.read_speed > maxReadSpeed) maxReadSpeed = io.read_speed;
      if (io.write_speed > maxWriteSpeed) maxWriteSpeed = io.write_speed;
    });
    if (!document.getElementById('page-storage').classList.contains('hidden')) {
      renderDiskIo();
    }
  }
}

// Render Disk I/O
function renderDiskIo() {
  const grid = document.getElementById('diskIoGrid');
  if (!grid) return;
  
  const diskNames = Object.keys(diskIoData);
  if (diskNames.length === 0) {
    grid.innerHTML = '<div class="text-xs text-[#71717a]">No disk I/O data available</div>';
    return;
  }
  
  grid.innerHTML = diskNames.map(name => {
    const io = diskIoData[name];
    const readPct = Math.min((io.read_speed / Math.max(maxReadSpeed, 1024*1024)) * 100, 100);
    const writePct = Math.min((io.write_speed / Math.max(maxWriteSpeed, 1024*1024)) * 100, 100);
    
    return `
      <div class="bg-[#1a1a24] rounded-lg p-3 border border-[#27272a]">
        <div class="flex items-center justify-between mb-3">
          <span class="text-xs font-medium text-[#e4e4e7]">${name}</span>
          <div class="flex gap-2">
            <span class="badge badge-green">R: ${fmtSpd(io.read_speed)}</span>
            <span class="badge badge-danger">W: ${fmtSpd(io.write_speed)}</span>
          </div>
        </div>
        <div class="space-y-2">
          <div>
            <div class="flex justify-between text-[10px] mb-1">
              <span class="text-[#00ff41]">↓ Read</span>
              <span class="text-[#71717a]">${io.read_iops?.toFixed(0) || 0} IOPS</span>
            </div>
            <div class="io-bar"><div class="io-fill-read" style="width:${readPct}%"></div></div>
          </div>
          <div>
            <div class="flex justify-between text-[10px] mb-1">
              <span class="text-[#ff00ff]">↑ Write</span>
              <span class="text-[#71717a]">${io.write_iops?.toFixed(0) || 0} IOPS</span>
            </div>
            <div class="io-bar"><div class="io-fill-write" style="width:${writePct}%"></div></div>
          </div>
        </div>
        <div class="mt-3 pt-2 border-t border-[#27272a] grid grid-cols-2 gap-2 text-[10px]">
          <div><span class="text-[#a1a1aa]">Total Read</span><div class="text-[#e4e4e7]">${fmtB(io.read_bytes)}</div></div>
          <div><span class="text-[#a1a1aa]">Total Write</span><div class="text-[#e4e4e7]">${fmtB(io.write_bytes)}</div></div>
        </div>
      </div>
    `;
  }).join('');
}

// Fetch System Info
async function fetchInfo() {
  try {
    const res = await fetch('/api/system/info');
    infoData = await res.json();
    document.getElementById('systemInfo').textContent = `${infoData.hostname} • ${infoData.platform} ${infoData.platform_release}`;
    setInterval(() => { document.getElementById('uptime').textContent = fmtUp(infoData.boot_time); }, 1000);
  } catch (e) { console.error('Failed to fetch info:', e); }
}

// Fetch Disks
async function fetchDisks() {
  try {
    const res = await fetch('/api/disks/partitions');
    disksData = await res.json();
    renderDisks();
  } catch (e) { console.error('Failed to fetch disks:', e); }
}

function renderDisks() {
  document.getElementById('diskList').innerHTML = disksData.slice(0, 4).map(d => `
    <div class="space-y-1">
      <div class="flex justify-between text-[10px]">
        <span class="text-[#a1a1aa] truncate max-w-[100px]">${d.mountpoint}</span>
        <span class="text-[#e4e4e7]">${fmtB(d.free)} free</span>
      </div>
      <div class="progress-bar"><div class="progress-fill" style="width:${d.percent}%;background:${getColor(d.percent)}"></div></div>
    </div>
  `).join('');
}

function renderStoragePage() {
  renderDiskIo();
  
  const storageGrid = document.getElementById('storageGrid');
  if (storageGrid) storageGrid.innerHTML = disksData.map(d => `
    <div class="cyber-card p-4">
      <div class="flex items-center gap-3 mb-3">
        <svg class="w-5 h-5 text-[#ff00ff]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4"></path></svg>
        <div><div class="text-sm text-[#e4e4e7]">${d.mountpoint}</div><div class="text-[10px] text-[#71717a]">${d.device} • ${d.fstype}</div></div>
      </div>
      <div class="mb-2"><div class="flex justify-between text-[10px] mb-1"><span class="text-[#a1a1aa]">Usage</span><span class="text-[#e4e4e7]">${d.percent.toFixed(1)}%</span></div>
      <div class="progress-bar"><div class="progress-fill" style="width:${d.percent}%;background:${getColor(d.percent)}"></div></div></div>
      <div class="grid grid-cols-3 gap-2 text-[10px]">
        <div><span class="text-[#a1a1aa]">Total</span><div class="text-[#e4e4e7]">${fmtB(d.total)}</div></div>
        <div><span class="text-[#a1a1aa]">Used</span><div class="text-[#e4e4e7]">${fmtB(d.used)}</div></div>
        <div><span class="text-[#a1a1aa]">Free</span><div class="text-[#00ff41]">${fmtB(d.free)}</div></div>
      </div>
    </div>
  `).join('');
}

// Temp File Cleanup
let cleanupRunning = false;

async function cleanupTempFiles() {
    if (cleanupRunning) return;
    
    cleanupRunning = true;
    const btn = document.getElementById('cleanupTempBtn');
    const resultsDiv = document.getElementById('cleanupResults');
    
    // Update button state
    btn.innerHTML = '&#8987; CLEANING...';
    btn.disabled = true;
    btn.classList.add('opacity-50', 'cursor-not-allowed');
    
    try {
        const response = await fetch('/api/cleanup/temp-files', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        // Show results
        resultsDiv.classList.remove('hidden');
        
        // Update result stats
        document.getElementById('filesDeleted').textContent = result.total_deleted.toLocaleString();
        document.getElementById('sizeFreed').textContent = fmtB(result.total_size_freed);
        document.getElementById('dirsProcessed').textContent = result.directories_processed;
        document.getElementById('cleanupStatus').textContent = result.success ? 'SUCCESS' : 'PARTIAL';
        
        // Handle errors
        const errorsDiv = document.getElementById('cleanupErrors');
        const errorsList = document.getElementById('errorsList');
        const successMsg = document.getElementById('successMessage');
        
        if (result.errors && result.errors.length > 0) {
            errorsDiv.classList.remove('hidden');
            successMsg.classList.add('hidden');
            errorsList.innerHTML = result.errors.map(error => `<div class="p-1 bg-[#1a1a1a] rounded text-xs">- ${error}</div>`).join('');
        } else {
            errorsDiv.classList.add('hidden');
            if (result.success && result.total_deleted > 0) {
                successMsg.classList.remove('hidden');
            }
        }
        
        // Highlight the space freed if significant
        if (result.total_size_freed > 0) {
            const sizeElement = document.getElementById('sizeFreed');
            sizeElement.style.color = '#00ff41';
            sizeElement.style.textShadow = '0 0 10px rgba(0,255,65,0.5)';
            
            // Add pulsing animation for large savings
            if (result.total_size_freed > 100 * 1024 * 1024) { // > 100MB
                sizeElement.style.animation = 'pulse 2s ease-in-out 3';
            }
        }
        
    } catch (error) {
        console.error('Cleanup failed:', error);
        
        // Show error state
        resultsDiv.classList.remove('hidden');
        document.getElementById('filesDeleted').textContent = '0';
        document.getElementById('sizeFreed').textContent = '0 B';
        document.getElementById('dirsProcessed').textContent = '0';
        document.getElementById('cleanupStatus').textContent = 'ERROR';
        
        const errorsDiv = document.getElementById('cleanupErrors');
        const errorsList = document.getElementById('errorsList');
        const successMsg = document.getElementById('successMessage');
        errorsDiv.classList.remove('hidden');
        successMsg.classList.add('hidden');
        errorsList.innerHTML = `<div class="p-1 bg-[#1a1a1a] rounded text-xs">- Failed to connect to cleanup service: ${error.message}</div>`;
    } finally {
        // Reset button state
        btn.innerHTML = '&#128465; CLEAR TEMP FILES';
        btn.disabled = false;
        btn.classList.remove('opacity-50', 'cursor-not-allowed');
        cleanupRunning = false;
        
        // Results now persist until manually dismissed via close button
    }
}

// Speed Test
let speedTestRunning = false;

async function runSpeedTest() {
    if (speedTestRunning) return;
    
    speedTestRunning = true;
    const btn = document.getElementById('speedTestBtn');
    const btnNetwork = document.getElementById('speedTestBtnNetwork');
    const resultDiv = document.getElementById('speedTestResult');
    const resultDivNetwork = document.getElementById('speedTestResultNetwork');
    
    // Update both buttons
    if (btn) {
        btn.innerHTML = '&#8987; TESTING...';
        btn.disabled = true;
        btn.classList.add('opacity-50', 'cursor-not-allowed');
    }
    if (btnNetwork) {
        btnNetwork.innerHTML = '&#8987; TESTING...';
        btnNetwork.disabled = true;
        btnNetwork.classList.add('opacity-50', 'cursor-not-allowed');
    }
    
    // Show result divs with loading state
    if (resultDiv) resultDiv.classList.remove('hidden');
    if (resultDivNetwork) resultDivNetwork.classList.remove('hidden');
    
    // Set loading state on both
    document.getElementById('speedDown').textContent = '...';
    document.getElementById('speedUp').textContent = '...';
    document.getElementById('speedPing').textContent = '...';
    document.getElementById('speedServer').textContent = 'Finding best server...';
    
    if (document.getElementById('speedDownNetwork')) {
        document.getElementById('speedDownNetwork').textContent = '...';
        document.getElementById('speedUpNetwork').textContent = '...';
        document.getElementById('speedPingNetwork').textContent = '...';
        document.getElementById('speedServerNetwork').textContent = 'Finding best server...';
    }
    
    try {
        const res = await fetch('/api/network/speedtest', { method: 'POST' });
        const data = await res.json();
        
        if (data.status === 'complete') {
            // Update dashboard widget
            document.getElementById('speedDown').textContent = data.download;
            document.getElementById('speedUp').textContent = data.upload;
            document.getElementById('speedPing').textContent = data.ping;
            document.getElementById('speedServer').textContent = `${data.server.name} • ${data.server.location}`;
            
            // Update network page
            if (document.getElementById('speedDownNetwork')) {
                document.getElementById('speedDownNetwork').textContent = data.download;
                document.getElementById('speedUpNetwork').textContent = data.upload;
                document.getElementById('speedPingNetwork').textContent = data.ping;
                document.getElementById('speedServerNetwork').textContent = `${data.server.name} • ${data.server.location}`;
            }
        } else if (data.status === 'running') {
            document.getElementById('speedServer').textContent = 'Test already running...';
            if (document.getElementById('speedServerNetwork')) {
                document.getElementById('speedServerNetwork').textContent = 'Test already running...';
            }
        } else {
            const errMsg = `Error: ${data.error || 'Unknown error'}`;
            document.getElementById('speedServer').textContent = errMsg;
            if (document.getElementById('speedServerNetwork')) {
                document.getElementById('speedServerNetwork').textContent = errMsg;
            }
        }
    } catch (e) {
        console.error('Speed test failed:', e);
        document.getElementById('speedDown').textContent = '--';
        document.getElementById('speedUp').textContent = '--';
        document.getElementById('speedPing').textContent = '--';
        document.getElementById('speedServer').textContent = `Error: ${e.message}`;
        
        if (document.getElementById('speedDownNetwork')) {
            document.getElementById('speedDownNetwork').textContent = '--';
            document.getElementById('speedUpNetwork').textContent = '--';
            document.getElementById('speedPingNetwork').textContent = '--';
            document.getElementById('speedServerNetwork').textContent = `Error: ${e.message}`;
        }
    } finally {
        speedTestRunning = false;
        if (btn) {
            btn.innerHTML = '⚡ SPEED TEST';
            btn.disabled = false;
            btn.classList.remove('opacity-50', 'cursor-not-allowed');
        }
        if (btnNetwork) {
            btnNetwork.innerHTML = '⚡ RUN SPEED TEST';
            btnNetwork.disabled = false;
            btnNetwork.classList.remove('opacity-50', 'cursor-not-allowed');
        }
    }
}

// Processes
async function fetchProcesses() {
  try {
    const sort = document.getElementById('procSort').value;
    const res = await fetch(`/api/processes?sort=${sort}&order=desc`);
    procsData = await res.json();
    renderProcesses();
  } catch (e) { console.error('Failed to fetch processes:', e); }
}

function renderProcesses() {
  const search = document.getElementById('procSearch').value.toLowerCase();
  const filtered = procsData.filter(p => p.name?.toLowerCase().includes(search));
  const statusBadge = (s) => ({ running: 'badge-green', sleeping: 'badge-cyan', stopped: 'badge-warning', zombie: 'badge-danger' }[s] || 'badge-cyan');
  document.getElementById('procTable').innerHTML = filtered.slice(0, 50).map(p => `
    <tr>
      <td class="text-[#00ff41]">${p.pid}</td>
      <td class="max-w-[150px] truncate">${p.name || '-'}</td>
      <td><span class="${p.cpu_percent > 50 ? 'text-[#ff3366]' : p.cpu_percent > 20 ? 'text-[#ffaa00]' : ''}">${(p.cpu_percent || 0).toFixed(1)}</span></td>
      <td><span class="${p.memory_percent > 50 ? 'text-[#ff3366]' : p.memory_percent > 20 ? 'text-[#ffaa00]' : ''}">${(p.memory_percent || 0).toFixed(1)}</span></td>
      <td>${fmtB(p.memory_info?.rss || 0)}</td>
      <td><span class="badge ${statusBadge(p.status)}">${p.status || '-'}</span></td>
      <td><button class="btn btn-danger" onclick="openKillModal(${p.pid}, '${(p.name || '').replace(/'/g, "\\'")}')">Kill</button></td>
    </tr>
  `).join('');
}

// Network Connections
async function fetchConnections() {
  try {
    const res = await fetch('/api/network/connections');
    connsData = await res.json();
    renderConnections();
  } catch (e) { console.error('Failed to fetch connections:', e); }
}

function renderConnections() {
  document.getElementById('connCount').textContent = connsData.length;
  const statusBadge = (s) => ({ ESTABLISHED: 'badge-green', LISTEN: 'badge-cyan', TIME_WAIT: 'badge-warning', CLOSE_WAIT: 'badge-warning' }[s] || 'badge-cyan');
  document.getElementById('connTable').innerHTML = connsData.slice(0, 100).map(c => `
    <tr>
      <td class="text-[10px]">${c.local_addr?.ip || '*'}:${c.local_addr?.port || '*'}</td>
      <td class="text-[10px]">${c.remote_addr?.ip || '*'}:${c.remote_addr?.port || '*'}</td>
      <td><span class="badge ${statusBadge(c.status)}">${c.status || '-'}</span></td>
      <td class="text-[#00ff41]">${c.pid || '-'}</td>
    </tr>
  `).join('');
}

// Kill Modal
function openKillModal(pid, name) { killTarget = pid; document.getElementById('killProcName').textContent = name; document.getElementById('killProcPid').textContent = pid; document.getElementById('killModal').classList.remove('hidden'); document.getElementById('killModal').classList.add('flex'); }
function closeKillModal() { document.getElementById('killModal').classList.add('hidden'); document.getElementById('killModal').classList.remove('flex'); killTarget = null; }
async function confirmKill() { if (killTarget) { await fetch(`/api/processes/${killTarget}/kill`, { method: 'POST' }); closeKillModal(); setTimeout(fetchProcesses, 500); } }

// Clock
setInterval(() => { document.getElementById('clock').textContent = new Date().toLocaleTimeString(); }, 1000);

// Event Listeners
document.getElementById('procSearch').addEventListener('input', renderProcesses);
document.getElementById('procSort').addEventListener('change', fetchProcesses);

// Periodic Updates
setInterval(fetchDisks, 10000);
setInterval(() => { if (!document.getElementById('page-processes').classList.contains('hidden')) fetchProcesses(); }, 2000);
setInterval(() => { if (!document.getElementById('page-network').classList.contains('hidden')) fetchConnections(); }, 5000);

// --- BLE Functions ---

function initBLE() {
    if (bleInitialized) return;
    initBLECharts();
    startBLEWebSocket();
    scanDevices();
    
    setInterval(() => {
        if (!document.getElementById('ble-tab-connections').classList.contains('hidden')) {
            updateConnectedList();
            updateSystemConnectedList();
        }
    }, 5000);
    
    setInterval(() => {
        if (streamingAddress) {
            checkStreamingDeviceAvailability();
        }
    }, 10000);
    
    bleLog("System initialized. Graphics engine loaded.", "sys");
    bleInitialized = true;
}

function switchBLETab(tabName) {
    const btnScanner = document.getElementById('tab-btn-scanner');
    const btnConn = document.getElementById('tab-btn-connections');
    const viewScanner = document.getElementById('ble-tab-scanner');
    const viewConn = document.getElementById('ble-tab-connections');

    if (tabName === 'scanner') {
        btnScanner.classList.remove('bg-transparent');
        btnConn.classList.add('bg-transparent');
        
        viewScanner.classList.remove('hidden');
        viewConn.classList.add('hidden');
        scanDevices();
    } else {
        btnScanner.classList.add('bg-transparent');
        btnConn.classList.remove('bg-transparent');
        
        viewScanner.classList.add('hidden');
        viewConn.classList.remove('hidden');
        updateConnectedList();
        updateSystemConnectedList();
    }
}

async function updateConnectedList() {
    const list = document.getElementById('ble-conn-list');
    try {
        const res = await fetch('/api/ble/connections');
        const connections = await res.json();
        
        list.innerHTML = '';
        if (connections.length === 0) {
             list.innerHTML = '<tr><td colspan="3" class="text-center text-[#71717a] py-4">NO APP CONNECTIONS</td></tr>';
             return;
        }

        connections.forEach(c => {
            const tr = document.createElement('tr');
            const isFocused = (c.address === connectedAddress);
            
            tr.innerHTML = `
                <td>
                    <div class="font-bold text-[#e4e4e7]">${c.name}</div>
                    <div class="text-[10px] text-[#71717a]">${c.address}</div>
                </td>
                <td><span class="badge badge-green">LINKED</span></td>
                <td class="text-center flex gap-2 justify-end">
                    <button class="btn ${isFocused ? 'btn-ghost text-[#00ff41] border-[#00ff41]' : 'btn-ghost'}" onclick="focusDevice('${c.address}')">
                        ${isFocused ? 'FOCUSED' : 'VIEW'}
                    </button>
                    <button class="btn btn-danger" onclick="disconnectDevice('${c.address}')">X</button>
                </td>
            `;
            list.appendChild(tr);
        });
    } catch (e) {
        console.error("Failed to fetch connections", e);
    }
}

async function updateSystemConnectedList() {
    const list = document.getElementById('ble-system-conn-list');
    try {
        const res = await fetch('/api/ble/system-connected');
        const data = await res.json();
        
        list.innerHTML = '';
        if (data.error) {
            list.innerHTML = `<tr><td colspan="3" class="text-center text-[#ff3366] py-4">${data.error}</td></tr>`;
            return;
        }
        
        if (!data.devices || data.devices.length === 0) {
            list.innerHTML = '<tr><td colspan="3" class="text-center text-[#71717a] py-4">NO BLUETOOTH DEVICES CONNECTED</td></tr>';
            return;
        }

        data.devices.forEach(c => {
            const tr = document.createElement('tr');
            const isStreaming = (c.address === streamingAddress);
            const isBLE = c.type === 'ble';
            const typeLabel = isBLE ? 'BLE' : 'CLASSIC';
            const typeBadgeClass = isBLE ? 'badge-blue' : 'badge-purple';
            
            tr.innerHTML = `
                <td>
                    <div class="font-bold text-[#e4e4e7]">${c.name}</div>
                    <div class="text-[10px] text-[#71717a]">${c.address} <span class="badge ${typeBadgeClass} ml-1">${typeLabel}</span></div>
                </td>
                <td><span class="badge ${c.isConnected ? 'badge-green' : 'badge-warning'}">${c.isConnected ? 'CONNECTED' : 'PAIRED'}</span></td>
                <td class="text-center flex gap-1 justify-center">
                    ${isBLE ? `
                    <button class="btn btn-ghost border ${isStreaming ? 'border-[#ff00ff] text-[#ff00ff] bg-[#ff00ff]/10' : 'border-[#ff00ff] text-[#ff00ff]'} text-[10px] px-2" 
                            onclick="toggleStream('${c.address}', '${c.name}')" 
                            title="${isStreaming ? 'Stop streaming' : 'Stream advertisements'}">
                        ${isStreaming ? '■' : '▶'}
                    </button>
                    ` : ''}
                    <button class="btn btn-ghost text-[#00d4ff] border-[#00d4ff] text-[10px] px-2" onclick="getSystemDeviceInfo('${c.address}', '${c.type}')">INFO</button>
                </td>
            `;
            list.appendChild(tr);
        });
    } catch (e) {
        console.error("Failed to fetch system connections", e);
        list.innerHTML = '<tr><td colspan="3" class="text-center text-[#ff3366] py-4">FETCH ERROR</td></tr>';
    }
}

async function getSystemDeviceInfo(address, deviceType = 'ble') {
    bleLog(`Fetching ${deviceType.toUpperCase()} device info for ${address}...`, "sys");
    
    try {
        const endpoint = deviceType === 'classic' 
            ? `/api/bt/system-device-info/${encodeURIComponent(address)}`
            : `/api/ble/system-device-info/${encodeURIComponent(address)}`;
        
        const res = await fetch(endpoint);
        const data = await res.json();
        
        if (data.error) {
            bleLog(`Error: ${data.error}`, "err");
            return;
        }
        
        bleLog(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`, "sys");
        bleLog(`DEVICE: ${data.name}`, "recv");
        bleLog(`Address: ${data.address}`, "sys");
        bleLog(`Type: ${deviceType.toUpperCase()}`, "sys");
        bleLog(`Status: ${data.isConnected ? 'CONNECTED' : 'DISCONNECTED'}`, "sys");
        
        if (deviceType === 'classic') {
            if (data.classOfDevice) {
                bleLog(`Device Class: ${data.classOfDevice.majorClass}`, "sys");
            }
            
            if (data.rfcommServices && data.rfcommServices.length > 0) {
                bleLog(`━━━ RFCOMM SERVICES (${data.rfcommServices.length}) ━━━`, "recv");
                data.rfcommServices.forEach((svc, idx) => {
                    bleLog(`[${idx + 1}] ${svc.serviceName}`, "recv");
                    if (svc.hostName) {
                        bleLog(`    Host: ${svc.hostName}`, "sys");
                    }
                });
            } else if (data.rfcommServicesError) {
                bleLog(`Services Error: ${data.rfcommServicesError}`, "err");
            } else {
                bleLog(`No RFCOMM services discovered`, "sys");
            }
        } else {
            if (data.rssi !== null && data.rssi !== undefined) {
                bleLog(`RSSI: ${data.rssi} dBm`, "recv");
            } else {
                bleLog(`RSSI: N/A (device not advertising)`, "sys");
            }
            
            if (data.services && data.services.length > 0) {
                bleLog(`━━━ GATT SERVICES (${data.services.length}) ━━━`, "recv");
                
                data.services.forEach((svc, idx) => {
                    const svcName = getServiceName(svc.uuid);
                    bleLog(`[${idx + 1}] ${svcName}`, "recv");
                    bleLog(`    UUID: ${svc.uuid}`, "sys");
                    
                    if (svc.characteristics && svc.characteristics.length > 0) {
                        svc.characteristics.forEach(char => {
                            const charName = getCharacteristicName(char.uuid);
                            const props = char.properties.join(', ') || 'None';
                            bleLog(`    ├─ ${charName}`, "sys");
                            bleLog(`    │  UUID: ${char.uuid}`, "sys");
                            bleLog(`    │  Props: ${props}`, "sys");
                        });
                    }
                    
                    if (svc.characteristicsError) {
                        bleLog(`    └─ Error: ${svc.characteristicsError}`, "err");
                    }
                });
            } else if (data.servicesError) {
                bleLog(`Services Error: ${data.servicesError}`, "err");
            } else {
                bleLog(`No GATT services discovered`, "sys");
            }
        }
        
        bleLog(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`, "sys");
        
    } catch (e) {
        bleLog(`Error fetching device info: ${e.message}`, "err");
    }
}

async function fetchBluetoothEventLogs() {
    bleLog(`Fetching Windows Bluetooth Event Logs...`, "sys");
    
    try {
        const res = await fetch('/api/bt/event-logs?max_events=30');
        const data = await res.json();
        
        if (data.error) {
            bleLog(`Error: ${data.error}`, "err");
            return;
        }
        
        bleLog(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`, "sys");
        bleLog(`WINDOWS BLUETOOTH EVENT LOG (${data.count} events)`, "recv");
        bleLog(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`, "sys");
        
        if (!data.events || data.events.length === 0) {
            bleLog(`No Bluetooth events found in Windows logs`, "sys");
            return;
        }
        
        data.events.forEach((evt, idx) => {
            const typeColor = evt.eventType === 'Error' ? 'err' : 
                              evt.eventType === 'Warning' ? 'send' : 'sys';
            bleLog(`[${evt.timestamp}] ${evt.source}`, "recv");
            bleLog(`  Type: ${evt.eventType} | ID: ${evt.eventId}`, typeColor);
            const cleanMsg = evt.message.replace(/\r?\n/g, ' ').trim();
            bleLog(`  ${cleanMsg.substring(0, 200)}${cleanMsg.length > 200 ? '...' : ''}`, "sys");
            bleLog(``, "sys");
        });
        
        bleLog(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`, "sys");
        
    } catch (e) {
        bleLog(`Error fetching event logs: ${e.message}`, "err");
    }
}

function getServiceName(uuid) {
    const services = {
        '00001800-0000-1000-8000-00805f9b34fb': 'Generic Access',
        '00001801-0000-1000-8000-00805f9b34fb': 'Generic Attribute',
        '0000180a-0000-1000-8000-00805f9b34fb': 'Device Information',
        '0000180f-0000-1000-8000-00805f9b34fb': 'Battery Service',
        '00001812-0000-1000-8000-00805f9b34fb': 'Human Interface Device',
        '00001803-0000-1000-8000-00805f9b34fb': 'Link Loss',
        '00001802-0000-1000-8000-00805f9b34fb': 'Immediate Alert',
        '00001804-0000-1000-8000-00805f9b34fb': 'Tx Power',
    };
    return services[uuid.toLowerCase()] || 'Custom Service';
}

function getCharacteristicName(uuid) {
    const chars = {
        '00002a00-0000-1000-8000-00805f9b34fb': 'Device Name',
        '00002a01-0000-1000-8000-00805f9b34fb': 'Appearance',
        '00002a04-0000-1000-8000-00805f9b34fb': 'Peripheral Preferred Connection',
        '00002a05-0000-1000-8000-00805f9b34fb': 'Service Changed',
        '00002a19-0000-1000-8000-00805f9b34fb': 'Battery Level',
        '00002a29-0000-1000-8000-00805f9b34fb': 'Manufacturer Name',
        '00002a24-0000-1000-8000-00805f9b34fb': 'Model Number',
        '00002a25-0000-1000-8000-00805f9b34fb': 'Serial Number',
        '00002a26-0000-1000-8000-00805f9b34fb': 'Firmware Revision',
        '00002a27-0000-1000-8000-00805f9b34fb': 'Hardware Revision',
        '00002a28-0000-1000-8000-00805f9b34fb': 'Software Revision',
        '00002a4d-0000-1000-8000-00805f9b34fb': 'Report',
        '00002a4b-0000-1000-8000-00805f9b34fb': 'Report Map',
        '00002a4a-0000-1000-8000-00805f9b34fb': 'HID Information',
        '00002a4c-0000-1000-8000-00805f9b34fb': 'HID Control Point',
        '00002a22-0000-1000-8000-00805f9b34fb': 'Boot Keyboard Input',
        '00002a32-0000-1000-8000-00805f9b34fb': 'Boot Keyboard Output',
        '00002a33-0000-1000-8000-00805f9b34fb': 'Boot Mouse Input',
    };
    return chars[uuid.toLowerCase()] || 'Custom Characteristic';
}

function focusDevice(address) {
    connectedAddress = address;
    updateUIConnected(true, address);
    bleLog(`Focus switched to ${address}`, "sys");
    rssiHistory = [];
    updateBLECharts(-100);
    updateConnectedList();
}

function bleLog(msg, type="sys") {
    const term = document.getElementById('terminal-output');
    const entry = document.createElement('div');
    entry.className = "log-entry";
    const time = new Date().toLocaleTimeString();
    let typeClass = "log-sys";
    if (type === "recv") typeClass = "log-recv";
    if (type === "err") typeClass = "log-err";
    entry.innerHTML = `<span class="log-time">[${time}]</span><span class="${typeClass}">${msg}</span>`;
    if (term) {
        term.appendChild(entry);
        term.scrollTop = term.scrollHeight;
    }
}

function clearBleLog() {
    if (!document.getElementById('terminal-output')) return;
    document.getElementById('terminal-output').innerHTML = '';
    bleLog("Terminal cleared.", "sys");
}

function initBLECharts() {
    if (!document.querySelector("#rssiGauge")) return;
    const gaugeOptions = {
        chart: { type: 'radialBar', height: 200, sparkline: { enabled: true } },
        plotOptions: {
            radialBar: {
                startAngle: -135, endAngle: 135,
                hollow: { size: '60%' },
                track: { background: '#1a1a24', strokeWidth: '97%' },
                dataLabels: {
                    name: { show: true, label: 'SIGNAL', color: '#71717a', fontSize: '10px', offsetY: 20 },
                    value: { show: true, fontSize: '24px', fontWeight: 'bold', color: '#00ff41', offsetY: -10, formatter: val => val + '%' }
                }
            }
        },
        fill: { type: 'gradient', gradient: { shade: 'dark', type: 'horizontal', gradientToColors: ['#00d4ff'], stops: [0, 100] } },
        stroke: { lineCap: 'round' },
        series: [0],
        labels: ['SIGNAL']
    };
    rssiGaugeChart = new ApexCharts(document.querySelector("#rssiGauge"), gaugeOptions);
    rssiGaugeChart.render();

    const lineOptions = {
        chart: {
            type: 'area', height: '100%', parentHeightOffset: 0,
            toolbar: { show: false },
            animations: { enabled: true, easing: 'linear', dynamicAnimation: { speed: 1000 } }
        },
        colors: ['#00ff41'],
        fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.4, opacityTo: 0.05, stops: [0, 100] } },
        dataLabels: { enabled: false },
        stroke: { curve: 'smooth', width: 2 },
        series: [{ name: 'RSSI', data: [] }],
        grid: { borderColor: '#27272a', strokeDashArray: 3, xaxis: { lines: { show: false } } },
        xaxis: { 
            labels: { show: false }, 
            axisBorder: { show: false }, 
            axisTicks: { show: false },
            tooltip: { enabled: false }
        },
        yaxis: { 
            min: -100, max: -20, 
            labels: { style: { colors: '#71717a', fontFamily: 'JetBrains Mono', fontSize: '10px' } } 
        },
        theme: { mode: 'dark' }
    };
    rssiChart = new ApexCharts(document.querySelector("#rssiChart"), lineOptions);
    rssiChart.render();
}

function updateBLECharts(rssi) {
    let percentage = Math.max(0, Math.min(100, ((rssi + 100) / 80) * 100));
    
    if (rssiGaugeChart) rssiGaugeChart.updateSeries([percentage.toFixed(1)]);

    rssiHistory.push(rssi);
    if (rssiHistory.length > MAX_HISTORY) rssiHistory.shift();
    
    if (rssiChart) rssiChart.updateSeries([{ data: rssiHistory }]);
    
    const textEl = document.getElementById('current-rssi-display');
    if (textEl) {
        textEl.innerText = `${rssi} dBm`;
        textEl.style.color = rssi > -60 ? '#00ff41' : rssi > -80 ? '#facc15' : '#ff3366';
    }
}

async function scanDevices() {
    const list = document.getElementById('ble-device-list');
    const status = document.getElementById('scan-status');
    if (status) status.classList.remove('hidden');
    
    try {
        const res = await fetch('/api/ble/scan');
        const devices = await res.json();
        
        if (list) {
            list.innerHTML = '';
            if (devices.length === 0) {
               list.innerHTML = '<tr><td colspan="3" class="text-center text-[#71717a] py-4">NO SIGNALS DETECTED</td></tr>';
            }

            devices.forEach(d => {
                const tr = document.createElement('tr');
                const isConnected = (d.address === connectedAddress);
                const isStreaming = (d.address === streamingAddress);
                
                tr.innerHTML = `
                    <td>
                        <div class="font-bold text-[#e4e4e7]">${d.name}</div>
                        <div class="text-[10px] text-[#71717a]">${d.address}</div>
                    </td>
                    <td class="text-center text-[#00ff41] font-mono">${d.rssi}</td>
                    <td class="text-center flex gap-1 justify-center">
                        <button class="btn btn-ghost border ${isStreaming ? 'border-[#ff00ff] text-[#ff00ff] bg-[#ff00ff]/10' : 'border-[#ff00ff] text-[#ff00ff]'} text-[10px] px-2" 
                                onclick="toggleStream('${d.address}', '${d.name}')" 
                                title="${isStreaming ? 'Stop streaming' : 'Stream advertisements'}">
                            ${isStreaming ? '■ STOP' : '▶ STREAM'}
                        </button>
                        ${isConnected 
                            ? `<button class="btn btn-danger text-[10px] px-2" onclick="disconnectDevice('${d.address}')">V-OUT</button>`
                            : `<button class="btn btn-ghost border border-[#00d4ff] text-[#00d4ff] hover:bg-[#00d4ff]/10 text-[10px] px-2" onclick="connectDevice('${d.address}', '${d.name}')">JACK-IN</button>`
                        }
                    </td>
                `;
                list.appendChild(tr);
            });
        }
    } catch (e) {
        bleLog("Scan failed: " + e.message, "err");
    } finally {
        if (status) status.classList.add('hidden');
    }
}

async function connectDevice(address, name) {
    bleLog(`Attempting connection to ${address}...`, "sys");
    
    try {
        const res = await fetch(`/api/ble/connect/${address}`, { method: 'POST' });
        const data = await res.json();
        
        if (data.status === 'connected') {
            connectedAddress = address;
            updateUIConnected(true, name);
            bleLog(`Connection established with ${address}`, "sys");
            scanDevices();
        } else {
            bleLog("Connection refused by target.", "err");
        }
    } catch (e) {
        bleLog("Connection error: " + e.message, "err");
    }
}

async function disconnectDevice(address) {
    try {
        await fetch(`/api/ble/disconnect/${address}`, { method: 'POST' });
        
        if (connectedAddress === address) {
            connectedAddress = null;
            updateUIConnected(false);
            rssiHistory = [];
            updateBLECharts(-100);
        }
        
        bleLog(`Disconnected from ${address}`, "sys");
        
        if (!document.getElementById('ble-tab-scanner').classList.contains('hidden')) scanDevices();
        if (!document.getElementById('ble-tab-connections').classList.contains('hidden')) updateConnectedList();

    } catch (e) {
        bleLog("Disconnect error: " + e.message, "err");
    }
}

function updateUIConnected(isConnected, name="") {
    const indicator = document.getElementById('connection-indicator');
    const nameLabel = document.getElementById('connected-device-name');
    
    if (isConnected && indicator) {
        indicator.classList.remove('hidden');
        indicator.classList.add('flex');
        nameLabel.innerText = name || connectedAddress;
    } else if (indicator) {
        indicator.classList.add('hidden');
        indicator.classList.remove('flex');
    }
}

function startBLEWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    bleWs = new WebSocket(`${protocol}//${window.location.host}/ws/ble`);
    
    bleWs.onopen = () => bleLog("Uplink established. Stream active.", "sys");
    
    bleWs.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'notification' && msg.address === connectedAddress) {
            bleLog(`RX [${msg.data}]`, "recv");
        } else if (msg.type === 'rssi_update' && msg.address === connectedAddress) {
            updateBLECharts(msg.rssi);
        } else if (msg.type === 'advertisement') {
            handleAdvertisement(msg);
        }
    };
    
    bleWs.onclose = () => {
         bleLog("Uplink terminated.", "sys");
         setTimeout(startBLEWebSocket, 3000);
    };
}

function handleAdvertisement(adv) {
    const time = new Date(adv.timestamp * 1000).toLocaleTimeString();
    
    bleLog(`━━━ ADV [${time}] ━━━`, "recv");
    bleLog(`RSSI: ${adv.rssi} dBm`, "recv");
    
    if (adv.tx_power !== null && adv.tx_power !== undefined) {
        bleLog(`TX Power: ${adv.tx_power} dBm`, "sys");
    }
    
    if (adv.local_name && adv.local_name !== adv.name) {
        bleLog(`Local Name: ${adv.local_name}`, "sys");
    }
    
    if (adv.service_uuids && adv.service_uuids.length > 0) {
        bleLog(`Services: ${adv.service_uuids.length}`, "sys");
        adv.service_uuids.forEach(uuid => {
            const name = getServiceName(uuid);
            bleLog(`  └─ ${name}`, "sys");
        });
    }
    
    if (adv.manufacturer_data && Object.keys(adv.manufacturer_data).length > 0) {
        bleLog(`Manufacturer Data:`, "sys");
        for (const [companyId, data] of Object.entries(adv.manufacturer_data)) {
            const companyName = getCompanyName(companyId);
            bleLog(`  └─ ${companyName}: ${data}`, "sys");
        }
    }
    
    if (adv.service_data && Object.keys(adv.service_data).length > 0) {
        bleLog(`Service Data:`, "sys");
        for (const [uuid, data] of Object.entries(adv.service_data)) {
            bleLog(`  └─ ${uuid.substring(0, 8)}...: ${data}`, "sys");
        }
    }
    
    if (streamingAddress && adv.address.toUpperCase() === streamingAddress.toUpperCase()) {
        updateBLECharts(adv.rssi);
    }
}

function getCompanyName(companyId) {
    const companies = {
        '6': 'Microsoft',
        '76': 'Apple',
        '117': 'Samsung',
        '224': 'Google',
        '301': 'Xiaomi',
        '343': 'Huawei',
        '89': 'Nordic Semiconductor',
        '13': 'Texas Instruments',
    };
    return companies[companyId] || `Company ${companyId}`;
}

async function toggleStream(address, name) {
    const previousStreamingAddress = streamingAddress;
    
    if (streamingAddress === address) {
        streamingAddress = null;
        refreshStreamButtons();
        
        try {
            await fetch('/api/ble/stream/stop', { method: 'POST' });
            bleLog(`Stopped streaming ${name}`, "sys");
        } catch (e) {
            bleLog(`Failed to stop stream: ${e.message}`, "err");
        }
    } else {
        streamingAddress = address;
        refreshStreamButtons();
        
        try {
            const res = await fetch(`/api/ble/stream/start/${encodeURIComponent(address)}`, { method: 'POST' });
            const data = await res.json();
            if (data.status === 'started') {
                bleLog(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`, "sys");
                bleLog(`STREAMING: ${name}`, "recv");
                bleLog(`Address: ${address}`, "sys");
                bleLog(`Waiting for advertisements...`, "sys");
            } else {
                streamingAddress = null;
                refreshStreamButtons();
                bleLog(`Failed to start stream: ${data.error}`, "err");
            }
        } catch (e) {
            streamingAddress = null;
            refreshStreamButtons();
            bleLog(`Failed to start stream: ${e.message}`, "err");
        }
    }
}

function refreshStreamButtons() {
    document.querySelectorAll('#ble-device-list tr').forEach(tr => {
        const addressEl = tr.querySelector('td:first-child .text-\\[10px\\]');
        if (addressEl) {
            const address = addressEl.textContent;
            const btn = tr.querySelector('button[onclick^="toggleStream"]');
            if (btn) {
                const isStreaming = (address === streamingAddress);
                btn.className = `btn btn-ghost border ${isStreaming ? 'border-[#ff00ff] text-[#ff00ff] bg-[#ff00ff]/10' : 'border-[#ff00ff] text-[#ff00ff]'} text-[10px] px-2`;
                btn.innerHTML = isStreaming ? '■ STOP' : '▶ STREAM';
            }
        }
    });
    
    document.querySelectorAll('#ble-system-conn-list tr').forEach(tr => {
        const addressEl = tr.querySelector('td:first-child .text-\\[10px\\]');
        if (addressEl) {
            const address = addressEl.textContent;
            const btn = tr.querySelector('button[onclick^="toggleStream"]');
            if (btn) {
                const isStreaming = (address === streamingAddress);
                btn.className = `btn btn-ghost border ${isStreaming ? 'border-[#ff00ff] text-[#ff00ff] bg-[#ff00ff]/10' : 'border-[#ff00ff] text-[#ff00ff]'} text-[10px] px-2`;
                btn.innerHTML = isStreaming ? '■' : '▶';
            }
        }
    });
}

async function checkStreamingDeviceAvailability() {
    if (!streamingAddress) return;
    
    try {
        const [scanRes, sysRes] = await Promise.all([
            fetch('/api/ble/scan').then(r => r.json()).catch(() => []),
            fetch('/api/ble/system-connected').then(r => r.json()).catch(() => ({ devices: [] }))
        ]);
        
        const scanAddresses = (scanRes || []).map(d => d.address.toUpperCase());
        const sysAddresses = ((sysRes.devices) || []).map(d => d.address.toUpperCase());
        const allAddresses = [...scanAddresses, ...sysAddresses];
        
        if (!allAddresses.includes(streamingAddress.toUpperCase())) {
            bleLog(`Streaming device ${streamingAddress} no longer available. Stopping stream.`, "sys");
            await fetch('/api/ble/stream/stop', { method: 'POST' });
            streamingAddress = null;
            refreshStreamButtons();
        }
    } catch (e) {
        console.error("Error checking streaming device availability:", e);
    }
}

// =====================
// FILE CHANGE LOG
// =====================
let fileLogEntries = [];
let fileLogStats = { new: 0, modified: 0, onedrive: 0, deleted: 0, newSize: 0, onedriveDownSize: 0, onedriveUpSize: 0, deletedSize: 0 };
let fileLogActiveFilter = 'all';
let fileLogPathCounts = {};
let fileLogUpdateInterval = null;
let fileLogSelectedDrive = 'C:';
let fileLogAvailableDrives = [];
let fileLogWebSocket = null;
let fileLogIsMonitoring = false;

/**
 * Switches between Storage sub-tabs (Disk Overview / File Change Log).
 *
 * @param {string} tabId - The tab ID to switch to ('disk-overview' or 'file-log').
 */
function switchStorageTab(tabId) {
    document.querySelectorAll('.storage-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabId);
    });
    document.querySelectorAll('.storage-tab-content').forEach(content => {
        content.classList.toggle('hidden', content.id !== `storage-tab-${tabId}`);
    });
    
    if (tabId === 'file-log') {
        initFileChangeLog();
    }
}

/**
 * Populates the drive selector dropdown with available drives.
 */
async function populateDriveSelector() {
    const select = document.getElementById('fileLogDriveSelect');
    if (!select) return;
    
    try {
        const response = await fetch('/api/disks/partitions');
        const disks = await response.json();
        
        fileLogAvailableDrives = disks.map(d => d.device.replace('\\', ''));
        
        select.innerHTML = fileLogAvailableDrives.map(drive => 
            `<option value="${drive}" ${drive === fileLogSelectedDrive ? 'selected' : ''}>${drive}\\</option>`
        ).join('');
    } catch (e) {
        console.error('Failed to fetch drives:', e);
        select.innerHTML = '<option value="C:">C:\\</option>';
    }
}

/**
 * Switches the file log to monitor a different drive.
 *
 * @param {string} drive - The drive letter with colon (e.g., 'C:', 'D:').
 */
async function switchFileLogDrive(drive) {
    // Stop monitoring old drive
    if (fileLogIsMonitoring) {
        await stopFileMonitoring(fileLogSelectedDrive);
    }
    
    fileLogSelectedDrive = drive;
    
    // Clear current data
    fileLogEntries = [];
    fileLogStats = { new: 0, modified: 0, onedrive: 0, deleted: 0, newSize: 0, onedriveDownSize: 0, onedriveUpSize: 0, deletedSize: 0 };
    fileLogPathCounts = {};
    
    updateFileLogSummary();
    renderFileLog();
    
    // Start monitoring new drive
    await startFileMonitoring(drive);
}

/**
 * Starts file monitoring for a drive.
 *
 * @param {string} drive - The drive letter with colon.
 */
async function startFileMonitoring(drive) {
    try {
        const response = await fetch('/api/file-monitor/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ drive: drive })
        });
        
        if (response.ok) {
            fileLogIsMonitoring = true;
            console.log(`Started monitoring ${drive}`);
        } else {
            console.error(`Failed to start monitoring ${drive}`);
        }
    } catch (e) {
        console.error('Error starting file monitoring:', e);
    }
}

/**
 * Stops file monitoring for a drive.
 *
 * @param {string} drive - The drive letter with colon.
 */
async function stopFileMonitoring(drive) {
    try {
        await fetch('/api/file-monitor/stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ drive: drive })
        });
        fileLogIsMonitoring = false;
        console.log(`Stopped monitoring ${drive}`);
    } catch (e) {
        console.error('Error stopping file monitoring:', e);
    }
}

/**
 * Connects to the file monitor WebSocket.
 */
function connectFileLogWebSocket() {
    if (fileLogWebSocket && fileLogWebSocket.readyState === WebSocket.OPEN) {
        return;
    }
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/file-monitor`;
    
    fileLogWebSocket = new WebSocket(wsUrl);
    
    fileLogWebSocket.onopen = () => {
        console.log('File monitor WebSocket connected');
        // Start a periodic ping to keep connection alive
        if (window.fileLogPingInterval) clearInterval(window.fileLogPingInterval);
        window.fileLogPingInterval = setInterval(() => {
            if (fileLogWebSocket && fileLogWebSocket.readyState === WebSocket.OPEN) {
                fileLogWebSocket.send('ping');
            }
        }, 15000);
    };
    
    fileLogWebSocket.onmessage = (event) => {
        console.log('File monitor received:', event.data);
        try {
            const message = JSON.parse(event.data);
            console.log('Parsed message:', message);
            if (message.type === 'file_change') {
                console.log('Handling file change event');
                handleFileChangeEvent(message.data);
            }
            // Ignore ping responses
        } catch (e) {
            console.error('Error parsing file monitor message:', e);
        }
    };
    
    fileLogWebSocket.onclose = () => {
        console.log('File monitor WebSocket closed, reconnecting in 3s...');
        if (window.fileLogPingInterval) clearInterval(window.fileLogPingInterval);
        setTimeout(connectFileLogWebSocket, 3000);
    };
    
    fileLogWebSocket.onerror = (error) => {
        console.error('File monitor WebSocket error:', error);
    };
}

/**
 * Handles a file change event from the WebSocket.
 *
 * @param {Object} data - The file change event data.
 */
function handleFileChangeEvent(data) {
    // Map backend event type to our display type
    let displayType = data.event_type;
    if (data.is_onedrive && (displayType === 'new' || displayType === 'modified')) {
        displayType = 'onedrive';
    }
    
    const entry = {
        timestamp: new Date(data.timestamp),
        path: data.path,
        type: displayType,
        size: data.size,
        isOneDrive: data.is_onedrive
    };
    
    fileLogEntries.push(entry);
    if (fileLogEntries.length > 500) fileLogEntries.shift();
    
    updateFileLogStats(entry);
    updateFileLogSummary();
    renderFileLog(true);
}

/**
 * Initializes the file change log with real-time monitoring.
 */
function initFileChangeLog() {
    // Populate drive selector
    populateDriveSelector();
    
    // Connect to WebSocket
    connectFileLogWebSocket();
    
    // Start monitoring the selected drive
    if (!fileLogIsMonitoring) {
        startFileMonitoring(fileLogSelectedDrive);
    }
    
    renderFileLog();
    
    // Set up filter buttons
    document.querySelectorAll('.file-log-filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            fileLogActiveFilter = btn.dataset.filter;
            document.querySelectorAll('.file-log-filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderFileLog();
        });
    });
}

/**
 * Generates initial mock file log data.
 */
function generateMockFileLogData() {
    const drive = fileLogSelectedDrive;
    const mockPaths = [
        { path: `${drive}\\Users\\User\\OneDrive\\Documents\\Reports\\Q4_2024_Summary.xlsx`, type: 'onedrive', size: 245760 },
        { path: `${drive}\\Users\\User\\AppData\\Local\\Temp\\cache_1234.tmp`, type: 'new', size: 8192 },
        { path: `${drive}\\Program Files\\MyApp\\config.json`, type: 'modified', size: 2048 },
        { path: `${drive}\\Users\\User\\OneDrive\\Pictures\\vacation_001.jpg`, type: 'onedrive', size: 3145728 },
        { path: `${drive}\\Windows\\Temp\\setup_log.txt`, type: 'deleted', size: 4096 },
        { path: `${drive}\\Users\\User\\Documents\\project\\src\\main.py`, type: 'modified', size: 15360 },
        { path: `${drive}\\Users\\User\\OneDrive\\Work\\presentation.pptx`, type: 'onedrive-sync', size: 524288 },
        { path: `${drive}\\Users\\User\\Downloads\\installer_v2.exe`, type: 'new', size: 52428800 },
        { path: `${drive}\\Users\\User\\AppData\\Roaming\\app\\settings.xml`, type: 'modified', size: 1024 },
        { path: `${drive}\\Users\\User\\OneDrive\\Documents\\notes.txt`, type: 'onedrive', size: 512 },
    ];
    
    const now = Date.now();
    mockPaths.forEach((item, i) => {
        const entry = {
            timestamp: new Date(now - (mockPaths.length - i) * 30000),
            path: item.path,
            type: item.type,
            size: item.size,
            isOneDrive: item.type.startsWith('onedrive')
        };
        fileLogEntries.push(entry);
        updateFileLogStats(entry);
    });
    
    updateFileLogSummary();
}

/**
 * Adds a random file log entry for the mock simulation.
 */
function addRandomFileLogEntry() {
    const drive = fileLogSelectedDrive;
    const types = ['new', 'modified', 'deleted', 'onedrive', 'onedrive-sync'];
    const paths = [
        `${drive}\\Users\\User\\OneDrive\\Documents`,
        `${drive}\\Users\\User\\Downloads`,
        `${drive}\\Windows\\Temp`,
        `${drive}\\Users\\User\\AppData\\Local`,
        `${drive}\\Users\\User\\Documents\\Projects`,
        `${drive}\\Users\\User\\OneDrive\\Work`,
        `${drive}\\Program Files`
    ];
    const extensions = ['.txt', '.docx', '.xlsx', '.json', '.tmp', '.log', '.py', '.js', '.png', '.pdf'];
    
    const type = types[Math.floor(Math.random() * types.length)];
    const basePath = paths[Math.floor(Math.random() * paths.length)];
    const ext = extensions[Math.floor(Math.random() * extensions.length)];
    const filename = `file_${Math.floor(Math.random() * 9999)}${ext}`;
    
    const entry = {
        timestamp: new Date(),
        path: `${basePath}\\${filename}`,
        type: type,
        size: Math.floor(Math.random() * 10485760) + 512,
        isOneDrive: type.startsWith('onedrive') || basePath.includes('OneDrive')
    };
    
    fileLogEntries.push(entry);
    if (fileLogEntries.length > 100) fileLogEntries.shift();
    
    updateFileLogStats(entry);
    updateFileLogSummary();
    renderFileLog(true);
}

/**
 * Updates the file log statistics counters.
 *
 * @param {Object} entry - The file log entry.
 */
function updateFileLogStats(entry) {
    if (entry.type === 'new') {
        fileLogStats.new++;
        fileLogStats.newSize += entry.size;
    } else if (entry.type === 'modified') {
        fileLogStats.modified++;
    } else if (entry.type === 'deleted') {
        fileLogStats.deleted++;
        fileLogStats.deletedSize += entry.size;
    } else if (entry.type === 'onedrive') {
        fileLogStats.onedrive++;
        fileLogStats.onedriveDownSize += entry.size;
    } else if (entry.type === 'onedrive-sync') {
        fileLogStats.onedrive++;
        fileLogStats.onedriveUpSize += entry.size;
    }
    
    // Track path counts
    const folder = entry.path.substring(0, entry.path.lastIndexOf('\\'));
    fileLogPathCounts[folder] = (fileLogPathCounts[folder] || 0) + 1;
}

/**
 * Updates the file log summary panel.
 */
function updateFileLogSummary() {
    // Check if we're on the file log tab (elements exist)
    const newCountEl = document.getElementById('fileLogNewCount');
    if (!newCountEl) return; // Not on file log tab, skip update
    
    newCountEl.textContent = fileLogStats.new;
    document.getElementById('fileLogModifiedCount').textContent = fileLogStats.modified;
    document.getElementById('fileLogOnedriveCount').textContent = fileLogStats.onedrive;
    document.getElementById('fileLogDeletedCount').textContent = fileLogStats.deleted;
    
    document.getElementById('fileLogNewSize').textContent = formatFileSize(fileLogStats.newSize);
    document.getElementById('fileLogOnedriveSize').textContent = formatFileSize(fileLogStats.onedriveDownSize);
    document.getElementById('fileLogOnedriveUpSize').textContent = formatFileSize(fileLogStats.onedriveUpSize);
    document.getElementById('fileLogTotalSize').textContent = formatFileSize(
        fileLogStats.newSize + fileLogStats.onedriveDownSize + fileLogStats.onedriveUpSize
    );
    
    // OneDrive status
    const lastOD = fileLogEntries.find(e => e.isOneDrive);
    const lastActivityEl = document.getElementById('fileLogLastActivity');
    if (lastOD && lastActivityEl) {
        lastActivityEl.textContent = formatTime(lastOD.timestamp);
    }
    const statusEl = document.getElementById('fileLogOnedriveStatus');
    if (statusEl) statusEl.textContent = 'Connected & Syncing';
    const pendingEl = document.getElementById('fileLogPending');
    if (pendingEl) pendingEl.textContent = `${Math.floor(Math.random() * 5)} files`;
    
    // Top active paths
    const sortedPaths = Object.entries(fileLogPathCounts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5);
    
    const activePathsEl = document.getElementById('fileLogActivePaths');
    if (activePathsEl && sortedPaths.length > 0) {
        activePathsEl.innerHTML = sortedPaths.map(([path, count]) => `
            <div class="file-log-active-path">
                <a href="#" class="file-log-path-link truncate" style="max-width: 200px;" title="${path}" onclick="openFolder('${path.replace(/\\/g, '\\\\')}'); return false;">${shortenPath(path)}</a>
                <span class="text-[#00d4ff]">${count} changes</span>
            </div>
        `).join('');
    }
}

/**
 * Opens a folder in Windows File Explorer.
 *
 * @param {string} path - The folder path to open.
 */
async function openFolder(path) {
    try {
        const response = await fetch('/api/open-folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: path })
        });
        
        if (!response.ok) {
            const error = await response.json();
            console.error('Failed to open folder:', error.detail);
        }
    } catch (e) {
        console.error('Error opening folder:', e);
    }
}

/**
 * Renders the file log entries.
 *
 * @param {boolean} isNewEntry - Whether this render is due to a new entry being added.
 */
function renderFileLog(isNewEntry = false) {
    const container = document.getElementById('fileChangeLog');
    if (!container) return;
    
    // Check if user is at the bottom before re-rendering
    const scrollThreshold = 30; // pixels from bottom to consider "at bottom"
    const wasAtBottom = (container.scrollHeight - container.scrollTop - container.clientHeight) <= scrollThreshold;
    
    let filtered = fileLogEntries;
    if (fileLogActiveFilter !== 'all') {
        if (fileLogActiveFilter === 'onedrive') {
            filtered = fileLogEntries.filter(e => e.type.startsWith('onedrive'));
        } else {
            filtered = fileLogEntries.filter(e => e.type === fileLogActiveFilter);
        }
    }
    
    container.innerHTML = filtered.map(entry => {
        const icon = getFileLogIcon(entry.type);
        const typeClass = entry.type.startsWith('onedrive') ? 
            (entry.type === 'onedrive-sync' ? 'type-onedrive-sync' : 'type-onedrive') : 
            `type-${entry.type}`;
        
        const pathParts = entry.path.split('\\');
        const filename = pathParts.pop();
        const folder = pathParts.join('\\');
        const folderEscaped = folder.replace(/\\/g, '\\\\');
        
        const tag = entry.isOneDrive ? '<span class="file-log-tag onedrive">OneDrive</span>' : '';
        
        return `
            <div class="file-log-entry ${typeClass}">
                <span class="file-log-time">${formatTime(entry.timestamp)}</span>
                <i class="codicon ${icon} file-log-icon"></i>
                <a href="#" class="file-log-path file-log-path-link" title="Open folder: ${escapeHtml(folder)}" onclick="openFolder('${folderEscaped}'); return false;">
                    <span class="folder">${escapeHtml(folder)}\\</span><span class="filename">${escapeHtml(filename)}</span>
                </a>
                <span class="file-log-size">${formatFileSize(entry.size)}</span>
                ${tag}
            </div>
        `;
    }).join('');
    
    // Auto-scroll to bottom only if user was already at bottom, or on initial load
    if (wasAtBottom || !isNewEntry) {
        container.scrollTop = container.scrollHeight;
    }
}

/**
 * Gets the codicon class for a file log entry type.
 *
 * @param {string} type - The entry type.
 * @returns {string} The codicon class.
 */
function getFileLogIcon(type) {
    switch (type) {
        case 'new': return 'codicon-new-file';
        case 'modified': return 'codicon-edit';
        case 'deleted': return 'codicon-trash';
        case 'moved': return 'codicon-file-symlink-file';
        case 'onedrive': return 'codicon-cloud-download';
        case 'onedrive-sync': return 'codicon-cloud-upload';
        default: return 'codicon-file';
    }
}

/**
 * Formats a file size in bytes to a human-readable string.
 *
 * @param {number} bytes - The size in bytes.
 * @returns {string} The formatted size string.
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

/**
 * Formats a timestamp to a time string.
 *
 * @param {Date} date - The date object.
 * @returns {string} The formatted time string.
 */
function formatTime(date) {
    return date.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

/**
 * Shortens a file path for display.
 *
 * @param {string} path - The full path.
 * @returns {string} The shortened path.
 */
function shortenPath(path) {
    if (path.length <= 35) return path;
    const parts = path.split('\\');
    if (parts.length <= 3) return path;
    return parts[0] + '\\...\\' + parts.slice(-2).join('\\');
}

/**
 * Escapes HTML special characters.
 *
 * @param {string} text - The text to escape.
 * @returns {string} The escaped text.
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Init
initCharts();
initBLE();
connectWS();
fetchInfo();
fetchDisks();