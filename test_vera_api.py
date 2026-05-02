"""
Test script for Vera Bot API
Run this script to test all endpoints and verify the API is working correctly.

Usage:
    python test_vera_api.py
"""

import requests
import json
from typing import Dict, Any

# Configuration
API_BASE_URL = "http://localhost:5000"
TIMEOUT = 5  # seconds

# Color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'


class VeraBotAPITester:
    """Test suite for Vera Bot API endpoints."""
    
    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url
        self.passed = 0
        self.failed = 0
        self.total = 0
    
    def print_header(self, text: str):
        """Print section header."""
        print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
        print(f"{BOLD}{BLUE}{text}{RESET}")
        print(f"{BOLD}{BLUE}{'='*60}{RESET}\n")
    
    def print_test(self, test_name: str):
        """Print test name."""
        print(f"{YELLOW}Testing: {test_name}{RESET}")
    
    def print_success(self, message: str = "✓ PASSED"):
        """Print success message."""
        self.passed += 1
        self.total += 1
        print(f"{GREEN}{message}{RESET}")
    
    def print_error(self, message: str = "✗ FAILED"):
        """Print error message."""
        self.failed += 1
        self.total += 1
        print(f"{RED}{message}{RESET}")
    
    def print_info(self, message: str):
        """Print info message."""
        print(f"{BLUE}  ➜ {message}{RESET}")
    
    def check_api_running(self) -> bool:
        """Check if API is running."""
        try:
            response = requests.get(f"{self.base_url}/v1/healthz", timeout=TIMEOUT)
            return response.status_code == 200
        except requests.exceptions.ConnectionError:
            print(f"{RED}❌ ERROR: Cannot connect to API at {self.base_url}{RESET}")
            print(f"{RED}Make sure to run: python app.py{RESET}")
            return False
    
    def test_healthz(self):
        """Test GET /v1/healthz endpoint."""
        self.print_test("GET /v1/healthz")
        try:
            response = requests.get(f"{self.base_url}/v1/healthz", timeout=TIMEOUT)
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            
            data = response.json()
            assert "status" in data, "Missing 'status' field"
            assert data["status"] == "ok", f"Expected status='ok', got '{data['status']}'"
            
            self.print_success("✓ PASSED")
            self.print_info(f"Response: {json.dumps(data, indent=2)}")
            return True
        except Exception as e:
            self.print_error(f"✗ FAILED: {str(e)}")
            return False
    
    def test_metadata(self):
        """Test GET /v1/metadata endpoint."""
        self.print_test("GET /v1/metadata")
        try:
            response = requests.get(f"{self.base_url}/v1/metadata", timeout=TIMEOUT)
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            
            data = response.json()
            required_fields = ["name", "version", "description"]
            
            for field in required_fields:
                assert field in data, f"Missing required field: {field}"
            
            assert data["name"] == "Vera Bot", f"Expected name='Vera Bot', got '{data['name']}'"
            assert data["version"] == "1.0", f"Expected version='1.0', got '{data['version']}'"
            
            self.print_success("✓ PASSED")
            self.print_info(f"Response: {json.dumps(data, indent=2)}")
            return True
        except Exception as e:
            self.print_error(f"✗ FAILED: {str(e)}")
            return False
    
    def test_context(self):
        """Test POST /v1/context endpoint."""
        self.print_test("POST /v1/context")
        try:
            payload = {
                "merchant_id": "12345",
                "region": "mumbai",
                "customer_count": 150
            }
            
            response = requests.post(
                f"{self.base_url}/v1/context",
                json=payload,
                timeout=TIMEOUT
            )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            
            data = response.json()
            assert data["status"] == "received", f"Expected status='received', got '{data['status']}'"
            
            self.print_success("✓ PASSED")
            self.print_info(f"Sent: {json.dumps(payload, indent=2)}")
            self.print_info(f"Response: {json.dumps(data, indent=2)}")
            return True
        except Exception as e:
            self.print_error(f"✗ FAILED: {str(e)}")
            return False
    
    def test_tick(self):
        """Test POST /v1/tick endpoint."""
        self.print_test("POST /v1/tick")
        try:
            payload = {"event": "daily_sync", "timestamp": "2026-05-02"}
            
            response = requests.post(
                f"{self.base_url}/v1/tick",
                json=payload,
                timeout=TIMEOUT
            )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            
            data = response.json()
            assert data["status"] == "ok", f"Expected status='ok', got '{data['status']}'"
            
            self.print_success("✓ PASSED")
            self.print_info(f"Response: {json.dumps(data, indent=2)}")
            return True
        except Exception as e:
            self.print_error(f"✗ FAILED: {str(e)}")
            return False
    
    def test_reply_food_low_orders(self):
        """Test POST /v1/reply - Food + Low Orders."""
        self.print_test("POST /v1/reply - Food + Low Orders")
        try:
            payload = {
                "category": "food",
                "merchant": "Pizza Palace",
                "trigger": "low_orders"
            }
            
            response = requests.post(
                f"{self.base_url}/v1/reply",
                json=payload,
                timeout=TIMEOUT
            )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            
            data = response.json()
            assert "messages" in data, "Missing 'messages' field"
            assert "cta" in data, "Missing 'cta' field"
            assert len(data["messages"]) > 0, "Messages array is empty"
            assert "text" in data["messages"][0], "Missing 'text' in message"
            
            # Verify deterministic response
            assert "Boost your orders" in data["messages"][0]["text"], "Wrong message content"
            assert data["cta"] == "Create Offer", "Wrong CTA"
            
            self.print_success("✓ PASSED - Deterministic response verified")
            self.print_info(f"Sent: {json.dumps(payload, indent=2)}")
            self.print_info(f"Response: {json.dumps(data, indent=2)}")
            return True
        except Exception as e:
            self.print_error(f"✗ FAILED: {str(e)}")
            return False
    
    def test_reply_food_festival(self):
        """Test POST /v1/reply - Food + Festival."""
        self.print_test("POST /v1/reply - Food + Festival")
        try:
            payload = {
                "category": "food",
                "merchant": "Pizza Hut",
                "trigger": "festival"
            }
            
            response = requests.post(
                f"{self.base_url}/v1/reply",
                json=payload,
                timeout=TIMEOUT
            )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            
            data = response.json()
            
            # Verify deterministic response
            assert "Celebrate with special festive combos" in data["messages"][0]["text"], "Wrong message content"
            assert data["cta"] == "Launch Campaign", "Wrong CTA"
            
            self.print_success("✓ PASSED - Deterministic response verified")
            self.print_info(f"Response: {json.dumps(data, indent=2)}")
            return True
        except Exception as e:
            self.print_error(f"✗ FAILED: {str(e)}")
            return False
    
    def test_reply_salon_low_orders(self):
        """Test POST /v1/reply - Salon + Low Orders."""
        self.print_test("POST /v1/reply - Salon + Low Orders")
        try:
            payload = {
                "category": "salon",
                "merchant": "Elite Salon",
                "trigger": "low_orders"
            }
            
            response = requests.post(
                f"{self.base_url}/v1/reply",
                json=payload,
                timeout=TIMEOUT
            )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            
            data = response.json()
            
            # Verify deterministic response
            assert "bookings" in data["messages"][0]["text"].lower(), "Wrong message content"
            assert data["cta"] == "Create Offer", "Wrong CTA"
            
            self.print_success("✓ PASSED - Deterministic response verified")
            self.print_info(f"Response: {json.dumps(data, indent=2)}")
            return True
        except Exception as e:
            self.print_error(f"✗ FAILED: {str(e)}")
            return False
    
    def test_reply_default_fallback(self):
        """Test POST /v1/reply - Default Fallback."""
        self.print_test("POST /v1/reply - Default Fallback (unknown category)")
        try:
            payload = {
                "category": "unknown_category",
                "merchant": "Some Store",
                "trigger": "some_trigger"
            }
            
            response = requests.post(
                f"{self.base_url}/v1/reply",
                json=payload,
                timeout=TIMEOUT
            )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            
            data = response.json()
            
            # Verify default response
            assert "Improve your business visibility" in data["messages"][0]["text"], "Wrong fallback message"
            assert data["cta"] == "Explore Options", "Wrong fallback CTA"
            
            self.print_success("✓ PASSED - Default fallback working")
            self.print_info(f"Response: {json.dumps(data, indent=2)}")
            return True
        except Exception as e:
            self.print_error(f"✗ FAILED: {str(e)}")
            return False
    
    def test_reply_missing_field(self):
        """Test POST /v1/reply - Missing required field."""
        self.print_test("POST /v1/reply - Missing 'category' field (error handling)")
        try:
            payload = {
                "merchant": "Pizza Palace",
                "trigger": "low_orders"
                # Missing 'category'
            }
            
            response = requests.post(
                f"{self.base_url}/v1/reply",
                json=payload,
                timeout=TIMEOUT
            )
            
            assert response.status_code == 400, f"Expected 400, got {response.status_code}"
            
            data = response.json()
            assert data["status"] == "error", "Expected error status"
            assert "category" in data["message"].lower(), "Error message should mention missing field"
            
            self.print_success("✓ PASSED - Error handling verified")
            self.print_info(f"Response: {json.dumps(data, indent=2)}")
            return True
        except Exception as e:
            self.print_error(f"✗ FAILED: {str(e)}")
            return False
    
    def test_determinism(self):
        """Test that responses are deterministic."""
        self.print_test("Determinism Check - Same input, same output")
        try:
            payload = {
                "category": "food",
                "merchant": "Test Restaurant",
                "trigger": "low_orders"
            }
            
            # Call the endpoint 3 times
            responses = []
            for i in range(3):
                response = requests.post(
                    f"{self.base_url}/v1/reply",
                    json=payload,
                    timeout=TIMEOUT
                )
                responses.append(response.json())
            
            # Verify all responses are identical
            for i in range(1, len(responses)):
                assert responses[i] == responses[0], f"Response {i} differs from response 0"
            
            self.print_success("✓ PASSED - Fully deterministic (3/3 identical responses)")
            self.print_info(f"Verified response: {json.dumps(responses[0], indent=2)}")
            return True
        except Exception as e:
            self.print_error(f"✗ FAILED: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all tests."""
        self.print_header("🤖 VERA BOT API - COMPREHENSIVE TEST SUITE")
        
        # Check if API is running
        if not self.check_api_running():
            return False
        
        print(f"{GREEN}✓ API is running at {self.base_url}{RESET}\n")
        
        # Run all tests
        self.print_header("1️⃣ BASIC ENDPOINTS")
        self.test_healthz()
        print()
        self.test_metadata()
        print()
        self.test_context()
        print()
        self.test_tick()
        
        self.print_header("2️⃣ REPLY ENDPOINT - DETERMINISTIC RULES")
        self.test_reply_food_low_orders()
        print()
        self.test_reply_food_festival()
        print()
        self.test_reply_salon_low_orders()
        print()
        self.test_reply_default_fallback()
        
        self.print_header("3️⃣ ERROR HANDLING & VALIDATION")
        self.test_reply_missing_field()
        
        self.print_header("4️⃣ DETERMINISM GUARANTEE")
        self.test_determinism()
        
        # Print summary
        self.print_header("📊 TEST SUMMARY")
        passed_pct = (self.passed / self.total * 100) if self.total > 0 else 0
        
        if self.failed == 0:
            print(f"{GREEN}{BOLD}✓ ALL TESTS PASSED!{RESET}\n")
        else:
            print(f"{RED}{BOLD}⚠ SOME TESTS FAILED{RESET}\n")
        
        print(f"Total Tests:  {self.total}")
        print(f"{GREEN}Passed:      {self.passed}{RESET}")
        if self.failed > 0:
            print(f"{RED}Failed:      {self.failed}{RESET}")
        print(f"Pass Rate:   {passed_pct:.1f}%\n")
        
        return self.failed == 0


def main():
    """Main entry point."""
    tester = VeraBotAPITester()
    success = tester.run_all_tests()
    
    if success:
        print(f"{GREEN}{BOLD}🚀 Vera Bot API is production-ready!{RESET}\n")
    else:
        print(f"{RED}{BOLD}⚠️  Please fix the failing tests{RESET}\n")
        exit(1)


if __name__ == "__main__":
    main()
