import numpy as np
import os
from PIL import Image
from hbit.encoders.dct import encode_dct, decode_dct
from hbit.core.sync import wrap_payload_with_sync, find_payload_boundaries
import hbit.core.accelerator as accel

def test_dct_jnd_robustness():
    print(f"Accelerator: {accel.xp.__name__}")
    
    # 1. Create Smooth Gradient Image (Challenging for JND)
    width, height = 1024, 1024
    x = np.linspace(0, 255, width)
    y = np.linspace(0, 255, height)
    xv, yv = np.meshgrid(x, y)
    
    # Create a smooth pattern
    img_data = (xv + yv) / 2
    img_data = np.stack([img_data, img_data, img_data], axis=2).astype(np.uint8)
    
    img_path = "test_gradient.png"
    Image.fromarray(img_data).save(img_path)
    
    # 2. Payload
    raw_payload = "1" * 100
    wrapped = wrap_payload_with_sync(raw_payload)
    print(f"Payload Len: {len(wrapped)}")
    
    # 3. Embed with JND
    print("Embedding with JND=True...")
    try:
        res = encode_dct(
            img_data, 
            wrapped, 
            channel=1, 
            strength=30.0, 
            use_jnd=True  # ENABLED
        )
        print(f"Blocks Modified: {res.blocks_modified}")
        
    except Exception as e:
        print(f"Embedding Failed: {e}")
        return

    # 4. Save High Quality JPEG
    out_path = "test_gradient_jnd.jpg"
    out_img = Image.fromarray(res.encoded_image)
    out_img.save(out_path, "JPEG", quality=100)
    print("Saved Q=100 JPEG")

    # 5. Extract
    print("\n--- Extraction ---")
    data_loaded = np.array(Image.open(out_path).convert("RGB"))
    
    dec = decode_dct(data_loaded, channel=1, strength=30.0)
    
    # Search Sync
    boundaries = find_payload_boundaries(dec.payload_bits)
    if boundaries:
        print(f"SYNC FOUND: {boundaries}")
    else:
        print("SYNC NOT FOUND!")
        
        # Analyze why
        print("Debugging Extract Stream (First 100 chars):")
        print(dec.payload_bits[:100])
        
        if len(dec.payload_bits) < len(wrapped):
            print("Extracted bits too short!")

if __name__ == "__main__":
    test_dct_jnd_robustness()
