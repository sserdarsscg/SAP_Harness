"""Scout script: login to SAP Datasphere and explore Repository Explorer."""
from playwright.sync_api import sync_playwright
import time


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=200)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        # Navigate to SAP Datasphere
        page.goto("https://vp-dsp-poc23.eu10.hcs.cloud.sap")
        page.wait_for_load_state("networkidle")

        # Login
        page.fill("#j_username", "serdar.sorgun@capgemini.com")
        page.fill("#j_password", "uD323500.")
        page.click("#logOnFormSubmit")

        # Wait for redirect to home
        page.wait_for_url("**/dwaas-core/**", timeout=30000)
        time.sleep(8)
        print(f"Home URL: {page.url}")

        # Navigate to Data Builder
        page.goto("https://vp-dsp-poc23.eu10.hcs.cloud.sap/dwaas-core/index.html#/databuilder")
        time.sleep(10)

        # Collapse nav bar if expanded to avoid click interception
        collapse_btn = page.locator("[title='Collapse Navigation Bar']")
        if collapse_btn.is_visible():
            print("Collapsing nav bar...")
            collapse_btn.click()
            time.sleep(2)

        # Use the search field to filter spaces
        search_input = page.locator("#shellMainContent---databuilderComponent---spaceSelection--spaceSearchField-I")
        if search_input.is_visible():
            print("Using search field to find space...")
            search_input.click()
            search_input.fill("ZZ_BDC_HARNESS_1")
            time.sleep(3)
            # Now press Enter or click on the filtered result
            search_input.press("Enter")
            time.sleep(3)

        # Now try to click the space row
        # The space text should be more accessible now
        space_link = page.locator("text=ZZ_BDC_HARNESS_1").first
        if space_link.is_visible():
            print(f"Space link found, clicking...")
            space_link.click()
            time.sleep(10)
            print(f"URL after space click: {page.url}")
        else:
            # Try double-click on the row
            print("Space link not visible after search, trying locator with role...")
            # Try clicking inside the main content area
            space_el = page.locator("[class*='spaceSelection'] >> text=ZZ_BDC_HARNESS_1").first
            if space_el.count() > 0:
                space_el.click()
                time.sleep(10)
                print(f"URL after selector click: {page.url}")
            else:
                # Last resort: click at coordinates
                # Find the element position
                el_box = page.locator("text=ZZ_BDC_HARNESS_1").first.bounding_box()
                if el_box:
                    print(f"Bounding box: {el_box}")
                    page.mouse.click(el_box["x"] + el_box["width"]/2, el_box["y"] + el_box["height"]/2)
                    time.sleep(10)
                    print(f"URL after mouse click: {page.url}")

        page.screenshot(path="after_space_click.png")
        print(f"URL: {page.url}")
        
        # Use the search field to find the view
        search_input = page.locator("#shellMainContent---databuilderComponent---databuilderLandingPage-EshComp-searchInputHelpPageSearchFieldGroup-input-inner")
        print("\nSearching for GV_BILLING_DOC_ITEM...")
        search_input.click()
        search_input.fill("GV_BILLING_DOC_ITEM")
        search_input.press("Enter")
        time.sleep(5)
        page.screenshot(path="search_result.png")
        
        # Use Playwright click on the checkbox (not JS evaluate)
        # The checkbox ID pattern: ...-ushell-search-result-table-{N}-item-selectMulti
        cb_locator = page.locator("[id$='-item-selectMulti']").first
        if cb_locator.count() > 0:
            print(f"Found checkbox, clicking with Playwright...")
            cb_locator.click(force=True)
            time.sleep(3)
        else:
            # Try role-based
            print("No checkbox by ID suffix, trying role=checkbox...")
            cb_locator = page.locator("tr:has-text('GV_BILLING_DOC_ITEM') [role='checkbox']").first
            cb_locator.click(force=True)
            time.sleep(3)
        
        page.screenshot(path="after_pw_checkbox.png")
        
        # Check share button state
        share_state = page.evaluate("""() => {
            const btn = document.getElementById('shellMainContent---databuilderComponent---databuilderLandingPage--shareButton');
            return btn ? {disabled: btn.disabled, className: btn.className.substring(0, 100)} : 'not found';
        }""")
        print(f"Share button state after Playwright checkbox click: {share_state}")
        
        # If still disabled, try clicking the row itself (not the checkbox)
        if share_state.get("disabled", True):
            print("Still disabled. Trying to click the row text directly...")
            # Click the GV_BILLING_DOC_ITEM text link
            view_link = page.locator("a:has-text('GV_BILLING_DOC_ITEM'), span:has-text('GV_BILLING_DOC_ITEM')").first
            if view_link.count() > 0:
                # Get bounding box and click slightly to the left (on the checkbox area)
                box = view_link.bounding_box()
                if box:
                    # Click about 50px to the left of the text (checkbox area)
                    checkbox_x = box["x"] - 50
                    checkbox_y = box["y"] + box["height"] / 2
                    print(f"Clicking at ({checkbox_x}, {checkbox_y}) - left of text")
                    page.mouse.click(checkbox_x, checkbox_y)
                    time.sleep(3)
                    
                    share_state2 = page.evaluate("""() => {
                        const btn = document.getElementById('shellMainContent---databuilderComponent---databuilderLandingPage--shareButton');
                        return btn ? {disabled: btn.disabled} : 'not found';
                    }""")
                    print(f"Share button after coord click: {share_state2}")
        
        # Final check and click Share if enabled
        share_disabled = page.evaluate("""() => {
            const btn = document.getElementById('shellMainContent---databuilderComponent---databuilderLandingPage--shareButton');
            return btn ? btn.disabled : true;
        }""")
        
        if not share_disabled:
            print("\n=== Share button ENABLED! Clicking... ===")
            page.locator("#shellMainContent---databuilderComponent---databuilderLandingPage--shareButton").click()
            time.sleep(5)
            page.screenshot(path="share_dialog.png")
            
            # Explore dialog content
            body_text = page.locator("body").inner_text()
            lines = body_text.split("\n")
            dialog_lines = [l.strip() for l in lines if l.strip() and ("share" in l.lower() or "target" in l.lower() or "ZZ_" in l)]
            print(f"\nDialog lines:")
            for l in dialog_lines[:20]:
                print(f"  {l[:120]}")
            
            # Find dialog elements
            dialogs = page.locator("[role='dialog']").all()
            print(f"\nDialogs: {len(dialogs)}")
            if dialogs:
                print(f"Dialog text:\n{dialogs[0].inner_text()[:800]}")
        else:
            print("\nShare still disabled after all attempts.")

        # Check body text for space/view info
        body_text = page.locator("body").inner_text()
        lines = body_text.split("\n")

        # Find ZZ_BDC lines
        zz_lines = [l.strip() for l in lines if "ZZ_BDC" in l]
        print(f"\nZZ_BDC lines: {len(zz_lines)}")
        for l in zz_lines[:5]:
            print(f"  {l[:100]}")

        # Find GV_ lines
        gv_lines = [l.strip() for l in lines if "GV_" in l]
        print(f"\nGV_ lines: {len(gv_lines)}")
        for l in gv_lines[:10]:
            print(f"  {l[:100]}")

        # Find share/Share
        share_lines = [l.strip() for l in lines if "share" in l.lower()]
        print(f"\nShare lines: {len(share_lines)}")
        for l in share_lines[:5]:
            print(f"  {l[:100]}")

        # List visible buttons
        all_btns = page.locator("button:visible").all()
        print(f"\nVisible buttons: {len(all_btns)}")
        for i, btn in enumerate(all_btns[:30]):
            try:
                info = btn.evaluate(
                    "el => ({id: el.id, "
                    "ariaLabel: el.getAttribute('aria-label'), "
                    "title: el.getAttribute('title'), "
                    "text: (el.innerText||'').substring(0,50)})"
                )
                if info.get("ariaLabel") or info.get("title") or (info.get("text") and info["text"].strip()):
                    print(f"  {i}: {info}")
            except:
                pass

        # Look for a space dropdown/selector
        inputs = page.locator("input:visible").all()
        print(f"\nVisible inputs: {len(inputs)}")
        for i, inp in enumerate(inputs[:10]):
            try:
                info = inp.evaluate(
                    "el => ({id: el.id, "
                    "placeholder: el.placeholder, "
                    "value: el.value, "
                    "ariaLabel: el.getAttribute('aria-label')})"
                )
                print(f"  {i}: {info}")
            except:
                pass

        # Save auth state
        context.storage_state(path="auth_state.json")
        print("\nAuth state saved.")
        browser.close()


if __name__ == "__main__":
    main()
