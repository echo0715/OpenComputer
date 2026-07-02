"""
Holo-3.1 agent — uses Hcompany's structured-output format via vLLM.

Docs: https://hub.hcompany.ai/quickstart

Env vars:
  OPENAI_BASE_URL   — vLLM endpoint base URL (e.g. http://nlpgpu06:8000/v1)
  OPENAI_API_KEY    — any non-empty string (vLLM doesn't validate)

History management
------------------
- Last `history_n` steps are kept as full conversation turns (with screenshots).
- Every `summary_interval` steps, completed steps are compacted into a one-line-
  per-step summary that lives in the system prompt. Only the tool_call action is
  kept; verbose "thought" text is discarded. This caps token growth over long runs.
"""

import base64
import json
import logging
import os
import time
from io import BytesIO
from typing import Dict, List, Optional, Tuple

from PIL import Image

from .base import BaseAgent

logger = logging.getLogger("agents.holo3")

MAX_RETRY_TIMES = 3

_STEP_SCHEMA = {
    "type": "object",
    "properties": {
        "note": {"type": "string"},
        "thought": {"type": "string"},
        "tool_call": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string"},
                # click_desktop / double_click_desktop / move_to_desktop / write_at_desktop
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "element": {"type": "string"},
                # click_desktop / mouse_down_desktop / mouse_up_desktop
                "button": {"type": "string"},         # "left" | "right" | "middle"
                # drag_and_drop
                "start_x": {"type": "integer"},
                "start_y": {"type": "integer"},
                "end_x": {"type": "integer"},
                "end_y": {"type": "integer"},
                # write_desktop / write_at_desktop / answer / update_plan
                "content": {"type": "string"},
                "text": {"type": "string"},           # alias for content
                # hotkey_desktop
                "keys": {"type": "array", "items": {"type": "string"}},
                # hold_and_tap_key_desktop
                "hold_key": {"type": "string"},
                "tap_key": {"type": "string"},
                # key_down_desktop / key_up_desktop
                "key": {"type": "string"},
                # scroll_desktop
                "direction": {"type": "string"},      # up | down | left | right
                "amount": {"type": "integer"},
                # wait_desktop
                "seconds": {"type": "number"},
                # answer / done
                "success": {"type": "boolean"},
            },
            "required": ["tool_name"],
        },
    },
    "required": ["thought", "tool_call"],
}

_SYSTEM_PROMPT = (
    "You are a computer use agent that controls a desktop GUI.\n"
    "At each step you receive a screenshot and output a structured action.\n"
    "All coordinates are integers in [0, 1000] (normalized to screen size).\n\n"
    "Available tools and their parameters:\n"
    "  click_desktop            — {tool_name, x, y, button}  button: \"left\"(default) or \"right\"\n"
    "  double_click_desktop     — {tool_name, x, y}\n"
    "  move_to_desktop          — {tool_name, x, y}\n"
    "  drag_and_drop            — {tool_name, start_x, start_y, end_x, end_y}\n"
    "  mouse_down_desktop       — {tool_name, x, y, button}\n"
    "  mouse_up_desktop         — {tool_name, x, y, button}\n"
    "  write_desktop            — {tool_name, content}\n"
    "  write_at_desktop         — {tool_name, x, y, content}\n"
    "  hotkey_desktop           — {tool_name, keys}  (e.g. keys: [\"ctrl\",\"s\"])\n"
    "  hold_and_tap_key_desktop — {tool_name, hold_key, tap_key}\n"
    "  key_down_desktop         — {tool_name, key}\n"
    "  key_up_desktop           — {tool_name, key}\n"
    "  scroll_desktop           — {tool_name, x, y, direction, amount}  direction: up/down/left/right\n"
    "  wait_desktop             — {tool_name, seconds}\n"
    "  answer                   — {tool_name, content}\n"
    "  update_plan              — {tool_name, content}\n\n"
    "Think step by step, then output the best action."
)


class Holo3Agent(BaseAgent):
    """
    Agent powered by Hcompany Holo-3.1 served via vLLM OpenAI-compatible endpoint.

    Every `summary_interval` completed steps are compacted into a one-line-per-step
    summary (no thoughts) stored in the system prompt. Only the most recent
    `history_n` steps are kept as full conversation turns with screenshots.
    """

    def __init__(
        self,
        model: str = "holo-3.1",
        history_n: int = 2,
        summary_interval: int = 20,
        **kwargs,
    ):
        kwargs.setdefault("temperature", 0.8)
        kwargs.setdefault("max_tokens", 4096)
        super().__init__(model=model, **kwargs)
        self.history_n = history_n
        self.summary_interval = summary_interval

        # Full history (all steps, 0-indexed).
        self._screenshot_b64s: List[str] = []
        self._responses: List[str] = []

        # Summary state.
        # Each entry: (start, end, text) covering steps [start, end) (0-indexed).
        self._summary_blocks: List[Tuple[int, int, str]] = []
        # How many steps have been folded into summaries.
        self._summary_coverage: int = 0

    def reset(self) -> None:
        self._screenshot_b64s = []
        self._responses = []
        self._summary_blocks = []
        self._summary_coverage = 0

    # ── Main predict loop ────────────────────────────────────────────────

    def predict(self, instruction: str, obs: Dict) -> Tuple[str, List[str]]:
        screenshot_bytes = obs["screenshot"]

        img = Image.open(BytesIO(screenshot_bytes))
        orig_w, orig_h = img.size

        current_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        # Try with decreasing history if context limit is exceeded.
        response_text = ""
        for effective_n in range(self.history_n, 0, -1):
            messages = self._build_messages(instruction, current_b64, effective_n)
            response_text, context_exceeded = self._call_api(messages)
            if not context_exceeded:
                break
            logger.warning(
                f"Context limit exceeded with {effective_n} image(s); "
                f"retrying with {effective_n - 1}"
            )

        self.last_raw_response = {"content": response_text}

        # Append AFTER building messages so this step's data doesn't leak in.
        self._screenshot_b64s.append(current_b64)
        self._responses.append(response_text)

        # Check whether to summarize the latest completed batch.
        n_steps = len(self._responses)
        unsummarized = n_steps - self._summary_coverage
        if unsummarized >= self.summary_interval:
            start = self._summary_coverage
            end = start + self.summary_interval
            block = self._make_summary_block(start, end)
            self._summary_blocks.append((start, end, block))
            self._summary_coverage = end
            logger.info(f"Summarized steps {start + 1}–{end}")

        try:
            step = json.loads(response_text or "{}")
        except json.JSONDecodeError:
            logger.error(f"Failed to parse Holo3 JSON: {response_text!r}")
            step = {}

        reasoning = step.get("thought", "")
        code = self._step_to_code(step, orig_w, orig_h)
        return reasoning, code

    # ── Message construction ─────────────────────────────────────────────

    def _build_messages(
        self, instruction: str, current_b64: str, effective_history_n: int
    ) -> List[Dict]:
        """
        Build the full message list for one API call.

        System prompt = base instructions + task + all summary blocks (if any).
        Conversation turns = unsummarized steps only, with images for the last
        `effective_history_n` of them.
        """
        # ── System prompt ──────────────────────────────────────────────
        sys_parts = [_SYSTEM_PROMPT, f"\nTask: {instruction}"]
        if self._summary_blocks:
            history_lines = ["[Completed action history]"]
            for blk_start, blk_end, blk_text in self._summary_blocks:
                history_lines.append(blk_text)
            sys_parts.append("\n".join(history_lines))
        messages: List[Dict] = [{"role": "system", "content": "\n\n".join(sys_parts)}]

        # ── Unsummarized conversation turns ────────────────────────────
        prev_b64s = self._screenshot_b64s[self._summary_coverage:]
        prev_responses = self._responses[self._summary_coverage:]

        # Include unsummarized history + current step.
        all_b64s = prev_b64s + [current_b64]
        n = len(all_b64s)
        image_start = max(0, n - effective_history_n)

        for i in range(n):
            is_current = i == n - 1
            show_image = i >= image_start

            if show_image:
                user_content = [
                    {"type": "text", "text": "<observation>\n"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{all_b64s[i]}"},
                    },
                    {"type": "text", "text": "\n</observation>"},
                ]
            else:
                user_content = [
                    {"type": "text", "text": "<observation>\n[screenshot omitted]\n</observation>"},
                ]

            messages.append({"role": "user", "content": user_content})

            if not is_current and i < len(prev_responses):
                messages.append({"role": "assistant", "content": prev_responses[i]})

        return messages

    # ── Summarisation ────────────────────────────────────────────────────

    def _make_summary_block(self, start: int, end: int) -> str:
        """Summarize steps [start, end) via LLM; fall back to rule-based on failure."""
        try:
            return self._make_summary_block_llm(start, end)
        except Exception as exc:
            logger.warning(f"LLM summarization failed ({exc}); using rule-based fallback")
            return self._make_summary_block_rules(start, end)

    def _make_summary_block_llm(self, start: int, end: int) -> str:
        """Call the model to produce a one-sentence summary per step."""
        import openai
        import re

        # Build the summarization prompt.
        step_lines = []
        for i in range(start, end):
            try:
                step = json.loads(self._responses[i] or "{}")
                thought = (step.get("thought") or "").strip()
                tool_call = json.dumps(step.get("tool_call") or {})
                step_lines.append(
                    f"Step {i + 1}:\n"
                    f"  Observation & reasoning: {thought}\n"
                    f"  Action taken: {tool_call}"
                )
            except Exception:
                step_lines.append(f"Step {i + 1}: (no data)")

        prompt = (
            "You are summarizing a GUI agent's action history.\n"
            "For each step below, write 1–2 sentences that capture:\n"
            "  1. What was observed on screen and why the action was chosen.\n"
            "  2. What action was taken.\n"
            "Be concise (≤ 30 words per step). Do not include any preamble.\n"
            "Format your entire response as:\n"
            "Step N: <1–2 sentences>\n\n"
            + "\n\n".join(step_lines)
        )

        base_url = os.environ.get("OPENAI_BASE_URL", "http://localhost:8000/v1")
        api_key = os.environ.get("OPENAI_API_KEY", "sk-dummy")
        client = openai.OpenAI(base_url=base_url, api_key=api_key, timeout=120)

        resp = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.0,
        )
        raw = resp.choices[0].message.content or ""

        # Strip any <think>…</think> block the model may emit.
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        # Parse "Step N: <text>" lines.
        summaries: Dict[int, str] = {}
        for line in raw.splitlines():
            m = re.match(r"Step\s+(\d+)\s*:\s*(.+)", line.strip(), re.IGNORECASE)
            if m:
                summaries[int(m.group(1))] = m.group(2).strip()

        # Build the block; fall back per-step to rule-based if a line is missing.
        lines = [f"Steps {start + 1}–{end}:"]
        for i in range(start, end):
            step_num = i + 1
            if step_num in summaries:
                desc = summaries[step_num]
            else:
                try:
                    tool = json.loads(self._responses[i] or "{}").get("tool_call") or {}
                except Exception:
                    tool = {}
                desc = self._describe_tool(tool)
            lines.append(f"  Step {step_num}: {desc}")

        return "\n".join(lines)

    def _make_summary_block_rules(self, start: int, end: int) -> str:
        """Rule-based fallback: format tool_call JSON into one sentence per step."""
        lines = [f"Steps {start + 1}–{end}:"]
        for i in range(start, end):
            try:
                step = json.loads(self._responses[i] or "{}")
                desc = self._describe_tool(step.get("tool_call") or {})
            except Exception:
                desc = "(action performed)"
            lines.append(f"  Step {i + 1}: {desc}")
        return "\n".join(lines)

    @staticmethod
    def _describe_tool(tool: Dict) -> str:
        """Rule-based one-sentence description of a tool_call (used as fallback)."""
        name = (tool.get("tool_name") or "").lower().strip()
        x, y = tool.get("x"), tool.get("y")
        coord = f" at ({x}, {y})" if x is not None and y is not None else ""
        elem = tool.get("element", "")
        elem_str = f" on '{elem}'" if elem else ""

        if name == "click":
            return f"Clicked{elem_str}{coord}."
        if name == "double_click":
            return f"Double-clicked{elem_str}{coord}."
        if name == "right_click":
            return f"Right-clicked{elem_str}{coord}."
        if name in ("write", "type"):
            content = tool.get("content") or ""
            short = (content[:60] + "…") if len(content) > 60 else content
            suffix = " and pressed Enter" if tool.get("press_enter") else ""
            return f"Typed '{short}'{suffix}."
        if name == "key":
            keys = tool.get("keys") or []
            return f"Pressed {'+'.join(str(k) for k in keys)}."
        if name in ("drag", "left_click_drag"):
            sx = tool.get("start_x") or tool.get("startX") or tool.get("x")
            sy = tool.get("start_y") or tool.get("startY") or tool.get("y")
            ex = tool.get("end_x") or tool.get("endX") or tool.get("target_x")
            ey = tool.get("end_y") or tool.get("endY") or tool.get("target_y")
            return f"Dragged from ({sx}, {sy}) to ({ex}, {ey})."
        if name == "scroll":
            direction = tool.get("direction") or "down"
            amount = tool.get("amount") or 3
            return f"Scrolled {direction} by {amount}{coord}."
        if name in ("answer", "done", "finish", "complete", "terminate", "success"):
            content = tool.get("content", "")
            success = tool.get("success", True)
            if content:
                return f"Completed task: {(content[:80] + '…') if len(content) > 80 else content}."
            return f"Marked task {'complete' if success else 'failed'}."
        if name in ("fail", "failure"):
            return "Marked task failed."
        if name == "wait":
            secs = tool.get("time") or tool.get("seconds") or 2
            return f"Waited {secs} seconds."
        return f"Performed action '{name}'."

    # ── API call ─────────────────────────────────────────────────────────

    @staticmethod
    def _is_context_length_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        return "context length" in msg or "input length" in msg or "maximum context" in msg

    def _call_api(self, messages: List[Dict]) -> Tuple[str, bool]:
        """
        Returns (response_text, context_exceeded).
        context_exceeded=True tells the caller to rebuild with fewer images.
        """
        import openai

        base_url = os.environ.get("OPENAI_BASE_URL", "http://localhost:8000/v1")
        api_key = os.environ.get("OPENAI_API_KEY", "sk-dummy")
        client = openai.OpenAI(base_url=base_url, api_key=api_key, timeout=600)

        for attempt in range(MAX_RETRY_TIMES):
            try:
                resp = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature if self.temperature is not None else 0.8,
                    extra_body={
                        "structured_outputs": {"json": _STEP_SCHEMA},
                        "chat_template_kwargs": {"enable_thinking": True},
                    },
                )
                return resp.choices[0].message.content or "", False
            except Exception as exc:
                if self._is_context_length_error(exc):
                    logger.warning(f"Context length exceeded: {exc}")
                    return "", True
                logger.error(f"Holo3 API error (attempt {attempt + 1}): {exc}")
                if attempt < MAX_RETRY_TIMES - 1:
                    time.sleep(5)
        return "", False

    # ── Action parsing ───────────────────────────────────────────────────

    def _step_to_code(self, step: Dict, orig_w: int, orig_h: int) -> List[str]:
        """Convert a parsed step dict into pyautogui action code strings."""
        tool = step.get("tool_call") or {}
        tool_name = (tool.get("tool_name") or "").lower().strip()

        def scale(x, y) -> Tuple[int, int]:
            return int(x / 1000 * orig_w), int(y / 1000 * orig_h)

        def get_xy() -> Optional[Tuple[int, int]]:
            x, y = tool.get("x"), tool.get("y")
            if x is None or y is None:
                return None
            return scale(x, y)

        code: List[str] = []

        if tool_name in ("click_desktop", "click"):
            xy = get_xy()
            if xy:
                button = (tool.get("button") or "left").lower()
                if button == "right":
                    code.append(f"pyautogui.rightClick({xy[0]}, {xy[1]})")
                else:
                    code.append(f"pyautogui.click({xy[0]}, {xy[1]})")

        elif tool_name == "right_click":
            xy = get_xy()
            if xy:
                code.append(f"pyautogui.rightClick({xy[0]}, {xy[1]})")

        elif tool_name in ("double_click_desktop", "double_click"):
            xy = get_xy()
            if xy:
                code.append(f"pyautogui.doubleClick({xy[0]}, {xy[1]})")

        elif tool_name == "move_to_desktop":
            xy = get_xy()
            if xy:
                code.append(f"pyautogui.moveTo({xy[0]}, {xy[1]})")

        elif tool_name in ("write_desktop", "write", "type"):
            content = tool.get("content") or tool.get("text") or ""
            press_enter = tool.get("press_enter", False)
            code.append(
                f"pyperclip.copy({json.dumps(content)}); "
                f"pyautogui.hotkey('ctrl', 'v'); time.sleep(0.1)"
            )
            if press_enter:
                code.append("pyautogui.press('enter')")

        elif tool_name == "write_at_desktop":
            xy = get_xy()
            content = tool.get("content") or tool.get("text") or ""
            if xy:
                code.append(f"pyautogui.click({xy[0]}, {xy[1]}); time.sleep(0.2)")
            code.append(
                f"pyperclip.copy({json.dumps(content)}); "
                f"pyautogui.hotkey('ctrl', 'v'); time.sleep(0.1)"
            )

        elif tool_name in ("hotkey_desktop", "key"):
            keys = tool.get("keys") or []
            if isinstance(keys, str):
                keys = [keys]
            if len(keys) > 1:
                keys_str = ", ".join(json.dumps(k) for k in keys)
                code.append(f"pyautogui.hotkey({keys_str})")
            elif keys:
                code.append(f"pyautogui.press({json.dumps(keys[0])})")

        elif tool_name == "hold_and_tap_key_desktop":
            hold = tool.get("hold_key") or ""
            tap = tool.get("tap_key") or ""
            if hold and tap:
                code.append(f"pyautogui.keyDown({json.dumps(hold)})")
                code.append(f"pyautogui.press({json.dumps(tap)})")
                code.append(f"pyautogui.keyUp({json.dumps(hold)})")

        elif tool_name == "key_down_desktop":
            key = tool.get("key") or ""
            if key:
                code.append(f"pyautogui.keyDown({json.dumps(key)})")

        elif tool_name == "key_up_desktop":
            key = tool.get("key") or ""
            if key:
                code.append(f"pyautogui.keyUp({json.dumps(key)})")

        elif tool_name in ("drag_and_drop", "drag", "left_click_drag"):
            sx = tool.get("start_x") or tool.get("startX")
            sy = tool.get("start_y") or tool.get("startY")
            ex = tool.get("end_x") or tool.get("endX") or tool.get("target_x")
            ey = tool.get("end_y") or tool.get("endY") or tool.get("target_y")
            if sx is not None and sy is not None and ex is not None and ey is not None:
                sx, sy = scale(sx, sy)
                ex, ey = scale(ex, ey)
                code.append(f"pyautogui.moveTo({sx}, {sy})")
                code.append(f"pyautogui.dragTo({ex}, {ey}, duration=0.5)")
            else:
                logger.warning(f"drag_and_drop missing coordinates: {tool}")

        elif tool_name == "mouse_down_desktop":
            xy = get_xy()
            button = (tool.get("button") or "left").lower()
            if xy:
                code.append(f"pyautogui.mouseDown({xy[0]}, {xy[1]}, button={json.dumps(button)})")

        elif tool_name == "mouse_up_desktop":
            xy = get_xy()
            button = (tool.get("button") or "left").lower()
            if xy:
                code.append(f"pyautogui.mouseUp({xy[0]}, {xy[1]}, button={json.dumps(button)})")

        elif tool_name in ("scroll_desktop", "scroll"):
            xy = get_xy()
            direction = (tool.get("direction") or "down").lower()
            amount = int(tool.get("amount") or 3)
            pixels = amount if direction in ("up", "right") else -amount
            if xy:
                code.append(f"pyautogui.moveTo({xy[0]}, {xy[1]})")
            code.append(f"pyautogui.scroll({pixels})")

        elif tool_name in ("wait_desktop", "wait"):
            secs = tool.get("seconds") or tool.get("time") or 2
            code.append(f"time.sleep({secs})")

        elif tool_name == "update_plan":
            pass  # planning only, no GUI action — continue loop

        elif tool_name in ("answer", "done", "finish", "complete", "terminate", "success"):
            success = tool.get("success", True)
            code.append("DONE" if success else "FAIL")

        elif tool_name in ("fail", "failure"):
            code.append("FAIL")

        else:
            logger.warning(f"Unknown Holo3 tool_name: {tool_name!r} — emitting WAIT")

        return code if code else ["WAIT"]
