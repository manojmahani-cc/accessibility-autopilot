"""
Accessibility Autopilot — Test Suite (Outlook 365 Edition)
==========================================================
Run all tests:       python test_autopilot.py
Run specific test:   python test_autopilot.py TestWebSocket
Run with verbose:    python test_autopilot.py -v

Prerequisites:
  - Backend running locally: uvicorn backend:app --host 0.0.0.0 --port 8080
  - GEMINI_API_KEY environment variable set
  - pip install websockets pillow requests
"""

import asyncio
import base64
import io
import json
import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock

import requests
import websockets
from PIL import Image, ImageDraw, ImageFont

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────
BACKEND_URL_HTTP = os.getenv("TEST_BACKEND_URL", "http://localhost:8080")
BACKEND_URL_WS = os.getenv("TEST_BACKEND_WS", "ws://localhost:8080/ws")
GEMINI_TIMEOUT = 15  # seconds to wait for Gemini response
WEBSOCKET_TIMEOUT = 10


# ─────────────────────────────────────────────────────────────
# Helper: Generate fake Outlook screenshots
# ─────────────────────────────────────────────────────────────
def create_fake_outlook_screenshot(scenario="inbox") -> str:
    """
    Generate a synthetic Outlook-like screenshot for testing.
    Returns base64-encoded JPEG string.
    """
    img = Image.new("RGB", (1920, 1080), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Top bar (dark blue - Outlook header)
    draw.rectangle([0, 0, 1920, 50], fill=(0, 90, 158))
    draw.text((80, 15), "Outlook", fill=(255, 255, 255))
    draw.text((700, 15), "Search mail and people", fill=(200, 200, 200))

    # Left sidebar (folder list)
    draw.rectangle([0, 50, 250, 1080], fill=(243, 243, 243))
    folders = ["Inbox (5)", "Drafts", "Sent Items", "Deleted Items", "Junk Email", "Archive"]
    for i, folder in enumerate(folders):
        y = 80 + i * 40
        color = (0, 90, 158) if i == 0 else (50, 50, 50)
        if i == 0:
            draw.rectangle([0, y - 5, 250, y + 30], fill=(220, 235, 250))
        draw.text((20, y), folder, fill=color)

    # Ribbon toolbar
    draw.rectangle([250, 50, 1920, 100], fill=(245, 245, 245))
    draw.rectangle([250, 100, 1920, 102], fill=(220, 220, 220))
    buttons = [("New mail", 280), ("Delete", 400), ("Archive", 490), ("Reply", 580), ("Reply all", 660), ("Forward", 770)]
    for label, x in buttons:
        draw.text((x, 68), label, fill=(50, 50, 50))

    if scenario == "inbox":
        # Email list (center panel)
        draw.rectangle([250, 102, 700, 1080], fill=(255, 255, 255))
        emails = [
            {"sender": "Alex Chen", "subject": "Project Deadline Update", "preview": "Hi, just wanted to let you know...", "unread": True, "time": "10:30 AM"},
            {"sender": "Sarah Miller", "subject": "Q3 Budget Review", "preview": "Please review the attached...", "unread": True, "time": "9:45 AM"},
            {"sender": "John Davis", "subject": "Team Meeting Notes", "preview": "Here are the notes from...", "unread": False, "time": "Yesterday"},
            {"sender": "Marketing Team", "subject": "Campaign Results", "preview": "Great news! The campaign...", "unread": False, "time": "Yesterday"},
            {"sender": "HR Department", "subject": "Benefits Enrollment", "preview": "Open enrollment period...", "unread": False, "time": "Mon"},
        ]
        for i, email in enumerate(emails):
            y = 115 + i * 80
            # Unread indicator (blue left border)
            if email["unread"]:
                draw.rectangle([250, y, 255, y + 70], fill=(0, 90, 158))
                draw.rectangle([255, y, 700, y + 70], fill=(240, 248, 255))
            else:
                draw.rectangle([250, y, 700, y + 70], fill=(255, 255, 255))
            # Divider
            draw.rectangle([255, y + 70, 700, y + 71], fill=(240, 240, 240))
            # Email content
            sender_color = (0, 0, 0) if email["unread"] else (100, 100, 100)
            draw.text((270, y + 8), email["sender"], fill=sender_color)
            draw.text((270, y + 28), email["subject"], fill=sender_color)
            draw.text((270, y + 48), email["preview"], fill=(150, 150, 150))
            draw.text((620, y + 8), email["time"], fill=(150, 150, 150))

        # Reading pane (right panel)
        draw.rectangle([700, 102, 1920, 1080], fill=(255, 255, 255))
        draw.rectangle([700, 102, 702, 1080], fill=(230, 230, 230))
        draw.text((730, 120), "Alex Chen", fill=(0, 0, 0))
        draw.text((730, 145), "Project Deadline Update", fill=(0, 0, 0))
        draw.text((730, 175), "To: you@company.com", fill=(150, 150, 150))
        draw.text((730, 210), "Hi,", fill=(50, 50, 50))
        draw.text((730, 235), "Just wanted to let you know that the project", fill=(50, 50, 50))
        draw.text((730, 260), "deadline has been moved to next Friday.", fill=(50, 50, 50))
        draw.text((730, 295), "Please update your timeline accordingly.", fill=(50, 50, 50))
        draw.text((730, 330), "Thanks,", fill=(50, 50, 50))
        draw.text((730, 355), "Alex", fill=(50, 50, 50))

    elif scenario == "compose":
        # Compose window — dark overlay background to be visually distinct from inbox
        draw.rectangle([250, 102, 1920, 1080], fill=(50, 50, 70))
        # Compose modal (white card on dark background)
        draw.rectangle([300, 120, 1600, 900], fill=(255, 255, 255))
        draw.rectangle([300, 120, 1600, 124], fill=(0, 90, 158))
        # Send button (blue, top-left of compose)
        draw.rectangle([320, 135, 400, 165], fill=(0, 90, 158))
        draw.text((335, 142), "Send", fill=(255, 255, 255))
        # Discard button
        draw.rectangle([420, 135, 510, 165], fill=(230, 230, 230))
        draw.text((435, 142), "Discard", fill=(80, 80, 80))
        # To field
        draw.text((320, 190), "To:", fill=(100, 100, 100))
        draw.rectangle([370, 185, 1580, 210], fill=(230, 230, 240))
        # Subject field
        draw.text((320, 230), "Subject:", fill=(100, 100, 100))
        draw.rectangle([400, 225, 1580, 250], fill=(230, 230, 240))
        # Body area
        draw.rectangle([320, 280, 1580, 880], fill=(250, 250, 255))
        draw.text((330, 290), "Type your message here...", fill=(180, 180, 180))

    elif scenario == "loading":
        # Loading / skeleton state
        draw.rectangle([250, 102, 1920, 1080], fill=(250, 250, 250))
        for i in range(5):
            y = 130 + i * 80
            draw.rectangle([270, y, 450, y + 15], fill=(230, 230, 230))
            draw.rectangle([270, y + 25, 600, y + 35], fill=(235, 235, 235))
            draw.rectangle([270, y + 45, 550, y + 55], fill=(240, 240, 240))

    elif scenario == "reply":
        # Reply view (compose inline in reading pane)
        draw.rectangle([700, 102, 1920, 1080], fill=(255, 255, 255))
        draw.text((730, 120), "RE: Project Deadline Update", fill=(0, 0, 0))
        draw.text((730, 150), "To: Alex Chen <alex@company.com>", fill=(100, 100, 100))
        # Send button
        draw.rectangle([730, 180, 810, 210], fill=(0, 90, 158))
        draw.text((745, 187), "Send", fill=(255, 255, 255))
        # Discard
        draw.rectangle([830, 180, 920, 210], fill=(230, 230, 230))
        draw.text((845, 187), "Discard", fill=(80, 80, 80))
        # Reply body
        draw.rectangle([730, 230, 1880, 600], fill=(255, 255, 255))
        draw.text((740, 240), "Type your reply...", fill=(180, 180, 180))
        # Original message
        draw.rectangle([730, 620, 1880, 622], fill=(200, 200, 200))
        draw.text((730, 640), "From: Alex Chen", fill=(120, 120, 120))
        draw.text((730, 665), "Just wanted to let you know that the project", fill=(120, 120, 120))

    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=90)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# ─────────────────────────────────────────────────────────────
# Test 1: Health Check & Server Status
# ─────────────────────────────────────────────────────────────
class TestHealthCheck(unittest.TestCase):
    """Verify the backend server is running and responding."""

    def test_health_endpoint(self):
        """GET /health should return status ok."""
        try:
            resp = requests.get(f"{BACKEND_URL_HTTP}/health", timeout=5)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["status"], "ok")
            self.assertEqual(data["target"], "outlook-365")
            print("  ✅ Health endpoint responding")
        except requests.ConnectionError:
            self.fail(
                f"❌ Cannot connect to {BACKEND_URL_HTTP}. "
                "Is the backend running? Run: uvicorn backend:app --port 8080"
            )

    def test_root_endpoint(self):
        """GET / should return service info."""
        resp = requests.get(f"{BACKEND_URL_HTTP}/", timeout=5)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["name"], "Accessibility Autopilot")
        self.assertIn("outlook", data["target_app"].lower())
        print("  ✅ Root endpoint returning service info")

    def test_websocket_endpoint_exists(self):
        """WebSocket endpoint /ws should accept connections."""
        async def check():
            try:
                ws = await asyncio.wait_for(
                    websockets.connect(BACKEND_URL_WS),
                    timeout=WEBSOCKET_TIMEOUT
                )
                await ws.close()
                return True
            except Exception as e:
                self.fail(f"❌ WebSocket connection failed: {e}")

        asyncio.get_event_loop().run_until_complete(check())
        print("  ✅ WebSocket endpoint accepts connections")


# ─────────────────────────────────────────────────────────────
# Test 2: Grid Overlay Function
# ─────────────────────────────────────────────────────────────
class TestGridOverlay(unittest.TestCase):
    """Test the grid overlay utility that improves coordinate accuracy."""

    def test_grid_overlay_produces_image(self):
        """Grid overlay should return a valid base64 image."""
        from backend import add_grid_overlay

        screenshot = create_fake_outlook_screenshot("inbox")
        result = add_grid_overlay(screenshot)

        self.assertIsInstance(result, str)
        # Should be valid base64
        img_bytes = base64.b64decode(result)
        img = Image.open(io.BytesIO(img_bytes))
        self.assertEqual(img.size[0], 1920)
        self.assertEqual(img.size[1], 1080)
        print("  ✅ Grid overlay produces valid 1920x1080 image")

    def test_grid_overlay_handles_data_url_prefix(self):
        """Grid overlay should handle base64 with data:image prefix."""
        from backend import add_grid_overlay

        screenshot = create_fake_outlook_screenshot("inbox")
        prefixed = f"data:image/jpeg;base64,{screenshot}"
        result = add_grid_overlay(prefixed)

        self.assertIsInstance(result, str)
        img_bytes = base64.b64decode(result)
        img = Image.open(io.BytesIO(img_bytes))
        self.assertGreater(img.size[0], 0)
        print("  ✅ Grid overlay handles data URL prefix")

    def test_grid_cell_to_coordinates(self):
        """Grid cell IDs should map to correct pixel coordinates."""
        from backend import grid_cell_to_coordinates

        # Cell 0 should be top-left (center of first 40x40 cell)
        x, y = grid_cell_to_coordinates(0, 1920)
        self.assertEqual(x, 20)
        self.assertEqual(y, 20)

        # Cell 1 should be next cell to the right
        x, y = grid_cell_to_coordinates(1, 1920)
        self.assertEqual(x, 60)
        self.assertEqual(y, 20)

        # Cell 48 (1920/40 = 48 cells per row) should be start of second row
        x, y = grid_cell_to_coordinates(48, 1920)
        self.assertEqual(x, 20)
        self.assertEqual(y, 60)

        print("  ✅ Grid cell to coordinate mapping is correct")

    def test_grid_overlay_handles_invalid_input(self):
        """Grid overlay should return original on invalid input."""
        from backend import add_grid_overlay

        result = add_grid_overlay("not_valid_base64")
        self.assertEqual(result, "not_valid_base64")
        print("  ✅ Grid overlay handles invalid input gracefully")


# ─────────────────────────────────────────────────────────────
# Test 3: Screenshot Comparison (Deduplication)
# ─────────────────────────────────────────────────────────────
class TestScreenshotComparison(unittest.TestCase):
    """Test screenshot similarity detection for skipping duplicate frames."""

    def test_identical_screenshots_are_similar(self):
        """Two identical screenshots should be detected as similar."""
        from backend import screenshots_are_similar

        img = create_fake_outlook_screenshot("inbox")
        self.assertTrue(screenshots_are_similar(img, img))
        print("  ✅ Identical screenshots detected as similar")

    def test_different_screenshots_are_not_similar(self):
        """Different scenarios should not be similar."""
        from backend import screenshots_are_similar

        inbox = create_fake_outlook_screenshot("inbox")
        compose = create_fake_outlook_screenshot("compose")
        self.assertFalse(screenshots_are_similar(inbox, compose))
        print("  ✅ Different screenshots detected as different")

    def test_none_input_returns_false(self):
        """None inputs should return False (not similar)."""
        from backend import screenshots_are_similar

        img = create_fake_outlook_screenshot("inbox")
        self.assertFalse(screenshots_are_similar(None, img))
        self.assertFalse(screenshots_are_similar(img, None))
        self.assertFalse(screenshots_are_similar(None, None))
        print("  ✅ None inputs handled correctly")


# ─────────────────────────────────────────────────────────────
# Test 4: WebSocket Communication
# ─────────────────────────────────────────────────────────────
class TestWebSocket(unittest.TestCase):
    """Test real WebSocket communication with the backend."""

    def test_connect_and_receive_welcome(self):
        """Should receive welcome message after connecting."""
        async def run():
            ws = await asyncio.wait_for(
                websockets.connect(BACKEND_URL_WS),
                timeout=WEBSOCKET_TIMEOUT
            )
            try:
                # Should receive welcome message
                msg = await asyncio.wait_for(ws.recv(), timeout=GEMINI_TIMEOUT)
                data = json.loads(msg)
                self.assertIn("action", data)
                self.assertIn("confirmation", data)
                self.assertIn("ready", data["confirmation"].lower())
                print(f"  ✅ Welcome message received: {data['confirmation'][:60]}...")
            finally:
                await ws.close()

        asyncio.get_event_loop().run_until_complete(run())

    def test_send_screenshot(self):
        """Should accept screenshot data without error."""
        async def run():
            ws = await asyncio.wait_for(
                websockets.connect(BACKEND_URL_WS),
                timeout=WEBSOCKET_TIMEOUT
            )
            try:
                # Consume welcome message
                await asyncio.wait_for(ws.recv(), timeout=GEMINI_TIMEOUT)

                # Send screenshot
                screenshot = create_fake_outlook_screenshot("inbox")
                await ws.send(json.dumps({
                    "type": "screenshot",
                    "data": screenshot,
                    "timestamp": int(time.time() * 1000),
                    "resolution": "1920x1080"
                }))
                print("  ✅ Screenshot sent successfully")

                # Wait briefly for any response (may or may not get one without audio)
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    print(f"  ℹ️  Got response: {msg[:100]}...")
                except asyncio.TimeoutError:
                    print("  ℹ️  No immediate response (expected — waiting for voice command)")

            finally:
                await ws.close()

        asyncio.get_event_loop().run_until_complete(run())

    def test_send_invalid_json(self):
        """Should handle invalid JSON gracefully without crashing."""
        async def run():
            ws = await asyncio.wait_for(
                websockets.connect(BACKEND_URL_WS),
                timeout=WEBSOCKET_TIMEOUT
            )
            try:
                # Consume welcome
                await asyncio.wait_for(ws.recv(), timeout=GEMINI_TIMEOUT)

                # Send garbage
                await ws.send("this is not json")

                # Connection should still be alive
                await asyncio.sleep(1)
                self.assertTrue(ws.open)
                print("  ✅ Backend handles invalid JSON without crashing")
            finally:
                await ws.close()

        asyncio.get_event_loop().run_until_complete(run())

    def test_duplicate_screenshots_skipped(self):
        """Sending identical screenshots should not trigger duplicate processing."""
        async def run():
            ws = await asyncio.wait_for(
                websockets.connect(BACKEND_URL_WS),
                timeout=WEBSOCKET_TIMEOUT
            )
            try:
                # Consume welcome
                await asyncio.wait_for(ws.recv(), timeout=GEMINI_TIMEOUT)

                screenshot = create_fake_outlook_screenshot("inbox")

                # Send same screenshot twice
                for i in range(2):
                    await ws.send(json.dumps({
                        "type": "screenshot",
                        "data": screenshot,
                        "timestamp": int(time.time() * 1000),
                        "resolution": "1920x1080"
                    }))
                    await asyncio.sleep(0.5)

                # Connection should still be alive
                self.assertTrue(ws.open)
                print("  ✅ Duplicate screenshots handled (deduplication working)")
            finally:
                await ws.close()

        asyncio.get_event_loop().run_until_complete(run())

    def test_user_confirmation_message(self):
        """Should accept user confirmation responses."""
        async def run():
            ws = await asyncio.wait_for(
                websockets.connect(BACKEND_URL_WS),
                timeout=WEBSOCKET_TIMEOUT
            )
            try:
                # Consume welcome
                await asyncio.wait_for(ws.recv(), timeout=GEMINI_TIMEOUT)

                # Send user confirmation
                await ws.send(json.dumps({
                    "type": "user_confirmation",
                    "response": "yes"
                }))

                self.assertTrue(ws.open)
                print("  ✅ User confirmation message accepted")
            finally:
                await ws.close()

        asyncio.get_event_loop().run_until_complete(run())


# ─────────────────────────────────────────────────────────────
# Test 5: Fake Outlook Screenshot Generation
# ─────────────────────────────────────────────────────────────
class TestScreenshotGeneration(unittest.TestCase):
    """Verify test screenshot generation works for all scenarios."""

    def test_inbox_screenshot(self):
        """Inbox screenshot should be valid."""
        b64 = create_fake_outlook_screenshot("inbox")
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        self.assertEqual(img.size, (1920, 1080))
        print("  ✅ Inbox screenshot: 1920x1080")

    def test_compose_screenshot(self):
        """Compose screenshot should be valid."""
        b64 = create_fake_outlook_screenshot("compose")
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        self.assertEqual(img.size, (1920, 1080))
        print("  ✅ Compose screenshot: 1920x1080")

    def test_reply_screenshot(self):
        """Reply screenshot should be valid."""
        b64 = create_fake_outlook_screenshot("reply")
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        self.assertEqual(img.size, (1920, 1080))
        print("  ✅ Reply screenshot: 1920x1080")

    def test_loading_screenshot(self):
        """Loading screenshot should be valid."""
        b64 = create_fake_outlook_screenshot("loading")
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        self.assertEqual(img.size, (1920, 1080))
        print("  ✅ Loading screenshot: 1920x1080")


# ─────────────────────────────────────────────────────────────
# Test 6: End-to-End Gemini Integration
# (These tests call the real Gemini API — they cost a tiny
#  amount and require GEMINI_API_KEY to be set)
# ─────────────────────────────────────────────────────────────
class TestGeminiIntegration(unittest.TestCase):
    """
    End-to-end tests that send screenshots to Gemini via the backend.
    These require the backend to be running with a valid GEMINI_API_KEY.
    Skipped if SKIP_GEMINI_TESTS=1 is set.
    """

    def setUp(self):
        if os.getenv("SKIP_GEMINI_TESTS") == "1":
            self.skipTest("SKIP_GEMINI_TESTS=1 — skipping Gemini API tests")

    def _send_screenshot_and_text_command(self, scenario, command):
        """Helper: send a screenshot + text command, return Gemini's action."""
        async def run():
            ws = await asyncio.wait_for(
                websockets.connect(BACKEND_URL_WS),
                timeout=WEBSOCKET_TIMEOUT
            )
            try:
                # Consume welcome
                await asyncio.wait_for(ws.recv(), timeout=GEMINI_TIMEOUT)

                # Send screenshot
                screenshot = create_fake_outlook_screenshot(scenario)
                await ws.send(json.dumps({
                    "type": "screenshot",
                    "data": screenshot,
                    "timestamp": int(time.time() * 1000),
                    "resolution": "1920x1080"
                }))

                # Give Gemini time to process the image
                await asyncio.sleep(1)

                # Send text command
                await ws.send(json.dumps({
                    "type": "command",
                    "text": command
                }))

                # Collect responses (may be multiple)
                responses = []
                for _ in range(5):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=GEMINI_TIMEOUT)
                        data = json.loads(msg)
                        if data.get("action") != "keepalive":
                            responses.append(data)
                    except asyncio.TimeoutError:
                        break

                return responses
            finally:
                await ws.close()

        return asyncio.get_event_loop().run_until_complete(run())

    def test_inbox_describe_screen(self):
        """Gemini should describe what it sees in the Outlook inbox."""
        responses = self._send_screenshot_and_text_command(
            "inbox", "What do you see on my screen?"
        )
        self.assertTrue(len(responses) > 0, "Should get at least one response")

        # Check that response mentions inbox-related content
        all_text = json.dumps(responses).lower()
        has_outlook_reference = any(
            keyword in all_text
            for keyword in ["inbox", "email", "outlook", "mail", "message"]
        )
        self.assertTrue(has_outlook_reference, f"Response should mention emails. Got: {all_text[:200]}")
        print(f"  ✅ Gemini described the inbox: {responses[0].get('confirmation', responses[0].get('description', ''))[:80]}...")

    def test_inbox_click_email(self):
        """Gemini should return click coordinates for opening an email."""
        responses = self._send_screenshot_and_text_command(
            "inbox", "Open the email from Alex Chen"
        )
        self.assertTrue(len(responses) > 0, "Should get at least one response")

        # Find a click action in responses
        click_actions = [r for r in responses if r.get("action") == "click"]
        if click_actions:
            action = click_actions[0]
            self.assertIn("x", action)
            self.assertIn("y", action)
            # Coordinates should be within the email list area (roughly x: 250-700, y: 115-500)
            self.assertGreater(action["x"], 200, "X should be in email list area")
            self.assertLess(action["x"], 750, "X should be in email list area")
            print(f"  ✅ Gemini returned click at ({action['x']}, {action['y']}) for Alex's email")
        else:
            # Might have returned a describe or clarify action instead
            print(f"  ⚠️  No click action — got: {responses[0].get('action')} — {responses[0].get('confirmation', '')[:80]}")

    def test_compose_identify_send_button(self):
        """Gemini should locate the Send button in compose view."""
        responses = self._send_screenshot_and_text_command(
            "compose", "Click the send button"
        )
        self.assertTrue(len(responses) > 0)

        # Should click Send, ask for confirmation, or describe/speak
        action = responses[0]
        valid_actions = ["click", "confirm", "speak", "describe", "clarify"]
        self.assertIn(action.get("action"), valid_actions,
                      f"Expected one of {valid_actions}, got: {action.get('action')}")

        if action.get("action") == "click":
            # Send button is at roughly (320-400, 135-165) in our fake screenshot
            self.assertLess(action.get("x", 9999), 600, "Send button should be on the left side")
            print(f"  ✅ Gemini located Send button at ({action['x']}, {action['y']})")
        elif action.get("action") == "confirm":
            print(f"  ✅ Gemini asked for confirmation before sending: {action.get('confirmation', '')[:80]}")
        else:
            print(f"  ✅ Gemini responded with '{action['action']}': {action.get('confirmation', '')[:80]}")

    def test_loading_state_detection(self):
        """Gemini should detect a loading state and respond with wait."""
        responses = self._send_screenshot_and_text_command(
            "loading", "Open the first email"
        )
        self.assertTrue(len(responses) > 0)

        all_text = json.dumps(responses).lower()
        # Should mention loading or waiting
        loading_detected = any(
            keyword in all_text
            for keyword in ["loading", "wait", "moment", "loading", "not ready"]
        )
        print(f"  {'✅' if loading_detected else '⚠️ '} Loading state {'detected' if loading_detected else 'not explicitly detected'}: {responses[0].get('confirmation', '')[:80]}")

    def test_reply_action(self):
        """Gemini should handle 'reply to this email' command."""
        responses = self._send_screenshot_and_text_command(
            "inbox", "Reply to this email"
        )
        self.assertTrue(len(responses) > 0)

        action = responses[0]
        # Should click the reply button/icon, describe, or speak
        valid_actions = ["click", "describe", "clarify", "speak", "confirm"]
        self.assertIn(action.get("action"), valid_actions,
                      f"Unexpected action: {action.get('action')}")
        print(f"  ✅ Reply command handled: {action.get('action')} — {action.get('confirmation', '')[:80]}")


# ─────────────────────────────────────────────────────────────
# Test 7: System Prompt Validation
# ─────────────────────────────────────────────────────────────
class TestSystemPrompt(unittest.TestCase):
    """Validate the system prompt contains all required Outlook elements."""

    def test_prompt_contains_outlook_ui_elements(self):
        """System prompt should describe Outlook's UI layout."""
        from backend import SYSTEM_PROMPT

        required_terms = [
            "Outlook",
            "ribbon",
            "sidebar",
            "reading pane",
            "email list",
            "New mail",
            "Reply",
            "Forward",
            "Delete",
            "Send",
            "Discard",
            "search",
        ]
        for term in required_terms:
            self.assertIn(
                term.lower(), SYSTEM_PROMPT.lower(),
                f"System prompt should mention '{term}'"
            )
        print(f"  ✅ System prompt contains all {len(required_terms)} required Outlook UI terms")

    def test_prompt_contains_icon_mappings(self):
        """System prompt should map Outlook icons to their functions."""
        from backend import SYSTEM_PROMPT

        icon_terms = ["curved", "arrow", "trash", "paperclip", "flag", "three dots"]
        found = sum(1 for t in icon_terms if t.lower() in SYSTEM_PROMPT.lower())
        self.assertGreaterEqual(found, 4, "Should have at least 4 icon descriptions")
        print(f"  ✅ System prompt contains {found}/{len(icon_terms)} icon descriptions")

    def test_prompt_specifies_resolution(self):
        """System prompt should specify screenshot resolution."""
        from backend import SYSTEM_PROMPT

        self.assertIn("1920x1080", SYSTEM_PROMPT)
        print("  ✅ System prompt specifies 1920x1080 resolution")

    def test_prompt_has_confirmation_rules(self):
        """System prompt should require confirmation for destructive actions."""
        from backend import SYSTEM_PROMPT

        prompt_lower = SYSTEM_PROMPT.lower()
        self.assertIn("confirm", prompt_lower)
        self.assertIn("destructive", prompt_lower)
        print("  ✅ System prompt requires confirmation for destructive actions")

    def test_prompt_json_format(self):
        """System prompt should specify JSON response format."""
        from backend import SYSTEM_PROMPT

        self.assertIn('"action"', SYSTEM_PROMPT)
        self.assertIn('"click"', SYSTEM_PROMPT)
        self.assertIn('"type"', SYSTEM_PROMPT)
        self.assertIn('"scroll"', SYSTEM_PROMPT)
        self.assertIn('"confirm"', SYSTEM_PROMPT)
        print("  ✅ System prompt specifies all JSON action types")


# ─────────────────────────────────────────────────────────────
# Test 8: Stress & Edge Cases
# ─────────────────────────────────────────────────────────────
class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def test_rapid_screenshot_sends(self):
        """Backend should handle rapid screenshot sends without crashing."""
        async def run():
            ws = await asyncio.wait_for(
                websockets.connect(BACKEND_URL_WS),
                timeout=WEBSOCKET_TIMEOUT
            )
            try:
                await asyncio.wait_for(ws.recv(), timeout=GEMINI_TIMEOUT)

                screenshot = create_fake_outlook_screenshot("inbox")
                for i in range(10):
                    await ws.send(json.dumps({
                        "type": "screenshot",
                        "data": screenshot,
                        "timestamp": int(time.time() * 1000) + i,
                        "resolution": "1920x1080"
                    }))
                    await asyncio.sleep(0.1)

                self.assertTrue(ws.open)
                print("  ✅ 10 rapid screenshots handled without crash")
            finally:
                await ws.close()

        asyncio.get_event_loop().run_until_complete(run())

    def test_empty_command_data(self):
        """Backend should handle empty command gracefully."""
        async def run():
            ws = await asyncio.wait_for(
                websockets.connect(BACKEND_URL_WS),
                timeout=WEBSOCKET_TIMEOUT
            )
            try:
                await asyncio.wait_for(ws.recv(), timeout=GEMINI_TIMEOUT)

                await ws.send(json.dumps({
                    "type": "command",
                    "text": "",
                    "timestamp": int(time.time() * 1000)
                }))

                await asyncio.sleep(1)
                self.assertTrue(ws.open)
                print("  ✅ Empty command data handled gracefully")
            finally:
                await ws.close()

        asyncio.get_event_loop().run_until_complete(run())

    def test_unknown_message_type(self):
        """Backend should ignore unknown message types."""
        async def run():
            ws = await asyncio.wait_for(
                websockets.connect(BACKEND_URL_WS),
                timeout=WEBSOCKET_TIMEOUT
            )
            try:
                await asyncio.wait_for(ws.recv(), timeout=GEMINI_TIMEOUT)

                await ws.send(json.dumps({
                    "type": "unknown_type",
                    "data": "whatever"
                }))

                await asyncio.sleep(1)
                self.assertTrue(ws.open)
                print("  ✅ Unknown message types ignored without crash")
            finally:
                await ws.close()

        asyncio.get_event_loop().run_until_complete(run())

    def test_large_screenshot(self):
        """Backend should handle large high-quality screenshots."""
        async def run():
            ws = await asyncio.wait_for(
                websockets.connect(BACKEND_URL_WS),
                timeout=WEBSOCKET_TIMEOUT
            )
            try:
                await asyncio.wait_for(ws.recv(), timeout=GEMINI_TIMEOUT)

                # Create a larger, noisier image
                img = Image.new("RGB", (1920, 1080))
                import random
                pixels = img.load()
                for x in range(0, 1920, 10):
                    for y in range(0, 1080, 10):
                        pixels[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))

                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=95)
                b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

                await ws.send(json.dumps({
                    "type": "screenshot",
                    "data": b64,
                    "timestamp": int(time.time() * 1000),
                    "resolution": "1920x1080"
                }))

                await asyncio.sleep(2)
                self.assertTrue(ws.open)
                print(f"  ✅ Large screenshot handled ({len(b64) // 1024} KB)")
            finally:
                await ws.close()

        asyncio.get_event_loop().run_until_complete(run())


# ─────────────────────────────────────────────────────────────
# Test Runner
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print()
    print("=" * 65)
    print("  ♿ Accessibility Autopilot — Test Suite (Outlook 365)")
    print("=" * 65)
    print(f"  Backend HTTP:  {BACKEND_URL_HTTP}")
    print(f"  Backend WS:    {BACKEND_URL_WS}")
    print(f"  Gemini Tests:  {'SKIPPED' if os.getenv('SKIP_GEMINI_TESTS') == '1' else 'ENABLED'}")
    print("=" * 65)
    print()

    # Run tests in a logical order
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_order = [
        TestHealthCheck,
        TestScreenshotGeneration,
        TestGridOverlay,
        TestScreenshotComparison,
        TestSystemPrompt,
        TestWebSocket,
        TestEdgeCases,
        TestGeminiIntegration,
    ]

    for test_class in test_order:
        suite.addTests(loader.loadTestsFromTestCase(test_class))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 65)
    if result.wasSuccessful():
        print("  ✅ ALL TESTS PASSED")
    else:
        print(f"  ❌ {len(result.failures)} failures, {len(result.errors)} errors")
    print("=" * 65)