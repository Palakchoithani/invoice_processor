import sys
from pathlib import Path
import pytest
import json
from unittest.mock import AsyncMock, MagicMock

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

@pytest.mark.asyncio
async def test_stream_generator():
    print("Testing SSE stream generator...")
    from app import stream
    
    # Mock request
    request = MagicMock()
    request.is_disconnected = AsyncMock(return_value=False)
    
    # Call the stream endpoint
    response = await stream(request)
    
    # The response is a StreamingResponse, its body_iterator yields chunks
    events = []
    async for chunk in response.body_iterator:
        if chunk.startswith("data: "):
            payload = json.loads(chunk[6:])
            events.append(payload["type"])
            print(f"Generator yielded: {payload['type']}")
            if len(events) >= 3:
                break
                
    assert "invoices" in events
    assert "jobs" in events
    assert "stats" in events
    print("✓ SSE stream generator verified successfully.")
