const LANG_STORAGE_KEY = "edge_voice_dashboard_lang";
const LOG_STORAGE_PREFIX = "edge_voice_dashboard_logs";
const LOG_MAX_LINES = 500;

let activeLang = localStorage.getItem(LANG_STORAGE_KEY) || "zh";
let activeLogKey = `${LOG_STORAGE_PREFIX}_unknown`;

const I18N = {
  zh: {
    dashboardTitle: "Edge Voice RAG 仪表板",
    transportControl: "传输控制",
    backendApiBase: "后端 API 地址",
    mode: "模式",
    modeWifi: "WiFi",
    modeBluetooth: "蓝牙串口",
    modeWired: "有线串口",
    enabled: "启用",
    wifiHint: "WiFi 模式通过后端 WebSocket 端点进行流式传输。",
    bluetoothSerial: "蓝牙串口",
    wiredSerial: "有线串口",
    port: "端口",
    baudrate: "波特率",
    timeoutMs: "超时 (ms)",
    readSize: "读取大小",
    frameBytes: "帧字节数",
    codec: "编码",
    deviceSampleRate: "设备采样率",
    applyTransport: "应用传输",
    reload: "重新加载",
    runtimeMode: "运行模式",
    runtimeEnabled: "运行启用",
    gatewayRunning: "网关运行",
    gatewayConnected: "网关连接",
    wifiVoiceStream: "WiFi 语音流",
    websocketUrl: "WebSocket 地址",
    connectStartMic: "连接并启动麦克风",
    disconnect: "断开连接",
    interrupt: "打断",
    connection: "连接",
    audio: "音频",
    switchToEnglish: "English",
    switchToChinese: "中文",
    commonOn: "开",
    commonOff: "关",
    commonUnknown: "未知",
    badgeTransport: "传输",
    badgeGateway: "网关",
    badgeConnectedAt: "已连接 @ {port}",
    badgeRunningAt: "运行中 @ {port}",
    badgeIdle: "空闲",
    badgeUnavailable: "不可用",
    hintEnableWifiToConnect: "请启用 WiFi 传输后再连接 WebSocket。",
    statusConnected: "已连接",
    statusDisconnected: "已断开",
    statusIdle: "空闲",
    statusCapturing: "采集中",
    statusPlaying: "播放中",
    errorApiBaseEmpty: "API 地址为空。",
    errorWsUrlEmpty: "WebSocket 地址为空。",
    logWsAlreadyConnected: "WebSocket 已连接。",
    logWsConnected: "WebSocket 已连接: {url}",
    logMicStartFailed: "麦克风启动失败: {error}",
    logWsDisconnected: "WebSocket 已断开。",
    logWsError: "WebSocket 错误。",
    logGatewayReady: "网关就绪。sample_rate={sample_rate} mode={mode}",
    logGatewayError: "网关错误: {message}",
    logControlEvent: "控制事件: {text}",
    logTextFrame: "文本帧: {text}",
    logMicStarted: "麦克风已启动。",
    logTransportLoaded: "传输配置已加载: mode={mode} enabled={enabled}",
    logTransportApplied: "传输配置已应用: mode={mode} enabled={enabled}",
    logWsDisconnectedByTransport: "WiFi 传输未激活，已断开 WebSocket。",
    logHealthRefreshFailed: "健康检查刷新失败: {error}",
    logApplyTransportFailed: "应用传输失败: {error}",
    logReloadTransportFailed: "重新加载传输失败: {error}",
    logConnectFailed: "连接失败: {error}",
    logInterruptSent: "已发送打断信号。",
    logInitialLoadFailed: "初始加载失败: {error}",
  },
  en: {
    dashboardTitle: "Edge Voice RAG Dashboard",
    transportControl: "Transport Control",
    backendApiBase: "Backend API Base",
    mode: "Mode",
    modeWifi: "WiFi",
    modeBluetooth: "Bluetooth Serial",
    modeWired: "Wired Serial",
    enabled: "Enabled",
    wifiHint: "WiFi mode uses WebSocket streaming through the configured backend endpoint.",
    bluetoothSerial: "Bluetooth Serial",
    wiredSerial: "Wired Serial",
    port: "Port",
    baudrate: "Baudrate",
    timeoutMs: "Timeout (ms)",
    readSize: "Read Size",
    frameBytes: "Frame Bytes",
    codec: "Codec",
    deviceSampleRate: "Device Sample Rate",
    applyTransport: "Apply Transport",
    reload: "Reload",
    runtimeMode: "Runtime Mode",
    runtimeEnabled: "Runtime Enabled",
    gatewayRunning: "Gateway Running",
    gatewayConnected: "Gateway Connected",
    wifiVoiceStream: "WiFi Voice Stream",
    websocketUrl: "WebSocket URL",
    connectStartMic: "Connect + Start Mic",
    disconnect: "Disconnect",
    interrupt: "Interrupt",
    connection: "Connection",
    audio: "Audio",
    switchToEnglish: "English",
    switchToChinese: "中文",
    commonOn: "on",
    commonOff: "off",
    commonUnknown: "unknown",
    badgeTransport: "transport",
    badgeGateway: "gateway",
    badgeConnectedAt: "connected @ {port}",
    badgeRunningAt: "running @ {port}",
    badgeIdle: "idle",
    badgeUnavailable: "unavailable",
    hintEnableWifiToConnect: "Enable WiFi transport to use WebSocket stream.",
    statusConnected: "connected",
    statusDisconnected: "disconnected",
    statusIdle: "idle",
    statusCapturing: "capturing",
    statusPlaying: "playing",
    errorApiBaseEmpty: "API base is empty.",
    errorWsUrlEmpty: "WebSocket URL is empty.",
    logWsAlreadyConnected: "WebSocket already connected.",
    logWsConnected: "WebSocket connected: {url}",
    logMicStartFailed: "Microphone start failed: {error}",
    logWsDisconnected: "WebSocket disconnected.",
    logWsError: "WebSocket error.",
    logGatewayReady: "Gateway ready. sample_rate={sample_rate} mode={mode}",
    logGatewayError: "Gateway error: {message}",
    logControlEvent: "Control event: {text}",
    logTextFrame: "Text frame: {text}",
    logMicStarted: "Microphone started.",
    logTransportLoaded: "Transport loaded: mode={mode} enabled={enabled}",
    logTransportApplied: "Transport applied: mode={mode} enabled={enabled}",
    logWsDisconnectedByTransport: "WebSocket disconnected because WiFi transport is not active.",
    logHealthRefreshFailed: "Health refresh failed: {error}",
    logApplyTransportFailed: "Apply transport failed: {error}",
    logReloadTransportFailed: "Reload transport failed: {error}",
    logConnectFailed: "Connect failed: {error}",
    logInterruptSent: "Interrupt sent.",
    logInitialLoadFailed: "Initial dashboard load failed: {error}",
  },
};

function t(key, vars = {}) {
  let text = (I18N[activeLang] && I18N[activeLang][key]) || I18N.en[key] || key;
  for (const [name, value] of Object.entries(vars)) {
    text = text.replace(`{${name}}`, String(value));
  }
  return text;
}

function setActiveLogKey(startupAt) {
  const nextKey = `${LOG_STORAGE_PREFIX}_${startupAt || "unknown"}`;
  const changed = nextKey !== activeLogKey;
  activeLogKey = nextKey;
  return changed;
}

function readPersistedLogLines() {
  try {
    const raw = localStorage.getItem(activeLogKey);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((item) => typeof item === "string");
  } catch {
    return [];
  }
}

function writePersistedLogLines(lines) {
  try {
    localStorage.setItem(activeLogKey, JSON.stringify(lines.slice(-LOG_MAX_LINES)));
  } catch {
    // Ignore storage quota errors.
  }
}

function appendPersistedLogLine(line) {
  const lines = readPersistedLogLines();
  lines.push(line);
  writePersistedLogLines(lines);
}

function restoreLogPanel() {
  const lines = readPersistedLogLines();
  dom.logs.textContent = lines.length > 0 ? `${lines.join("\n")}\n` : "";
  dom.logs.scrollTop = dom.logs.scrollHeight;
}

const dom = {
  langToggleBtn: document.getElementById("langToggleBtn"),
  apiBase: document.getElementById("apiBase"),
  transportMode: document.getElementById("transportMode"),
  transportEnabled: document.getElementById("transportEnabled"),
  bluetoothConfig: document.getElementById("bluetoothConfig"),
  wiredConfig: document.getElementById("wiredConfig"),
  wifiHint: document.getElementById("wifiHint"),
  saveTransportBtn: document.getElementById("saveTransportBtn"),
  reloadTransportBtn: document.getElementById("reloadTransportBtn"),
  runtimeMode: document.getElementById("runtimeMode"),
  runtimeEnabled: document.getElementById("runtimeEnabled"),
  runtimeGatewayRunning: document.getElementById("runtimeGatewayRunning"),
  runtimeGatewayConnected: document.getElementById("runtimeGatewayConnected"),
  backendTransportBadge: document.getElementById("backendTransportBadge"),
  gatewayBadge: document.getElementById("gatewayBadge"),
  wsUrl: document.getElementById("wsUrl"),
  connectBtn: document.getElementById("connectBtn"),
  disconnectBtn: document.getElementById("disconnectBtn"),
  interruptBtn: document.getElementById("interruptBtn"),
  connectionStatus: document.getElementById("connectionStatus"),
  audioStatus: document.getElementById("audioStatus"),
  logs: document.getElementById("logs"),
  btPort: document.getElementById("btPort"),
  btBaudrate: document.getElementById("btBaudrate"),
  btTimeoutMs: document.getElementById("btTimeoutMs"),
  btReadSize: document.getElementById("btReadSize"),
  btFramePayloadBytes: document.getElementById("btFramePayloadBytes"),
  btAudioCodec: document.getElementById("btAudioCodec"),
  btSampleRate: document.getElementById("btSampleRate"),
  wdPort: document.getElementById("wdPort"),
  wdBaudrate: document.getElementById("wdBaudrate"),
  wdTimeoutMs: document.getElementById("wdTimeoutMs"),
  wdReadSize: document.getElementById("wdReadSize"),
  wdFramePayloadBytes: document.getElementById("wdFramePayloadBytes"),
  wdAudioCodec: document.getElementById("wdAudioCodec"),
  wdSampleRate: document.getElementById("wdSampleRate"),
};

function applyLanguage() {
  document.documentElement.lang = activeLang === "zh" ? "zh-CN" : "en";
  document.title = t("dashboardTitle");

  for (const element of document.querySelectorAll("[data-i18n]")) {
    const key = element.getAttribute("data-i18n");
    element.textContent = t(key);
  }

  if (dom.langToggleBtn) {
    dom.langToggleBtn.textContent = activeLang === "zh" ? t("switchToEnglish") : t("switchToChinese");
  }
}

function parseIntSafe(value, fallback, minimum = 1) {
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed)) {
    return fallback;
  }
  return Math.max(minimum, parsed);
}

function normalizeBaseUrl(rawBase) {
  const cleaned = String(rawBase || "").trim();
  if (!cleaned) {
    throw new Error(t("errorApiBaseEmpty"));
  }
  const url = new URL(cleaned);
  url.pathname = url.pathname.replace(/\/+$/, "");
  return url;
}

function setPill(node, text, tone) {
  node.textContent = text;
  node.className = `pill ${tone}`;
}

function stateLabel(value) {
  return value ? t("commonOn") : t("commonOff");
}

class VoiceClient {
  constructor() {
    this.socket = null;
    this.audioContext = null;
    this.nextPlayTime = 0;
    this.micStream = null;
    this.sourceNode = null;
    this.processorNode = null;
    this.targetSampleRate = 16000;
    this.jitterSafetySeconds = 0.1;
    this.connectionState = "disconnected";
    this.audioState = "idle";
  }

  log(message) {
    const timestamp = new Date().toLocaleTimeString();
    const line = `[${timestamp}] ${message}`;
    dom.logs.textContent += `${line}\n`;
    dom.logs.scrollTop = dom.logs.scrollHeight;
    appendPersistedLogLine(line);
  }

  setConnection(status) {
    this.connectionState = status;
    const keyMap = {
      connected: "statusConnected",
      disconnected: "statusDisconnected",
    };
    dom.connectionStatus.textContent = t(keyMap[status] || "commonUnknown");
  }

  setAudio(status) {
    this.audioState = status;
    const keyMap = {
      idle: "statusIdle",
      capturing: "statusCapturing",
      playing: "statusPlaying",
    };
    dom.audioStatus.textContent = t(keyMap[status] || "commonUnknown");
  }

  refreshLocalizedStates() {
    this.setConnection(this.connectionState);
    this.setAudio(this.audioState);
  }

  isConnected() {
    return this.socket !== null && this.socket.readyState === WebSocket.OPEN;
  }

  async connect(url) {
    if (this.isConnected()) {
      this.log(t("logWsAlreadyConnected"));
      return;
    }

    if (!url) {
      throw new Error(t("errorWsUrlEmpty"));
    }

    this.audioContext = this.audioContext || new AudioContext();
    await this.audioContext.resume();

    return new Promise((resolve, reject) => {
      let settled = false;
      this.socket = new WebSocket(url);
      this.socket.binaryType = "arraybuffer";

      this.socket.onopen = async () => {
        this.setConnection("connected");
        this.log(t("logWsConnected", { url }));

        try {
          await this.startMicrophone();
          this.sendControl("speech_start");
          settled = true;
          resolve();
        } catch (error) {
          this.log(t("logMicStartFailed", { error: error.message }));
          settled = true;
          reject(error);
        }
      };

      this.socket.onmessage = async (event) => {
        if (typeof event.data === "string") {
          this.handleControlFrame(event.data);
          return;
        }
        const buffer = event.data instanceof Blob ? await event.data.arrayBuffer() : event.data;
        this.handleIncomingPcm(buffer);
      };

      this.socket.onclose = () => {
        this.stopMicrophone();
        this.setConnection("disconnected");
        this.setAudio("idle");
        this.log(t("logWsDisconnected"));
        this.socket = null;
      };

      this.socket.onerror = () => {
        this.log(t("logWsError"));
        if (!settled) {
          settled = true;
          reject(new Error(t("logWsError")));
        }
      };
    });
  }

  async disconnect() {
    this.sendControl("interrupt");
    this.stopMicrophone();

    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }

    this.setConnection("disconnected");
    this.setAudio("idle");
  }

  sendControl(action) {
    if (!this.isConnected()) {
      return;
    }
    this.socket.send(JSON.stringify({ action }));
  }

  handleControlFrame(rawText) {
    try {
      const message = JSON.parse(rawText);
      if (message.event === "ready") {
        this.log(
          t("logGatewayReady", {
            sample_rate: message.sample_rate,
            mode: message.transport_mode || t("commonUnknown"),
          })
        );
        return;
      }
      if (message.event === "pong") {
        return;
      }
      if (message.event === "error") {
        this.log(t("logGatewayError", { message: message.message || t("commonUnknown") }));
        return;
      }
      this.log(t("logControlEvent", { text: rawText }));
    } catch {
      this.log(t("logTextFrame", { text: rawText }));
    }
  }

  async startMicrophone() {
    if (this.micStream) {
      return;
    }

    this.micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });

    this.sourceNode = this.audioContext.createMediaStreamSource(this.micStream);
    this.processorNode = this.audioContext.createScriptProcessor(4096, 1, 1);

    this.processorNode.onaudioprocess = (event) => {
      if (!this.isConnected()) {
        return;
      }

      const input = event.inputBuffer.getChannelData(0);
      const downsampled = this.downsample(input, this.audioContext.sampleRate, this.targetSampleRate);
      const pcm = this.floatToInt16(downsampled);
      this.socket.send(pcm.buffer);
    };

    this.sourceNode.connect(this.processorNode);
    this.processorNode.connect(this.audioContext.destination);
    this.setAudio("capturing");
    this.log(t("logMicStarted"));
  }

  stopMicrophone() {
    if (this.processorNode) {
      this.processorNode.disconnect();
      this.processorNode.onaudioprocess = null;
      this.processorNode = null;
    }

    if (this.sourceNode) {
      this.sourceNode.disconnect();
      this.sourceNode = null;
    }

    if (this.micStream) {
      this.micStream.getTracks().forEach((track) => track.stop());
      this.micStream = null;
    }
  }

  handleIncomingPcm(arrayBuffer) {
    if (!arrayBuffer || arrayBuffer.byteLength === 0) {
      return;
    }

    const int16Data = new Int16Array(arrayBuffer);
    const float32Data = new Float32Array(int16Data.length);

    for (let i = 0; i < int16Data.length; i += 1) {
      float32Data[i] = int16Data[i] / 32768.0;
    }

    this.schedulePlayback(float32Data);
  }

  schedulePlayback(float32Data) {
    if (!this.audioContext) {
      return;
    }

    if (this.nextPlayTime < this.audioContext.currentTime) {
      this.nextPlayTime = this.audioContext.currentTime + this.jitterSafetySeconds;
    }

    const buffer = this.audioContext.createBuffer(1, float32Data.length, this.targetSampleRate);
    buffer.getChannelData(0).set(float32Data);

    const source = this.audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(this.audioContext.destination);
    source.start(this.nextPlayTime);

    this.nextPlayTime += buffer.duration;
    this.setAudio("playing");
  }

  downsample(input, inputSampleRate, outputSampleRate) {
    if (outputSampleRate >= inputSampleRate) {
      return input;
    }

    const ratio = inputSampleRate / outputSampleRate;
    const outputLength = Math.round(input.length / ratio);
    const output = new Float32Array(outputLength);

    let outputIndex = 0;
    let inputIndex = 0;

    while (outputIndex < outputLength) {
      const nextInputIndex = Math.round((outputIndex + 1) * ratio);
      let sum = 0;
      let count = 0;

      for (let i = inputIndex; i < nextInputIndex && i < input.length; i += 1) {
        sum += input[i];
        count += 1;
      }

      output[outputIndex] = count > 0 ? sum / count : 0;
      outputIndex += 1;
      inputIndex = nextInputIndex;
    }

    return output;
  }

  floatToInt16(float32) {
    const buffer = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i += 1) {
      const sample = Math.max(-1, Math.min(1, float32[i]));
      buffer[i] = sample < 0 ? sample * 32768 : sample * 32767;
    }
    return buffer;
  }
}

class DashboardController {
  constructor(client) {
    this.client = client;
    this.healthTimer = null;
    this.knownWsPath = "/ws/audio-stream";
    this.lastTransportStatus = null;
    this.lastUartStatus = null;
  }

  log(message) {
    this.client.log(message);
  }

  buildUrl(path) {
    const base = normalizeBaseUrl(dom.apiBase.value);
    return new URL(path, `${base.toString()}/`).toString();
  }

  deriveWsUrl(wsPath) {
    const base = normalizeBaseUrl(dom.apiBase.value);
    const protocol = base.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${base.host}${wsPath}`;
  }

  setRuntimeStatus(status, uart) {
    this.lastTransportStatus = status;
    this.lastUartStatus = uart;

    dom.runtimeMode.textContent = status.mode || t("commonUnknown");
    dom.runtimeEnabled.textContent = stateLabel(Boolean(status.enabled));
    dom.runtimeGatewayRunning.textContent = stateLabel(Boolean(status.gateway_running));
    dom.runtimeGatewayConnected.textContent = stateLabel(Boolean(status.gateway_connected));

    const transportTone = !status.enabled ? "bad" : status.mode === "wifi" ? "ok" : "warn";
    const transportText = `${t("badgeTransport")}: ${status.mode || t("commonUnknown")} / ${
      status.enabled ? t("commonOn") : t("commonOff")
    }`;
    setPill(dom.backendTransportBadge, transportText, transportTone);

    const gatewayRunning = Boolean(uart?.running);
    const gatewayConnected = Boolean(uart?.connected);
    const gatewayTone = gatewayConnected ? "ok" : gatewayRunning ? "warn" : "neutral";
    const gatewayText = gatewayConnected
      ? `${t("badgeGateway")}: ${t("badgeConnectedAt", { port: uart.port || t("commonUnknown") })}`
      : gatewayRunning
        ? `${t("badgeGateway")}: ${t("badgeRunningAt", { port: uart?.port || t("commonUnknown") })}`
        : `${t("badgeGateway")}: ${t("badgeIdle")}`;
    setPill(dom.gatewayBadge, gatewayText, gatewayTone);
  }

  populateSerial(prefix, config) {
    dom[`${prefix}Port`].value = config.port || "";
    dom[`${prefix}Baudrate`].value = String(config.baudrate ?? "");
    dom[`${prefix}TimeoutMs`].value = String(config.timeout_ms ?? "");
    dom[`${prefix}ReadSize`].value = String(config.read_size ?? "");
    dom[`${prefix}FramePayloadBytes`].value = String(config.frame_payload_bytes ?? "");
    dom[`${prefix}AudioCodec`].value = config.audio_codec || "ulaw8k";
    dom[`${prefix}SampleRate`].value = String(config.device_sample_rate ?? "");
  }

  collectSerial(prefix) {
    return {
      port: dom[`${prefix}Port`].value.trim(),
      baudrate: parseIntSafe(dom[`${prefix}Baudrate`].value, 115200, 1200),
      timeout_ms: parseIntSafe(dom[`${prefix}TimeoutMs`].value, 40, 1),
      read_size: parseIntSafe(dom[`${prefix}ReadSize`].value, 512, 64),
      frame_payload_bytes: parseIntSafe(dom[`${prefix}FramePayloadBytes`].value, 512, 64),
      audio_codec: dom[`${prefix}AudioCodec`].value,
      device_sample_rate: parseIntSafe(dom[`${prefix}SampleRate`].value, 16000, 4000),
    };
  }

  collectTransportPayload() {
    return {
      mode: dom.transportMode.value,
      enabled: dom.transportEnabled.checked,
      bluetooth: this.collectSerial("bt"),
      wired: this.collectSerial("wd"),
      wifi: { ws_path: this.knownWsPath },
    };
  }

  updateVisibility() {
    const mode = dom.transportMode.value;
    dom.bluetoothConfig.classList.toggle("hidden", mode !== "bluetooth");
    dom.wiredConfig.classList.toggle("hidden", mode !== "wired");
    dom.wifiHint.classList.toggle("hidden", mode !== "wifi");

    const wifiReady = mode === "wifi" && dom.transportEnabled.checked;
    dom.connectBtn.disabled = !wifiReady;
    dom.connectBtn.title = wifiReady ? "" : t("hintEnableWifiToConnect");
  }

  async loadTransport() {
    const url = this.buildUrl("/api/dashboard/transport");
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`transport GET failed (${response.status})`);
    }

    const payload = await response.json();
    const config = payload.config || {};
    const status = payload.status || {};

    dom.transportMode.value = config.mode || "wifi";
    dom.transportEnabled.checked = Boolean(config.enabled);
    this.populateSerial("bt", config.bluetooth || {});
    this.populateSerial("wd", config.wired || {});

    this.knownWsPath = payload.ws_path || config.wifi?.ws_path || this.knownWsPath;
    dom.wsUrl.value = this.deriveWsUrl(this.knownWsPath);

    this.updateVisibility();
    this.setRuntimeStatus(status, null);
    this.log(t("logTransportLoaded", { mode: config.mode, enabled: String(config.enabled) }));
  }

  async saveTransport() {
    const payload = this.collectTransportPayload();
    const url = this.buildUrl("/api/dashboard/transport");

    const response = await fetch(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`transport PUT failed (${response.status}): ${detail}`);
    }

    const body = await response.json();
    this.knownWsPath = body.ws_path || this.knownWsPath;
    dom.wsUrl.value = this.deriveWsUrl(this.knownWsPath);
    this.setRuntimeStatus(body.status || {}, null);
    this.updateVisibility();

    if ((payload.mode !== "wifi" || !payload.enabled) && this.client.isConnected()) {
      await this.client.disconnect();
      this.log(t("logWsDisconnectedByTransport"));
    }

    this.log(t("logTransportApplied", { mode: payload.mode, enabled: String(payload.enabled) }));
    await this.refreshHealth();
  }

  async refreshHealth() {
    try {
      const response = await fetch(this.buildUrl("/healthz"));
      if (!response.ok) {
        throw new Error(`healthz failed (${response.status})`);
      }

      const health = await response.json();
      if (setActiveLogKey(health.startup_at)) {
        restoreLogPanel();
      }

      this.setRuntimeStatus(health.transport || {}, health.uart || {});
      return health;
    } catch (error) {
      this.log(t("logHealthRefreshFailed", { error: error.message }));
      setPill(dom.backendTransportBadge, `${t("badgeTransport")}: ${t("badgeUnavailable")}`, "bad");
      setPill(dom.gatewayBadge, `${t("badgeGateway")}: ${t("badgeUnavailable")}`, "bad");
      return null;
    }
  }

  startHealthPolling() {
    this.stopHealthPolling();
    this.healthTimer = window.setInterval(() => {
      this.refreshHealth();
    }, 5000);
  }

  stopHealthPolling() {
    if (this.healthTimer) {
      window.clearInterval(this.healthTimer);
      this.healthTimer = null;
    }
  }

  bindEvents() {
    dom.transportMode.addEventListener("change", () => this.updateVisibility());
    dom.transportEnabled.addEventListener("change", () => this.updateVisibility());

    dom.saveTransportBtn.addEventListener("click", async () => {
      try {
        await this.saveTransport();
      } catch (error) {
        this.log(t("logApplyTransportFailed", { error: error.message }));
      }
    });

    dom.reloadTransportBtn.addEventListener("click", async () => {
      try {
        await this.loadTransport();
        await this.refreshHealth();
      } catch (error) {
        this.log(t("logReloadTransportFailed", { error: error.message }));
      }
    });

    dom.connectBtn.addEventListener("click", async () => {
      try {
        await this.client.connect(dom.wsUrl.value.trim());
      } catch (error) {
        this.log(t("logConnectFailed", { error: error.message }));
      }
    });

    dom.disconnectBtn.addEventListener("click", async () => {
      await this.client.disconnect();
    });

    dom.interruptBtn.addEventListener("click", () => {
      this.client.sendControl("interrupt");
      this.log(t("logInterruptSent"));
    });

    if (dom.langToggleBtn) {
      dom.langToggleBtn.addEventListener("click", () => {
        activeLang = activeLang === "zh" ? "en" : "zh";
        localStorage.setItem(LANG_STORAGE_KEY, activeLang);
        applyLanguage();
        this.updateVisibility();
        if (this.lastTransportStatus) {
          this.setRuntimeStatus(this.lastTransportStatus, this.lastUartStatus);
        }
        this.client.refreshLocalizedStates();
      });
    }
  }

  async init() {
    this.bindEvents();
    applyLanguage();
    restoreLogPanel();
    this.client.refreshLocalizedStates();
    this.updateVisibility();

    try {
      await this.refreshHealth();
      await this.loadTransport();
      await this.refreshHealth();
    } catch (error) {
      this.log(t("logInitialLoadFailed", { error: error.message }));
    }

    this.startHealthPolling();
  }
}

const client = new VoiceClient();
const dashboard = new DashboardController(client);

dashboard.init();
