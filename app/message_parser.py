"""
MAZAO GUARD - Message Parser
Converts farmer messages like "North corner 28 71 490" into structured data
"""

import re
from typing import Dict, List

class MessageParser:
    """
    Parses natural language input from farmers
    """
    
    BAG_INDICATORS = ['bag', 'section', 'corner', 'side', 'pile', 'stack']
    
    @classmethod
    def parse(cls, message: str, known_bags: List[str]) -> Dict:
        """
        Parse a farmer's message into structured data.
        """
        message = message.lower().strip()
        
        # Remove common command words
        for word in ['add', 'record', 'log', 'reading', 'new']:
            message = message.replace(word, '')
        
        message = ' '.join(message.split())
        
        bag_name = None
        # Try to match known bag names
        for bag in known_bags:
            bag_lower = bag.lower()
            if bag_lower in message:
                bag_name = bag
                message = message.replace(bag_lower, '')
                break
        
        # If no known bag, try heuristic
        if not bag_name:
            words = message.split()
            for i, word in enumerate(words):
                if word in cls.BAG_INDICATORS and i+1 < len(words):
                    bag_name = words[i+1]
                    message = ' '.join(words[:i] + words[i+2:])
                    break
        
        # Extract numbers
        numbers = re.findall(r'(\d+(?:\.\d+)?)', message)
        numbers = [float(n) for n in numbers]
        
        if len(numbers) < 2:
            return {
                'success': False,
                'error': 'not_enough_numbers',
                'message': 'Please provide temperature and humidity. Example: "North corner 28 71"'
            }
        
        if len(numbers) > 3:
            numbers = numbers[:3]
        
        result = {
            'success': True,
            'bag_name': bag_name,
            'temperature': numbers[0],
            'humidity': numbers[1],
            'co2': numbers[2] if len(numbers) > 2 else None
        }
        
        # Validate
        if result['temperature'] < 0 or result['temperature'] > 50:
            result['success'] = False
            result['message'] = 'Temperature should be between 0°C and 50°C'
        elif result['humidity'] < 0 or result['humidity'] > 100:
            result['success'] = False
            result['message'] = 'Humidity should be between 0% and 100%'
        elif result['co2'] and (result['co2'] < 300 or result['co2'] > 2000):
            result['success'] = False
            result['message'] = 'CO2 should be between 300 and 2000 ppm'
        
        return result
    
    @classmethod
    def parse_setup(cls, message: str) -> Dict:
        """
        Parse a message for setting up a new bag.
        Example: "new bag north corner"
        """
        message = message.lower().strip()
        for word in ['new', 'add', 'create', 'setup', 'register']:
            message = message.replace(word, '')
        for word in cls.BAG_INDICATORS:
            message = message.replace(word, '')
        bag_name = ' '.join(message.split()).strip()
        if not bag_name:
            return {
                'success': False,
                'error': 'no_bag_name',
                'message': 'Please provide a name. Example: "new bag north corner"'
            }
        bag_name = ' '.join(word.capitalize() for word in bag_name.split())
        return {
            'success': True,
            'bag_name': bag_name
        }