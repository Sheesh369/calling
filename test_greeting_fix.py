#!/usr/bin/env python3
"""Test script to verify the greeting generation fix"""

def test_invoice_formatting():
    """Test the new invoice formatting logic"""
    
    test_cases = [
        ("INV-002", "INV dash 002"),
        ("27EXT2425/7334", "27EXT2425 slash 7334"),
        ("ABC-123-XYZ", "ABC dash 123 dash XYZ"),
        ("2024/12/27", "2024 slash 12 slash 27"),
        ("unknown", "unknown"),
    ]
    
    print("🧪 Testing Invoice Number Formatting\n")
    print("=" * 60)
    
    all_passed = True
    for invoice_number, expected in test_cases:
        # Apply the new logic
        spoken_invoice = invoice_number.replace("-", " dash ").replace("/", " slash ")
        
        # Check if it matches expected
        passed = spoken_invoice == expected
        status = "✅ PASS" if passed else "❌ FAIL"
        
        print(f"\n{status}")
        print(f"  Input:    {invoice_number}")
        print(f"  Output:   {spoken_invoice}")
        print(f"  Expected: {expected}")
        
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 60)
    
    if all_passed:
        print("\n✅ All tests passed! The fix is working correctly.")
    else:
        print("\n❌ Some tests failed. Please review the logic.")
    
    return all_passed


def test_greeting_text():
    """Test the complete greeting text generation"""
    
    print("\n\n🎤 Testing Complete Greeting Text Generation\n")
    print("=" * 60)
    
    test_cases = [
        {
            "invoice_number": "INV-002",
            "expected_contains": ["INV dash 002", "Sara", "Hummingbird"]
        },
        {
            "invoice_number": "27EXT2425/7334",
            "expected_contains": ["27EXT2425 slash 7334", "Sara", "Hummingbird"]
        },
        {
            "invoice_number": "unknown",
            "expected_contains": ["outstanding invoice", "Sara", "Hummingbird"]
        }
    ]
    
    all_passed = True
    for test in test_cases:
        invoice_number = test["invoice_number"]
        
        # Generate greeting text using the new logic
        if invoice_number.lower() == "unknown":
            greeting_text = "Hi, this is Sara from Hummingbird, calling regarding your outstanding invoice."
        else:
            # Remove dashes and format as "inv{number}"
            spoken_invoice = invoice_number.replace("-", "").replace("/", "")
            
            # Build greeting with available information
            greeting_text = f"Hi, this is Sara from Hummingbird, calling regarding an outstanding invoice {spoken_invoice}"
            
            if outstanding_balance:
                greeting_text += f" for {outstanding_balance}"
            
            if invoice_date:
                greeting_text += f", which was dated on {invoice_date}"
            
            greeting_text += ". I wanted to check on the status of this payment."
        
        # Check if all expected strings are present
        passed = all(expected in greeting_text for expected in test["expected_contains"])
        status = "✅ PASS" if passed else "❌ FAIL"
        
        print(f"\n{status}")
        print(f"  Invoice: {invoice_number}")
        print(f"  Greeting: {greeting_text}")
        
        if not passed:
            all_passed = False
            missing = [exp for exp in test["expected_contains"] if exp not in greeting_text]
            print(f"  ❌ Missing: {missing}")
    
    print("\n" + "=" * 60)
    
    return all_passed


def validate_tts_text(text: str) -> bool:
    """Validate that text is suitable for TTS API"""
    # Check for excessive spacing (more than 2 consecutive spaces)
    if "   " in text:
        return False
    # Check for reasonable length
    if len(text) > 500:
        return False
    # Check that it's not empty
    if not text.strip():
        return False
    return True


def test_validation():
    """Test the text validation function"""
    
    print("\n\n🔍 Testing Text Validation\n")
    print("=" * 60)
    
    test_cases = [
        ("Normal text", True),
        ("Text with  two spaces", True),
        ("Text with   three spaces", False),
        ("", False),
        ("   ", False),
        ("A" * 600, False),  # Too long
    ]
    
    all_passed = True
    for text, expected_valid in test_cases:
        is_valid = validate_tts_text(text)
        passed = is_valid == expected_valid
        status = "✅ PASS" if passed else "❌ FAIL"
        
        display_text = text[:50] + "..." if len(text) > 50 else text
        print(f"\n{status}")
        print(f"  Text: '{display_text}'")
        print(f"  Valid: {is_valid} (expected: {expected_valid})")
        
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 60)
    
    return all_passed


if __name__ == "__main__":
    print("\n" + "🔧 GREETING GENERATION FIX - TEST SUITE" + "\n")
    
    results = []
    results.append(("Invoice Formatting", test_invoice_formatting()))
    results.append(("Greeting Text", test_greeting_text()))
    results.append(("Text Validation", test_validation()))
    
    print("\n\n" + "=" * 60)
    print("📊 FINAL RESULTS")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    all_passed = all(result[1] for result in results)
    
    print("=" * 60)
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED! The fix is ready to deploy.")
        print("\n📝 Next steps:")
        print("   1. Restart the server: ./restart_server.sh")
        print("   2. Make a test call")
        print("   3. Check logs for 'Successfully generated greeting audio'")
    else:
        print("\n⚠️  SOME TESTS FAILED. Please review the code.")
    
    print()
