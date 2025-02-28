#!/usr/bin/env python3
from flask import Flask, Response, render_template, request
import cv2
import time
import threading
import numpy as np
import argparse
import socket
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variables
frame_buffer = None
buffer_lock = threading.Lock()
camera = None
camera_lock = threading.Lock()

app = Flask(__name__)

def get_ip_address():
    """Get the primary IP address of this machine"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't need to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def open_camera(device_path, fourcc=None, width=None, height=None):
    """Open camera with specific settings"""
    global camera
    
    with camera_lock:
        # Close existing camera if open
        if camera is not None and camera.isOpened():
            camera.release()
        
        # Create new VideoCapture
        camera = cv2.VideoCapture(device_path, cv2.CAP_V4L2)
        
        if not camera.isOpened():
            logger.error(f"Failed to open camera: {device_path}")
            return False
        
        # Set properties if specified
        if fourcc:
            fourcc_int = cv2.VideoWriter_fourcc(*fourcc)
            camera.set(cv2.CAP_PROP_FOURCC, fourcc_int)
            logger.info(f"Set fourcc to {fourcc}")
        
        if width and height:
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            logger.info(f"Set resolution to {width}x{height}")
        
        # Log camera properties
        actual_fourcc = int(camera.get(cv2.CAP_PROP_FOURCC))
        fourcc_str = "".join([chr((actual_fourcc >> 8 * i) & 0xFF) for i in range(4)])
        actual_width = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        logger.info(f"Camera configured with:")
        logger.info(f"- Device: {device_path}")
        logger.info(f"- FOURCC: {fourcc_str} ({actual_fourcc})")
        logger.info(f"- Resolution: {actual_width}x{actual_height}")
        
        return True

def camera_capture_thread(interval=0.1):
    """Background thread to continuously capture frames"""
    global frame_buffer, camera
    
    logger.info("Starting camera capture thread")
    
    consecutive_failures = 0
    while True:
        with camera_lock:
            if camera is None or not camera.isOpened():
                time.sleep(0.5)
                continue
                
            ret, frame = camera.read()
        
        if ret:
            consecutive_failures = 0
            with buffer_lock:
                frame_buffer = frame
        else:
            consecutive_failures += 1
            logger.warning(f"Frame capture failed ({consecutive_failures} consecutive failures)")
            
            if consecutive_failures >= 5:
                logger.error("Too many consecutive failures, attempting to reopen camera")
                with camera_lock:
                    device = camera.get(cv2.CAP_PROP_BACKEND)
                    camera.release()
                    camera = cv2.VideoCapture(device, cv2.CAP_V4L2)
                consecutive_failures = 0
        
        time.sleep(interval)

def generate_frames():
    """Generate MJPEG frames for streaming"""
    global frame_buffer
    
    while True:
        with buffer_lock:
            if frame_buffer is None:
                # If no frame is available, generate a black frame
                img = np.zeros((480, 640, 3), dtype=np.uint8)
                text = "Waiting for camera..."
                cv2.putText(img, text, (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            else:
                img = frame_buffer.copy()
        
        # Convert to JPEG for streaming
        ret, jpeg = cv2.imencode('.jpg', img)
        if not ret:
            continue
            
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        
        time.sleep(0.05)  # Limit frame rate

# Web routes
@app.route('/')
def index():
    """Render the main page"""
    with camera_lock:
        if camera is None or not camera.isOpened():
            camera_status = "Not connected"
            camera_info = {}
        else:
            camera_status = "Connected"
            camera_info = {
                "width": int(camera.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": camera.get(cv2.CAP_PROP_FPS),
                "format": int(camera.get(cv2.CAP_PROP_FOURCC))
            }
    
    # Get list of video devices
    import glob
    video_devices = sorted(glob.glob('/dev/video*'))
    
    return render_template('index.html', 
                          camera_status=camera_status,
                          camera_info=camera_info,
                          video_devices=video_devices)

@app.route('/stream')
def stream():
    """Stream MJPEG to browser"""
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/connect', methods=['POST'])
def connect_camera():
    """Connect to a camera with the specified settings"""
    device = request.form.get('device', '/dev/video0')
    fourcc = request.form.get('fourcc', '')
    width = request.form.get('width', '')
    height = request.form.get('height', '')
    
    # Convert to proper types
    width = int(width) if width.isdigit() else None
    height = int(height) if height.isdigit() else None
    fourcc = fourcc if fourcc else None
    
    success = open_camera(device, fourcc, width, height)
    if success:
        return "Camera connected successfully"
    else:
        return "Failed to connect to camera", 400

@app.route('/snapshot')
def snapshot():
    """Take a snapshot and return it as a downloadable image"""
    global frame_buffer
    
    with buffer_lock:
        if frame_buffer is None:
            return "No frame available", 400
        
        img = frame_buffer.copy()
    
    ret, jpeg = cv2.imencode('.jpg', img)
    if not ret:
        return "Failed to encode image", 500
    
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return Response(
        jpeg.tobytes(),
        mimetype="image/jpeg",
        headers={"Content-Disposition": f"attachment;filename=snapshot_{timestamp}.jpg"}
    )

def create_templates():
    """Create the HTML templates needed for the web interface"""
    import os
    
    # Create templates directory if it doesn't exist
    if not os.path.exists('templates'):
        os.makedirs('templates')
    
    # Create index.html template
    with open('templates/index.html', 'w') as f:
        f.write('''
<!DOCTYPE html>
<html>
<head>
    <title>Raspberry Pi Camera Stream</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            text-align: center;
            margin-bottom: 20px;
        }
        .video-container {
            background-color: #ddd;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
            text-align: center;
        }
        .video-stream {
            max-width: 100%;
            border: 1px solid #999;
        }
        .controls {
            background-color: white;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .status {
            margin-top: 20px;
            padding: 15px;
            background-color: white;
            border-radius: 5px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        select, input {
            width: 100%;
            padding: 8px;
            margin-bottom: 15px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        button {
            background-color: #4CAF50;
            color: white;
            padding: 10px 15px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            margin-right: 10px;
            margin-bottom: 10px;
        }
        button:hover {
            background-color: #45a049;
        }
        .snapshot-btn {
            background-color: #2196F3;
        }
        .snapshot-btn:hover {
            background-color: #0b7dda;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        table, th, td {
            border: 1px solid #ddd;
        }
        th, td {
            padding: 8px;
            text-align: left;
        }
        th {
            background-color: #f2f2f2;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Raspberry Pi Camera Stream</h1>
        </div>
        
        <div class="video-container">
            <img src="{{ url_for('stream') }}" class="video-stream" alt="Camera Stream">
        </div>
        
        <div class="controls">
            <h2>Camera Controls</h2>
            <form action="{{ url_for('connect_camera') }}" method="post" id="camera-form">
                <label for="device">Camera Device:</label>
                <select name="device" id="device">
                    {% for device in video_devices %}
                    <option value="{{ device }}">{{ device }}</option>
                    {% endfor %}
                </select>
                
                <label for="fourcc">Format (FOURCC):</label>
                <select name="fourcc" id="fourcc">
                    <option value="BGR3">BGR3 (BGR 24-bit)</option>
                    <option value="YV12">YV12 (YUV 12-bit)</option>
                    <option value="MJPG">MJPG (Motion JPEG)</option>
                    <option value="YUYV">YUYV (YUV 4:2:2)</option>
                    <option value="">Default format</option>
                </select>
                
                <label for="width">Width:</label>
                <input type="number" name="width" id="width" placeholder="e.g., 640">
                
                <label for="height">Height:</label>
                <input type="number" name="height" id="height" placeholder="e.g., 480">
                
                <button type="submit">Connect Camera</button>
                <a href="{{ url_for('snapshot') }}"><button type="button" class="snapshot-btn">Take Snapshot</button></a>
            </form>
        </div>
        
        <div class="status">
            <h2>Camera Status</h2>
            <p><strong>Status:</strong> {{ camera_status }}</p>
            
            {% if camera_info %}
            <table>
                <tr>
                    <th>Property</th>
                    <th>Value</th>
                </tr>
                <tr>
                    <td>Resolution</td>
                    <td>{{ camera_info.width }} x {{ camera_info.height }}</td>
                </tr>
                <tr>
                    <td>FPS</td>
                    <td>{{ camera_info.fps }}</td>
                </tr>
                <tr>
                    <td>Format</td>
                    <td>{{ camera_info.format }}</td>
                </tr>
            </table>
            {% endif %}
        </div>
    </div>
    
    <script>
        document.getElementById('camera-form').addEventListener('submit', function(e) {
            e.preventDefault();
            
            // Get form data
            const formData = new FormData(this);
            
            // Submit form via AJAX
            fetch('{{ url_for('connect_camera') }}', {
                method: 'POST',
                body: formData
            })
            .then(response => response.text())
            .then(data => {
                alert(data);
                location.reload();
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Failed to connect to camera');
            });
        });
    </script>
</body>
</html>
        ''')

def main():
    parser = argparse.ArgumentParser(description='Raspberry Pi Camera Web Server')
    parser.add_argument('--port', type=int, default=8080, help='Port to run the server on')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to bind the server to')
    parser.add_argument('--device', type=str, default=None, help='Video device path (e.g., /dev/video14)')
    parser.add_argument('--fourcc', type=str, default=None, help='FOURCC code (e.g., BGR3, YV12)')
    parser.add_argument('--width', type=int, default=None, help='Desired frame width')
    parser.add_argument('--height', type=int, default=None, help='Desired frame height')
    
    args = parser.parse_args()
    
    # Create HTML templates
    create_templates()
    
    # Start camera if device specified
    if args.device:
        open_camera(args.device, args.fourcc, args.width, args.height)
    
    # Start background thread for capturing frames
    capture_thread = threading.Thread(target=camera_capture_thread, daemon=True)
    capture_thread.start()
    
    # Get IP address
    ip_address = get_ip_address()
    logger.info(f"Starting server at http://{ip_address}:{args.port}")
    
    # Run the Flask app
    app.run(host=args.host, port=args.port, debug=False, threaded=True)

if __name__ == "__main__":
    main()
