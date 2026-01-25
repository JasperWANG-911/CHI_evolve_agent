import bpy
import socket
import threading
import json
import queue
import time

# global message queue for inter-thread communication
message_queue = queue.Queue()
server_running = False

def execute_code_safe(code):
    """Execute code and return result"""
    try:
        namespace = {'bpy': bpy, '_result': None}
        exec(code, namespace)
        
        if '_result' in namespace and namespace['_result'] is not None:
            return {
                'status': 'success',
                'error': None,
                'data': namespace['_result']
            }
        else:
            return {'status': 'success', 'error': None}
    except Exception as e:
        return {'status': 'error', 'error': str(e)}

def server_thread_func(port=8089):
    """Server thread function"""
    global server_running
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.settimeout(0.5)
    server.bind(('localhost', port))
    server.listen(1)
    server_running = True
    
    print(f"Blender server started on port {port}")
    
    while server_running:
        try:
            client, address = server.accept()
            
            # Receive data
            data = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk
                if len(chunk) < 4096:
                    break
            
            code = data.decode('utf-8')
            
            # Put in queue for main thread to process
            response_queue = queue.Queue()
            message_queue.put({
                'code': code,
                'response_queue': response_queue
            })
            
            # Wait for response (with timeout)
            try:
                result = response_queue.get(timeout=30)
            except queue.Empty:
                result = {'status': 'error', 'error': 'Execution timeout'}
            
            # Send response
            client.send(json.dumps(result).encode('utf-8'))
            client.close()
            
        except socket.timeout:
            continue
        except Exception as e:
            if server_running:
                print(f"Server error: {e}")
    
    server.close()
    print("Server stopped")

def process_messages():
    """Process pending messages - called by timer"""
    try:
        # Process one message per call to avoid blocking
        if not message_queue.empty():
            msg = message_queue.get_nowait()
            code = msg['code']
            response_queue = msg['response_queue']
            
            # Execute code
            result = execute_code_safe(code)
            
            # Send result back
            response_queue.put(result)
    except queue.Empty:
        pass
    except Exception as e:
        print(f"Error processing message: {e}")
    
    # Keep the timer running
    return 0.05  # Check every 50ms

# Start everything when the script runs
if __name__ == "__main__":
    print("Starting Blender Code Server...")
    
    # Start server thread
    thread = threading.Thread(target=server_thread_func)
    thread.daemon = True
    thread.start()
    
    # Register timer to process messages
    if hasattr(bpy.app.timers, 'is_registered'):
        if not bpy.app.timers.is_registered(process_messages):
            bpy.app.timers.register(process_messages)
    else:
        # Older Blender versions
        bpy.app.timers.register(process_messages)
    
    print("Server is running. Blender GUI should remain responsive.")
    
    # In GUI mode, we don't need to keep the script running
    # The timer will keep everything working