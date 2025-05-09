# patched_playwright_engine.py

import types
from pathlib import Path

from scrapling.core._types import (Callable, Dict, Optional,
                                   SelectorWaitStates, Union)
from scrapling.core.utils import log, lru_cache
from scrapling.engines.constants import (DEFAULT_STEALTH_FLAGS,
                                         NSTBROWSER_DEFAULT_QUERY)
from scrapling.engines.toolbelt import (Response, StatusText,
                                        async_intercept_route,
                                        check_type_validity, construct_cdp_url,
                                        construct_proxy_dict,
                                        generate_convincing_referer,
                                        generate_headers, intercept_route,
                                        js_bypass_path)

from scrapling.engines.pw import PlaywrightEngine


def make_custom_fetch(profile_dir: Path):
    def custom_fetch(self, url: str) -> Response:
        from playwright.sync_api import Response as PlaywrightResponse, sync_playwright

        final_response = None
        referer = generate_convincing_referer(url) if self.google_search else None

        def handle_response(finished_response: PlaywrightResponse):
            nonlocal final_response
            if finished_response.request.resource_type == "document" and finished_response.request.is_navigation_request():
                final_response = finished_response

        with sync_playwright() as p:
            browser_context = p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=self.headless,
                **self._PlaywrightEngine__context_kwargs()
            )

            page = browser_context.new_page()
            page.set_default_navigation_timeout(self.timeout)
            page.set_default_timeout(self.timeout)
            page.on("response", handle_response)

            if self.extra_headers:
                page.set_extra_http_headers(self.extra_headers)

            if self.disable_resources:
                page.route("**/*", intercept_route)

            if self.stealth:
                for script in self.__stealth_scripts():
                    page.add_init_script(path=script)

            first_response = page.goto(url, referer=referer)
            page.wait_for_load_state(state="domcontentloaded")

            if self.network_idle:
                page.wait_for_load_state('networkidle')

            if self.page_action is not None:
                try:
                    page = self.page_action(page)
                except Exception as e:
                    log.error(f"Error executing page_action: {e}")

            if self.wait_selector and isinstance(self.wait_selector, str):
                try:
                    waiter = page.locator(self.wait_selector)
                    waiter.first.wait_for(state=self.wait_selector_state)
                    page.wait_for_load_state(state="load")
                    page.wait_for_load_state(state="domcontentloaded")
                    if self.network_idle:
                        page.wait_for_load_state('networkidle')
                except Exception as e:
                    log.error(f"Error waiting for selector {self.wait_selector}: {e}")

            page.wait_for_timeout(self.wait)
            final_response = final_response if final_response else first_response
            if not final_response:
                raise ValueError("Failed to get a response from the page")

            encoding = final_response.headers.get('content-type', '') or 'utf-8'
            status_text = final_response.status_text or StatusText.get(final_response.status)
            history = self._process_response_history(first_response)

            try:
                page_content = page.content()
            except Exception as e:
                log.error(f"Error getting page content: {e}")
                page_content = ""

            response = Response(
                url=page.url,
                text=page_content,
                body=page_content.encode('utf-8'),
                status=final_response.status,
                reason=status_text,
                encoding=encoding,
                cookies={cookie['name']: cookie['value'] for cookie in page.context.cookies()},
                headers=first_response.all_headers(),
                request_headers=first_response.request.all_headers(),
                history=history,
                **self.adaptor_arguments
            )

            if self.adaptor_arguments.get("pause_before_close", False):
                input("🛑 Browser is paused. Press Enter to close...")

            page.close()
            browser_context.close()
            return response
    return custom_fetch


def make_custom_async_fetch(profile_dir: Path):
    async def custom_async_fetch(self, url: str) -> Response:
        import asyncio
        from playwright.async_api import Response as PlaywrightResponse, async_playwright

        final_response = None
        referer = generate_convincing_referer(url) if self.google_search else None

        async def handle_response(finished_response: PlaywrightResponse):
            nonlocal final_response
            if finished_response.request.resource_type == "document" and finished_response.request.is_navigation_request():
                final_response = finished_response

        async with async_playwright() as p:
            browser_context = await p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=self.headless,
                **self._PlaywrightEngine__context_kwargs()
            )

            page = await browser_context.new_page()
            page.set_default_navigation_timeout(self.timeout)
            page.set_default_timeout(self.timeout)
            page.on("response", handle_response)

            if self.extra_headers:
                await page.set_extra_http_headers(self.extra_headers)

            if self.disable_resources:
                await page.route("**/*", async_intercept_route)

            if self.stealth:
                for script in self.__stealth_scripts():
                    await page.add_init_script(path=script)

            first_response = await page.goto(url, referer=referer)
            await page.wait_for_load_state(state="domcontentloaded")

            if self.network_idle:
                await page.wait_for_load_state('networkidle')

            if self.page_action is not None:
                try:
                    page = await self.page_action(page)
                except Exception as e:
                    log.error(f"Error executing async page_action: {e}")

            if self.wait_selector and isinstance(self.wait_selector, str):
                try:
                    waiter = page.locator(self.wait_selector)
                    await waiter.first.wait_for(state=self.wait_selector_state)
                    await page.wait_for_load_state(state="load")
                    await page.wait_for_load_state(state="domcontentloaded")
                    if self.network_idle:
                        await page.wait_for_load_state('networkidle')
                except Exception as e:
                    log.error(f"Error waiting for selector {self.wait_selector}: {e}")

            await page.wait_for_timeout(self.wait)
            final_response = final_response if final_response else first_response
            if not final_response:
                raise ValueError("Failed to get a response from the page")

            encoding = final_response.headers.get('content-type', '') or 'utf-8'
            status_text = final_response.status_text or StatusText.get(final_response.status)
            history = await self._async_process_response_history(first_response)

            try:
                page_content = await page.content()
            except Exception as e:
                log.error(f"Error getting page content in async: {e}")
                page_content = ""

            response = Response(
                url=page.url,
                text=page_content,
                body=page_content.encode('utf-8'),
                status=final_response.status,
                reason=status_text,
                encoding=encoding,
                cookies={cookie['name']: cookie['value'] for cookie in await page.context.cookies()},
                headers=await first_response.all_headers(),
                request_headers=await first_response.request.all_headers(),
                history=history,
                **self.adaptor_arguments
            )

            if self.adaptor_arguments.get("pause_before_close", False):
                print("🛑 Browser is paused. Sleeping 10s...")
                await asyncio.sleep(10)

            await page.close()
            await browser_context.close()
            return response
    return custom_async_fetch


def make_interactive_fetch(profile_dir: Path):
    def interactive_fetch(self, url: str):
        from playwright.sync_api import Response as PlaywrightResponse, sync_playwright

        final_response = None
        referer = generate_convincing_referer(url) if self.google_search else None

        def handle_response(resp: PlaywrightResponse):
            nonlocal final_response
            if resp.request.resource_type == "document" and resp.request.is_navigation_request():
                final_response = resp

        p = sync_playwright().start()
        browser_context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=self.headless,
            **self._PlaywrightEngine__context_kwargs()
        )

        page = browser_context.new_page()
        page.set_default_navigation_timeout(self.timeout)
        page.set_default_timeout(self.timeout)
        page.on("response", handle_response)

        if self.extra_headers:
            page.set_extra_http_headers(self.extra_headers)

        if self.disable_resources:
            page.route("**/*", intercept_route)

        if self.stealth:
            for script in self.__stealth_scripts():
                page.add_init_script(path=script)

        first_response = page.goto(url, referer=referer)
        page.wait_for_load_state("domcontentloaded")

        if self.network_idle:
            page.wait_for_load_state("networkidle")

        if self.page_action:
            try:
                page = self.page_action(page)
            except Exception as e:
                log.error(f"Error in page_action: {e}")

        if self.wait_selector and isinstance(self.wait_selector, str):
            try:
                waiter = page.locator(self.wait_selector)
                waiter.first.wait_for(state=self.wait_selector_state)
                page.wait_for_load_state("load")
                page.wait_for_load_state("domcontentloaded")
                if self.network_idle:
                    page.wait_for_load_state("networkidle")
            except Exception as e:
                log.error(f"Selector wait failed: {e}")

        page.wait_for_timeout(self.wait)
        final_response = final_response or first_response

        encoding = final_response.headers.get("content-type", "") or "utf-8"
        status_text = final_response.status_text or StatusText.get(final_response.status)
        history = self._process_response_history(first_response)

        try:
            page_content = page.content()
        except Exception as e:
            log.error(f"Content error: {e}")
            page_content = ""

        response = Response(
            url=page.url,
            text=page_content,
            body=page_content.encode("utf-8"),
            status=final_response.status,
            reason=status_text,
            encoding=encoding,
            cookies={cookie['name']: cookie['value'] for cookie in page.context.cookies()},
            headers=first_response.all_headers(),
            request_headers=first_response.request.all_headers(),
            history=history,
            **self.adaptor_arguments
        )

        return response, page  # Page stays open
    return interactive_fetch


def make_async_interactive_fetch(profile_dir: Path):
    async def async_interactive_fetch(self, url: str):
        from playwright.async_api import Response as PlaywrightResponse, async_playwright

        final_response = None
        referer = generate_convincing_referer(url) if self.google_search else None

        async def handle_response(resp: PlaywrightResponse):
            nonlocal final_response
            if resp.request.resource_type == "document" and resp.request.is_navigation_request():
                final_response = resp

        p = await async_playwright().start()
        browser_context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=self.headless,
            **self._PlaywrightEngine__context_kwargs()
        )

        page = await browser_context.new_page()
        page.set_default_navigation_timeout(self.timeout)
        page.set_default_timeout(self.timeout)
        page.on("response", handle_response)

        if self.extra_headers:
            await page.set_extra_http_headers(self.extra_headers)

        if self.disable_resources:
            await page.route("**/*", async_intercept_route)

        if self.stealth:
            for script in self.__stealth_scripts():
                await page.add_init_script(path=script)

        first_response = await page.goto(url, referer=referer)
        await page.wait_for_load_state("domcontentloaded")

        if self.network_idle:
            await page.wait_for_load_state("networkidle")

        if self.page_action:
            try:
                page = await self.page_action(page)
            except Exception as e:
                log.error(f"Error in async page_action: {e}")

        if self.wait_selector and isinstance(self.wait_selector, str):
            try:
                waiter = page.locator(self.wait_selector)
                await waiter.first.wait_for(state=self.wait_selector_state)
                await page.wait_for_load_state("load")
                await page.wait_for_load_state("domcontentloaded")
                if self.network_idle:
                    await page.wait_for_load_state("networkidle")
            except Exception as e:
                log.error(f"Selector wait failed: {e}")

        await page.wait_for_timeout(self.wait)
        final_response = final_response or first_response

        encoding = final_response.headers.get("content-type", "") or "utf-8"
        status_text = final_response.status_text or StatusText.get(final_response.status)
        history = await self._async_process_response_history(first_response)

        try:
            page_content = await page.content()
        except Exception as e:
            log.error(f"Content error: {e}")
            page_content = ""

        response = Response(
            url=page.url,
            text=page_content,
            body=page_content.encode("utf-8"),
            status=final_response.status,
            reason=status_text,
            encoding=encoding,
            cookies={cookie['name']: cookie['value'] for cookie in await page.context.cookies()},
            headers=await first_response.all_headers(),
            request_headers=await first_response.request.all_headers(),
            history=history,
            **self.adaptor_arguments
        )

        return response, page  # Page stays open
    return async_interactive_fetch


def load_patched_playwright_engine(profile_dir: Path) -> type:
    """Monkey-patch and return patched PlaywrightEngine with custom profile_dir"""
    PlaywrightEngine.fetch = make_custom_fetch(profile_dir)
    PlaywrightEngine.async_fetch = make_custom_async_fetch(profile_dir)
    PlaywrightEngine.interactive_fetch = make_interactive_fetch(profile_dir)
    PlaywrightEngine.async_interactive_fetch = make_async_interactive_fetch(profile_dir)
    return PlaywrightEngine
