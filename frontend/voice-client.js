const wsUrlInput = document.getElementById("wsUrl");
const connectBtn = document.getElementById("connectBtn");
const disconnectBtn = document.getElementById("disconnectBtn");
const interruptBtn = document.getElementById("interruptBtn");
const connectionStatus = document.getElementById("connectionStatus");
const audioStatus = document.getElementById("audioStatus");
const logs = document.getElementById("logs");

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
    logs.textContent += `[${timestamp}] ${message}\n`;
    logs.scrollTop = logs.scrollHeight;
  }

  setConnection(status) {
    connectionStatus.textContent = status;
  }

  setAudio(status) {
    audioStatus.textContent = status;
  }

  async connect(url) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.log("Socket already connected.");
      return;
    }

    this.audioContext = this.audioContext || new AudioContext();
    await this.audioContext.resume();

    return new Promise((resolve, reject) => {
      this.socket = new WebSocket(url);
      this.socket.binaryType = "arraybuffer";

      this.socket.onopen = async () => {
        this.setConnection("connected");
        this.log("WebSocket connected.");

        try {
          await this.startMicrophone();
          this.sendControl("speech_start");
          resolve();
        } catch (error) {
          this.log(`Microphone start failed: ${error.message}`);
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
        this.setConnection("disconnected");
        this.setAudio("idle");
        this.log("WebSocket disconnected.");
      };

      this.socket.onerror = (error) => {
        this.log(`WebSocket error: ${error?.message || "unknown"}`);
        reject(new Error("WebSocket error"));
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
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }
    this.socket.send(JSON.stringify({ action }));
  }

  handleControlFrame(rawText) {
    try {
      const message = JSON.parse(rawText);
      if (message.event === "ready") {
        this.log(`Gateway ready. sample_rate=${message.sample_rate}`);
        return;
      }
      if (message.event === "pong") {
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
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
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

const client = new VoiceClient();

connectBtn.addEventListener("click", async () => {
  try {
    await client.connect(wsUrlInput.value.trim());
  } catch (error) {
    client.log(`Connect failed: ${error.message}`);
  }
});

disconnectBtn.addEventListener("click", async () => {
  await client.disconnect();
});

interruptBtn.addEventListener("click", () => {
  client.sendControl("interrupt");
  client.log("Interrupt sent.");
});
