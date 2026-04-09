import json
from pathlib import Path
from typing import List, Dict, Any

class WebDomMapper:
    """
    WebDomMapper extracts a simplified, text-based representation of a webpage's DOM
    specifically optimized for LLM agents. It filters for interactive elements and
    assigns unique numerical IDs.
    """

    # The core JavaScript logic to be injected into the page via Playwright
    DOM_SCANNER_JS = """
    () => {
        const interactiveElements = [];
        const blacklistedTags = ['SCRIPT', 'STYLE', 'NOSCRIPT', 'META', 'LINK', 'SVG', 'IFRAME'];
        
        const isElementVisible = (el) => {
            if (!el.getClientRects().length) return false;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
            if (el.getAttribute('aria-hidden') === 'true') return false;
            
            const rect = el.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) return false;
            
            // Basic view-port check (can be expanded)
            return true;
        };

        const isInteractive = (el) => {
            const tagName = el.tagName;
            const role = el.getAttribute('role');
            const style = window.getComputedStyle(el);
            
            if (['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(tagName)) return true;
            if (role === 'button' || role === 'link' || role === 'checkbox' || role === 'menuitem') return true;
            if (el.hasAttribute('onclick') || style.cursor === 'pointer') return true;
            if (el.contentEditable === 'true') return true;
            
            return false;
        };

        const getSimplifiedText = (el) => {
            if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                return el.placeholder || el.value || '';
            }
            return el.innerText ? el.innerText.trim().substring(0, 50) : '';
        };

        const walk = (node, indexObj) => {
            if (node.nodeType !== Node.ELEMENT_NODE) return;
            if (blacklistedTags.includes(node.tagName)) return;
            
            if (!isElementVisible(node)) return;

            if (isInteractive(node)) {
                const index = indexObj.count++;
                node.setAttribute('nexus-index', index.toString());
                
                interactiveElements.push({
                    index: index,
                    tag: node.tagName.toLowerCase(),
                    text: getSimplifiedText(node),
                    type: node.type || '',
                    placeholder: node.placeholder || '',
                    ariaLabel: node.getAttribute('aria-label') || '',
                    title: node.title || '',
                    id: node.id || '',
                    className: node.className || ''
                });
                
                // Note: We might want to stop recursion here if the interactive element is a container
                // but for links/buttons with spans, we might still want text. 
                // Browser-use usually flattens or handles nested text.
            }

            for (const child of node.children) {
                walk(child, indexObj);
            }
        };

        walk(document.body, { count: 1 });
        return interactiveElements;
    }
    """

    @staticmethod
    async def inject_and_map_dom(page) -> str:
        """
        Injects the scanner script into the Playwright page and returns a formatted
        string representation of the interactive elements.
        """
        elements = await page.evaluate(WebDomMapper.DOM_SCANNER_JS)
        
        output = []
        for el in elements:
            # tag_header is "[id] <tag>"
            tag_header = f"[{el['index']}] <{el['tag']}>"
            attributes = []
            
            # For inputs/textareas, if text matches placeholder, only show placeholder or text once
            if el['tag'] in ['input', 'textarea']:
                if el['text'] and el['text'] != el['placeholder']:
                    attributes.append(f"text: \"{el['text']}\"")
                if el['placeholder']:
                    attributes.append(f"placeholder: \"{el['placeholder']}\"")
            else:
                if el['text']:
                    attributes.append(f"text: \"{el['text']}\"")
            
            if el['ariaLabel']:
                attributes.append(f"aria-label: \"{el['ariaLabel']}\"")
            if el['title']:
                attributes.append(f"title: \"{el['title']}\"")
            
            if attributes:
                output.append(f"{tag_header} {' '.join(attributes)}")
            else:
                output.append(tag_header)
            
        return "\n".join(output)

    @staticmethod
    def get_elements_json(elements: List[Dict[str, Any]]) -> str:
        """Utility to serialize to JSON for Agent tool use."""
        return json.dumps(elements, indent=2)
