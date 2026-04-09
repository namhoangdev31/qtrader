import json
import logging

def extract_json(response: str) -> dict:
    try:
        clean_json = response.strip()
        
        # 1. Remove markdown code blocks
        if "```" in clean_json:
            clean_json = clean_json.split("```")[-2].split("json")[-1].strip()
        
        # 2. Extract block between first { and last }
        start_idx = clean_json.find("{")
        end_idx = clean_json.rfind("}")
        
        if start_idx != -1 and end_idx != -1:
            clean_json = clean_json[start_idx : end_idx + 1]
        
        return json.loads(clean_json)
    except Exception as e:
        print(f"Error parsing: {e}")
        return {}

# Test Cases
test_responses = [
    '{"action": "BUY", "confidence": 0.8}',
    'Here is the JSON: {"action": "BUY", "confidence": 0.8}\nHope this helps!',
    '```json\n{"action": "BUY", "confidence": 0.8}\n```',
    'Some text ```json {"action": "BUY", "confidence": 0.8} ``` more text',
    'Invalid JSON { "action": "BUY", ',
]

for i, resp in enumerate(test_responses):
    result = extract_json(resp)
    print(f"Test {i}: {'PASS' if result.get('action') == 'BUY' else 'FAIL'}")
    print(f"  Input: {resp!r}")
    print(f"  Result: {result}\n")
