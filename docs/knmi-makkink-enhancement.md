# KNMI Weather Integration for Netherlands Users 🇳🇱

## Introduction

The KNMI weather integration provides Netherlands users with enhanced evapotranspiration calculations using professional-grade Makkink reference evapotranspiration data from the Royal Netherlands Meteorological Institute (KNMI). This integration combines the accuracy of official meteorological data with reliable fallback mechanisms to ensure optimal irrigation management.

## Key Features

### Enhanced Evapotranspiration Accuracy

- **Makkink Method**: Uses the same professional-grade evapotranspiration calculations employed by Dutch agricultural professionals
- **Climate-Specific**: Calibrated specifically for Netherlands climate conditions
- **Official Data Source**: Direct integration with KNMI's EV24 dataset

### Comprehensive Weather Coverage

- **Current Observations**: Real-time weather data from KNMI observation stations
- **Professional ET Data**: Daily Makkink evapotranspiration values with 1-day processing delay
- **Forecast Integration**: Optional 5-day forecasts via Weerlive.nl API
- **Intelligent Fallbacks**: Automatic PyETO calculations when Makkink data is unavailable

### Reliability & Performance

- **Zero Breaking Changes**: Fully compatible with existing Smart Irrigation configurations
- **Transparent Operation**: Clear logging indicates which data sources and calculation methods are active
- **Optimized API Usage**: Efficient data retrieval aligned with KNMI's data availability patterns

## Data Sources Comparison

| Data Source | Accuracy for NL | Data Type | Update Frequency | Calibration |
|-------------|----------------|-----------|------------------|-------------|
| **KNMI Makkink** | ⭐⭐⭐⭐⭐ | Professional ET | Daily | Netherlands-specific |
| **KNMI Observations** | ⭐⭐⭐⭐⭐ | Current weather | Real-time | Netherlands stations |
| **Weerlive.nl Forecasts** | ⭐⭐⭐⭐ | 5-day forecast | Regular updates | Netherlands-focused |
| **PyETO Fallback** | ⭐⭐⭐⭐ | Calculated ET | Real-time | Universal FAO-56 |

## Installation & Setup

### Prerequisites

**Geographic Requirements:**

- Location within Netherlands territory for optimal KNMI station coverage

**Required API Keys:**

- **KNMI API Key**: Obtain from [KNMI Data Platform](https://dataplatform.knmi.nl/) (required)
- **Weerlive.nl API Key**: Obtain from [Weerlive.nl](https://weerlive.nl/weerlive_api_v2.php) (optional, for enhanced forecasts)

**System Requirements:**

- Smart Irrigation integration with KNMI weather service support

### Configuration Steps

#### 1. Basic KNMI Configuration

In Smart Irrigation configuration:

- **Weather Service**: Select "KNMI"
- **KNMI API Key**: Enter your KNMI Data Platform API key
- **Calculation Module**: Select "KNMI" for Makkink ET calculations
- **Sensor Group**: Configure weather parameters (temperature, wind, pressure, humidity, etc.)

#### 2. Enhanced Forecast Configuration (Optional)

To enable Netherlands-specific forecasts:

- **Weerlive.nl API Key**: Enter your Weerlive.nl API key in the optional field
- Leave blank to use observations-only mode

#### 3. Calculation Module Options

| Module | Use Case | Calculation Method | Recommended For |
|--------|----------|-------------------|-----------------|
| **KNMI** | Netherlands users | Makkink ET + PyETO fallback | Primary choice for NL |
| **PyETO** | Global usage | Traditional Penman-Monteith | Non-NL locations |
| **Passthrough** | Direct ET values | Weather service ET | Special configurations |

### Data Flow & Processing

**Primary Operation Mode:**

1. **Weather Observations**: Real-time data from nearest KNMI station
2. **Makkink ET Retrieval**: Yesterday's professional ET data from EV24 dataset
3. **Forecast Integration**: 5-day Netherlands weather forecasts (if Weerlive.nl configured)
4. **Intelligent Processing**: Combines data sources with automatic quality validation

**Fallback Operation Mode:**

1. **PyETO Calculations**: Standard evapotranspiration calculations using real-time weather data
2. **Automatic Activation**: Triggered when Makkink data unavailable
3. **Seamless Transition**: No user intervention required

## Timing Optimization for Makkink Data

### Understanding KNMI Data Availability

KNMI's Makkink evapotranspiration data follows a specific processing schedule that affects optimal configuration timing:

- **Data Processing Delay**: Makkink ET values are calculated and published with a 1-day delay
- **Availability Pattern**: Yesterday's Makkink data becomes available today
- **Update Schedule**: New data typically available in early morning hours

### Timing Configuration Impact

The choice of calculation timing significantly affects data freshness and irrigation accuracy:

**Suboptimal: Evening Calculations (23:00)**

- Uses day-before-yesterday's Makkink ET data
- Results in 2-day-old evapotranspiration information
- Morning irrigation based on outdated plant water loss data

**Optimal: Early Morning Calculations (06:00)**

- Uses yesterday's actual Makkink ET data
- Provides 1-day-old evapotranspiration information (freshest available)
- Morning irrigation based on recent plant water loss data

### Recommended Configuration Sequence

For optimal KNMI Makkink data utilization:

1. **05:00** - Weather data update (retrieves yesterday's Makkink ET)
2. **06:00** - Irrigation calculation (uses fresh Makkink data)
3. **06:00+** - Irrigation execution (based on yesterday's actual evapotranspiration)
4. **23:00** - Data cleanup (removes outdated weather data)

### Update Frequency Considerations

#### Daily Updates (Recommended)

- Single API call per day
- Aligned with KNMI's daily Makkink data release schedule
- Most efficient use of API resources

#### Hourly Updates (Functional but Inefficient)

- 24 API calls for the same daily Makkink value
- No data freshness advantage
- Higher API usage without benefit

### Establishing Correct Timing

To align updates with optimal timing:

1. **Configure Update Time**: Set the daily update time to 05:00 in Smart Irrigation configuration
2. **Set Update Frequency**: Configure 24-hour (daily) update frequency
3. **Configure Calculation Time**: Set irrigation calculations to run at 06:00 or later
4. **Verify Operation**: Monitor logs to confirm Makkink data availability during calculations

The system will automatically update weather data at your configured time each day, ensuring fresh Makkink ET data is available for morning irrigation calculations.

### Implementation Notes

#### Smart Irrigation Timing Control

Smart Irrigation provides precise control over update timing through its configuration interface:

- **Daily Update Time**: Configurable to any time (recommended: 05:00)
- **Update Frequency**: Set to 24 hours for daily updates
- **Calculation Timing**: Independent scheduling for irrigation calculations
- **Automatic Execution**: No manual restarts required
