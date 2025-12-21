#!/usr/bin/env python3
"""
Patch for PyTorch 2.6+ weights_only compatibility.
This script patches lightning_fabric and pytorch_lightning to use weights_only=False 
for loading checkpoints that contain omegaconf objects (used by pyannote).
"""
import sys
from pathlib import Path

def get_site_packages():
    """Get the site-packages directory."""
    return Path(sys.prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"

def patch_file(file_path, old_pattern, new_pattern, description):
    """Generic function to patch a file."""
    if not file_path.exists():
        print(f"Warning: {file_path} not found, skipping")
        return False
    
    content = file_path.read_text()
    
    if new_pattern in content:
        print(f"{file_path.name}: already patched")
        return True
    
    if old_pattern in content:
        content = content.replace(old_pattern, new_pattern)
        file_path.write_text(content)
        print(f"{file_path.name}: {description}")
        return True
    else:
        print(f"Warning: Pattern not found in {file_path.name}")
        return False

def patch_cloud_io():
    """Patch lightning_fabric/utilities/cloud_io.py"""
    site_packages = get_site_packages()
    cloud_io_path = site_packages / "lightning_fabric" / "utilities" / "cloud_io.py"
    
    # Try with comma first, then without
    success = patch_file(
        cloud_io_path,
        "weights_only: Optional[bool] = None,",
        "weights_only: Optional[bool] = False,",
        "Changed weights_only default from None to False"
    )
    if not success:
        success = patch_file(
            cloud_io_path,
            "weights_only: Optional[bool] = None",
            "weights_only: Optional[bool] = False",
            "Changed weights_only default from None to False"
        )
    return success

def patch_saving():
    """Patch pytorch_lightning/core/saving.py"""
    site_packages = get_site_packages()
    saving_path = site_packages / "pytorch_lightning" / "core" / "saving.py"
    
    return patch_file(
        saving_path,
        "weights_only: Optional[bool] = None,",
        "weights_only: Optional[bool] = False,",
        "Changed weights_only default from None to False"
    )

def patch_module():
    """Patch pytorch_lightning/core/module.py"""
    site_packages = get_site_packages()
    module_path = site_packages / "pytorch_lightning" / "core" / "module.py"
    
    return patch_file(
        module_path,
        "weights_only: Optional[bool] = None,",
        "weights_only: Optional[bool] = False,",
        "Changed weights_only default from None to False"
    )

def main():
    print("Patching PyTorch Lightning for PyTorch 2.6+ compatibility...")
    print("=" * 60)
    
    results = []
    
    # Patch all relevant files
    results.append(("lightning_fabric/cloud_io.py", patch_cloud_io()))
    results.append(("pytorch_lightning/saving.py", patch_saving()))
    results.append(("pytorch_lightning/module.py", patch_module()))
    
    print("=" * 60)
    print("Patch summary:")
    for name, success in results:
        status = "✓" if success else "✗"
        print(f"  {status} {name}")
    
    # Return success if at least the cloud_io was patched (main one)
    return results[0][1]

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
