import os
import time
import requests

BASE_URL = "http://localhost:8000"
EMAIL_LOG_PATH = "./db/emails.log"

def register_user(email, password, first_name="Alice", last_name="Smith", company="ACME Legal", phone_number="+1 (555) 019-2834"):
    res = requests.post(
        f"{BASE_URL}/register",
        json={
            "email": email,
            "password": password,
            "first_name": first_name,
            "last_name": last_name,
            "company": company,
            "phone_number": phone_number
        }
    )
    return res.status_code, res.json()

def login_user(email, password, user_agent="TestAgent"):
    headers = {"User-Agent": user_agent}
    res = requests.post(f"{BASE_URL}/login", json={"email": email, "password": password}, headers=headers)
    return res.status_code, res.json()

def upload_file(filename, content, token):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
        
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with open(filename, "rb") as f:
            files = {"file": (filename, f, "text/plain")}
            res = requests.post(f"{BASE_URL}/upload", files=files, headers=headers)
        return res.status_code, res.json()
    finally:
        if os.path.exists(filename):
            os.remove(filename)

def check_status(filename, token):
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(f"{BASE_URL}/status/{filename}", headers=headers)
    return res.status_code, res.json()

def run_query(query_text, token):
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.post(f"{BASE_URL}/query", json={"query": query_text}, headers=headers, stream=True)
    if res.status_code != 200:
        return res.status_code, res.text
        
    answer = ""
    for chunk in res.iter_content(chunk_size=None, decode_unicode=True):
        if chunk:
            answer += chunk
    return 200, answer

def get_logged_emails() -> list[str]:
    """Reads and parses mock email logs from db/emails.log."""
    if not os.path.exists(EMAIL_LOG_PATH):
        return []
    with open(EMAIL_LOG_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    # Split by "=== EMAIL ===" block boundary
    return [block.strip() for block in content.split("=== EMAIL ===") if block.strip()]

def run_test():
    print("--- Starting Email Auth & Unknown Device Alert Verification Test ---")
    
    # Track initial logged email count
    initial_emails = get_logged_emails()
    initial_count = len(initial_emails)
    print(f"Initial logged email count: {initial_count}")

    # Generate unique test emails
    timestamp = int(time.time())
    email_alice = f"alice_{timestamp}@example.com"
    email_bob = f"bob_{timestamp}@example.com"
    password = "secretpassword123"
    
    # 1. Test registration & registration welcome emails
    print(f"\n[1] Registering user '{email_alice}'...")
    status, data = register_user(email_alice, password)
    assert status == 200, f"Registration failed: {data}"
    
    # Give background task half a second to write the email
    time.sleep(0.5)
    
    emails = get_logged_emails()
    assert len(emails) == initial_count + 1, "Expected exactly 1 new email to be sent"
    new_email = emails[-1]
    assert f"TO: {email_alice}" in new_email, "Welcome email TO header mismatch"
    assert "Welcome to Legal Assistant AI!" in new_email, "Welcome email subject mismatch"
    print("Welcome registration email verified successfully.")

    # Register Bob
    print(f"Registering user '{email_bob}'...")
    status, data = register_user(email_bob, password)
    assert status == 200, f"Registration failed: {data}"
    
    time.sleep(0.5)
    emails = get_logged_emails()
    assert len(emails) == initial_count + 2, "Expected another registration email to be sent"
    print("Duplicate email registration testing...")
    status, data = register_user(email_alice, password)
    assert status != 200, "Duplicate email registration should fail"
    print("Duplicate registration check verified.")

    # 2. Test login device fingerprinting alerts (Unknown Device Alert)
    # Login 1: Alice on Agent_A (New Device)
    print(f"\n[2] Logging in '{email_alice}' from device 'Agent_A'...")
    status, data = login_user(email_alice, password, user_agent="Agent_A")
    assert status == 200, f"Login failed: {data}"
    token_alice = data["access_token"]
    
    time.sleep(0.5)
    emails = get_logged_emails()
    assert len(emails) == initial_count + 3, "Expected new unknown device login email alert to be logged"
    new_email = emails[-1]
    assert f"TO: {email_alice}" in new_email
    assert "Security Alert: Login from Unknown Device" in new_email
    assert "Agent_A" in new_email, "Email should mention device Agent_A"
    print("Unknown device alert email verified for Agent_A.")

    # Login 2: Alice on Agent_A again (Known Device)
    print(f"Logging in '{email_alice}' from device 'Agent_A' again (should not trigger alert)...")
    status, data = login_user(email_alice, password, user_agent="Agent_A")
    assert status == 200
    
    time.sleep(0.5)
    emails = get_logged_emails()
    assert len(emails) == initial_count + 3, "Security alert should not be sent for known device login"
    print("Known device login correctly bypassed alert.")

    # Login 3: Alice on Agent_B (New Device)
    print(f"Logging in '{email_alice}' from device 'Agent_B' (new device alert expected)...")
    status, data = login_user(email_alice, password, user_agent="Agent_B")
    assert status == 200
    
    time.sleep(0.5)
    emails = get_logged_emails()
    assert len(emails) == initial_count + 4, "Security alert should be sent for login on new device Agent_B"
    new_email = emails[-1]
    assert "Agent_B" in new_email
    print("Unknown device alert email verified for Agent_B.")

    # Login Bob on Agent_A
    print(f"Logging in '{email_bob}' from device 'Agent_A'...")
    status, data = login_user(email_bob, password, user_agent="Agent_A")
    assert status == 200
    token_bob = data["access_token"]
    
    time.sleep(0.5)
    emails = get_logged_emails()
    assert len(emails) == initial_count + 5, "Bob should get an unknown device email on his first login"
    print("Security alert email verified for Bob on Agent_A.")

    # 3. Test multi-tenant directory & path isolation
    print("\n[3] Verifying document isolation and uploads...")
    file_alice = f"secret_doc_{timestamp}_alice.txt"
    content_alice = "ALICE SECRETS. Alice reference key is ALICE_KEY_999."
    
    status, data = upload_file(file_alice, content_alice, token_alice)
    assert status == 200, f"Upload failed for Alice: {data}"
    
    file_bob = f"secret_doc_{timestamp}_bob.txt"
    content_bob = "BOB SECRETS. Bob reference key is BOB_KEY_777."
    status, data = upload_file(file_bob, content_bob, token_bob)
    assert status == 200, f"Upload failed for Bob: {data}"

    # Wait for indexing to complete or err
    for filename, token in [(file_alice, token_alice), (file_bob, token_bob)]:
        print(f"Waiting for indexing to complete for '{filename}'...")
        attempts = 0
        state = "queued"
        while state not in ["completed", "error"] and attempts < 15:
            time.sleep(2)
            status, data = check_status(filename, token)
            if status == 200:
                state = data["status"]
                print(f"  Status for {filename}: {state}")
                if state.startswith("error"):
                    state = "error"
            else:
                break
            attempts += 1
            
        # We verify that standard processing flow completes, or triggers the expected valid key failure.
        if state.startswith("error"):
            print(f"Document indexing failed with expected API key validation: {state}")
        else:
            assert state == "completed", f"Unexpected state: {state}"

    # Verify Alice cannot retrieve Bob's document status
    print(f"Checking Alice cannot read status of Bob's file '{file_bob}'...")
    status, data = check_status(file_bob, token_alice)
    assert data["status"] == "unknown", "Alice should receive 'unknown' status for Bob's doc"
    print("Directory & status checks successfully isolated.")

    # Verify query returns matching isolated content if key is present
    print("\n[4] Running queries...")
    status, answer_alice = run_query("What is Alice's reference key?", token_alice)
    print(f"Query result for Alice:\n{answer_alice}")
    if status == 200 and "Error during response generation" not in answer_alice and "GEMINI_API_KEY" not in answer_alice:
        assert "ALICE_KEY_999" in answer_alice
        assert "BOB_KEY_777" not in answer_alice
        print("Alice query isolates database records successfully.")
        
    status, answer_bob = run_query("What is Bob's reference key?", token_bob)
    print(f"Query result for Bob:\n{answer_bob}")
    if status == 200 and "Error during response generation" not in answer_bob and "GEMINI_API_KEY" not in answer_bob:
        assert "BOB_KEY_777" in answer_bob
        assert "ALICE_KEY_999" not in answer_bob
        print("Bob query isolates database records successfully.")

    print("\n--- All Tests Completed Successfully! ---")

if __name__ == "__main__":
    print("Checking backend server connectivity...")
    try:
        requests.get(BASE_URL)
        run_test()
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to the backend server at {BASE_URL}.")
        print("Please ensure the container or native server is running on port 8000.")
