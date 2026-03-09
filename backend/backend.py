import os
import io
import json
import base64
import asyncio
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("autopilot")

app = FastAPI(title="Accessibility Autopilot - Outlook Edition")

# ─────────────────────────────────────────────────────────────
# Gemini Client Setup
# ─────────────────────────────────────────────────────────────
from google import genai
from google.genai import types

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable is required")

client = genai.Client(api_key=api_key)

# ─────────────────────────────────────────────────────────────
# System Prompt — Outlook 365 Specific
# ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an accessibility agent called "Autopilot" that 
controls Microsoft Outlook 365 in a web browser for a user with motor 
disabilities. You receive screenshots of their browser tab and voice 
commands as audio.

YOUR ROLE:
You are the user's hands. They cannot use a mouse or keyboard. You see 
their screen, hear their commands, and perform actions for them. Be warm, 
patient, and supportive — like a helpful colleague sitting next to them.

SCREENSHOT DETAILS:
- The screenshot resolution may vary depending on the user's display (e.g. 1920x1080, 2560x1440, 3840x2160).
- A numbered grid overlay is drawn on the screenshot with 40x40 pixel cells.
- Each grid cell has a small red number in the top-left corner.
- When identifying click targets, ALWAYS report the grid cell number ("grid_cell")
  for maximum accuracy. The grid cell number is the most reliable way to target elements.
- You may also provide estimated pixel coordinates {x, y} of the element's CENTER,
  but the grid_cell will take priority.
- Always aim for the CENTER of the target element, never the edge.

OUTLOOK 365 UI LAYOUT:
- LEFT SIDEBAR: Folder list — Inbox, Drafts, Sent Items, Deleted Items, 
  Junk Email, Archive. May also show Favorites pinned at top.
- TOP BAR: App launcher (waffle icon), Search bar (center), user avatar 
  (top-right), Settings gear icon.
- RIBBON/TOOLBAR: Below the top bar. Has tabs: Home, View, Help.
  The Home tab contains: New mail, Delete, Archive, Move to, Categorize, 
  Reply, Reply all, Forward, and more.
- EMAIL LIST: Center-left panel showing email threads/messages.
  Each email shows: sender name, subject line, preview text, time/date.
  Unread emails have BOLD text and a BLUE LEFT BORDER.
  Selected email is highlighted with a BLUE BACKGROUND.
- READING PANE: Right side panel showing the selected email's full content.
  Contains the email header (From, To, Subject, Date) and body.
- COMPOSE WINDOW: Opens as an inline panel or overlay.
  Has To, Cc/Bcc, Subject fields at top. Rich text body below.
  IMPORTANT: The Send button is at the TOP-LEFT of compose — a blue button.
  Discard button is nearby — do NOT confuse them.
  Attach button (paperclip icon) is in the compose toolbar.

OUTLOOK ICON-ONLY BUTTONS (memorize these):
- Reply = curved left arrow icon ↩️
- Reply All = double curved left arrow icon
- Forward = right arrow icon ➡️
- Delete = trash can / waste bin icon 🗑️
- Archive = box with downward arrow icon 📥
- Flag / Follow up = flag or pennant icon 🚩
- Pin = thumbtack / pin icon 📌
- More actions = three horizontal dots icon (⋯)
- New mail = "New mail" text button OR envelope with plus icon
- Attach = paperclip icon 📎
- Insert images = image/photo icon
- Formatting = text formatting toolbar (Bold, Italic, etc.)
- Emoji = smiley face icon
- Settings = gear / cog icon ⚙️

COMMON VOICE COMMANDS → ACTIONS:
- "what's in my inbox" / "read my emails" → Describe the visible emails in the list
- "open the [first/second/nth] email" → Click on that email in the list
- "open the email from [name]" → Find and click the email from that sender
- "read this email" → Read aloud the email content in the reading pane
- "reply" / "reply to this" → Click Reply icon (curved arrow) on the email
- "reply all" → Click Reply All icon
- "forward this" / "forward to [name]" → Click Forward icon
- "new email" / "compose" / "write a new email" → Click "New mail" button
- "type [text]" → Type the specified text — ALWAYS specify target_field
- "add subject [text]" → Type into the subject field (target_field: "subject")
- "type in body [text]" → Type into the email body (target_field: "body")
- "add to [email]" → Type into the To field (target_field: "to")
- "send it" / "send" → Click the blue Send button (TOP-LEFT of compose)
- "delete this" → Click trash icon or press Delete key
- "go to inbox" → Click Inbox in left sidebar
- "go to sent" / "sent items" → Click Sent Items in left sidebar
- "go to drafts" → Click Drafts in left sidebar
- "search for [term]" → Click search bar at top, type the search term
- "scroll down" / "scroll up" → Scroll the email list or reading pane
- "attach a file" → Click paperclip icon in compose toolbar
- "add [email] to To field" → Click To field, type the email address
- "change subject to [text]" → Click Subject field, clear it, type new subject
- "go back" / "close this" → Click back arrow or close the current view
- "what does this say" / "describe my screen" → Describe the current screen state

RESPONSE FORMAT:
Always respond with valid JSON in this exact structure:
{
  "action": "click" | "type" | "scroll" | "key_press" | "wait" | "describe" | "clarify" | "confirm",
  "x": 450,
  "y": 280,
  "grid_cell": 123,
  "target_text": "exact visible text label of the element to click",
  "text": "text to type if action is type",
  "target_field": "which field to type in: to, cc, subject, body",
  "key": "Delete",
  "direction": "down",
  "confirmation": "Spoken message to say to the user",
  "description": "Screen description if action is describe"
}

IMPORTANT FIELD RULES:
- For click actions, ALWAYS include "target_text" — the exact visible
  text label of the UI element you want to click (e.g. "Inbox", "Sent Items",
  "New mail", "Reply", "Delete", the sender name, the email subject, etc.).
  This is used to locate the element precisely in the DOM.
- For type actions, ALWAYS include "target_field" to specify which field
  to type into. Valid values: "to", "cc", "bcc", "subject", "body".
  This ensures text goes into the correct field. Without it, text may end up
  in the wrong field.

Examples:
- Click folder: {"action": "click", "x": 170, "y": 400, "grid_cell": 55, "target_text": "Inbox", "confirmation": "Opening your Inbox"}
- Click folder: {"action": "click", "x": 170, "y": 500, "grid_cell": 70, "target_text": "Sent Items", "confirmation": "Opening Sent Items"}
- Click button: {"action": "click", "x": 140, "y": 75, "grid_cell": 3, "target_text": "New mail", "confirmation": "Opening a new email"}
- Click email: {"action": "click", "x": 600, "y": 420, "grid_cell": 250, "target_text": "Suraj Chawla in Teams", "confirmation": "Opening the email from Suraj"}
- Type in subject: {"action": "type", "text": "Project Update", "target_field": "subject", "confirmation": "Adding the subject line"}
- Type in body: {"action": "type", "text": "Hi team,\nHere is the update.\nThanks,\nAgent", "target_field": "body", "confirmation": "Typing the email body"}
  (Use \\n in text for line breaks — each \\n will create a new line in the email)
- Type in To: {"action": "type", "text": "john@company.com", "target_field": "to", "confirmation": "Adding the recipient"}
- Type in Cc: {"action": "type", "text": "manager@company.com", "target_field": "cc", "confirmation": "Adding CC recipient"}
- Scroll: {"action": "scroll", "direction": "down", "confirmation": "Scrolling down to see more emails"}
- Key press: {"action": "key_press", "key": "Delete", "confirmation": "Deleting this email"}
- Wait: {"action": "wait", "confirmation": "The page is still loading, give me a moment"}
- Describe: {"action": "describe", "description": "Your inbox has 12 emails...", "confirmation": "Let me tell you what I see on your screen"}
- Clarify: {"action": "clarify", "confirmation": "I see two emails from Sarah — do you mean the one about Budget or the one about Meeting Notes?"}
- Confirm: {"action": "confirm", "confirmation": "I'm about to send this email to alex@company.com. Should I go ahead?"}

CRITICAL RULES:
1. ALWAYS respond with ONLY valid JSON — no extra text before or after the JSON.
   Do not add explanations, just the JSON object.
2. ALWAYS speak your action before performing it via the "confirmation" field.
3. Before DESTRUCTIVE actions (Send, Delete, Move), set action to "confirm"
   FIRST and wait for user approval. Only execute after they say yes.
4. If the UI shows a loading spinner or skeleton screen, respond with
   {"action": "wait"} and ask for a new screenshot after 2 seconds.
5. If the command is ambiguous (multiple matching elements), use "clarify".
6. After every action, expect a new screenshot to verify the result.
7. For multi-step operations (e.g., "forward to john@email.com"), break into
   individual steps: first click Forward, then wait for compose, then type
   the email address in the To field.
8. The Send button in Outlook compose is BLUE and at the TOP-LEFT.
   Do NOT click the Discard button which is nearby.
9. When reading emails aloud, summarize long emails — don't read every word.
10. If a command doesn't seem to work, suggest an alternative approach.
11. ALWAYS include "target_field" in type actions. Use "subject" for the
    subject line, "body" for the email body, "to" for recipients, "cc" for CC.
    NEVER send a type action without target_field when in compose mode.
12. Do NOT use a click action to focus a field and then a separate type action.
    Instead, use a SINGLE type action with the correct target_field — the
    system will automatically focus the right field before typing.
13. When the user says "subject - X" or "add subject X", X is the SUBJECT TEXT
    to type, NOT an email address. Same for "body - X". Only "to - X" and
    "cc - X" expect email addresses. NEVER ask for an email address when the
    user is providing subject or body text.
14. When the user provides multiple fields at once (e.g., "To - a@b.com,
    Subject - Hello, body - Hi there"), handle them ONE AT A TIME as separate
    type actions. Start with the first field mentioned.

VOICE PERSONALITY:
- Warm, calm, and encouraging
- Use short, clear sentences
- Describe what you see before acting: "I can see your inbox with 8 emails..."
- Celebrate successful actions: "Done! Your reply has been sent."
- Be honest about uncertainty: "I'm not 100% sure which button that is, let me try..."
"""

# ─────────────────────────────────────────────────────────────
# Grid Overlay — Improves coordinate accuracy for dense UIs
# ─────────────────────────────────────────────────────────────
GRID_SIZE = 40  # pixels per grid cell

def add_grid_overlay(image_base64: str) -> str:
    """Add a numbered grid overlay to the screenshot for precise targeting."""
    try:
        # Decode base64 image
        if "," in image_base64:
            image_base64 = image_base64.split(",")[1]
        
        image_bytes = base64.b64decode(image_base64)
        img = Image.open(io.BytesIO(image_bytes))
        draw = ImageDraw.Draw(img)
        
        w, h = img.size
        cell_id = 0
        
        # Draw grid lines and cell numbers
        for y in range(0, h, GRID_SIZE):
            for x in range(0, w, GRID_SIZE):
                # Draw cell border
                draw.rectangle(
                    [x, y, min(x + GRID_SIZE, w), min(y + GRID_SIZE, h)],
                    outline=(255, 0, 0, 80),
                    width=1
                )
                # Draw cell number
                try:
                    draw.text(
                        (x + 2, y + 1),
                        str(cell_id),
                        fill=(255, 0, 0, 150),
                    )
                except Exception:
                    pass
                cell_id += 1
        
        # Convert back to base64
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=90)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
    
    except Exception as e:
        logger.error(f"Grid overlay failed: {e}")
        return image_base64  # Return original if overlay fails


def grid_cell_to_coordinates(cell_id: int, image_width: int = 1920) -> tuple:
    """Convert a grid cell number to center pixel coordinates."""
    cols = image_width // GRID_SIZE
    row = cell_id // cols
    col = cell_id % cols
    center_x = col * GRID_SIZE + GRID_SIZE // 2
    center_y = row * GRID_SIZE + GRID_SIZE // 2
    return center_x, center_y

# ─────────────────────────────────────────────────────────────
# Screenshot Comparison — Detect loading states
# ─────────────────────────────────────────────────────────────
last_screenshot = None

def screenshots_are_similar(img1_b64: str, img2_b64: str, threshold: float = 0.95) -> bool:
    """Check if two screenshots are very similar (page hasn't changed)."""
    try:
        if img1_b64 is None or img2_b64 is None:
            return False
        
        if "," in img1_b64:
            img1_b64 = img1_b64.split(",")[1]
        if "," in img2_b64:
            img2_b64 = img2_b64.split(",")[1]

        img1 = Image.open(io.BytesIO(base64.b64decode(img1_b64))).resize((192, 108))
        img2 = Image.open(io.BytesIO(base64.b64decode(img2_b64))).resize((192, 108))
        
        pixels1 = list(img1.getdata())
        pixels2 = list(img2.getdata())
        
        if len(pixels1) != len(pixels2):
            return False
        
        matching = sum(1 for p1, p2 in zip(pixels1, pixels2) 
                      if all(abs(a - b) < 30 for a, b in zip(p1, p2)))
        similarity = matching / len(pixels1)
        return similarity > threshold
    
    except Exception:
        return False

# ─────────────────────────────────────────────────────────────
# Gemini generateContent helper
# ─────────────────────────────────────────────────────────────
MODEL = "gemini-2.5-flash-lite"

# Keep conversation history per connection (max last 20 turns to limit token usage)
MAX_HISTORY = 20

def parse_gemini_response(response_text: str, image_width: int = 1920) -> dict:
    """Parse Gemini response text into an action dict."""
    response_text = response_text.strip()

    # Handle markdown code blocks if Gemini wraps in ```json
    if response_text.startswith("```"):
        response_text = response_text.split("\n", 1)[1]
        response_text = response_text.rsplit("```", 1)[0].strip()

    # Try direct JSON parse first
    try:
        action = json.loads(response_text)
    except json.JSONDecodeError:
        # Gemini sometimes wraps JSON in explanatory text
        # Try to extract JSON object from the text
        import re
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text)
        if json_match:
            action = json.loads(json_match.group())
        else:
            raise

    # If Gemini provided a grid_cell, calculate coordinates from it
    # Grid cell is more reliable than x,y estimates — prefer it
    if "grid_cell" in action and action.get("action") == "click":
        cell_x, cell_y = grid_cell_to_coordinates(action["grid_cell"], image_width)
        action["x"] = cell_x
        action["y"] = cell_y

    return action


async def call_gemini(conversation_history: list) -> str:
    """Call Gemini generateContent API with conversation history."""
    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=conversation_history,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.1,
        ),
    )
    return response.text


# ─────────────────────────────────────────────────────────────
# WebSocket Endpoint — Main Agent Loop
# ─────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def agent_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Client connected")

    global last_screenshot
    last_screenshot = None
    conversation_history = []  # Maintains context across turns
    latest_screenshot_parts = None  # Most recent screenshot parts for Gemini
    current_image_width = 1920  # Track actual image width for grid conversion

    try:
        # Send welcome message
        await websocket.send_json({
            "action": "speak",
            "confirmation": "Autopilot is ready. I can see your screen. What would you like to do?"
        })
        logger.info("Welcome message sent, using generateContent API")

        while True:
            # Receive data from Chrome Extension
            try:
                raw_data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )
                data = json.loads(raw_data)
            except asyncio.TimeoutError:
                await websocket.send_json({"action": "keepalive"})
                continue
            except json.JSONDecodeError:
                logger.warning("Received invalid JSON")
                continue

            if data["type"] == "screenshot":
                screenshot_b64 = data["data"]

                # Check if screen has changed since last capture
                if screenshots_are_similar(last_screenshot, screenshot_b64):
                    continue  # Skip if nothing changed — saves API calls

                last_screenshot = screenshot_b64

                # Parse actual resolution from extension
                resolution_str = data.get("resolution", "1920x1080")
                try:
                    img_w, img_h = map(int, resolution_str.split("x"))
                    current_image_width = img_w
                except Exception:
                    current_image_width = 1920

                # Add grid overlay for precise coordinate targeting
                gridded_screenshot = add_grid_overlay(screenshot_b64)

                # Store the latest screenshot parts — will be sent with next command
                latest_screenshot_parts = [
                    types.Part(inline_data=types.Blob(
                        mime_type="image/jpeg",
                        data=base64.b64decode(gridded_screenshot)
                    )),
                    types.Part(text=f"New screenshot received ({img_w}x{img_h}). Grid overlay applied with {GRID_SIZE}px cells.")
                ]
                logger.info(f"Screenshot captured ({img_w}x{img_h}, with grid), ready for next command")

            elif data["type"] == "command":
                # User sends a text command (typed or transcribed from voice)
                user_text = data.get("text", "").strip()
                if not user_text:
                    continue

                logger.info(f"User command: {user_text}")

                # Build the message parts: screenshot (if available) + text command
                parts = []
                if latest_screenshot_parts:
                    parts.extend(latest_screenshot_parts)
                parts.append(types.Part(text=f"User command: {user_text}"))

                # Add to conversation history
                conversation_history.append(
                    types.Content(role="user", parts=parts)
                )

                # Trim history to keep within token limits
                if len(conversation_history) > MAX_HISTORY:
                    conversation_history = conversation_history[-MAX_HISTORY:]

                # Call Gemini generateContent API
                try:
                    response_text = await call_gemini(conversation_history)
                    logger.info(f"Gemini response: {response_text[:200]}")

                    # Add assistant response to history
                    conversation_history.append(
                        types.Content(role="model", parts=[
                            types.Part(text=response_text)
                        ])
                    )

                    # Parse and send action to client
                    try:
                        action = parse_gemini_response(response_text, current_image_width)
                        await websocket.send_json(action)
                        logger.info(f"Action sent to client: {action.get('action')}")
                    except json.JSONDecodeError:
                        # Gemini returned non-JSON text — treat as spoken response
                        await websocket.send_json({
                            "action": "speak",
                            "confirmation": response_text
                        })

                except Exception as e:
                    logger.error(f"Gemini API error: {e}", exc_info=True)
                    await websocket.send_json({
                        "action": "speak",
                        "confirmation": "Sorry, I had trouble processing that. Could you try again?"
                    })

            # elif data["type"] == "audio":
            #     # Audio input commented out for now — use text commands instead
            #     audio_data = data["data"]
            #     if not audio_data:
            #         continue
            #     logger.info("Audio received but audio input is disabled. Use text commands.")

            elif data["type"] == "user_confirmation":
                # User responded to a confirm action (yes/no)
                confirmation = data.get("response", "").lower()
                logger.info(f"User confirmation: {confirmation}")

                # Add confirmation to history and get next action
                conversation_history.append(
                    types.Content(role="user", parts=[
                        types.Part(text=f"User responded to confirmation: '{confirmation}'")
                    ])
                )

                if len(conversation_history) > MAX_HISTORY:
                    conversation_history = conversation_history[-MAX_HISTORY:]

                try:
                    response_text = await call_gemini(conversation_history)
                    logger.info(f"Gemini response: {response_text[:200]}")

                    conversation_history.append(
                        types.Content(role="model", parts=[
                            types.Part(text=response_text)
                        ])
                    )

                    try:
                        action = parse_gemini_response(response_text, current_image_width)
                        await websocket.send_json(action)
                        logger.info(f"Action sent to client: {action.get('action')}")
                    except json.JSONDecodeError:
                        await websocket.send_json({
                            "action": "speak",
                            "confirmation": response_text
                        })

                except Exception as e:
                    logger.error(f"Gemini API error: {e}", exc_info=True)
                    await websocket.send_json({
                        "action": "speak",
                        "confirmation": "Sorry, something went wrong. Please try again."
                    })

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "action": "error",
                "confirmation": "Something went wrong. Please try restarting Autopilot."
            })
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
# Health Check Endpoint
# ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "accessibility-autopilot", "target": "outlook-365"}


@app.get("/")
async def root():
    return {
        "name": "Accessibility Autopilot",
        "version": "2.0",
        "target_app": "Microsoft Outlook 365 (Browser)",
        "status": "running",
        "websocket_endpoint": "/ws"
    }