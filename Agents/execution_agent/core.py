import socket
import json
import logging
import os
from pathlib import Path

class ExecutionAgent:
    """
    ExecutionAgent, to execute code in Blender.
    """
    
    def __init__(self, host='localhost', port=8089, timeout=1000):
        """
        initialize the ExecutionAgent. Need to run blender_server.py first.
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.logger = self._setup_logger()
        self.project_root = Path(__file__).parent.parent.parent
    
    def _setup_logger(self):
        """Set up the logger."""
        logger = logging.getLogger('ExecutionAgent')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def connect(self):
        """
        Establish a connection to Blender.
        """
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(self.timeout)
            client.connect((self.host, self.port))
            self.logger.info(f"Connected to: {self.host}:{self.port}")
            return client
        except Exception as e:
            self.logger.error(f"Failed to connect to Blender: {e}")
            raise ConnectionError(f"Unable to connect to Blender server: {e}")

    def execute_code(self, code):
        """
        Execute code in Blender.
        """
        client = None
        try:
            # Establish connection
            client = self.connect()

            # Send code
            self.logger.info("Sending code to Blender...")
            self.logger.debug(f"Code length: {len(code)} characters")
            client.send(code.encode('utf-8'))

            # Receive response with larger buffer
            self.logger.info("Waiting for Blender response...")
            response_parts = []
            while True:
                try:
                    part = client.recv(4096)
                    if not part:
                        break
                    response_parts.append(part.decode('utf-8'))
                    # Try to parse as JSON to see if we got complete response
                    try:
                        json.loads(''.join(response_parts))
                        break
                    except json.JSONDecodeError:
                        # Not complete yet, continue receiving
                        continue
                except socket.timeout:
                    self.logger.warning("Socket timeout while receiving response")
                    break
            
            response = ''.join(response_parts)
            
            # Parse JSON response
            result = json.loads(response)
            
            if result['status'] == 'success':
                self.logger.info("Code execution successful")
            else:
                self.logger.error(f"Code execution error: {result.get('error', 'Unknown error')}")
                
            return result
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decoding failed: {e}")
            self.logger.error(f"Raw response: {response if 'response' in locals() else 'No response received'}")
            return None
            
        except socket.timeout:
            self.logger.error("Socket timeout - execution took too long")
            return None
            
        except Exception as e:
            self.logger.error(f"Code execution failed: {e}")
            return None
            
        finally:
            # Ensure connection is closed
            if client:
                try:
                    client.close()
                    self.logger.info("Connection closed")
                except:
                    pass
    
    def test_connection(self):
        """
        Test connection to Blender server.
        """
        try:
            # Simple test code
            test_code = "import bpy"
            result = self.execute_code(test_code)
            return result is not None and result.get('status') == 'success'
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False
    
    def execute_codes_file(self, file_path: str, capture_views: bool = True):
        if not os.path.isabs(file_path):
            file_path = self.project_root / file_path
        
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Script not found: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()

        self.logger.info(f"Sending {file_path} to Blender")
        self.logger.info(f"Code preview (first 200 chars): {code[:200]}...")

        # Execute the main code
        result = self.execute_code(code)
        
        self.logger.info(f"Code being executed:\n{code[:500]}...")
        
        return result
    
    def execute_step_code(self, code: str, capture_views: bool = False):
        """Execute specific step code directly"""
        self.logger.info(f"Executing step code (length: {len(code)} chars)")
        self.logger.debug(f"Code preview: {code[:200]}...")
        
        # Execute the code
        result = self.execute_code(code)
        
        return result

# demo_usage:
if __name__ == "__main__":
    execution_agent = ExecutionAgent()

    if not execution_agent.test_connection():
        print("Cannot connect to Blender server. Please ensure it is running.")
    else:
        result = execution_agent.execute_codes_file("execution_code.py")
        # check status of result
        print("Execution result:", result)