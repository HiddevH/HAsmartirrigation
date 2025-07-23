import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), 'custom_components'))
from smart_irrigation.weathermodules.KNMIClient import KNMIClient

sample_response = {
    'liveweer': [{'lv': 82, 'luchtd': 1012.72, 'dauwp': 15.7}],
    'wk_verw': [
        {'max_temp': 16, 'min_temp': 16, 'windms': 3, 'neersl_perc_dag': 0},
        {'max_temp': 24, 'min_temp': 14, 'windms': 3, 'neersl_perc_dag': 0}
    ]
}

client = KNMIClient('test', '1.0', 52.0910879, 5.1124231, 10, weerlive_api_key='demo')
client._current_conditions = sample_response['liveweer'][0]
forecast_data = client._parse_weerlive_forecast(sample_response)
print('Forecast data:', forecast_data)
if forecast_data:
    print('First day:', forecast_data[0])
