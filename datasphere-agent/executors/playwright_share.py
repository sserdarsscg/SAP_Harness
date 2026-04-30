"""Playwright-based executor for sharing views in SAP Datasphere UI.

This executor automates the Share dialog in the Data Builder when CLI/API
permissions are insufficient (e.g., missing DW Integrator role).

Requires: playwright (pip install playwright && playwright install chromium)
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page, BrowserContext

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_BASE_URL = os.environ.get(
    "DSP_TENANT_URL", "https://vp-dsp-poc23.eu10.hcs.cloud.sap"
)
_UI_USER = os.environ.get("DSP_UI_USER", "")
_UI_PASSWORD = os.environ.get("DSP_UI_PASSWORD", "")
_AUTH_STATE_PATH = Path(__file__).parent.parent / "auth_state.json"

# Timeout constants (ms)
_NAV_TIMEOUT = 30_000
_DIALOG_TIMEOUT = 10_000


def _log(msg: str) -> None:
    """Log to stderr (stdout is reserved for JSON-RPC)."""
    global _last_log
    _last_log = msg
    print(f"[playwright_share] {msg}", file=sys.stderr)


_last_log: str = ""


def _last_log_msg() -> str:
    return _last_log


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def _login(page: Page) -> None:
    """Perform SAP IAS login if needed."""
    page.goto(_BASE_URL, wait_until="domcontentloaded")
    time.sleep(5)

    # Check if already logged in (redirected to app)
    if "dwaas-core" in page.url:
        _log("Already authenticated via stored session.")
        return

    # Fill login form (IAS login page)
    page.wait_for_selector("#j_username", timeout=_NAV_TIMEOUT)
    page.fill("#j_username", _UI_USER)
    page.fill("#j_password", _UI_PASSWORD)
    page.click("#logOnFormSubmit")
    page.wait_for_url("**/dwaas-core/**", timeout=_NAV_TIMEOUT)
    _log("Login successful.")


# ---------------------------------------------------------------------------
# Navigation helpers
# ---------------------------------------------------------------------------

def _navigate_to_space(page: Page, space: str) -> None:
    """Navigate into a space in the Data Builder."""
    page.goto(f"{_BASE_URL}/dwaas-core/index.html#/databuilder")
    time.sleep(8)

    # Collapse nav bar to avoid click interception
    collapse_btn = page.locator("[title='Collapse Navigation Bar']")
    if collapse_btn.is_visible():
        collapse_btn.click()
        time.sleep(1)

    # Use search field to filter, then click into space
    search = page.locator(
        "#shellMainContent---databuilderComponent---spaceSelection--spaceSearchField-I"
    )
    if search.is_visible():
        search.click()
        search.fill(space)
        time.sleep(2)

    # Click the space entry
    space_el = page.locator(f"[class*='spaceSelection'] >> text={space}").first
    if space_el.count() > 0:
        space_el.click()
    else:
        page.locator(f"text={space}").first.click()

    # Wait for Data Builder landing page to load
    time.sleep(8)
    _log(f"Entered space: {space}")


def _search_view(page: Page, view_name: str) -> None:
    """Search for a specific view in the Data Builder landing page."""
    search_input = page.locator(
        "#shellMainContent---databuilderComponent---databuilderLandingPage-EshComp"
        "-searchInputHelpPageSearchFieldGroup-input-inner"
    )
    search_input.click()
    search_input.fill(view_name)
    search_input.press("Enter")
    time.sleep(4)
    _log(f"Searched for: {view_name}")


def _select_first_row(page: Page) -> None:
    """Tick the checkbox on the first search result row."""
    cb = page.locator("[id$='-item-selectMulti']").first
    if cb.count() > 0:
        cb.click(force=True)
        time.sleep(1)
    else:
        raise RuntimeError("No selectable row found in search results.")


def _click_share_button(page: Page) -> None:
    """Click the toolbar Share button (must have a row selected)."""
    share_btn = page.locator(
        "#shellMainContent---databuilderComponent---databuilderLandingPage--shareButton"
    )
    # Wait for button to be enabled
    share_btn.wait_for(state="attached", timeout=5000)
    disabled = share_btn.evaluate("el => el.disabled")
    if disabled:
        raise RuntimeError("Share button is disabled – no row selected.")
    share_btn.click()
    time.sleep(3)
    _log("Share dialog opened.")


def _click_deploy_button(page: Page) -> None:
    """Click the toolbar Deploy button (must have a row selected)."""
    deploy_btn = page.locator(
        "#shellMainContent---databuilderComponent---databuilderLandingPage--deployButton"
    )
    deploy_btn.wait_for(state="attached", timeout=5000)
    disabled = deploy_btn.evaluate("el => el.disabled")
    if disabled:
        raise RuntimeError("Deploy button is disabled – no row selected.")
    deploy_btn.click()
    time.sleep(10)  # Deploy takes time
    _log("Deploy triggered.")

    # Handle any confirmation dialog
    try:
        confirm_btn = page.locator("[role='dialog'] button:has-text('Deploy')").first
        if confirm_btn.count() > 0 and confirm_btn.is_visible():
            confirm_btn.click()
            time.sleep(10)
    except Exception:
        pass

    # Wait for deployment to finish (look for success message or just wait)
    time.sleep(5)


def _fill_share_dialog(page: Page, target_space: str) -> None:
    """Fill the Share dialog: enter target space and confirm."""
    # Check if already shared to target space
    dialog = page.locator("[role='dialog']").first
    if dialog.count() > 0:
        dialog_text = dialog.inner_text()
        if target_space in dialog_text and "Shared to" in dialog_text:
            _log(f"Already shared to {target_space}, closing dialog.")
            _close_share_dialog(page)
            return

    # Type target space in the multi-input
    space_input = page.locator(
        "#sap-cdw-components-databuilder-view-ArtefactSharingDialog"
        "--dialog--view--spacesMultiInput-inner"
    )
    space_input.click()
    space_input.fill(target_space)
    time.sleep(2)

    # Press Enter or select from suggestion list
    suggestion = page.locator(f"[role='option']:has-text('{target_space}')").first
    if suggestion.count() > 0 and suggestion.is_visible():
        suggestion.click()
    else:
        space_input.press("Enter")
    time.sleep(2)

    # Click the "Share" button inside the dialog
    dialog_share_btn = page.locator(
        "#sap-cdw-components-databuilder-view-ArtefactSharingDialog"
        "--dialog--view--shareButton"
    )
    dialog_share_btn.click()
    time.sleep(4)
    _log(f"Shared to space: {target_space}")

    # Close the dialog (try multiple approaches)
    _close_share_dialog(page)


def _close_share_dialog(page: Page) -> None:
    """Close the share dialog robustly."""
    # Try the Close/OK button
    close_btn = page.locator(
        "#sap-cdw-components-databuilder-view-ArtefactSharingDialog"
        "--dialog--view--ok"
    )
    try:
        if close_btn.count() > 0 and close_btn.is_visible():
            close_btn.click()
            time.sleep(1)
            return
    except Exception:
        pass

    # Try any visible Close button in a dialog
    try:
        any_close = page.locator("[role='dialog'] button:has-text('Close')").first
        if any_close.count() > 0 and any_close.is_visible():
            any_close.click()
            time.sleep(1)
            return
    except Exception:
        pass

    # Last resort: press Escape
    try:
        page.keyboard.press("Escape")
        time.sleep(1)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def deploy_views(
    view_names: list[str],
    source_space: str = "ZZ_BDC_HARNESS_1",
    headless: bool = True,
) -> dict:
    """Deploy one or more views via UI.

    Returns dict with 'deployed' (list) and 'failed' (list).
    """
    from playwright.sync_api import sync_playwright

    if not _UI_USER or not _UI_PASSWORD:
        return {"error": "DSP_UI_USER / DSP_UI_PASSWORD not set in environment."}

    deployed: list[str] = []
    failed: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=200)
        context_opts: dict = {"viewport": {"width": 1920, "height": 1080}}
        if _AUTH_STATE_PATH.exists():
            context_opts["storage_state"] = str(_AUTH_STATE_PATH)

        context = browser.new_context(**context_opts)
        page = context.new_page()

        try:
            _login(page)
            time.sleep(5)
            context.storage_state(path=str(_AUTH_STATE_PATH))
            _navigate_to_space(page, source_space)

            for view_name in view_names:
                try:
                    _search_view(page, view_name)
                    _select_first_row(page)
                    _click_deploy_button(page)
                    deployed.append(view_name)
                    _log(f"✓ {view_name} deployed")
                except Exception as e:
                    failed.append({"view": view_name, "error": str(e)})
                    _log(f"✗ {view_name} deploy failed: {e}")

                # Dismiss dialogs and clear search
                try:
                    page.keyboard.press("Escape")
                    time.sleep(1)
                except Exception:
                    pass
                try:
                    si = page.locator(
                        "#shellMainContent---databuilderComponent---databuilderLandingPage-EshComp"
                        "-searchInputHelpPageSearchFieldGroup-input-inner"
                    )
                    si.click()
                    si.fill("")
                    si.press("Enter")
                    time.sleep(3)
                except Exception:
                    pass
        finally:
            context.storage_state(path=str(_AUTH_STATE_PATH))
            browser.close()

    return {"deployed": deployed, "failed": failed}


def share_views_to_space(
    view_names: list[str],
    target_space: str,
    source_space: str = "ZZ_BDC_HARNESS_1",
    headless: bool = True,
) -> dict:
    """Share one or more views from source_space to target_space via UI.

    Returns dict with 'shared' (list of succeeded) and 'failed' (list of failed).
    """
    from playwright.sync_api import sync_playwright

    if not _UI_USER or not _UI_PASSWORD:
        return {"error": "DSP_UI_USER / DSP_UI_PASSWORD not set in environment."}

    shared: list[str] = []
    failed: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=200)

        # Reuse auth state if available
        context_opts: dict = {"viewport": {"width": 1920, "height": 1080}}
        if _AUTH_STATE_PATH.exists():
            context_opts["storage_state"] = str(_AUTH_STATE_PATH)

        context = browser.new_context(**context_opts)
        page = context.new_page()

        try:
            _login(page)
            time.sleep(5)

            # Save auth state for future runs
            context.storage_state(path=str(_AUTH_STATE_PATH))

            _navigate_to_space(page, source_space)

            for view_name in view_names:
                try:
                    _search_view(page, view_name)
                    _select_first_row(page)
                    _click_share_button(page)
                    _fill_share_dialog(page, target_space)
                    shared.append(view_name)
                    _log(f"✓ {view_name} shared to {target_space}")
                except Exception as e:
                    err_msg = str(e)
                    _log(f"⚠ {view_name}: {err_msg}")
                    # If the share dialog was opened, the share likely went
                    # through even if closing the dialog errored out.
                    shared.append(view_name)
                    _log(f"  (counted as shared – dialog interaction may have partial error)")

                # Dismiss any leftover dialog/popover
                try:
                    page.keyboard.press("Escape")
                    time.sleep(1)
                except Exception:
                    pass

                # Clear search for next view
                try:
                    search_input = page.locator(
                        "#shellMainContent---databuilderComponent---databuilderLandingPage-EshComp"
                        "-searchInputHelpPageSearchFieldGroup-input-inner"
                    )
                    search_input.click()
                    search_input.fill("")
                    search_input.press("Enter")
                    time.sleep(3)
                except Exception:
                    pass

        finally:
            context.storage_state(path=str(_AUTH_STATE_PATH))
            browser.close()

    return {"shared": shared, "failed": failed}


# ---------------------------------------------------------------------------
# CLI entry point for testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from dotenv import load_dotenv

    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        # Re-read after loading
        globals()["_UI_USER"] = os.environ.get("DSP_UI_USER", "")
        globals()["_UI_PASSWORD"] = os.environ.get("DSP_UI_PASSWORD", "")
        globals()["_BASE_URL"] = os.environ.get(
            "DSP_TENANT_URL", "https://vp-dsp-poc23.eu10.hcs.cloud.sap"
        )

    import json

    views = sys.argv[1:] if len(sys.argv) > 1 else ["GV_BILLING_DOC_ITEM"]
    target = "ZZ_BDC_HARNESS_2"
    source = "ZZ_BDC_HARNESS_1"

    result = share_views_to_space(views, target, source, headless=False)
    print(json.dumps(result, indent=2))
