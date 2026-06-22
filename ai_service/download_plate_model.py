"""
ดาวน์โหลดโมเดลตรวจจับป้ายทะเบียนไทย (YOLOv8n) จาก Hugging Face
โมเดล: HurricaneOD - Thai License Plate Detector
ที่มา: https://huggingface.co/Rattatammanoon/hurricaneod-thai-plate-detector
"""
import os
import sys
import shutil

# Fix encoding for Windows terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("[*] Downloading Thai License Plate Detection Model...")
print("    Source: Rattatammanoon/hurricaneod-thai-plate-detector (HuggingFace)")
print()

try:
    from huggingface_hub import hf_hub_download
except ImportError:
    print("[*] Installing huggingface_hub...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub"])
    from huggingface_hub import hf_hub_download

# Download model from HuggingFace
print("[*] Downloading HurricaneOD_beta.pt (Thai plate model)...")
try:
    model_path = hf_hub_download(
        repo_id="Rattatammanoon/hurricaneod-thai-plate-detector",
        filename="HurricaneOD_beta.pt"
    )
    # Copy to current directory as plate_detect.pt
    dest = os.path.join(os.path.dirname(__file__) or ".", "plate_detect.pt")
    shutil.copy(model_path, dest)
    size_mb = os.path.getsize(dest) / (1024 * 1024)
    print(f"[OK] Downloaded! Saved as: plate_detect.pt ({size_mb:.1f} MB)")
    print()
    print("[*] Now convert to ONNX for faster inference:")
    print("    python export_onnx.py")
except Exception as e:
    print(f"[ERROR] Download failed: {e}")
    print()
    print("[HELP] Manual download:")
    print("  1. Go to: https://huggingface.co/Rattatammanoon/hurricaneod-thai-plate-detector")
    print("  2. Download 'HurricaneOD_beta.pt'")
    print("  3. Rename to 'plate_detect.pt' and place in this folder")

