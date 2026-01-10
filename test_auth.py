#!/usr/bin/env python3
"""
Test script for authentication system
Run this after starting the server to verify auth is working
"""

import requests
import json

BASE_URL = "http://localhost:7860"

def test_login():
    """Test login with default admin credentials"""
    print("Testing login...")
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": "admin", "password": "admin123"},
        headers={"ngrok-skip-browser-warning": "true"}
    )
    
    if response.status_code == 200:
        data = response.json()
        print("✓ Login successful!")
        print(f"  Token: {data['access_token'][:20]}...")
        print(f"  User: {data['user']['username']} ({data['user']['role']})")
        return data['access_token']
    else:
        print(f"✗ Login failed: {response.status_code}")
        print(f"  Error: {response.text}")
        return None

def test_get_me(token):
    """Test getting current user info"""
    print("\nTesting /api/auth/me...")
    response = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
            "ngrok-skip-browser-warning": "true"
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        print("✓ Get user info successful!")
        print(f"  Username: {data['username']}")
        print(f"  Email: {data['email']}")
        print(f"  Role: {data['role']}")
        return True
    else:
        print(f"✗ Get user info failed: {response.status_code}")
        return False

def test_create_user(token):
    """Test creating a new user"""
    print("\nTesting user creation...")
    response = requests.post(
        f"{BASE_URL}/api/users",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "test123",
            "role": "user"
        },
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "ngrok-skip-browser-warning": "true"
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        print("✓ User creation successful!")
        print(f"  User ID: {data['id']}")
        print(f"  Username: {data['username']}")
        return data['id']
    elif response.status_code == 400 and "already exists" in response.text:
        print("⚠ User already exists (this is okay)")
        return None
    else:
        print(f"✗ User creation failed: {response.status_code}")
        print(f"  Error: {response.text}")
        return None

def test_list_users(token):
    """Test listing all users"""
    print("\nTesting user listing...")
    response = requests.get(
        f"{BASE_URL}/api/users",
        headers={
            "Authorization": f"Bearer {token}",
            "ngrok-skip-browser-warning": "true"
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        print("✓ User listing successful!")
        print(f"  Total users: {len(data['users'])}")
        for user in data['users']:
            print(f"    - {user['username']} ({user['role']}) - Active: {user['is_active']}")
        return True
    else:
        print(f"✗ User listing failed: {response.status_code}")
        return False

def test_protected_endpoint(token):
    """Test accessing protected endpoint"""
    print("\nTesting protected endpoint (/calls)...")
    response = requests.get(
        f"{BASE_URL}/calls",
        headers={
            "Authorization": f"Bearer {token}",
            "ngrok-skip-browser-warning": "true"
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        print("✓ Protected endpoint access successful!")
        print(f"  Total calls: {len(data['calls'])}")
        return True
    else:
        print(f"✗ Protected endpoint access failed: {response.status_code}")
        return False

def main():
    print("=" * 60)
    print("Authentication System Test")
    print("=" * 60)
    
    # Test login
    token = test_login()
    if not token:
        print("\n✗ Cannot proceed without valid token")
        return
    
    # Test getting user info
    test_get_me(token)
    
    # Test creating user
    test_create_user(token)
    
    # Test listing users
    test_list_users(token)
    
    # Test protected endpoint
    test_protected_endpoint(token)
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print("\n✗ Error: Cannot connect to server")
        print("  Make sure the server is running: python server.py")
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
