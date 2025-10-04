"""Core automation engine for the job application bot."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping

from jinja2 import Environment
from playwright.sync_api import Browser, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from .config import AutomationConfig, JobConfig

LOGGER = logging.getLogger("job_bot")
if not LOGGER.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)


class JobAutomationError(RuntimeError):
    """Raised when automation fails for a job."""


class JobApplicationBot:
    """Execute job application flows using Playwright."""

    def __init__(
        self,
        config: AutomationConfig,
        *,
        headless: bool | None = None,
    ) -> None:
        self._config = config
        self._headless_override = headless
        self._jinja_env = Environment(autoescape=False)
        self._jinja_env.globals.update(
            path=self._path_helper,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self, *, dry_run: bool = False) -> None:
        """Run every job listed in the configuration."""

        context = self._build_template_context()

        if dry_run:
            self._dry_run(context)
            return

        browser_kwargs: Dict[str, Any] = {
            "headless": self._headless_override
            if self._headless_override is not None
            else self._config.browser.headless,
        }
        if self._config.browser.slow_mo is not None:
            browser_kwargs["slow_mo"] = self._config.browser.slow_mo

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**browser_kwargs)
            try:
                for job in self._config.jobs:
                    LOGGER.info("Running job '%s' (%s)", job.name, job.url)
                    try:
                        with self._job_context(browser) as page:
                            self._execute_job(job, page, context)
                    except JobAutomationError:
                        raise
                    except Exception as exc:  # pragma: no cover - defensive
                        raise JobAutomationError(
                            f"Job '{job.name}' failed with unexpected error"
                        ) from exc
            finally:
                browser.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_template_context(self) -> Dict[str, Any]:
        raw_profile = dict(self._config.profile)
        preliminary_context = {"profile": raw_profile}
        rendered_profile = self._render(raw_profile, preliminary_context)
        return {"profile": rendered_profile}

    def _path_helper(self, relative: str) -> str:
        path = (self._config.base_dir / relative).expanduser().resolve()
        return str(path)

    def _render(self, value: Any, context: Mapping[str, Any]) -> Any:
        if isinstance(value, str):
            template = self._jinja_env.from_string(value)
            return template.render(**context)
        if isinstance(value, Mapping):
            return {k: self._render(v, context) for k, v in value.items()}
        if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
            return [self._render(item, context) for item in value]
        return value

    def _dry_run(self, context: Mapping[str, Any]) -> None:
        for job in self._config.jobs:
            LOGGER.info("[dry-run] Job '%s' -> %s", job.name, job.url)
            job_context = {**context, "job": asdict(job)}
            for index, step in enumerate(job.steps, start=1):
                rendered = self._render({"action": step.action, **step.options}, job_context)
                LOGGER.info("  Step %02d: %s", index, rendered)

    @contextmanager
    def _job_context(self, browser: Browser) -> Iterable[Page]:
        kwargs = {}
        if self._config.browser.locale:
            kwargs["locale"] = self._config.browser.locale
        context = browser.new_context(**kwargs)
        try:
            page = context.new_page()
            yield page
        finally:
            context.close()

    def _execute_job(
        self,
        job: JobConfig,
        page: Page,
        global_context: Mapping[str, Any],
    ) -> None:
        job_context = {**global_context, "job": {"name": job.name, **job.metadata}}
        timeout_ms = self._config.browser.timeout_ms

        self._goto(page, job.url, timeout_ms)

        for index, step in enumerate(job.steps, start=1):
            rendered_step = self._render({"action": step.action, **step.options}, job_context)
            action = rendered_step.pop("action")
            LOGGER.info("  step %02d -> %s", index, action)
            handler = ACTION_HANDLERS.get(action)
            if not handler:
                raise JobAutomationError(f"Unsupported action '{action}'")
            try:
                handler(page, rendered_step, timeout_ms, self)
            except PlaywrightTimeoutError as exc:
                raise JobAutomationError(
                    f"Timed out waiting for selector during step {index} ({action})"
                ) from exc

    def _goto(self, page: Page, url: str, timeout_ms: int) -> None:
        LOGGER.info("  navigating to %s", url)
        page.goto(url, wait_until="load", timeout=timeout_ms)


# ----------------------------------------------------------------------
# Action handlers
# ----------------------------------------------------------------------


def _require_selector(step: MutableMapping[str, Any]) -> str:
    selector = step.get("selector")
    if not selector:
        raise JobAutomationError("Step requires a 'selector'")
    return str(selector)


def _ensure_files(bot: JobApplicationBot, value: Any) -> List[str]:
    if isinstance(value, (list, tuple)):
        files = [str(v) for v in value]
    else:
        files = [str(value)]
    return [bot._path_helper(path) for path in files]


def handle_fill(page: Page, step: MutableMapping[str, Any], timeout_ms: int, bot: JobApplicationBot) -> None:
    selector = _require_selector(step)
    if "value" not in step:
        raise JobAutomationError("Fill action requires a 'value'")
    value = step.get("value")
    page.fill(selector, str(value), timeout=timeout_ms)


def handle_type(page: Page, step: MutableMapping[str, Any], timeout_ms: int, bot: JobApplicationBot) -> None:
    selector = _require_selector(step)
    value = step.get("value", "")
    delay = step.get("delay")
    kwargs = {"timeout": timeout_ms}
    if delay is not None:
        kwargs["delay"] = int(delay)
    page.type(selector, str(value), **kwargs)


def handle_click(page: Page, step: MutableMapping[str, Any], timeout_ms: int, bot: JobApplicationBot) -> None:
    selector = _require_selector(step)
    kwargs = {"timeout": timeout_ms}
    if "button" in step:
        kwargs["button"] = str(step["button"])
    if "click_count" in step:
        kwargs["click_count"] = int(step["click_count"])
    if "delay" in step:
        kwargs["delay"] = int(step["delay"])
    page.click(selector, **kwargs)


def handle_check(page: Page, step: MutableMapping[str, Any], timeout_ms: int, bot: JobApplicationBot) -> None:
    selector = _require_selector(step)
    if step.get("checked", True):
        page.check(selector, timeout=timeout_ms)
    else:
        page.uncheck(selector, timeout=timeout_ms)


def handle_select(page: Page, step: MutableMapping[str, Any], timeout_ms: int, bot: JobApplicationBot) -> None:
    selector = _require_selector(step)
    value = step.get("value")
    values = step.get("values")
    if value is None and values is None:
        raise JobAutomationError("Select action requires 'value' or 'values'")
    kwargs: Dict[str, Any] = {"timeout": timeout_ms}
    if value is not None:
        kwargs["value"] = str(value)
    if values is not None:
        if isinstance(values, Iterable) and not isinstance(values, str):
            kwargs["values"] = [str(v) for v in values]
        else:
            kwargs["values"] = [str(values)]
    page.select_option(selector, **kwargs)


def handle_upload(page: Page, step: MutableMapping[str, Any], timeout_ms: int, bot: JobApplicationBot) -> None:
    selector = _require_selector(step)
    if "files" not in step:
        raise JobAutomationError("Upload action requires 'files'")
    files = _ensure_files(bot, step.get("files"))
    page.set_input_files(selector, files, timeout=timeout_ms)


def handle_wait(page: Page, step: MutableMapping[str, Any], timeout_ms: int, bot: JobApplicationBot) -> None:
    duration = int(step.get("duration_ms") or step.get("ms") or 1000)
    page.wait_for_timeout(duration)


def handle_wait_for_selector(page: Page, step: MutableMapping[str, Any], timeout_ms: int, bot: JobApplicationBot) -> None:
    selector = _require_selector(step)
    state = step.get("state")
    kwargs = {"timeout": timeout_ms}
    if state:
        kwargs["state"] = str(state)
    page.wait_for_selector(selector, **kwargs)


def handle_assert_text(page: Page, step: MutableMapping[str, Any], timeout_ms: int, bot: JobApplicationBot) -> None:
    selector = step.get("selector")
    text = step.get("text")
    if text is None:
        raise JobAutomationError("assert_text requires 'text'")
    if selector:
        locator = page.locator(str(selector))
        locator.wait_for(state="visible", timeout=timeout_ms)
        content = locator.inner_text()
    else:
        content = page.content()
    if str(text) not in content:
        raise JobAutomationError(
            f"assert_text failed to find '{text}' in the page content"
        )


def handle_press(page: Page, step: MutableMapping[str, Any], timeout_ms: int, bot: JobApplicationBot) -> None:
    selector = _require_selector(step)
    keys = step.get("keys") or step.get("key")
    if not keys:
        raise JobAutomationError("press requires 'keys' or 'key'")
    page.press(selector, str(keys), timeout=timeout_ms)


def handle_hover(page: Page, step: MutableMapping[str, Any], timeout_ms: int, bot: JobApplicationBot) -> None:
    selector = _require_selector(step)
    page.hover(selector, timeout=timeout_ms)


def handle_goto(page: Page, step: MutableMapping[str, Any], timeout_ms: int, bot: JobApplicationBot) -> None:
    url = step.get("url")
    if not url:
        raise JobAutomationError("goto action requires 'url'")
    wait_until = str(step.get("wait_until", "load"))
    page.goto(str(url), wait_until=wait_until, timeout=timeout_ms)


ACTION_HANDLERS = {
    "goto": handle_goto,
    "fill": handle_fill,
    "type": handle_type,
    "click": handle_click,
    "check": handle_check,
    "select": handle_select,
    "upload": handle_upload,
    "wait": handle_wait,
    "wait_for_selector": handle_wait_for_selector,
    "assert_text": handle_assert_text,
    "press": handle_press,
    "hover": handle_hover,
}

__all__ = ["JobApplicationBot", "JobAutomationError", "ACTION_HANDLERS"]
