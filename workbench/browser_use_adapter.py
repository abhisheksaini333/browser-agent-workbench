"""Browser Use compatibility with a two-action, application-authorized controller."""

import os

os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")


async def create_context(playwright_browser):
    from browser_use.browser.browser import Browser, BrowserConfig
    from browser_use.browser.context import BrowserContextConfig, BrowserContext

    wrapper = Browser(config=BrowserConfig(headless=True, disable_security=False))
    wrapper.playwright_browser = playwright_browser

    class OwnedContext(BrowserContext):
        async def _create_context(self, browser):
            return await browser.new_context(
                service_workers="block", bypass_csp=False, ignore_https_errors=False
            )

    context = OwnedContext(
        browser=wrapper, config=BrowserContextConfig(disable_security=False)
    )
    session = await context.get_session()
    return wrapper, context, session.context, session.current_page


async def submit(browser_context, quantity):
    from browser_use.controller.service import Controller
    from browser_use.browser.context import BrowserContext
    from pydantic import BaseModel

    controller = Controller()
    # The model never receives or invokes the unrestricted default registry.
    controller.registry.registry.actions.clear()

    class FillQuantity(BaseModel):
        quantity: int

    @controller.action(
        "Fill approved quantity", param_model=FillQuantity, requires_browser=True
    )
    async def fill_quantity(params: FillQuantity, browser: BrowserContext):
        if params.quantity != quantity:
            raise ValueError("controller arguments differ from approval")
        await (await browser.get_current_page()).get_by_label(
            "Quantity", exact=True
        ).fill(str(params.quantity))
        return "Approved quantity entered"

    @controller.action("Submit approved operation", requires_browser=True)
    async def submit_approved(browser: BrowserContext):
        await (await browser.get_current_page()).get_by_role(
            "button", name="Submit approved operation", exact=True
        ).click()
        return "Submission dispatched; receipt must still be verified"

    Action = controller.registry.create_action_model()
    for value in ({"fill_quantity": {"quantity": quantity}}, {"submit_approved": {}}):
        result = await controller.act(Action(**value), browser_context)
        if result.error:
            raise RuntimeError(result.error)
    return ["fill_quantity", "submit_approved"]
