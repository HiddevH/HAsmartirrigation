# KNMI Makkink Enhancement for Netherlands Users 🇳🇱

## Overview

Smart Irrigation now provides **enhanced evapotranspiration accuracy for Netherlands users** through professional-grade Makkink calculations from the Royal Netherlands Meteorological Institute (KNMI), with automatic PyETO fallback for reliability.

**Key Benefits:**

- **Enhanced accuracy**: Climate-specific calculations calibrated for Dutch conditions
- **Professional grade**: Same data Dutch agricultural professionals use
- **Automatic fallback**: Uses PyETO when Makkink data unavailable
- **Zero breaking changes**: Works with existing configurations

## How It Works

The KNMI module intelligently combines two calculation methods:

1. **Primary**: Fetches yesterday's Makkink ET from KNMI's EV24 dataset (professional meteorological data)
2. **Fallback**: Uses proven PyETO calculations when Makkink data is unavailable
3. **Transparent**: Clear logging shows which calculation method is active

| Aspect | Makkink (KNMI) | PyETO (Fallback) |
|--------|----------------|------------------|
| **Accuracy for Netherlands** | ⭐⭐⭐⭐⭐ Excellent | ⭐⭐⭐⭐ Very Good |
| **Data source** | KNMI professional data | Real-time weather parameters |
| **Calibration** | Dutch climate specific | Universal FAO-56 formula |

## Setup Guide

### Prerequisites

1. **Location**: Netherlands territory
2. **KNMI API Key**: Get from [KNMI Data Platform](https://dataplatform.knmi.nl/)
3. **Smart Irrigation**: Latest version with KNMI support

### Configuration

#### KNMI Module (Recommended for Netherlands)

**Weather Service**: KNMI with your API key  
**Calculation Module**: KNMI  
**Sensor Group**: Weather parameters (temperature, wind, pressure, etc.)

**Result**: Uses Makkink ET when available, falls back to PyETO when needed.

#### Alternative Options

| Module | When to Use | Calculation Method |
|--------|-------------|-------------------|
| **PyETO** | Global use, traditional calculations | Always PyETO/Penman-Monteith |
| **Passthrough** | Use weather service ET directly | Weather service pre-calculated ET |

## ⚠️ Critical: Optimize Calculation Timing

**The default calculation time (23:00) is suboptimal for KNMI Makkink data.**

### The Problem

- **Evening calculation (23:00)**: Uses day-before-yesterday's Makkink ET
- **Morning irrigation**: Based on 2-day-old evapotranspiration data
- **Result**: Poor irrigation timing

### The Solution

**Change calculation time to early morning (06:00):**

- **Early morning (06:00)**: Uses yesterday's actual Makkink ET
- **Irrigation**: Based on previous day's actual plant water loss
- **Result**: Optimal irrigation timing with fresh data

### Why This Matters

KNMI provides **daily Makkink values** with a 1-day processing delay:

- Yesterday's data becomes available today
- Early morning calculations use the freshest relevant data
- Evening calculations introduce unnecessary data lag

### Update Frequency Recommendations

**Daily updates (most efficient)**: Single API call per day  
**Hourly updates (works but less efficient)**: 24 calls for same daily data

*Note: Smart Irrigation's time multiplier system automatically handles both frequencies correctly, but daily updates are more API-efficient for daily Makkink data.*

### 🔧 **Optimal Configuration Sequence**

For KNMI Makkink data, the ideal sequence is:

1. **05:00**: Daily weather data update (fetches yesterday's Makkink ET)
2. **06:00**: Automatic calculation (uses fresh Makkink data)  
3. **07:00**: Weather data pruning (clears old data after calculation)
4. **06:00+**: Irrigation based on yesterday's actual evapotranspiration

**Why this timing works:**

- ✅ Fresh Makkink data available at calculation time
- ✅ Data cleared after calculation to prevent stale data accumulation
- ✅ 24-hour intervals align with daily Makkink data updates
- ✅ Morning irrigation with optimal plant water management

**⚠️ Critical Timing Limitation**: Smart Irrigation only allows configuration of update **frequency** (how often), not update **timing** (when the cycle starts). With 24-hour updates, the first update occurs immediately upon restart, then every 24 hours from that point. This means the update timing relative to your calculation time depends on when Smart Irrigation was last restarted.

**Solution**: To ensure updates occur before calculations, restart Smart Irrigation at your desired update time (e.g., 05:00) to establish the correct 24-hour cycle timing.
