#!/usr/bin/env python3
"""Test script to verify Weerlive.nl API response parsing."""

import json
import sys
import os

# Add the custom_components path to allow imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'custom_components'))

# Import the client
from smart_irrigation.weathermodules.KNMIClient import KNMIClient

# Sample API response from the user
sample_response = {
    "liveweer": [
        {
            "plaats": "Hilversum",
            "timestamp": 1753301883,
            "time": "23-07-2025 22:18:03",
            "temp": 19,
            "gtemp": 18.5,
            "samenv": "Zwaar bewolkt",
            "lv": 82,
            "windr": "NNW",
            "windrgr": 313.7,
            "windms": 1.6,
            "windbft": 2,
            "windknp": 3.1,
            "windkmh": 5.8,
            "luchtd": 1012.72,
            "ldmmhg": 760,
            "dauwp": 15.7,
            "zicht": 49900,
            "gr": 0,
        }
    ],
    "wk_verw": [
        {
            "dag": "23-07-2025",
            "image": "halfbewolkt",
            "max_temp": 16,
            "min_temp": 16,
            "windbft": 2,
            "windkmh": 10,
            "windknp": 6,
            "windms": 3,
            "windrgr": 345,
            "windr": "NW",
            "neersl_perc_dag": 0,
            "zond_perc_dag": 100
        },
        {
            "dag": "24-07-2025",
            "image": "halfbewolkt",
            "max_temp": 24,
            "min_temp": 14,
            "windbft": 2,
            "windkmh": 10,
            "windknp": 6,
            "windms": 3,
            "windrgr": 287,
            "windr": "W",
            "neersl_perc_dag": 0,
            "zond_perc_dag": 78
        },
        {
            "dag": "25-07-2025",
            "image": "halfbewolkt",
            "max_temp": 23,
            "min_temp": 16,
            "windbft": 2,
            "windkmh": 7,
            "windknp": 4,
            "windms": 2,
            "windrgr": 307,
            "windr": "NW",
            "neersl_perc_dag": 0,
            "zond_perc_dag": 64
        },
        {
            "dag": "26-07-2025",
            "image": "halfbewolkt",
            "max_temp": 26,
            "min_temp": 14,
            "windbft": 2,
            "windkmh": 10,
            "windknp": 6,
            "windms": 3,
            "windrgr": 289,
            "windr": "W",
            "neersl_perc_dag": 0,
            "zond_perc_dag": 77
        },
        {
            "dag": "27-07-2025",
            "image": "halfbewolkt",
            "max_temp": 23,
            "min_temp": 15,
            "windbft": 2,
            "windkmh": 10,
            "windknp": 6,
            "windms": 3,
            "windrgr": 296,
            "windr": "W",
            "neersl_perc_dag": 0,
            "zond_perc_dag": 33
        }
    ],
    "api": [
        {
            "bron": "Bron: Weerdata KNMI/NOAA via Weerlive.nl",
            "max_verz": 300,
            "rest_verz": 299
        }
    ]
}

def test_parsing():
    """Test the parsing of Weerlive.nl API response."""
    print("Testing Weerlive.nl API response parsing...")
    
    # Create a minimal client instance (we won't actually call APIs)
    client = KNMIClient(
        api_key="test_key",
        api_version="1.0", 
        latitude=52.0910879,
        longitude=5.1124231,
        elevation=10,
        weerlive_api_key="demo"
    )
    
    # Store current conditions from the response
    client._current_conditions = sample_response['liveweer'][0]
    
    # Test the parsing function
    forecast_data = client._parse_weerlive_forecast(sample_response)
    
    if forecast_data:
        print(f"✅ Successfully parsed {len(forecast_data)} forecast days")
        
        for i, day in enumerate(forecast_data):
            print(f"\nDay {i+1} raw data: {day}")
            print(f"  Temperature: {day.get('Temperature', 'N/A')}°C")
            print(f"  Max Temp: {day.get('Maximum Temperature', 'N/A')}°C")
            print(f"  Min Temp: {day.get('Minimum Temperature', 'N/A')}°C") 
            print(f"  Wind Speed: {day.get('Windspeed', 'N/A')} m/s")
            print(f"  Humidity: {day.get('Humidity', 'N/A')}%")
            print(f"  Pressure: {day.get('Pressure', 'N/A')} hPa")
            print(f"  Precipitation: {day.get('Precipitation', 'N/A')} mm")
            print(f"  Dew Point: {day.get('Dewpoint', 'N/A')}°C")
            
        print("\n✅ Weerlive.nl parsing test completed successfully!")
        return True
    else:
        print("❌ Failed to parse forecast data")
        return False

if __name__ == "__main__":
    success = test_parsing()
    sys.exit(0 if success else 1)
