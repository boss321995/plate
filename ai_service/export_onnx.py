import os
from ultralytics import YOLO

print("🚀 Starting ONNX Model Export for CPU Acceleration...")

def export_model(model_name):
    if not os.path.exists(model_name):
        print(f"⚠️ Warning: Model '{model_name}' not found. Skipping.")
        return
        
    print(f"\n📦 Loading '{model_name}'...")
    try:
        model = YOLO(model_name)
        # Export the model to ONNX format. 
        # opset=12 is widely supported.
        print(f"⚙️ Exporting to ONNX format (this may take a minute)...")
        export_path = model.export(format="onnx", opset=12)
        print(f"✅ Success! Exported to: {export_path}")
    except Exception as e:
        print(f"❌ Error exporting '{model_name}': {e}")

if __name__ == "__main__":
    # 1. Export Vehicle Detector (yolov8n.pt)
    export_model("yolov8n.pt")
    
    # 2. Export Plate Detector (plate_detect.pt) if it exists
    export_model("plate_detect.pt")
    
    print("\n🎉 All exports completed. You can now use .onnx models in your server!")
