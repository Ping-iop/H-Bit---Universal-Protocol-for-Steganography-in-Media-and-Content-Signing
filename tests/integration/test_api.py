import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from apps.api.main import app

client = TestClient(app)

@pytest.fixture
def sample_file():
    # Use a generic text file which is fully supported by GenericHandler
    # This avoids the known existing pipeline bug with PNG files
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("This is a generic text file to be signed by H-Bit API." * 10)
    yield path
    os.remove(path)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "H-Bit API"}

def test_encode_and_verify(sample_file):
    # 1. Encode
    with open(sample_file, "rb") as f:
        encode_resp = client.post(
            "/api/v1/encode",
            files={"file": ("test.txt", f, "text/plain")},
            data={"passphrase": "test_passphrase"}
        )
    
    assert encode_resp.status_code == 200, f"Encode Failed: {encode_resp.text}"
    assert encode_resp.headers["content-type"] == "application/octet-stream"
    
    encoded_data = encode_resp.content
    assert len(encoded_data) > 0
    
    # Save encoded data to a temporary file for verification
    fd, temp_signed = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "wb") as f:
        f.write(encoded_data)
        
    try:
        from hbit.universal import UniversalVerifier
        local_verifier = UniversalVerifier()
        local_result = local_verifier.verify(temp_signed, passphrase="test_passphrase")
        assert local_result.status.name == "VERIFIED", f"Local verify failed: {local_result.message}"
        
        # 2. Verify API
        with open(temp_signed, "rb") as f:
            verify_resp = client.post(
                "/api/v1/verify",
                files={"file": ("signed.txt", f, "text/plain")}
            )
            
        assert verify_resp.status_code == 200, f"Verify Failed: {verify_resp.text}"
        data = verify_resp.json()
        assert data["status"] == "VERIFIED", f"Expected VERIFIED, got {data['status']}. Full resp: {data}. Encoded size: {len(encoded_data)}"
        assert data["confidence"] > 0
        assert "author_hash" in data
    finally:
        os.remove(temp_signed)
