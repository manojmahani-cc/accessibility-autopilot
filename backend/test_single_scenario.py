"""
Accessibility Autopilot — Single Scenario Quick Test
=====================================================
Tests ONE end-to-end scenario: Send an Outlook inbox screenshot
to Gemini and ask it to identify and click the first email.

This test does NOT require the backend server to be running.
It calls the Gemini generateContent API directly to verify:
  1. Your API key works
  2. Gemini can understand an Outlook screenshot
  3. Gemini returns a valid action JSON with coordinates

Usage:
  export GEMINI_API_KEY=your_key_here
  python test_single_scenario.py
"""

import asyncio
import base64
import io
import json
import os
import sys
import time
from PIL import Image, ImageDraw


# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-2.5-flash-lite"

# MODEL = "gemini-2.0-flash-lite-001"

# Simplified system prompt for this test
TEST_SYSTEM_PROMPT = """You are an accessibility agent controlling Microsoft Outlook 365 
in a web browser. You receive a screenshot and a text command.

The screenshot is EXACTLY 1920x1080 pixels.

OUTLOOK UI LAYOUT:
- LEFT SIDEBAR (x: 0-250): Folders — Inbox, Drafts, Sent Items
- RIBBON/TOOLBAR (x: 250-1920, y: 50-102): New mail, Delete, Archive, Reply, Forward
- EMAIL LIST (x: 250-700, y: 102-1080): List of emails with sender, subject, preview
- READING PANE (x: 700-1920, y: 102-1080): Selected email content

Respond with ONLY valid JSON, no other text. Use this format:
{
  "action": "click",
  "x": <pixel_x>,
  "y": <pixel_y>,
  "element_description": "<what you're clicking>",
  "confirmation": "<what to say to the user>"
}
"""


# ─────────────────────────────────────────────────────────────
# Generate a fake Outlook inbox screenshot
# ─────────────────────────────────────────────────────────────
def create_outlook_inbox_screenshot() -> bytes:
    """Generate a realistic Outlook inbox screenshot."""
    img = Image.new("RGB", (1920, 1080), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # ── Top bar (Outlook blue header) ──
    draw.rectangle([0, 0, 1920, 50], fill=(0, 90, 158))
    draw.text((80, 15), "Outlook", fill=(255, 255, 255))
    draw.text((700, 15), "Search mail and people", fill=(180, 210, 240))
    draw.text((1800, 15), "JD", fill=(255, 255, 255))  # User avatar initials

    # ── Left sidebar ──
    draw.rectangle([0, 50, 250, 1080], fill=(243, 243, 243))
    folders = [
        ("Inbox (3)", True),
        ("Drafts (1)", False),
        ("Sent Items", False),
        ("Deleted Items", False),
        ("Junk Email", False),
        ("Archive", False),
    ]
    for i, (folder, selected) in enumerate(folders):
        y = 80 + i * 40
        if selected:
            draw.rectangle([0, y - 5, 250, y + 30], fill=(220, 235, 250))
            draw.rectangle([0, y - 5, 4, y + 30], fill=(0, 90, 158))
        color = (0, 90, 158) if selected else (60, 60, 60)
        draw.text((20, y), folder, fill=color)

    # ── Ribbon toolbar ──
    draw.rectangle([250, 50, 1920, 100], fill=(245, 245, 245))
    draw.rectangle([250, 100, 1920, 102], fill=(220, 220, 220))
    ribbon_items = [
        ("New mail", 290),
        ("Delete", 420),
        ("Archive", 510),
        ("|", 570),
        ("Reply", 600),
        ("Reply all", 680),
        ("Forward", 790),
    ]
    for label, x in ribbon_items:
        fill = (200, 200, 200) if label == "|" else (60, 60, 60)
        draw.text((x, 68), label, fill=fill)

    # ── Email list (center panel) ──
    emails = [
        {
            "sender": "Alex Chen",
            "subject": "Project Deadline Update",
            "preview": "Hi, just wanted to let you know that the deadline...",
            "time": "10:30 AM",
            "unread": True,
        },
        {
            "sender": "Sarah Miller",
            "subject": "Q3 Budget Review - Action Required",
            "preview": "Please review the attached budget spreadsheet...",
            "time": "9:15 AM",
            "unread": True,
        },
        {
            "sender": "John Davis",
            "subject": "Team Meeting Notes - Oct 15",
            "preview": "Here are the notes from today's standup...",
            "time": "Yesterday",
            "unread": True,
        },
        {
            "sender": "Marketing Team",
            "subject": "Campaign Performance Results",
            "preview": "Great news! The Q3 campaign exceeded targets...",
            "time": "Yesterday",
            "unread": False,
        },
        {
            "sender": "HR Department",
            "subject": "Open Enrollment Reminder",
            "preview": "This is a reminder that benefits enrollment...",
            "time": "Monday",
            "unread": False,
        },
        {
            "sender": "Lisa Park",
            "subject": "Design Review Feedback",
            "preview": "I've reviewed the mockups and have some...",
            "time": "Monday",
            "unread": False,
        },
    ]

    for i, email in enumerate(emails):
        y = 115 + i * 85
        # Background
        bg_color = (240, 248, 255) if email["unread"] else (255, 255, 255)
        if i == 0:
            bg_color = (230, 242, 255)  # First email slightly highlighted
        draw.rectangle([250, y, 700, y + 80], fill=bg_color)
        # Unread indicator
        if email["unread"]:
            draw.rectangle([250, y, 255, y + 80], fill=(0, 90, 158))
        # Divider line
        draw.rectangle([255, y + 80, 700, y + 81], fill=(235, 235, 235))
        # Text
        sender_color = (0, 0, 0) if email["unread"] else (110, 110, 110)
        subject_color = (30, 30, 30) if email["unread"] else (100, 100, 100)
        draw.text((270, y + 10), email["sender"], fill=sender_color)
        draw.text((620, y + 10), email["time"], fill=(160, 160, 160))
        draw.text((270, y + 32), email["subject"], fill=subject_color)
        draw.text((270, y + 55), email["preview"][:50], fill=(160, 160, 160))

    # ── Reading pane (right side — showing first email) ──
    draw.rectangle([700, 102, 702, 1080], fill=(230, 230, 230))  # Divider
    draw.rectangle([702, 102, 1920, 1080], fill=(255, 255, 255))

    # Email header in reading pane
    draw.text((740, 130), "Alex Chen", fill=(0, 0, 0))
    draw.text((740, 158), "Project Deadline Update", fill=(40, 40, 40))
    draw.text((740, 188), "To: you@company.com", fill=(140, 140, 140))
    draw.text((740, 208), "Today at 10:30 AM", fill=(140, 140, 140))

    # Separator
    draw.rectangle([740, 240, 1880, 241], fill=(230, 230, 230))

    # Email body
    body_lines = [
        "Hi,",
        "",
        "Just wanted to let you know that the project deadline has been",
        "moved to next Friday (October 25th).",
        "",
        "Please update your timeline accordingly and let me know if you",
        "have any concerns about meeting the new deadline.",
        "",
        "Also, can you send me the latest status report by EOD tomorrow?",
        "",
        "Thanks,",
        "Alex",
    ]
    for i, line in enumerate(body_lines):
        draw.text((740, 260 + i * 24), line, fill=(50, 50, 50))

    # Convert to bytes
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────
# Pretty print helpers
# ─────────────────────────────────────────────────────────────
def print_header(text):
    print(f"\n{'=' * 65}")
    print(f"  {text}")
    print(f"{'=' * 65}")


def print_step(num, text):
    print(f"\n  Step {num}: {text}")
    print(f"  {'─' * 55}")


def print_pass(text):
    print(f"  ✅ PASS: {text}")


def print_fail(text):
    print(f"  ❌ FAIL: {text}")


def print_info(text):
    print(f"  ℹ️  {text}")


def print_result(label, value):
    print(f"     {label}: {value}")


# ─────────────────────────────────────────────────────────────
# Main Test
# ─────────────────────────────────────────────────────────────
async def run_test():
    print_header("♿ Accessibility Autopilot — Single Scenario Test")
    print_info(f"Model: {MODEL}")
    print_info(f"API Key: {'✅ Set' if API_KEY else '❌ MISSING'}")

    if not API_KEY:
        print_fail("GEMINI_API_KEY environment variable is not set!")
        print_info("Run: export GEMINI_API_KEY=your_key_here")
        return False

    all_passed = True

    # ──────────────────────────────────────
    # Step 1: Generate test screenshot
    # ──────────────────────────────────────
    print_step(1, "Generate fake Outlook inbox screenshot")
    try:
        screenshot_bytes = create_outlook_inbox_screenshot()
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        size_kb = len(screenshot_bytes) / 1024
        print_pass(f"Screenshot created ({size_kb:.0f} KB, 1920x1080)")

        # Save locally for inspection
        with open("test_screenshot.jpg", "wb") as f:
            f.write(screenshot_bytes)
        print_info("Saved to test_screenshot.jpg (open to inspect)")
    except Exception as e:
        print_fail(f"Screenshot generation failed: {e}")
        return False

    # ──────────────────────────────────────
    # Step 2: Connect to Gemini
    # ──────────────────────────────────────
    print_step(2, "Connect to Gemini API")
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=API_KEY)
        print_pass("Gemini client created")
    except ImportError:
        print_fail("google-genai package not installed. Run: pip install google-genai")
        return False
    except Exception as e:
        print_fail(f"Client creation failed: {e}")
        return False

    # ──────────────────────────────────────
    # Step 3: Send screenshot + command
    # ──────────────────────────────────────
    print_step(3, "Send screenshot + voice command to Gemini")
    user_command = "Open the first email in my inbox — it should be from Alex Chen"
    print_info(f"Command: \"{user_command}\"")

    try:
        start_time = time.time()

        response = client.models.generate_content(
            model=MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            inline_data=types.Blob(
                                mime_type="image/jpeg",
                                data=screenshot_bytes,
                            )
                        ),
                        types.Part(text=user_command),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                system_instruction=TEST_SYSTEM_PROMPT,
                temperature=0.1,  # Low temp for consistent actions
            ),
        )

        elapsed = time.time() - start_time
        print_pass(f"Gemini responded in {elapsed:.2f}s")
    except Exception as e:
        print_fail(f"Gemini API call failed: {e}")
        all_passed = False
        return False

    # ──────────────────────────────────────
    # Step 4: Parse response
    # ──────────────────────────────────────
    print_step(4, "Parse Gemini's response")

    raw_text = response.text.strip()
    print_info(f"Raw response ({len(raw_text)} chars):")
    print(f"\n     {'─' * 50}")
    for line in raw_text.split("\n"):
        print(f"     {line}")
    print(f"     {'─' * 50}\n")

    # Clean up markdown fences if present
    clean_text = raw_text
    if clean_text.startswith("```"):
        clean_text = clean_text.split("\n", 1)[1] if "\n" in clean_text else clean_text[3:]
    if clean_text.endswith("```"):
        clean_text = clean_text.rsplit("```", 1)[0]
    clean_text = clean_text.strip()

    try:
        action = json.loads(clean_text)
        print_pass("Response is valid JSON")
    except json.JSONDecodeError as e:
        print_fail(f"Response is NOT valid JSON: {e}")
        print_info("This means the system prompt needs tuning to enforce JSON output")
        all_passed = False
        return all_passed

    # ──────────────────────────────────────
    # Step 5: Validate action structure
    # ──────────────────────────────────────
    print_step(5, "Validate action structure")

    # Check required fields
    checks = {
        "has 'action' field": "action" in action,
        "action is 'click'": action.get("action") == "click",
        "has 'x' coordinate": "x" in action and isinstance(action["x"], (int, float)),
        "has 'y' coordinate": "y" in action and isinstance(action["y"], (int, float)),
        "has 'confirmation' message": "confirmation" in action and len(action.get("confirmation", "")) > 0,
    }

    for label, passed in checks.items():
        if passed:
            print_pass(label)
        else:
            print_fail(label)
            all_passed = False

    if "x" in action and "y" in action:
        print_result("Click coordinates", f"({action['x']}, {action['y']})")
    if "element_description" in action:
        print_result("Target element", action["element_description"])
    if "confirmation" in action:
        print_result("Voice confirmation", action["confirmation"])

    # ──────────────────────────────────────
    # Step 6: Validate coordinate accuracy
    # ──────────────────────────────────────
    print_step(6, "Validate coordinate accuracy")

    if "x" in action and "y" in action:
        x, y = action["x"], action["y"]

        coord_checks = {
            "X is within screen width (0-1920)": 0 <= x <= 1920,
            "Y is within screen height (0-1080)": 0 <= y <= 1080,
            "X is in email list area (250-700)": 250 <= x <= 700,
            "Y is near first email row (115-200)": 100 <= y <= 220,
        }

        for label, passed in coord_checks.items():
            if passed:
                print_pass(label)
            else:
                print_fail(label)
                all_passed = False

        # Check if click is reasonably close to first email
        # First email in our screenshot is roughly at y=115 to y=195
        first_email_center_x = 475  # Center of email list
        first_email_center_y = 155  # Center of first email row
        distance = ((x - first_email_center_x) ** 2 + (y - first_email_center_y) ** 2) ** 0.5

        print_result("Expected center", f"~({first_email_center_x}, {first_email_center_y})")
        print_result("Actual click", f"({x}, {y})")
        print_result("Distance from ideal", f"{distance:.0f}px")

        if distance < 100:
            print_pass(f"Coordinate accuracy is GOOD ({distance:.0f}px from ideal)")
        elif distance < 200:
            print_info(f"Coordinate accuracy is ACCEPTABLE ({distance:.0f}px from ideal)")
        else:
            print_fail(f"Coordinate accuracy is POOR ({distance:.0f}px from ideal)")
            print_info("Consider using grid overlay strategy to improve accuracy")
            all_passed = False
    else:
        print_fail("No coordinates in response — cannot validate accuracy")
        all_passed = False

    # ──────────────────────────────────────
    # Step 7: Visual verification
    # ──────────────────────────────────────
    print_step(7, "Generate visual verification image")

    try:
        img = Image.open(io.BytesIO(screenshot_bytes))
        draw = ImageDraw.Draw(img)

        if "x" in action and "y" in action:
            cx, cy = int(action["x"]), int(action["y"])
            # Draw crosshair at click location
            draw.ellipse([cx - 25, cy - 25, cx + 25, cy + 25], outline=(255, 0, 0), width=3)
            draw.ellipse([cx - 15, cy - 15, cx + 15, cy + 15], outline=(255, 0, 0), width=2)
            draw.line([cx - 35, cy, cx + 35, cy], fill=(255, 0, 0), width=2)
            draw.line([cx, cy - 35, cx, cy + 35], fill=(255, 0, 0), width=2)
            # Label
            draw.rectangle([cx + 30, cy - 20, cx + 200, cy + 5], fill=(255, 0, 0))
            draw.text((cx + 35, cy - 17), f"CLICK ({cx}, {cy})", fill=(255, 255, 255))

        img.save("test_result.jpg", quality=90)
        print_pass("Saved to test_result.jpg — open to see where Gemini would click")
        print_info("The red crosshair shows the exact click target")
    except Exception as e:
        print_info(f"Could not save visual: {e}")

    # ──────────────────────────────────────
    # Summary
    # ──────────────────────────────────────
    print_header("Test Results")
    if all_passed:
        print("  ✅ ALL CHECKS PASSED — Gemini can understand Outlook and return actions!")
        print()
        print("  Next steps:")
        print("    1. Start the full backend:  uvicorn backend:app --port 8080")
        print("    2. Load the Chrome extension in chrome://extensions")
        print("    3. Open outlook.office.com and start Autopilot")
        print("    4. Run full test suite:  python test_autopilot.py")
    else:
        print("  ⚠️  SOME CHECKS FAILED — see details above")
        print()
        print("  Common fixes:")
        print("    - JSON parse error → Tweak system prompt to enforce JSON-only output")
        print("    - Wrong coordinates → Add grid overlay, specify resolution more clearly")
        print("    - API key error → Check GEMINI_API_KEY is set correctly")
        print("    - Import error → Run: pip install google-genai Pillow")

    print(f"\n{'=' * 65}\n")
    return all_passed


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    success = asyncio.run(run_test())
    sys.exit(0 if success else 1)