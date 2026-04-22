const dom = {
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
    throw new Error("API base is empty.");
  }
  const url = new URL(cleaned);
  url.pathname = url.pathname.replace(/\/+$/, "");
  return url;
}

function setPill(node, text, tone) {
  node.textContent = text;
  node.className = `pill ${tone}`;
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
  }

  log(message) {
    const timestamp = new Date().toLocaleTimeString();
    dom.logs.textContent += `[${timestamp}] ${message}\n`;
    dom.logs.scrollTop = dom.logs.scrollHeight;
  }

  setConnection(status) {
    dom.connectionStatus.textContent = status;
  }

  setAudio(status) {
    dom.audioStatus.textContent = status;
  }

  isConnected() {
    return this.socket !== null && this.socket.readyState === WebSocket.OPEN;
  }

  async connect(url) {
    if (this.isConnected()) {
      this.log("WebSocket already connected.");
      return;
    }

    if (!url) {
      throw new Error("WebSocket URL is empty.");
    }

    this.audioContext = this.audioContext || new AudioContext();
    await this.audioContext.resume();

    return new Promise((resolve, reject) => {
      let settled = false;
      this.socket = new WebSocket(url);
      this.socket.binaryType = "arraybuffer";

      this.socket.onopen = async () => {
        this.setConnection("connected");
        this.log(`WebSocket connected: ${url}`);

        try {
          await this.startMicrophone();
          this.sendControl("speech_start");
          settled = true;
          resolve();
        } catch (error) {
          this.log(`Microphone start failed: ${error.message}`);
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
        this.log("WebSocket disconnected.");
        this.socket = null;
      };

      this.socket.onerror = () => {
        this.log("WebSocket error.");
        if (!settled) {
          settled = true;
          reject(new Error("WebSocket error"));
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
          `Gateway ready. sample_rate=${message.sample_rate} mode=${message.transport_mode || "unknown"}`
        );
        return;
      }
      if (message.event === "pong") {
        return;
      }
      if (message.event === "error") {
        this.log(`Gateway error: ${message.message || "unknown"}`);
        return;
      }
      this.log(`Control event: ${rawText}`);
    } catch {
      this.log(`Text frame: ${rawText}`);
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
    this.log("Microphone started.");
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
    dom.runtimeMode.textContent = status.mode || "unknown";
    dom.runtimeEnabled.textContent = status.enabled ? "true" : "false";
    dom.runtimeGatewayRunning.textContent = status.gateway_running ? "true" : "false";
    dom.runtimeGatewayConnected.textContent = status.gateway_connected ? "true" : "false";

    const transportTone = !status.enabled
      ? "bad"
      : status.mode === "wifi"
        ? "ok"
        : "warn";
    setPill(
      dom.backendTransportBadge,
      `transport: ${status.mode || "unknown"} / ${status.enabled ? "on" : "off"}`,
      transportTone
    );

    const gatewayRunning = Boolean(uart?.running);
    const gatewayConnected = Boolean(uart?.connected);
    const gatewayTone = gatewayConnected ? "ok" : gatewayRunning ? "warn" : "neutral";
    const gatewayText = gatewayConnected
      ? `gateway: connected @ ${uart.port || "unknown"}`
      : gatewayRunning
        ? `gateway: running @ ${uart?.port || "unknown"}`
        : "gateway: idle";
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
    dom.connectBtn.title = wifiReady ? "" : "Enable WiFi transport to use WebSocket stream.";
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
    this.log(`Transport loaded: mode=${config.mode} enabled=${config.enabled}`);
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
      this.log("WebSocket disconnected because WiFi transport is not active.");
    }

    this.log(`Transport applied: mode=${payload.mode} enabled=${payload.enabled}`);
    await this.refreshHealth();
  }

  async refreshHealth() {
    try {
      const response = await fetch(this.buildUrl("/healthz"));
      if (!response.ok) {
        throw new Error(`healthz failed (${response.status})`);
      }
      const health = await response.json();
      this.setRuntimeStatus(health.transport || {}, health.uart || {});
    } catch (error) {
      this.log(`Health refresh failed: ${error.message}`);
      setPill(dom.backendTransportBadge, "transport: unavailable", "bad");
      setPill(dom.gatewayBadge, "gateway: unavailable", "bad");
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
        this.log(`Apply transport failed: ${error.message}`);
      }
    });

    dom.reloadTransportBtn.addEventListener("click", async () => {
      try {
        await this.loadTransport();
        await this.refreshHealth();
      } catch (error) {
        this.log(`Reload transport failed: ${error.message}`);
      }
    });

    dom.connectBtn.addEventListener("click", async () => {
      try {
        await this.client.connect(dom.wsUrl.value.trim());
      } catch (error) {
        this.log(`Connect failed: ${error.message}`);
      }
    });

    dom.disconnectBtn.addEventListener("click", async () => {
      await this.client.disconnect();
    });

    dom.interruptBtn.addEventListener("click", () => {
      this.client.sendControl("interrupt");
      this.log("Interrupt sent.");
    });
  }

  async init() {
    this.bindEvents();
    this.updateVisibility();

    try {
      await this.loadTransport();
      await this.refreshHealth();
    } catch (error) {
      this.log(`Initial dashboard load failed: ${error.message}`);
    }

    this.startHealthPolling();
  }
}

const client = new VoiceClient();
const dashboard = new DashboardController(client);

dashboard.init();
