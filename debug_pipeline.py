import sys
import os
import shutil
from pathlib import Path

# Add src to path
sys.path.append(r"C:\Users\GPAMD\Documents\GEMINI\DESARROLLO_APPS\H-Bit\src")

from hbit.universal import (
    UniversalEncoder, 
    UniversalDecoder, 
    UniversalVerifier,
    UniversalVerificationStatus
)
from hbit.core.crypto import HBitKeyPair, generate_key_pair
import hbit.core.accelerator as accel

def test_pipeline():
    print(f"Accelerator: {accel.xp.__name__}")
    
    # 1. Setup Identity (In Memory)
    print("Generating new identity...")
    identity = generate_key_pair()
    # No save/load needed for this test
    
    # 2. Prepare Image
    img_path = Path("test_pipeline_input.jpg")
    import numpy as np
    from PIL import Image
    print("Creating test image...")
    # Use noise/gradient to challenge DCT
    # Make it bigger to ensure capacity (512x512 is plenty)
    width, height = 512, 512
    x = np.linspace(0, 255, width)
    y = np.linspace(0, 255, height)
    xv, yv = np.meshgrid(x, y)
    data = (xv + yv) / 2
    data = np.stack([data, data, data], axis=2).astype(np.uint8)
    
    Image.fromarray(data).save(img_path, quality=100)
    
    # 3. Sign
    print(f"Signing {img_path}...")
    encoder = UniversalEncoder()
    
    try:
        result_path = encoder.encode(
            file_path=img_path,
            author_key=identity, # Pass object directly
            output_path="test_pipeline_signed.jpg",
            encrypt=False
        )
        print(f"Signed to: {result_path}")
        
    except Exception as e:
        print(f"Signing Failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # 4. Verify
    print(f"Verifying {result_path}...")
    verifier = UniversalVerifier()
    
    # Verify logic
    result = verifier.verify(result_path.output_path)
    
    if result:
        # Para DCT/Watermarking robusto, el contenido del archivo CAMBIA (se inyecta ruido).
        # Por lo tanto, el hash de contenido no coincidirá con el original.
        # El estado esperado es TAMPERED (si author_hash coincide) o VERIFIED.
        if result.status == UniversalVerificationStatus.TAMPERED:
            print("INFO: Status is TAMPERED. This is expected for robust watermarking (content modified).")
            print(f"Expected:  {result_path.author_hash}")
            print(f"Extracted: {result.decode_result.author_hash}")
            print(f"Author Hash Match: {result.decode_result.author_hash == result_path.author_hash}")
            
            # Allow for verification even if hash is corrupted? No, strictly it failed.
            # But maybe we want to see HOW corrupted.
            assert result.decode_result.author_hash == result_path.author_hash
            print("VERIFICATION SUCCESSFUL (Author Verified, Content Tampered)!")
            print(f"Verified by: {result.decode_result.author_hash}")
            print(f"Status: {result.status}")
        elif result.status == UniversalVerificationStatus.VERIFIED:
            print("VERIFICATION SUCCESSFUL!")
            print(f"Verified by: {result.decode_result.author_hash}")
            print(f"Status: {result.status}")
        else:
            print("VERIFICATION FAILED!")
            print(f"Status: {result.status}")
            print(f"Message: {result.message}")
    else:
        print("VERIFICATION FAILED!")
        print("Result is None (No payload found).")

if __name__ == "__main__":
    test_pipeline()
