import csv
import json
import random
import os
from typing import List, Dict, Optional
from anthropic import Anthropic
from pathlib import Path


class ScenePlanningAgent:
    """
    Scene Planning Agent: Parse natural language descriptions and plan scene compositions.
    """
    
    def __init__(self):
        # Initialize Anthropic client
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("Missing ANTHROPIC_API_KEY environment variable")
        
        self.client = Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"
        
        # Get project root (2 levels up from scene_planning_agent/core.py)
        self.project_root = Path(__file__).parent.parent.parent
        
        # System prompt for parsing
        self.system_prompt = """Extract objects and quantities from the scene description.

For quantities: 
1. if a number is mentioned, use it;
2. if a number is not mentioned, but a word like 'few', 'several', or 'many' is used, use a reasonable estimate (e.g., 'few' = 3);
3. if no quantity is mentioned, make your best guess based on common sense. Otherwise, default to 1.

Output JSON format:
{
    "objects": [
        {"name": "house", "quantity": 1},
        {"name": "tree", "quantity": 4}
    ]
}

Only include what's explicitly mentioned. Keep it simple."""

    def parse_description(self, description: str) -> dict:
        """Parse natural language description into structured format."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            system=self.system_prompt,
            messages=[{"role": "user", "content": description}]
        )
        
        # Extract JSON from response
        content = response.content[0].text
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0]
        else:
            json_str = content
            
        return json.loads(json_str.strip())
    
    def load_assets_csv(self, csv_path: str) -> Dict[str, List[Dict]]:
        """Load assets.csv and organize by tag."""
        # Handle both absolute and relative paths
        if not os.path.isabs(csv_path):
            # If relative path, make it relative to project root
            csv_path = self.project_root / csv_path
        
        csv_path = Path(csv_path)
        
        if not csv_path.exists():
            raise FileNotFoundError(f"Assets CSV not found at: {csv_path}")
        
        assets_by_tag = {}
        
        with open(csv_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                tag = row['tag']
                if tag not in assets_by_tag:
                    assets_by_tag[tag] = []
                assets_by_tag[tag].append({
                    'file_path': row['file path'],
                    'file_name': row['file name']
                })
        
        return assets_by_tag
    
    def generate_combinations(self, config: dict, assets_by_tag: Dict[str, List[Dict]], 
                            num_combinations: int = 10) -> Optional[List[Dict]]:
        """Generate asset combinations based on configuration."""
        # Verify required objects
        missing_assets = []
        for obj in config['objects']:
            if obj['name'] not in assets_by_tag:
                missing_assets.append(obj['name'])
        
        if missing_assets:
            return {
                "error": f"Missing asset types: {', '.join(missing_assets)}",
                "missing_assets": missing_assets
            }
        
        combinations = []
        
        # Generate combinations
        for i in range(num_combinations):
            combo = {
                'combination_id': i + 1,
                'objects': []
            }
            
            for obj in config['objects']:
                available = assets_by_tag[obj['name']]
                selected = random.choices(available, k=obj['quantity'])
                
                for idx, file_info in enumerate(selected):
                    # Special case: if object type is 'house' and quantity is 1, use 'house' as instance_id
                    if obj['name'] == 'house' and obj['quantity'] == 1:
                        instance_id = 'house'
                    else:
                        instance_id = f"{obj['name']}_{idx + 1}"
                    
                    combo['objects'].append({
                        'type': obj['name'],
                        'instance_id': instance_id,
                        'file_path': file_info['file_path'],
                        'file_name': file_info['file_name']
                    })
            
            combinations.append(combo)
        
        return combinations
    
    def plan_scene(self, description: str, assets_csv_path: str, 
                   num_combinations) -> dict:
        """
        Parse description and generate scene combinations.
        """
        try:
            # Step 1: Parse natural language description
            config = self.parse_description(description)
            
            # Step 2: Load available assets
            assets_by_tag = self.load_assets_csv(assets_csv_path)
            
            # Step 3: Generate combinations
            combinations = self.generate_combinations(
                config, assets_by_tag, num_combinations
            )
            
            # Check if error occurred
            if isinstance(combinations, dict) and "error" in combinations:
                return {
                    "success": False,
                    "error": combinations["error"],
                    "parsed_config": config,
                    "missing_assets": combinations.get("missing_assets", [])
                }
            
            return {
                "success": True,
                "parsed_config": config,
                "total_combinations": len(combinations),
                "combinations": combinations
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }