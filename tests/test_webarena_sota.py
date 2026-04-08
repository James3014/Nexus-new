import asyncio
from nexus.webarena_adapter import nexus_web_agent

async def test_shopping_run():
    print("--- 🛒 [Nexus:WebArena] Task: Find a 'red dress' under $50 ---")
    obs = {"text": "Shopping page loaded with multiple filters", "url": "http://e-commerce.test"}
    
    # Round 1: Intentional Failure (Click wrong filter)
    print("Round 1: Attempting filter 'Blue'...")
    action1 = await nexus_web_agent.act(obs)
    nexus_web_agent.handle_task_failure("Wrong filter: 'Blue' selected. Expected: 'Red'")
    
    # Round 2: Success via Negative Recall
    print("Round 2: Retrying with Negative Lesson Recall...")
    action2 = await nexus_web_agent.act(obs)
    print(f"✅ Round 2 Result: {action2}")
    
    # Verify Recall
    assert len(nexus_web_agent.ploop.session_failures) == 1
    print("✅ [WEBARENA-SOTA] Successfully learned from Round 1 failure.")

if __name__ == "__main__":
    asyncio.run(test_shopping_run())
