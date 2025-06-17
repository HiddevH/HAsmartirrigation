#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

try:
    # Test basic import
    from custom_components.smart_irrigation.calcmodules.knmi import KNMI
    print('✅ KNMI module loads successfully')
    
    # Test class can be instantiated 
    knmi = KNMI(None, 'Test KNMI module', {})
    print('✅ KNMI module can be instantiated')
    print(f'Module name: {knmi.name}')
    
    # Test that it has the required methods
    print(f'Has calculate method: {hasattr(knmi, "calculate")}')
    
except Exception as e:
    print(f'❌ Error: {e}')
    import traceback
    traceback.print_exc()
