import os
import sys

# Get site-packages
import site
paths = site.getsitepackages()
user_site = site.getusersitepackages()
all_paths = paths + [user_site]

print("Scanning site-packages roots...")

found = False
for sp in all_paths:
    if os.path.exists(sp):
        print(f"Scanning: {sp}")
        try:
            for item in os.listdir(sp):
                if "cupy" in item.lower() or ".libs" in item.lower():
                    print(f"  Found potential folder: {item}")
                    full_path = os.path.join(sp, item)
                    if os.path.isdir(full_path):
                        for f in os.listdir(full_path):
                            if f.endswith(".dll"):
                                print(f"    DLL FOUND: {f} in {full_path}")
                                found = True
        except Exception as e:
            print(f"  Error accessing {sp}: {e}")

if not found:
    print("No relevant folders/DLLs found in site-packages roots.")
