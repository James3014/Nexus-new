import pytest
from playwright.async_api import async_playwright
from pathlib import Path
from nexus.core.web_dom_mapper import WebDomMapper

@pytest.mark.asyncio
async def test_web_dom_mapper_basic():
    """Tests the basic DOM mapping functionality."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Load the test file
        test_file_path = Path.cwd() / "tests" / "assets" / "test_page.html"
        await page.goto(f"file://{test_file_path}")
        
        # Map the DOM
        mapped_text = await WebDomMapper.inject_and_map_dom(page)
        
        # Assertions
        assert "[1] <button> text: \"Click Me\"" in mapped_text
        assert "[2] <a> text: \"Go to Example\"" in mapped_text
        assert "[3] <input> placeholder: \"Enter name\"" in mapped_text
        
        # Hidden button should not be mapped
        assert "Hidden" not in mapped_text
        assert "<script>" not in mapped_text
        
        await browser.close()
