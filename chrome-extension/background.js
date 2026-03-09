// ─────────────────────────────────────────────────────────────
// Accessibility Autopilot — Background Service Worker
// Updated for Outlook 365 (higher quality capture + smarter actions)
// ─────────────────────────────────────────────────────────────

let ws = null;
let captureTimer = null;
let isRunning = false;
let activeTabId = null;
let debuggerAttached = false;
let config = {
  backendUrl: "ws://localhost:8080/ws",
  captureInterval: 1500,
  imageQuality: 90,    // Higher quality for Outlook's dense UI
  confirmActions: true,
  enableTTS: false,     // Text-to-speech off by default
};

// ─────────────────────────────────────────────────────────────
// Logging — sends messages to popup.html for display
// ─────────────────────────────────────────────────────────────
function log(message, level = "info") {
  console.log(`[Autopilot ${level.toUpperCase()}] ${message}`);
  chrome.runtime.sendMessage({ type: "log", message, level }).catch(() => {});
}

function setStatus(state) {
  chrome.runtime.sendMessage({ type: "status", state }).catch(() => {});
}

// ─────────────────────────────────────────────────────────────
// WebSocket Connection to Cloud Run Backend
// ─────────────────────────────────────────────────────────────
function connectWebSocket() {
  return new Promise((resolve, reject) => {
    try {
      ws = new WebSocket(config.backendUrl);

      ws.onopen = () => {
        log("Connected to backend", "action");
        setStatus("active");
        resolve(true);
      };

      ws.onclose = (event) => {
        log(`Disconnected from backend (code: ${event.code})`, "error");
        setStatus("inactive");
        if (isRunning) {
          log("Attempting to reconnect in 3 seconds...", "info");
          setTimeout(() => {
            if (isRunning) connectWebSocket();
          }, 3000);
        }
      };

      ws.onerror = (error) => {
        log("WebSocket error — check backend URL", "error");
        reject(error);
      };

      ws.onmessage = (event) => {
        handleBackendMessage(event.data);
      };
    } catch (err) {
      log(`Connection failed: ${err.message}`, "error");
      reject(err);
    }
  });
}

// ─────────────────────────────────────────────────────────────
// Handle Actions from Backend (Gemini responses)
// ─────────────────────────────────────────────────────────────
async function handleBackendMessage(rawData) {
  let msg;
  try {
    msg = JSON.parse(rawData);
  } catch (e) {
    log("Invalid message from backend", "error");
    return;
  }

  if (msg.action === "keepalive") return;

  // Log the confirmation message
  if (msg.confirmation) {
    log(`Agent: ${msg.confirmation}`, "action");
  }

  switch (msg.action) {
    case "click":
      await executeClick(msg.x, msg.y, msg.confirmation, msg.target_text);
      break;

    case "type":
      await executeType(msg.text, msg.confirmation, msg.target_field);
      break;

    case "scroll":
      await executeScroll(msg.direction, msg.confirmation);
      break;

    case "key_press":
      await executeKeyPress(msg.key, msg.confirmation);
      break;

    case "confirm":
      // Show confirmation dialog to user before executing
      await showConfirmation(msg.confirmation);
      break;

    case "clarify":
      // Agent is asking user for clarification — just speak it
      await speakText(msg.confirmation);
      break;

    case "describe":
      // Agent is describing the screen
      await speakText(msg.description || msg.confirmation);
      break;

    case "speak":
      await speakText(msg.confirmation);
      break;

    case "speak_audio":
      // Play raw audio from Gemini
      if (msg.audio) {
        await playAudioBase64(msg.audio);
      }
      break;

    case "wait":
      log("Agent is waiting for page to load...", "info");
      setStatus("processing");
      await speakText(msg.confirmation || "Just a moment, the page is loading.");
      // Trigger a new screenshot after 2 seconds
      setTimeout(() => captureAndSend(), 2000);
      break;

    case "error":
      log(`Agent error: ${msg.confirmation}`, "error");
      await speakText(msg.confirmation);
      break;

    default:
      log(`Unknown action: ${msg.action}`, "error");
  }
}

// ─────────────────────────────────────────────────────────────
// Action Executors — Click, Type, Scroll, Key Press
// ─────────────────────────────────────────────────────────────

async function executeClick(x, y, confirmation, targetText) {
  if (!debuggerAttached || !activeTabId) {
    log("Cannot click — debugger not attached", "error");
    return;
  }

  setStatus("processing");

  // Scale coordinates from image-space to viewport-space (CSS pixels)
  const scaleFactor = config._scaleFactor || 1;
  const viewportX = Math.round(x / scaleFactor);
  const viewportY = Math.round(y / scaleFactor);

  let clicked = false;

  // STRATEGY 1: Try to find element by text content (most reliable for Outlook)
  if (targetText) {
    try {
      const result = await chrome.debugger.sendCommand(
        { tabId: activeTabId },
        "Runtime.evaluate",
        {
          expression: `
            (function() {
              const targetText = ${JSON.stringify(targetText)};

              // Helper: find the best clickable element matching the text
              function findByText(text) {
                // Try multiple strategies to find the element

                // Strategy A: aria-label match (buttons, icons)
                let el = document.querySelector('[aria-label="' + text + '"]');
                if (el) return { el, method: 'aria-label' };

                // Strategy B: title attribute match
                el = document.querySelector('[title="' + text + '"]');
                if (el) return { el, method: 'title' };

                // Strategy C: button/link with exact text
                const allClickable = document.querySelectorAll('button, a, [role="treeitem"], [role="button"], [role="menuitem"], [role="tab"], [role="option"], [role="link"]');
                for (const node of allClickable) {
                  if (node.textContent.trim() === text || node.innerText.trim() === text) {
                    return { el: node, method: 'exact-text' };
                  }
                }

                // Strategy D: any element containing the text (partial match)
                const walker = document.createTreeWalker(
                  document.body,
                  NodeFilter.SHOW_ELEMENT,
                  null
                );
                let bestMatch = null;
                let bestLen = Infinity;
                while (walker.nextNode()) {
                  const node = walker.currentNode;
                  const nodeText = node.textContent.trim();
                  // Match elements whose direct text content matches
                  if (nodeText === text || node.innerText?.trim() === text) {
                    // Prefer smaller (more specific) elements
                    if (nodeText.length < bestLen) {
                      bestMatch = node;
                      bestLen = nodeText.length;
                    }
                  }
                }
                if (bestMatch) return { el: bestMatch, method: 'tree-walk' };

                // Strategy E: partial/contains match for longer text
                for (const node of allClickable) {
                  if (node.textContent.includes(text) || text.includes(node.textContent.trim())) {
                    return { el: node, method: 'partial' };
                  }
                }

                return null;
              }

              const match = findByText(targetText);
              if (match) {
                // Scroll into view if needed
                match.el.scrollIntoViewIfNeeded?.();

                // Get element center for visual indicator
                const rect = match.el.getBoundingClientRect();
                const cx = Math.round(rect.left + rect.width / 2);
                const cy = Math.round(rect.top + rect.height / 2);

                // Click it
                match.el.click();

                return JSON.stringify({
                  found: true,
                  method: match.method,
                  tag: match.el.tagName,
                  cx: cx,
                  cy: cy,
                  text: match.el.textContent.trim().slice(0, 40)
                });
              }
              return JSON.stringify({ found: false });
            })();
          `,
          returnByValue: true,
        }
      );

      if (result && result.result && result.result.value) {
        const clickResult = JSON.parse(result.result.value);
        if (clickResult.found) {
          log(`Text-click "${targetText}" → ${clickResult.tag} via ${clickResult.method} at (${clickResult.cx}, ${clickResult.cy})`, "action");
          await showClickIndicator(clickResult.cx, clickResult.cy);
          clicked = true;
        }
      }
    } catch (e) {
      log(`Text-based click failed: ${e.message}`, "error");
    }
  }

  // STRATEGY 2: Fall back to coordinate-based clicking
  if (!clicked) {
    log(`Coordinate click at (${x}, ${y}) → viewport (${viewportX}, ${viewportY}) [scale=${scaleFactor}]`, "action");

    try {
      await showClickIndicator(viewportX, viewportY);
      await sleep(300);

      // Move mouse to target first (required by React)
      await chrome.debugger.sendCommand(
        { tabId: activeTabId },
        "Input.dispatchMouseEvent",
        { type: "mouseMoved", x: viewportX, y: viewportY }
      );
      await sleep(50);

      // Mouse down
      await chrome.debugger.sendCommand(
        { tabId: activeTabId },
        "Input.dispatchMouseEvent",
        { type: "mousePressed", x: viewportX, y: viewportY, button: "left", clickCount: 1 }
      );
      await sleep(30);

      // Mouse up
      await chrome.debugger.sendCommand(
        { tabId: activeTabId },
        "Input.dispatchMouseEvent",
        { type: "mouseReleased", x: viewportX, y: viewportY, button: "left", clickCount: 1 }
      );

      // JS click fallback on element at coordinates
      try {
        await chrome.debugger.sendCommand(
          { tabId: activeTabId },
          "Runtime.evaluate",
          {
            expression: `
              (function() {
                const el = document.elementFromPoint(${viewportX}, ${viewportY});
                if (el) { el.click(); return 'clicked: ' + el.tagName; }
                return 'no element';
              })();
            `,
          }
        );
      } catch (e) { /* non-critical */ }

      log(`Click executed at viewport (${viewportX}, ${viewportY})`, "action");
    } catch (err) {
      log(`Click failed: ${err.message}`, "error");
    }
  }

  // Wait for UI to update, then capture verification screenshot
  await sleep(800);
  await captureAndSend();
  setStatus("active");
}

async function executeType(text, confirmation, targetField) {
  if (!debuggerAttached || !activeTabId) {
    log("Cannot type — debugger not attached", "error");
    return;
  }

  if (!text) {
    log("Type action received with no text — skipping", "error");
    return;
  }

  setStatus("processing");
  log(`Typing: "${text.substring(0, 50)}${text.length > 50 ? '...' : ''}"${targetField ? ` in [${targetField}]` : ''}`, "action");

  try {
    // If a target field is specified, focus it first via DOM search
    if (targetField) {
      const focusResult = await chrome.debugger.sendCommand(
        { tabId: activeTabId },
        "Runtime.evaluate",
        {
          expression: `
            (function() {
              const field = ${JSON.stringify(targetField)}.toLowerCase();
              let el = null;

              // Strategy 1: Find by placeholder text
              const inputs = document.querySelectorAll('input, textarea, [contenteditable="true"], [role="textbox"]');
              for (const inp of inputs) {
                const placeholder = (inp.getAttribute('placeholder') || '').toLowerCase();
                const ariaLabel = (inp.getAttribute('aria-label') || '').toLowerCase();
                const title = (inp.getAttribute('title') || '').toLowerCase();

                if (placeholder.includes(field) || ariaLabel.includes(field) || title.includes(field)) {
                  el = inp;
                  break;
                }
              }

              // Strategy 2: Find by associated label text
              if (!el) {
                const labels = document.querySelectorAll('label, [role="label"]');
                for (const label of labels) {
                  if (label.textContent.toLowerCase().includes(field)) {
                    // Find the input near/after this label
                    const nextInput = label.querySelector('input, textarea, [contenteditable="true"]')
                      || label.nextElementSibling
                      || label.parentElement.querySelector('input, textarea, [contenteditable="true"]');
                    if (nextInput) { el = nextInput; break; }
                  }
                }
              }

              // Strategy 3: For "body" field — find the main contenteditable area
              if (!el && (field === 'body' || field === 'message body' || field === 'email body')) {
                // Outlook compose body is usually a large contenteditable div
                const editables = document.querySelectorAll('[contenteditable="true"][role="textbox"], [contenteditable="true"]');
                // Pick the largest contenteditable (the body, not small inline editors)
                let maxArea = 0;
                for (const ed of editables) {
                  const rect = ed.getBoundingClientRect();
                  const area = rect.width * rect.height;
                  if (area > maxArea && rect.width > 200 && rect.height > 100) {
                    maxArea = area;
                    el = ed;
                  }
                }
              }

              // Strategy 4: For "subject" — look for input with "subject" in any attribute
              if (!el && field.includes('subject')) {
                el = document.querySelector('input[aria-label*="ubject" i], input[placeholder*="ubject" i], input[id*="ubject" i]');
              }

              // Strategy 5: For "to" field
              if (!el && (field === 'to' || field === 'to field')) {
                el = document.querySelector('input[aria-label*="To" i], [role="combobox"][aria-label*="To" i], input[placeholder*="To" i]');
              }

              if (el) {
                el.focus();
                el.click();
                // For contenteditable, place cursor at end
                if (el.getAttribute('contenteditable') === 'true') {
                  const range = document.createRange();
                  const sel = window.getSelection();
                  range.selectNodeContents(el);
                  range.collapse(false);
                  sel.removeAllRanges();
                  sel.addRange(range);
                }
                return JSON.stringify({
                  found: true,
                  tag: el.tagName,
                  type: el.getAttribute('contenteditable') ? 'contenteditable' : 'input'
                });
              }
              return JSON.stringify({ found: false });
            })();
          `,
          returnByValue: true,
        }
      );

      if (focusResult && focusResult.result && focusResult.result.value) {
        const res = JSON.parse(focusResult.result.value);
        if (res.found) {
          log(`Focused ${targetField} field (${res.tag}, ${res.type})`, "action");
          await sleep(200);  // Let Outlook register the focus
        } else {
          log(`Could not find "${targetField}" field — typing into current focus`, "error");
        }
      }
    }

    // Normalize newlines: replace literal \n sequences with actual newline chars
    const normalizedText = text.replace(/\\n/g, '\n');

    // Type each character with a small delay for Outlook to process
    for (const char of normalizedText) {
      if (char === '\n' || char === '\r') {
        // Press Enter for newlines
        await chrome.debugger.sendCommand(
          { tabId: activeTabId },
          "Input.dispatchKeyEvent",
          {
            type: "keyDown",
            key: "Enter",
            code: "Enter",
            windowsVirtualKeyCode: 13,
            nativeVirtualKeyCode: 13,
          }
        );
        await chrome.debugger.sendCommand(
          { tabId: activeTabId },
          "Input.dispatchKeyEvent",
          {
            type: "keyUp",
            key: "Enter",
            code: "Enter",
            windowsVirtualKeyCode: 13,
            nativeVirtualKeyCode: 13,
          }
        );
        await sleep(50);
        continue;
      }

      await chrome.debugger.sendCommand(
        { tabId: activeTabId },
        "Input.dispatchKeyEvent",
        {
          type: "keyDown",
          text: char,
          unmodifiedText: char,
          key: char,
        }
      );

      await chrome.debugger.sendCommand(
        { tabId: activeTabId },
        "Input.dispatchKeyEvent",
        {
          type: "keyUp",
          text: char,
          unmodifiedText: char,
          key: char,
        }
      );

      // Small delay between characters — Outlook's rich text editor
      // can drop characters if typed too fast
      await sleep(30);
    }

    log(`Typed ${text.length} characters`, "action");

    // Capture new screenshot after typing
    await sleep(500);
    await captureAndSend();
  } catch (err) {
    log(`Type failed: ${err.message}`, "error");
  }

  setStatus("active");
}

async function executeScroll(direction, confirmation) {
  if (!debuggerAttached || !activeTabId) {
    log("Cannot scroll — debugger not attached", "error");
    return;
  }

  setStatus("processing");
  const deltaY = direction === "down" ? 400 : -400;
  log(`Scrolling ${direction}`, "action");

  try {
    // Use viewport center (not hardcoded 1920x1080)
    const scaleFactor = config._scaleFactor || 1;
    const centerX = Math.round(960 / scaleFactor);
    const centerY = Math.round(540 / scaleFactor);

    await chrome.debugger.sendCommand(
      { tabId: activeTabId },
      "Input.dispatchMouseEvent",
      {
        type: "mouseWheel",
        x: centerX,
        y: centerY,
        deltaX: 0,
        deltaY: deltaY,
      }
    );

    // Wait for scroll to settle, then capture
    await sleep(600);
    await captureAndSend();
  } catch (err) {
    log(`Scroll failed: ${err.message}`, "error");
  }

  setStatus("active");
}

async function executeKeyPress(key, confirmation) {
  if (!debuggerAttached || !activeTabId) {
    log("Cannot press key — debugger not attached", "error");
    return;
  }

  setStatus("processing");
  log(`Pressing key: ${key}`, "action");

  // Map common key names to Chrome debugger key codes
  const keyMap = {
    "Enter": { key: "Enter", code: "Enter", keyCode: 13 },
    "Tab": { key: "Tab", code: "Tab", keyCode: 9 },
    "Escape": { key: "Escape", code: "Escape", keyCode: 27 },
    "Backspace": { key: "Backspace", code: "Backspace", keyCode: 8 },
    "Delete": { key: "Delete", code: "Delete", keyCode: 46 },
    "ArrowUp": { key: "ArrowUp", code: "ArrowUp", keyCode: 38 },
    "ArrowDown": { key: "ArrowDown", code: "ArrowDown", keyCode: 40 },
    "ArrowLeft": { key: "ArrowLeft", code: "ArrowLeft", keyCode: 37 },
    "ArrowRight": { key: "ArrowRight", code: "ArrowRight", keyCode: 39 },
  };

  const keyInfo = keyMap[key] || { key: key, code: key, keyCode: 0 };

  try {
    await chrome.debugger.sendCommand(
      { tabId: activeTabId },
      "Input.dispatchKeyEvent",
      {
        type: "keyDown",
        key: keyInfo.key,
        code: keyInfo.code,
        windowsVirtualKeyCode: keyInfo.keyCode,
        nativeVirtualKeyCode: keyInfo.keyCode,
      }
    );

    await chrome.debugger.sendCommand(
      { tabId: activeTabId },
      "Input.dispatchKeyEvent",
      {
        type: "keyUp",
        key: keyInfo.key,
        code: keyInfo.code,
        windowsVirtualKeyCode: keyInfo.keyCode,
        nativeVirtualKeyCode: keyInfo.keyCode,
      }
    );

    await sleep(500);
    await captureAndSend();
  } catch (err) {
    log(`Key press failed: ${err.message}`, "error");
  }

  setStatus("active");
}

// ─────────────────────────────────────────────────────────────
// Visual Click Indicator — Shows where agent will click
// ─────────────────────────────────────────────────────────────
async function showClickIndicator(x, y) {
  try {
    await chrome.debugger.sendCommand(
      { tabId: activeTabId },
      "Runtime.evaluate",
      {
        expression: `
          (function() {
            // Remove any existing indicator
            const old = document.getElementById('autopilot-click-indicator');
            if (old) old.remove();

            const indicator = document.createElement('div');
            indicator.id = 'autopilot-click-indicator';
            indicator.style.cssText = \`
              position: fixed;
              left: ${x - 20}px;
              top: ${y - 20}px;
              width: 40px;
              height: 40px;
              border: 3px solid #2563eb;
              border-radius: 50%;
              background: rgba(37, 99, 235, 0.15);
              pointer-events: none;
              z-index: 999999;
              animation: autopilotPulse 0.6s ease-out;
            \`;

            // Add animation keyframes
            if (!document.getElementById('autopilot-styles')) {
              const style = document.createElement('style');
              style.id = 'autopilot-styles';
              style.textContent = \`
                @keyframes autopilotPulse {
                  0% { transform: scale(0.5); opacity: 1; }
                  100% { transform: scale(1.5); opacity: 0; }
                }
              \`;
              document.head.appendChild(style);
            }

            document.body.appendChild(indicator);

            // Remove after animation
            setTimeout(() => indicator.remove(), 800);
          })();
        `,
      }
    );
  } catch (err) {
    // Non-critical — just skip the indicator
  }
}

// ─────────────────────────────────────────────────────────────
// Confirmation Dialog — For destructive actions
// ─────────────────────────────────────────────────────────────
async function showConfirmation(message) {
  await speakText(message);

  // Also inject a visual confirmation banner into the page
  try {
    await chrome.debugger.sendCommand(
      { tabId: activeTabId },
      "Runtime.evaluate",
      {
        expression: `
          (function() {
            const old = document.getElementById('autopilot-confirm');
            if (old) old.remove();

            const banner = document.createElement('div');
            banner.id = 'autopilot-confirm';
            banner.style.cssText = \`
              position: fixed;
              bottom: 20px;
              left: 50%;
              transform: translateX(-50%);
              background: #1e293b;
              color: white;
              padding: 16px 24px;
              border-radius: 12px;
              font-family: -apple-system, sans-serif;
              font-size: 14px;
              z-index: 999999;
              box-shadow: 0 8px 32px rgba(0,0,0,0.3);
              display: flex;
              align-items: center;
              gap: 12px;
              max-width: 500px;
            \`;
            banner.innerHTML = \`
              <span style="font-size: 20px;">⚠️</span>
              <span>${message.replace(/'/g, "\\'")}</span>
              <span style="color: #94a3b8; font-size: 12px; margin-left: 8px;">Say "yes" or "no"</span>
            \`;
            document.body.appendChild(banner);

            // Auto-remove after 15 seconds
            setTimeout(() => banner.remove(), 15000);
          })();
        `,
      }
    );
  } catch (err) {
    // Non-critical
  }
}

// ─────────────────────────────────────────────────────────────
// Text-to-Speech — Speak confirmations to the user
// ─────────────────────────────────────────────────────────────
async function speakText(text) {
  if (!text) return;
  if (!config.enableTTS) {
    log(`Agent says: ${text}`, "info");
    return;
  }

  try {
    await chrome.tts.speak(text, {
      rate: 1.0,
      pitch: 1.0,
      volume: 1.0,
      lang: "en-US",
    });
  } catch (err) {
    log(`TTS failed: ${err.message}`, "error");
  }
}

async function playAudioBase64(audioBase64) {
  try {
    // Inject audio playback into the active tab
    await chrome.debugger.sendCommand(
      { tabId: activeTabId },
      "Runtime.evaluate",
      {
        expression: `
          (function() {
            const audio = new Audio("data:audio/mp3;base64,${audioBase64}");
            audio.play().catch(e => console.log("Audio play failed:", e));
          })();
        `,
      }
    );
  } catch (err) {
    log(`Audio playback failed: ${err.message}`, "error");
  }
}

// ─────────────────────────────────────────────────────────────
// Screen Capture — High quality for Outlook's dense UI
// ─────────────────────────────────────────────────────────────
async function captureAndSend() {
  if (!isRunning || !ws || ws.readyState !== WebSocket.OPEN) return;

  try {
    const screenshot = await chrome.tabs.captureVisibleTab(null, {
      format: "jpeg",
      quality: config.imageQuality, // 90% for Outlook
    });

    // Remove the data URL prefix — send just base64
    const base64Data = screenshot.replace(/^data:image\/\w+;base64,/, "");

    // Detect actual image dimensions (may differ from viewport on high-DPI)
    // Note: Service workers have no DOM, so use createImageBitmap instead of new Image()
    let imgDims = { width: 1920, height: 1080 };
    try {
      const response = await fetch(screenshot);
      const blob = await response.blob();
      const bitmap = await createImageBitmap(blob);
      imgDims = { width: bitmap.width, height: bitmap.height };
      bitmap.close();
    } catch (e) {
      // Fallback to default dimensions
    }

    // Get the viewport size for coordinate scaling
    const tab = await chrome.tabs.get(activeTabId);
    let viewportWidth = imgDims.width;
    let viewportHeight = imgDims.height;
    try {
      const result = await chrome.debugger.sendCommand(
        { tabId: activeTabId },
        "Runtime.evaluate",
        { expression: "JSON.stringify({w: window.innerWidth, h: window.innerHeight})" }
      );
      if (result && result.result && result.result.value) {
        const vp = JSON.parse(result.result.value);
        viewportWidth = vp.w;
        viewportHeight = vp.h;
      }
    } catch (e) {
      // Fallback: use image dimensions
    }

    // Store the scale factor for coordinate conversion
    config._scaleFactor = imgDims.width / viewportWidth;

    ws.send(JSON.stringify({
      type: "screenshot",
      data: base64Data,
      timestamp: Date.now(),
      resolution: `${imgDims.width}x${imgDims.height}`,
      viewportSize: `${viewportWidth}x${viewportHeight}`,
      devicePixelRatio: config._scaleFactor,
    }));
  } catch (err) {
    log(`Screenshot capture failed: ${err.message}`, "error");
  }
}

// ─────────────────────────────────────────────────────────────
// Microphone Capture via Offscreen Document
// ─────────────────────────────────────────────────────────────
// Note: Chrome Manifest V3 service workers can't directly access
// navigator.mediaDevices. We use chrome.tabCapture.getMediaStreamId
// or an offscreen document approach. For hackathon simplicity,
// audio is captured from the popup and forwarded here.

// Listen for text commands from popup.html
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "sendText" && ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: "command",
      text: msg.text,
      timestamp: Date.now(),
    }));
    log(`Command sent: ${msg.text}`, "info");
  }

  // Listen for user confirmation responses (yes/no)
  if (msg.action === "sendConfirmation" && ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: "user_confirmation",
      response: msg.response,
      timestamp: Date.now(),
    }));
    log(`Confirmation sent: ${msg.response}`, "info");
  }
});

// // Audio input commented out for now — using text commands instead
// chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
//   if (msg.type === "audio_data" && ws && ws.readyState === WebSocket.OPEN) {
//     ws.send(JSON.stringify({
//       type: "audio",
//       data: msg.data,
//       timestamp: Date.now(),
//     }));
//   }
// });

// ─────────────────────────────────────────────────────────────
// Debugger Management — For simulating clicks/typing
// ─────────────────────────────────────────────────────────────
async function attachDebugger(tabId) {
  try {
    await chrome.debugger.attach({ tabId: tabId }, "1.3");
    debuggerAttached = true;
    activeTabId = tabId;
    log("Debugger attached to tab", "info");
  } catch (err) {
    if (err.message.includes("Already attached")) {
      debuggerAttached = true;
      activeTabId = tabId;
      log("Debugger already attached", "info");
    } else {
      log(`Debugger attach failed: ${err.message}`, "error");
      throw err;
    }
  }
}

async function detachDebugger() {
  if (debuggerAttached && activeTabId) {
    try {
      await chrome.debugger.detach({ tabId: activeTabId });
      log("Debugger detached", "info");
    } catch (err) {
      // Ignore detach errors
    }
    debuggerAttached = false;
  }
}

// Auto-detach if user closes debugger banner
chrome.debugger.onDetach.addListener((source, reason) => {
  debuggerAttached = false;
  log(`Debugger detached: ${reason}`, "info");
  if (isRunning) {
    log("Debugger was detached — stopping agent", "error");
    stopAgent();
  }
});

// ─────────────────────────────────────────────────────────────
// Start / Stop Agent
// ─────────────────────────────────────────────────────────────
async function startAgent(userConfig) {
  if (isRunning) return { success: false, error: "Already running" };

  config = { ...config, ...userConfig };
  log(`Starting with config: interval=${config.captureInterval}ms, quality=${config.imageQuality}%`);

  try {
    // Find a suitable tab — prefer Outlook, skip chrome:// and extension pages
    let tab = null;

    // First, try to find an Outlook tab
    const outlookTabs = await chrome.tabs.query({ currentWindow: true });
    tab = outlookTabs.find(t =>
      t.url && (
        t.url.includes("outlook.office.com") ||
        t.url.includes("outlook.office365.com") ||
        t.url.includes("outlook.live.com")
      )
    );

    // If no Outlook tab, use the active tab but skip chrome:// and extension pages
    if (!tab) {
      const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (activeTab && activeTab.url && !activeTab.url.startsWith("chrome://") && !activeTab.url.startsWith("chrome-extension://")) {
        tab = activeTab;
      }
    }

    // Last resort: find any non-chrome tab
    if (!tab) {
      tab = outlookTabs.find(t =>
        t.url && !t.url.startsWith("chrome://") && !t.url.startsWith("chrome-extension://")
      );
    }

    if (!tab) throw new Error("No suitable tab found. Please open Outlook 365 in a tab first.");

    activeTabId = tab.id;
    // Focus the target tab so the user can see what's happening
    await chrome.tabs.update(tab.id, { active: true });
    log(`Active tab: ${tab.title} (${tab.url})`);

    // Attach debugger for click/type simulation
    await attachDebugger(tab.id);

    // Connect to backend
    await connectWebSocket();

    // Start screenshot capture loop
    isRunning = true;
    captureTimer = setInterval(() => captureAndSend(), config.captureInterval);
    log("Screenshot capture started");

    // Capture initial screenshot immediately
    await captureAndSend();

    return { success: true };
  } catch (err) {
    log(`Start failed: ${err.message}`, "error");
    await stopAgent();
    return { success: false, error: err.message };
  }
}

async function stopAgent() {
  isRunning = false;

  if (captureTimer) {
    clearInterval(captureTimer);
    captureTimer = null;
  }

  if (ws) {
    ws.close();
    ws = null;
  }

  await detachDebugger();

  setStatus("inactive");
  log("Agent stopped");
}

// ─────────────────────────────────────────────────────────────
// Listen for Start/Stop from Popup
// ─────────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "start") {
    startAgent(msg.config).then(sendResponse);
    return true; // Keep channel open for async response
  }

  if (msg.action === "stop") {
    stopAgent().then(() => sendResponse({ success: true }));
    return true;
  }

  if (msg.action === "status" || msg.action === "getStatus") {
    sendResponse({ isRunning, running: isRunning, debuggerAttached });
    return true;
  }

  if (msg.action === "updateConfig") {
    config = { ...config, ...msg.config };
    log(`Config updated: TTS=${config.enableTTS}`, "info");
    sendResponse({ success: true });
    return true;
  }
});

// ─────────────────────────────────────────────────────────────
// Track active tab changes
// ─────────────────────────────────────────────────────────────
chrome.tabs.onActivated.addListener(async (activeInfo) => {
  if (!isRunning) return;

  // Re-attach debugger to new tab
  await detachDebugger();
  try {
    await attachDebugger(activeInfo.tabId);
    log("Switched to new tab — debugger re-attached", "info");
    await captureAndSend();
  } catch (err) {
    log(`Tab switch — debugger attach failed: ${err.message}`, "error");
  }
});

// ─────────────────────────────────────────────────────────────
// Utility
// ─────────────────────────────────────────────────────────────
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}