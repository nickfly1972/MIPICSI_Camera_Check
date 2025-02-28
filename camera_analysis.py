#!/usr/bin/env python3
import cv2
import numpy as np
import time
import argparse

def capture_from_camera(device_path, fourcc=None, width=None, height=None, format_force=None):
    """
    Attempt to capture from a camera with specific settings
    
    Parameters:
    - device_path: Path to video device (e.g., /dev/video14)
    - fourcc: Four character code for video codec (e.g., 'BGR3', 'YV12')
    - width, height: Desired resolution
    - format_force: Force a specific pixel format
    """
    # Create VideoCapture object
    cap = cv2.VideoCapture(device_path, cv2.CAP_V4L2)
    
    if not cap.isOpened():
        print(f"Failed to open {device_path}")
        return False
    
    # Set properties if specified
    if fourcc:
        fourcc_int = cv2.VideoWriter_fourcc(*fourcc)
        cap.set(cv2.CAP_PROP_FOURCC, fourcc_int)
        print(f"Set fourcc to {fourcc} ({fourcc_int})")
    
    if width and height:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        print(f"Set resolution to {width}x{height}")
    
    # Get actual properties after setting
    actual_fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
    fourcc_str = "".join([chr((actual_fourcc >> 8 * i) & 0xFF) for i in range(4)])
    actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    print(f"Camera reports:")
    print(f"- FOURCC: {fourcc_str} ({actual_fourcc})")
    print(f"- Resolution: {actual_width}x{actual_height}")
    
    # Capture frame
    print("Attempting to capture frame...")
    for i in range(5):  # Try a few times
        ret, frame = cap.read()
        if ret:
            print(f"Successfully captured frame with shape {frame.shape}")
            
            # Save the image
            output_file = f"capture_{device_path.split('/')[-1]}.jpg"
            cv2.imwrite(output_file, frame)
            print(f"Saved frame to {output_file}")
            
            # Display basic frame info
            print(f"Frame dtype: {frame.dtype}")
            print(f"Frame min/max values: {np.min(frame)}/{np.max(frame)}")
            
            cap.release()
            return True
        
        print(f"Attempt {i+1} failed, trying again...")
        time.sleep(1)
    
    print("Failed to capture any frames after multiple attempts")
    cap.release()
    return False

def main():
    parser = argparse.ArgumentParser(description='Capture from Raspberry Pi camera')
    parser.add_argument('--device', type=str, required=True, help= "/dev/video14"#'Video device path (e.g., /dev/video14)')
    parser.add_argument('--fourcc', type=str, help= "BGR3" #'FOURCC code (e.g., BGR3, YV12)')
    parser.add_argument('--width', type=int, help= 640#'Desired frame width')
    parser.add_argument('--height', type=int, help= 480 #'Desired frame height')
    
    args = parser.parse_args()
    
    # Try with specified settings
    success = capture_from_camera(args.device, args.fourcc, args.width, args.height)
    
    if not success:
        print("\nInitial capture failed. Trying alternative settings...")
        
        # If BGR3 was specified but failed, try YV12 and vice versa
        if args.fourcc == 'BGR3':
            print("Trying with YV12 format instead of BGR3")
            capture_from_camera(args.device, 'YV12', args.width, args.height)
        elif args.fourcc == 'YV12':
            print("Trying with BGR3 format instead of YV12")
            capture_from_camera(args.device, 'BGR3', args.width, args.height)
        else:
            # Try both formats
            print("Trying with BGR3 format")
            capture_from_camera(args.device, 'BGR3', args.width, args.height)
            print("\nTrying with YV12 format")
            capture_from_camera(args.device, 'YV12', args.width, args.height)

if __name__ == "__main__":
    main()
