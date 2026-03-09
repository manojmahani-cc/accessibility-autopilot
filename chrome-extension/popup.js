let isRunning = false;
let recognition = null;
let isListening = false;

// ─────────────────────────────────────────────────────
// Logging
// ─────────────────────────────────────────────────────
function addLog(message, type = '') {
  const logBox = document.getElementById('logBox');
  const entry = document.createElement('div');
  entry.className = `log-entry ${type}`;
  const time = new Date().toLocaleTimeString('en-US', {
    hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
  entry.textContent = `[${time}] ${message}`;
  logBox.appendChild(entry);
  logBox.scrollTop = logBox.scrollHeight;

  // Keep log manageable
  while (logBox.children.length > 50) {
    logBox.removeChild(logBox.firstChild);
  }
}

function setStatus(state) {
  const dot = document.getElementById('statusDot');
  const text = document.getElementById('statusText');
  dot.className = `status-indicator ${state}`;
  const labels = {
    inactive: 'Inactive',
    active: 'Ready',
    processing: 'Processing...'
  };
  text.textContent = labels[state] || state;
}

// ─────────────────────────────────────────────────────
// Send text command to backend via background.js
// ─────────────────────────────────────────────────────
function sendCommand() {
  const input = document.getElementById('commandInput');
  const command = input.value.trim();
  if (!command) return;

  addLog('You: ' + command, 'info');
  chrome.runtime.sendMessage({ action: 'sendText', text: command });
  input.value = '';
  input.focus();
}

// ─────────────────────────────────────────────────────
// Speech Recognition (Speech-to-Text)
// ─────────────────────────────────────────────────────
function setupSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    addLog('Speech recognition not supported in this browser', 'error');
    return false;
  }

  recognition = new SpeechRecognition();
  recognition.continuous = true;      // Keep listening until user clicks stop
  recognition.interimResults = true;  // Show partial results while speaking
  recognition.lang = 'en-US';

  recognition.onresult = (event) => {
    // Build full transcript from all result entries (continuous mode produces multiple)
    let fullTranscript = '';
    for (let i = 0; i < event.results.length; i++) {
      fullTranscript += event.results[i][0].transcript;
    }
    // Live preview only — processing happens when user clicks 🎤 to stop
    document.getElementById('commandInput').value = fullTranscript;
  };

  recognition.onend = () => {
    // Chrome auto-stops continuous recognition after ~60s
    // If we're still supposed to be listening, restart seamlessly
    if (isListening) {
      try { recognition.start(); } catch(e) { stopListening(); }
      return;
    }
  };

  recognition.onerror = (event) => {
    if (event.error === 'no-speech') {
      addLog('No speech detected — try again', 'error');
    } else if (event.error === 'not-allowed') {
      addLog('Microphone access denied — check browser permissions', 'error');
    } else {
      addLog('Speech error: ' + event.error, 'error');
    }
    stopListening();
  };

  return true;
}

function toggleMic() {
  if (isListening) {
    recognition.stop();
    // Finalize: process the accumulated transcript
    const text = document.getElementById('commandInput').value.trim();
    if (text) {
      const reviewBeforeSend = document.getElementById('confirmActions').checked;
      if (reviewBeforeSend) {
        addLog('Voice (review): ' + text, 'info');
        document.getElementById('commandInput').focus();
      } else {
        addLog('Voice: ' + text, 'info');
        sendCommand();
      }
    }
    stopListening();
  } else {
    startListening();
  }
}

async function startListening() {
  // Request microphone permission first — Chrome extensions need explicit access
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    // Got permission — stop the stream immediately (SpeechRecognition manages its own)
    stream.getTracks().forEach(track => track.stop());
  } catch (err) {
    addLog('Microphone access denied — please allow mic in browser settings', 'error');
    return;
  }

  if (!recognition) {
    if (!setupSpeechRecognition()) return;
  }

  try {
    recognition.start();
    isListening = true;
    const micBtn = document.getElementById('micBtn');
    micBtn.classList.remove('ready');
    micBtn.classList.add('listening');
    micBtn.title = 'Listening... (click to stop)';
    document.getElementById('commandInput').placeholder = 'Listening... speak now';
  } catch (err) {
    addLog('Could not start mic: ' + err.message, 'error');
  }
}

function stopListening() {
  isListening = false;
  const micBtn = document.getElementById('micBtn');
  micBtn.classList.remove('listening');
  const audioEnabled = document.getElementById('enableAudio').checked;
  if (audioEnabled && isRunning) {
    micBtn.classList.add('ready');
    micBtn.title = 'Click to speak a command';
  }
  document.getElementById('commandInput').placeholder = 'Type a command... (Ctrl+Enter to send)';
}

// ─────────────────────────────────────────────────────
// Audio Toggle — Controls mic button + TTS
// ─────────────────────────────────────────────────────
function updateAudioState() {
  const audioEnabled = document.getElementById('enableAudio').checked;
  const micBtn = document.getElementById('micBtn');

  if (audioEnabled && isRunning) {
    micBtn.disabled = false;
    micBtn.classList.add('ready');
    micBtn.title = 'Click to speak a command';
  } else {
    micBtn.disabled = true;
    micBtn.classList.remove('ready', 'listening');
    micBtn.title = 'Voice input (enable Audio in Settings)';
    if (isListening && recognition) {
      recognition.stop();
      stopListening();
    }
  }

  // Update TTS in background script
  chrome.runtime.sendMessage({
    action: 'updateConfig',
    config: { enableTTS: audioEnabled }
  });
}

// ─────────────────────────────────────────────────────
// Start / Stop Agent
// ─────────────────────────────────────────────────────
async function startAgent() {
  const url = document.getElementById('backendUrl').value.trim();
  if (!url) {
    addLog('Please enter a backend URL', 'error');
    return;
  }

  addLog('Starting Autopilot...', 'info');
  document.getElementById('startBtn').disabled = true;

  const audioEnabled = document.getElementById('enableAudio').checked;

  // Tell background script to start
  chrome.runtime.sendMessage({
    action: 'start',
    config: {
      backendUrl: url,
      captureInterval: parseInt(document.getElementById('captureInterval').value),
      imageQuality: parseInt(document.getElementById('imageQuality').value),
      confirmActions: document.getElementById('confirmActions').checked,
      enableTTS: audioEnabled
    }
  }, (response) => {
    if (response && response.success) {
      isRunning = true;
      document.getElementById('stopBtn').disabled = false;
      document.getElementById('commandInput').disabled = false;
      document.getElementById('sendBtn').disabled = false;
      setStatus('active');
      addLog('Autopilot is active! Type or speak your commands.', 'action');
      document.getElementById('commandInput').focus();
      updateAudioState();  // Enable mic button if audio is on
    } else {
      addLog('Failed to start: ' + (response?.error || 'Unknown error'), 'error');
      document.getElementById('startBtn').disabled = false;
    }
  });
}

function stopAgent() {
  isRunning = false;
  document.getElementById('startBtn').disabled = false;
  document.getElementById('stopBtn').disabled = true;
  document.getElementById('commandInput').disabled = true;
  document.getElementById('sendBtn').disabled = true;
  setStatus('inactive');

  // Stop mic if listening
  if (isListening && recognition) {
    recognition.stop();
  }
  updateAudioState();

  chrome.runtime.sendMessage({ action: 'stop' });
  addLog('Autopilot stopped', 'info');
}

// ─────────────────────────────────────────────────────
// Listen for messages from background script
// ─────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'log') {
    addLog(msg.message, msg.level || '');
  }
  if (msg.type === 'status') {
    setStatus(msg.state);
  }
});

// ─────────────────────────────────────────────────────
// Wire up event listeners once DOM is ready
// ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('startBtn').addEventListener('click', startAgent);
  document.getElementById('stopBtn').addEventListener('click', stopAgent);
  document.getElementById('sendBtn').addEventListener('click', sendCommand);
  document.getElementById('micBtn').addEventListener('click', toggleMic);

  document.getElementById('commandInput').addEventListener('keydown', (e) => {
    // Ctrl+Enter sends the command; plain Enter creates a new line
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      sendCommand();
    }
  });

  // Audio checkbox toggles mic + TTS
  document.getElementById('enableAudio').addEventListener('change', updateAudioState);

  // Check if agent is already running when popup opens
  chrome.runtime.sendMessage({ action: 'status' }, (response) => {
    if (chrome.runtime.lastError) return;
    if (response && response.isRunning) {
      isRunning = true;
      document.getElementById('startBtn').disabled = true;
      document.getElementById('stopBtn').disabled = false;
      document.getElementById('commandInput').disabled = false;
      document.getElementById('sendBtn').disabled = false;
      setStatus('active');
      addLog('Agent is already running', 'info');
      updateAudioState();
    }
  });
});
