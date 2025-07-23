"""Client to talk to KNMI Data Platform API."""  # pylint: disable=invalid-name

import datetime
import json
import logging
import math
import sys

import requests

# DO NOT USE THESE FOR TESTING, INSTEAD DEFINE THE CONSTS IN THIS FILE
from ..const import (  # noqa: TID252
    MAPPING_CURRENT_PRECIPITATION,
    MAPPING_DEWPOINT,
    MAPPING_EVAPOTRANSPIRATION,
    MAPPING_HUMIDITY,
    MAPPING_MAX_TEMP,
    MAPPING_MIN_TEMP,
    MAPPING_PRECIPITATION,
    MAPPING_PRESSURE,
    MAPPING_TEMPERATURE,
    MAPPING_WINDSPEED,
)

_LOGGER = logging.getLogger(__name__)

# KNMI EDR API URLs
KNMI_OBSERVATIONS_URL = (
    "https://api.dataplatform.knmi.nl/edr/v1/collections/observations/position"
)
KNMI_LOCATIONS_URL = (
    "https://api.dataplatform.knmi.nl/edr/v1/collections/observations/locations"
)
KNMI_FORECAST_URL = "https://api.dataplatform.knmi.nl/edr/v1/collections/harmonie_arome_cy43_p1/position"
KNMI_EV24_URL = (
    "https://api.dataplatform.knmi.nl/edr/v1/collections/EV24/cube"
)

# Weerlive.nl API for forecasts (Netherlands-specific)
WEERLIVE_FORECAST_URL = "https://weerlive.nl/api/weerlive_api_v2.php"

RETRY_TIMES = 3

# Required KNMI parameter names for validation (based on KNMI parameter codes)
KNMI_wind_speed_key_name = "ff_10m_10"  # Wind speed in m/s
KNMI_pressure_key_name = "p_nap_msl_10"  # Atmospheric pressure in hPa
KNMI_humidity_key_name = "u_10"  # Relative humidity in %
KNMI_temp_key_name = "t_dryb_10"  # Air temperature in Celsius
KNMI_dew_point_key_name = "t_dewp_10"  # Dew point temperature in Celsius
KNMI_precip_key_name = "ri_regenm_10"  # Precipitation intensity in mm/h (10-minute average)
KNMI_precip_duration_key_name = "dr_regenm_10"  # Precipitation duration in seconds (within 10-minute period)
KNMI_evapotranspiration_key_name = "evaporation"  # Makkink evapotranspiration in kg m-2 (equivalent to mm)

# For forecast data - using gridded collections
KNMI_max_temp_key_name = "tx_dryb_10"  # Maximum temperature
KNMI_min_temp_key_name = "tn_dryb_10"  # Minimum temperature
KNMI_forecast_precip_key_name = "ri_regenm_10"  # Precipitation intensity

KNMI_required_keys = {
    KNMI_wind_speed_key_name,
    KNMI_pressure_key_name,
    KNMI_humidity_key_name,
    KNMI_temp_key_name,
    KNMI_dew_point_key_name,
}

KNMI_required_keys_daily = {
    KNMI_wind_speed_key_name,
    KNMI_pressure_key_name,
    KNMI_humidity_key_name,
    KNMI_max_temp_key_name,
    KNMI_min_temp_key_name,
    KNMI_dew_point_key_name,
    KNMI_forecast_precip_key_name,
}

# Validators (based on typical Dutch weather ranges)
KNMIValidators = {
    "ff_10m_10": {"max": 50, "min": 0},  # Wind speed m/s
    "t_dryb_10": {"max": 45, "min": -25},  # Temperature °C
    "t_dewp_10": {"max": 35, "min": -30},  # Dew point °C
    "u_10": {"max": 100, "min": 0},  # Humidity %
    "p_nap_msl_10": {"max": 1050, "min": 950},  # Pressure hPa
}


class KNMIClient:  # pylint: disable=invalid-name
    """KNMI Data Platform Client."""

    def __init__(
        self,
        api_key,
        api_version,
        latitude,
        longitude,
        elevation,
        cache_seconds=0,
        override_cache=False,
        weerlive_api_key=None,
    ) -> None:
        """Init."""
        self.api_key = api_key.strip().replace(" ", "")
        self.api_version = (
            api_version.strip() if api_version is not None else "1.0"
        )  # Not used by KNMI but kept for compatibility
        self.longitude = longitude
        self.latitude = latitude
        self.elevation = elevation

        # Set up headers for API authentication
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

        # Weerlive.nl forecast configuration
        self.weerlive_api_key = weerlive_api_key.strip().replace(" ", "") if weerlive_api_key else None
        self.enable_weerlive_forecast = bool(self.weerlive_api_key)
        if self.enable_weerlive_forecast:
            _LOGGER.info("KNMI enhanced with Weerlive.nl forecasts for Netherlands")

        # Initialize cache variables
        self.cache_seconds = cache_seconds
        self.override_cache = override_cache
        # disabling cache for now
        self.override_cache = True
        self._last_time_called = datetime.datetime(1900, 1, 1, 0, 0, 0)
        self._cached_data = None
        self._cached_forecast_data = None
        self._weather_stations = None  # Cache for weather stations
        
        # Defer nearest station lookup until first API call to avoid blocking HTTP requests during init
        self.nearest_station = None
        self._station_initialized = False
        self.coords = None  # Will be set when station is found

    def get_forecast_data(self):
        """Return forecast data from Weerlive.nl if configured.

        KNMI doesn't provide real-time forecast API similar to other weather services.
        If Weerlive.nl API key is configured, use that for Netherlands-specific forecasts.
        Otherwise, return None and Smart Irrigation will fall back to current observations.
        """
        if self.enable_weerlive_forecast:
            forecast_data = self._get_weerlive_forecast()
            if forecast_data:
                return forecast_data
        
        _LOGGER.warning(
            "KNMI forecast data not available. %s",
            "Configure Weerlive.nl API key for enhanced Netherlands forecasts." if not self.enable_weerlive_forecast 
            else "Smart Irrigation will use current observations only."
        )
        return None

    def _ensure_station_initialized(self):
        """Ensure nearest weather station is found and coordinates are set."""
        if not self._station_initialized:
            # Find nearest weather station and use its coordinates
            self.nearest_station = self._find_nearest_station(self.latitude, self.longitude)
            if self.nearest_station:
                _LOGGER.info(
                    "Using KNMI weather station '%s' (ID: %s) at [%.4f, %.4f] for location [%.4f, %.4f]",
                    self.nearest_station["name"],
                    self.nearest_station["id"],
                    self.nearest_station["longitude"],
                    self.nearest_station["latitude"],
                    self.longitude,
                    self.latitude,
                )
                # Use station coordinates for API calls
                self.coords = f"POINT({self.nearest_station['longitude']} {self.nearest_station['latitude']})"
            else:
                _LOGGER.warning(
                    "No KNMI weather station found near [%.4f, %.4f], using original coordinates",
                    self.longitude,
                    self.latitude,
                )
                # KNMI EDR API expects coords in specific format
                self.coords = f"POINT({self.longitude} {self.latitude})"
            
            self._station_initialized = True

    def get_data(self):
        """Validate and return current weather data."""
        # Ensure station is initialized before making API calls
        self._ensure_station_initialized()
        
        if (
            self._cached_data is None
            or self.override_cache
            or datetime.datetime.now()
            >= self._last_time_called + datetime.timedelta(seconds=self.cache_seconds)
        ):
            try:
                # Get current observations (with delay for processing)
                end_time = datetime.datetime.now() - datetime.timedelta(
                    hours=2
                )  # 2 hours ago to account for processing delay
                start_time = end_time - datetime.timedelta(hours=1)  # 1 hour window

                # Format times for KNMI API
                datetime_param = f"{start_time.isoformat()}Z/{end_time.isoformat()}Z"

                # Parameters we want from observations
                parameter_names = [
                    KNMI_temp_key_name,
                    KNMI_wind_speed_key_name,
                    KNMI_pressure_key_name,
                    KNMI_humidity_key_name,
                    KNMI_dew_point_key_name,
                    KNMI_precip_key_name,
                    KNMI_precip_duration_key_name,
                ]

                params = {
                    "coords": self.coords,
                    "datetime": datetime_param,
                    "parameter-name": ",".join(parameter_names),
                    "f": "CoverageJSON",
                }

                for i in range(RETRY_TIMES):
                    req = requests.get(
                        KNMI_OBSERVATIONS_URL,
                        headers=self.headers,
                        params=params,
                        timeout=60,
                    )
                    if req.status_code == 200:
                        break
                    i = i + 1

                if req.status_code != 200:
                    _LOGGER.error(
                        "KNMI API returned error status code: %s - %s",
                        req.status_code,
                        req.text,
                    )
                    return None

                doc = json.loads(req.text)
                _LOGGER.debug(
                    "KNMI API response: status=%s, ranges_keys=%s",
                    req.status_code,
                    list(doc.get("ranges", {}).keys()) if "ranges" in doc else "No ranges"
                )

                # Parse KNMI EDR response
                if "ranges" in doc and doc["ranges"]:
                    parsed_data = {}

                    # Get the most recent data point
                    latest_data = self._get_latest_observation(doc["ranges"])
                    _LOGGER.debug("Latest observation data keys: %s", list(latest_data.keys()) if latest_data else "None")

                    if not latest_data:
                        _LOGGER.warning(
                            "No recent observation data available from KNMI"
                        )
                        return None

                    # Validate required keys and extract data (with fallbacks for missing data)
                    missing_keys = []
                    for k in KNMI_required_keys:
                        if k not in latest_data:
                            missing_keys.append(k)
                        elif k in KNMIValidators:
                            value = latest_data[k]
                            if value is not None and (
                                value < KNMIValidators[k]["min"]
                                or value > KNMIValidators[k]["max"]
                            ):
                                self.validationError(
                                    k,
                                    value,
                                    KNMIValidators[k]["min"],
                                    KNMIValidators[k]["max"],
                                )
                    
                    # If too many required keys are missing, station data is incomplete
                    if len(missing_keys) > len(KNMI_required_keys) // 2:  # More than half missing
                        _LOGGER.warning(
                            "KNMI station has insufficient data. Missing: %s. Will use fallback values.",
                            missing_keys
                        )

                    # Convert and store the data (with null checks)
                    wind_speed = latest_data.get(KNMI_wind_speed_key_name)
                    parsed_data[MAPPING_WINDSPEED] = self._convert_wind_speed_to_2m(wind_speed) if wind_speed is not None else 0.0

                    pressure = latest_data.get(KNMI_pressure_key_name)
                    parsed_data[MAPPING_PRESSURE] = self.relative_to_absolute_pressure(
                        pressure, self.elevation
                    ) if pressure is not None else 1013.25  # Standard atmospheric pressure

                    parsed_data[MAPPING_HUMIDITY] = latest_data.get(KNMI_humidity_key_name, 50.0)  # Default 50%
                    parsed_data[MAPPING_TEMPERATURE] = latest_data.get(KNMI_temp_key_name, 15.0)  # Default 15°C
                    parsed_data[MAPPING_DEWPOINT] = latest_data.get(KNMI_dew_point_key_name, 10.0)  # Default 10°C

                    # Calculate current precipitation intensity (mm/h)
                    # KNMI provides ri_regenm_10 as precipitation intensity in mm/h
                    # and dr_regenm_10 as duration of precipitation in seconds within the 10-min period
                    precip_intensity_mm_h = latest_data.get(KNMI_precip_key_name) or 0.0
                    precip_duration_sec = latest_data.get(KNMI_precip_duration_key_name) or 0.0

                    # Use the intensity directly as it's already in mm/h
                    # Only report precipitation if there was actual precipitation duration
                    if precip_duration_sec > 0 and precip_intensity_mm_h > 0:
                        parsed_data[MAPPING_CURRENT_PRECIPITATION] = precip_intensity_mm_h
                    else:
                        parsed_data[MAPPING_CURRENT_PRECIPITATION] = 0.0

                    # Daily precipitation - get sum from last 24 hours
                    parsed_data[MAPPING_PRECIPITATION] = self._get_daily_precipitation()

                    # Daily Makkink evapotranspiration from EV24 dataset (enhanced for Dutch users)
                    makkink_et = self._get_daily_makkink_evapotranspiration()
                    if makkink_et is not None:
                        parsed_data[MAPPING_EVAPOTRANSPIRATION] = makkink_et
                        _LOGGER.info(
                            "Using KNMI Makkink evapotranspiration: %s mm (enhanced accuracy for Netherlands)",
                            makkink_et,
                        )
                    else:
                        _LOGGER.debug(
                            "Makkink evapotranspiration not available, Smart Irrigation will use PyETO calculations"
                        )

                    _LOGGER.debug(
                        "KNMIClient daily precipitation: %s",
                        parsed_data[MAPPING_PRECIPITATION],
                    )

                    self._cached_data = parsed_data
                    self._last_time_called = datetime.datetime.now()
                    return parsed_data

                _LOGGER.warning(
                    "Ignoring KNMI input: missing or empty 'ranges' in KNMI API return"
                )
                return None

            except Exception as ex:
                _LOGGER.warning("Error in KNMI get_data: %s", ex)
                raise
        else:
            # return cached_data
            _LOGGER.info("Returning cached KNMI data")
            return self._cached_data

    def _convert_wind_speed_to_2m(self, wind_speed_10m):
        """Convert wind speed from 10m height to 2m height using logarithmic profile."""
        if wind_speed_10m is None:
            return 0.0
        # KNMI reports wind speed at 10m height, convert to 2m using same formula as other clients
        return wind_speed_10m * (4.87 / math.log((67.8 * 10) - 5.42))

    def relative_to_absolute_pressure(self, pressure, height):
        """Convert relative pressure to absolute pressure."""
        if pressure is None:
            return None
        # Constants
        g = 9.80665  # m/s^2
        M = 0.0289644  # kg/mol
        R = 8.31447  # J/(mol*K)
        T0 = 288.15  # K

        # Calculate temperature at given height
        temperature = T0 - (g * M * float(height)) / (R * T0)
        # Calculate absolute pressure at given height
        return pressure * (T0 / temperature) ** (g * M / (R * 287))

    def _group_forecast_by_day(self, ranges_data):
        """Group forecast data by day."""
        daily_groups = {}

        for param_name, param_data in ranges_data.items():
            if "values" not in param_data:
                continue

            for time_str, value in param_data["values"].items():
                # Parse the time and group by date
                try:
                    dt = datetime.datetime.fromisoformat(
                        time_str.replace("Z", "+00:00")
                    )
                    date_key = dt.date()

                    if date_key not in daily_groups:
                        daily_groups[date_key] = {}

                    if param_name not in daily_groups[date_key]:
                        daily_groups[date_key][param_name] = []

                    daily_groups[date_key][param_name].append(value)

                except (ValueError, AttributeError) as ex:
                    _LOGGER.debug("Could not parse time '%s': %s", time_str, ex)
                    continue

        # Convert to list sorted by date
        return [daily_groups[date] for date in sorted(daily_groups.keys())]

    def _get_latest_observation(self, ranges_data):
        """Get the most recent observation from the CoverageJSON ranges data."""
        latest_data = {}

        # For CoverageJSON format, values are arrays corresponding to time axis
        for param_name, param_data in ranges_data.items():
            if "values" not in param_data:
                continue

            values = param_data["values"]
            if values and len(values) > 0:
                # Find the most recent non-None value
                latest_value = None
                for value in reversed(values):  # Start from most recent
                    if value is not None:
                        latest_value = value
                        break
                
                # Only add to latest_data if we found a non-None value
                if latest_value is not None:
                    latest_data[param_name] = latest_value

        return latest_data

    def _get_weerlive_forecast(self):
        """Get 5-day forecast from Weerlive.nl (Netherlands-specific)."""
        # Check cache first
        if (
            self._cached_forecast_data is not None
            and not self.override_cache
            and datetime.datetime.now()
            < self._last_time_called + datetime.timedelta(seconds=self.cache_seconds)
        ):
            _LOGGER.debug("Returning cached Weerlive.nl forecast data")
            return self._cached_forecast_data
        
        try:
            params = {
                'key': self.weerlive_api_key,
                'locatie': f"{self.latitude},{self.longitude}",
            }
            
            response = requests.get(
                WEERLIVE_FORECAST_URL, 
                params=params, 
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Store current conditions for use in forecast parsing
                if 'liveweer' in data and data['liveweer']:
                    self._current_conditions = data['liveweer'][0]
                else:
                    self._current_conditions = {}
                
                forecast_data = self._parse_weerlive_forecast(data)
                if forecast_data:
                    # Cache the successful result
                    self._cached_forecast_data = forecast_data
                    _LOGGER.info("Using Weerlive.nl forecasts with KNMI observations + Makkink ET (Netherlands enhanced)")
                    return forecast_data
                else:
                    _LOGGER.debug("Weerlive.nl returned valid response but no forecast data could be parsed")
            else:
                _LOGGER.debug("Weerlive.nl API returned status code: %s", response.status_code)
                
        except Exception as ex:
            _LOGGER.debug("Weerlive.nl forecast failed: %s", ex)
        
        return None

    def _parse_weerlive_forecast(self, data):
        """Parse Weerlive.nl forecast response into Smart Irrigation format."""
        try:
            if not data or 'wk_verw' not in data:
                _LOGGER.debug("Invalid Weerlive.nl response structure - missing wk_verw")
                return None
            
            forecast_days = []
            
            # Weerlive.nl returns forecast in 'wk_verw' array (week forecast)
            wk_verw_data = data['wk_verw']
            
            if not wk_verw_data or not isinstance(wk_verw_data, list):
                _LOGGER.debug("No forecast data in wk_verw array")
                return None
            
            # Parse each day's forecast
            for i, day_data in enumerate(wk_verw_data):
                if day_data:
                    parsed_day = self._parse_weerlive_day(day_data, f"day_{i}")
                    if parsed_day:
                        forecast_days.append(parsed_day)
            
            if forecast_days:
                _LOGGER.debug("Successfully parsed %d forecast days from Weerlive.nl", len(forecast_days))
                return forecast_days
            
        except Exception as ex:
            _LOGGER.debug("Error parsing Weerlive.nl forecast: %s", ex)
        
        return None

    def _parse_weerlive_day(self, day_data, day_key):
        """Parse a single day's forecast data from Weerlive.nl."""
        try:
            parsed_day = {}
            
            # Temperature (Celsius) - use max/min from wk_verw
            max_temp = None
            min_temp = None
            
            if 'max_temp' in day_data and day_data['max_temp'] is not None:
                max_temp = float(day_data['max_temp'])
                parsed_day[MAPPING_MAX_TEMP] = max_temp
            
            if 'min_temp' in day_data and day_data['min_temp'] is not None:
                min_temp = float(day_data['min_temp'])
                parsed_day[MAPPING_MIN_TEMP] = min_temp
            
            # Calculate average temperature for main temperature value
            if max_temp is not None and min_temp is not None:
                avg_temp = (max_temp + min_temp) / 2
                parsed_day[MAPPING_TEMPERATURE] = avg_temp
            elif max_temp is not None:
                parsed_day[MAPPING_TEMPERATURE] = max_temp
            elif min_temp is not None:
                parsed_day[MAPPING_TEMPERATURE] = min_temp
            
            # Wind speed (already in m/s in 'windms' field)
            if 'windms' in day_data and day_data['windms'] is not None:
                parsed_day[MAPPING_WINDSPEED] = float(day_data['windms'])
            
            # Precipitation estimation based on percentage
            precipitation = 0.0
            rain_chance = 0.0
            if 'neersl_perc_dag' in day_data and day_data['neersl_perc_dag'] is not None:
                try:
                    rain_chance = float(day_data['neersl_perc_dag'])
                    # Convert percentage to estimated precipitation amount
                    if rain_chance >= 80:
                        precipitation = 8.0  # Heavy rain estimate (8mm)
                    elif rain_chance >= 60:
                        precipitation = 4.0  # Moderate rain estimate (4mm)
                    elif rain_chance >= 40:
                        precipitation = 2.0  # Light rain estimate (2mm)
                    elif rain_chance >= 20:
                        precipitation = 0.5  # Very light rain estimate (0.5mm)
                    else:
                        precipitation = 0.0  # No rain
                except (ValueError, TypeError):
                    precipitation = 0.0
                    rain_chance = 0.0
            
            parsed_day[MAPPING_PRECIPITATION] = precipitation
            
            # For fields not directly available in wk_verw, use reasonable estimates
            # or get from current conditions in liveweer if available
            current = getattr(self, '_current_conditions', {})
            
            # Humidity - estimate based on weather conditions or use current
            if 'lv' in current:
                parsed_day[MAPPING_HUMIDITY] = float(current['lv'])
            else:
                # Estimate humidity based on rain chance
                if rain_chance >= 60:
                    parsed_day[MAPPING_HUMIDITY] = 85.0  # High humidity with rain
                elif rain_chance >= 30:
                    parsed_day[MAPPING_HUMIDITY] = 70.0  # Moderate humidity
                else:
                    parsed_day[MAPPING_HUMIDITY] = 60.0  # Lower humidity
            
            # Pressure - use current or typical Dutch value
            if 'luchtd' in current:
                parsed_day[MAPPING_PRESSURE] = float(current['luchtd'])
            else:
                parsed_day[MAPPING_PRESSURE] = 1013.25  # Standard atmospheric pressure
            
            # Dew point - calculate from temperature and humidity if possible
            if MAPPING_TEMPERATURE in parsed_day and MAPPING_HUMIDITY in parsed_day:
                temp = parsed_day[MAPPING_TEMPERATURE]
                humidity = parsed_day[MAPPING_HUMIDITY]
                
                # Magnus formula for dew point calculation
                a = 17.27
                b = 237.7
                alpha = ((a * temp) / (b + temp)) + math.log(humidity / 100.0)
                dew_point = (b * alpha) / (a - alpha)
                parsed_day[MAPPING_DEWPOINT] = dew_point
            elif 'dauwp' in current:
                parsed_day[MAPPING_DEWPOINT] = float(current['dauwp'])
            
            _LOGGER.debug("Parsed Weerlive.nl day %s: %s", day_key, parsed_day)
            return parsed_day if parsed_day else None
            
        except Exception as ex:
            _LOGGER.debug("Error parsing Weerlive.nl day %s: %s", day_key, ex)
            return None

    def _get_daily_precipitation(self):
        """Get daily precipitation sum from last 24 hours."""
        # Ensure station is initialized before making API calls
        self._ensure_station_initialized()
        
        try:
            # Get precipitation data for last 24 hours
            end_time = datetime.datetime.now() - datetime.timedelta(
                hours=3
            )  # 3 hours ago to account for processing delay
            start_time = end_time - datetime.timedelta(hours=24)

            datetime_param = f"{start_time.isoformat()}Z/{end_time.isoformat()}Z"

            params = {
                "coords": self.coords,
                "datetime": datetime_param,
                "parameter-name": KNMI_precip_key_name,
                "f": "CoverageJSON",
            }

            req = requests.get(
                KNMI_OBSERVATIONS_URL, headers=self.headers, params=params, timeout=30
            )

            if req.status_code == 200:
                doc = json.loads(req.text)
                if "ranges" in doc and KNMI_precip_key_name in doc["ranges"]:
                    values = doc["ranges"][KNMI_precip_key_name].get("values", [])
                    # KNMI provides precipitation intensity in mm/h for 10-minute periods
                    # Convert each 10-minute intensity reading to actual precipitation amount
                    # intensity (mm/h) * (10 minutes / 60 minutes) = mm in that 10-minute period
                    total_precip = sum(v * (10 / 60) for v in values if v is not None and v > 0)
                    return total_precip

        except Exception as ex:
            _LOGGER.debug("Could not get daily precipitation: %s", ex)

        return 0.0

    def _get_daily_makkink_evapotranspiration(self):
        """Get daily Makkink evapotranspiration from KNMI EV24 dataset.
        
        Returns:
            Daily Makkink evapotranspiration in mm, or None if unavailable.
        """
        # Ensure station is initialized before making API calls
        self._ensure_station_initialized()
        
        try:
            # Get yesterday's evapotranspiration data since today's data may not be available yet
            # KNMI EV24 has a processing delay
            end_date = datetime.datetime.now() - datetime.timedelta(days=1)
            start_date = end_date
            
            # Format as date-only for daily data (EV24 provides daily values)
            datetime_param = f"{start_date.strftime('%Y-%m-%d')}"

            params = {
                "coords": self.coords,
                "datetime": datetime_param,
                "parameter-name": KNMI_evapotranspiration_key_name,
                "f": "CoverageJSON",
            }

            req = requests.get(
                KNMI_EV24_URL, headers=self.headers, params=params, timeout=30
            )

            if req.status_code == 200:
                doc = json.loads(req.text)
                if "ranges" in doc and KNMI_evapotranspiration_key_name in doc["ranges"]:
                    values = doc["ranges"][KNMI_evapotranspiration_key_name].get("values", [])
                    if values and len(values) > 0:
                        # EV24 provides daily evapotranspiration in kg m-2, which is equivalent to mm
                        # Return the most recent value (should be only one for daily data)
                        et_value = values[-1] if isinstance(values, list) else values
                        if et_value is not None and et_value >= 0:
                            _LOGGER.debug(
                                "Retrieved Makkink evapotranspiration: %s mm for date %s",
                                et_value,
                                datetime_param,
                            )
                            return float(et_value)

            _LOGGER.debug(
                "Could not get Makkink evapotranspiration data from EV24 API. Status: %s",
                req.status_code,
            )

        except Exception as ex:
            _LOGGER.debug("Could not get Makkink evapotranspiration: %s", ex)

        return None

    def _safe_average(self, data_dict, key):
        """Safely calculate average of values for a key."""
        if key not in data_dict or not data_dict[key]:
            return 0.0
        values = [v for v in data_dict[key] if v is not None]
        return sum(values) / len(values) if values else 0.0

    def _safe_max(self, data_dict, key):
        """Safely get maximum value for a key."""
        if key not in data_dict or not data_dict[key]:
            return 0.0
        values = [v for v in data_dict[key] if v is not None]
        return max(values) if values else 0.0

    def _safe_min(self, data_dict, key):
        """Safely get minimum value for a key."""
        if key not in data_dict or not data_dict[key]:
            return 0.0
        values = [v for v in data_dict[key] if v is not None]
        return min(values) if values else 0.0

    def _safe_sum(self, data_dict, key):
        """Safely sum values for a key."""
        if key not in data_dict or not data_dict[key]:
            return 0.0
        values = [v for v in data_dict[key] if v is not None]
        return sum(values) if values else 0.0

    def _find_nearest_station(self, lat, lon):
        """Find the best KNMI weather station with required data availability."""
        try:
            stations = self._get_weather_stations()
            if not stations:
                return None

            # Define priority stations known to have complete data (KNMI main stations)
            # These are the primary KNMI weather stations with comprehensive measurements
            priority_stations = {
                "06260",  # De Bilt (KNMI HQ) - most complete data
                "06240",  # Schiphol - major airport station
                "06350",  # Gilze-Rijen - southern Netherlands
                "06280",  # Eelde - northern Netherlands  
                "06310",  # Vlissingen - southwestern Netherlands
                "06380",  # Maastricht - southeastern Netherlands
                "06235",  # Den Helder - northern coastal
                "06249",  # Berkhout - central Netherlands
            }

            candidates = []
            
            for station in stations:
                station_lat = station["latitude"]
                station_lon = station["longitude"]
                station_id = station["id"]

                distance = self._calculate_distance(lat, lon, station_lat, station_lon)
                
                # Calculate priority score
                priority_score = 0
                if station_id in priority_stations:
                    priority_score = 10  # High priority for main stations
                
                # Prefer closer stations but prioritize data availability
                final_score = priority_score - (distance * 0.1)  # Distance penalty
                
                candidates.append({
                    'station': station,
                    'distance': distance,
                    'priority_score': priority_score,
                    'final_score': final_score,
                    'is_main_station': station_id in priority_stations
                })

            if not candidates:
                return None

            # Sort by final score (priority + distance consideration)
            candidates.sort(key=lambda x: x['final_score'], reverse=True)
            
            # Try to find a main station within reasonable distance first
            for candidate in candidates[:10]:  # Check top 10 candidates
                if candidate['is_main_station'] and candidate['distance'] <= 150:  # 150km max for main stations
                    _LOGGER.info(
                        "Selected priority KNMI station '%s' (ID: %s) - Distance: %.1f km (main station with complete data)",
                        candidate['station']['name'], 
                        candidate['station']['id'], 
                        candidate['distance']
                    )
                    return candidate['station']
            
            # Fall back to closest station with data quality testing
            for candidate in candidates[:5]:  # Test top 5
                station = candidate['station']
                distance = candidate['distance']
                
                if distance <= 200:  # Maximum 200km for any station
                    data_quality_score = self._test_station_data_quality(station)
                    
                    if data_quality_score >= 3:  # At least 3/5 required parameters
                        _LOGGER.info(
                            "Selected KNMI station '%s' (ID: %s) - Distance: %.1f km, Data quality: %d/5",
                            station['name'], station['id'], distance, data_quality_score
                        )
                        return station

            # Last resort: return closest station
            if candidates:
                nearest = candidates[0]
                _LOGGER.warning(
                    "Using nearest available station '%s' (ID: %s) - Distance: %.1f km (limited data expected)",
                    nearest['station']['name'], 
                    nearest['station']['id'], 
                    nearest['distance']
                )
                return nearest['station']

            return None

        except Exception as ex:
            _LOGGER.warning("Could not find suitable KNMI weather station: %s", ex)
            return None

    def _test_station_data_quality(self, station):
        """Test how much of the required data a KNMI station actually provides.
        
        Returns:
            int: Score from 0-5 indicating how many required parameters have data
        """
        try:
            # Use station coordinates for testing
            coords = f"POINT({station['longitude']} {station['latitude']})"
            
            # Test recent data (last 6 hours to account for processing delays)
            end_time = datetime.datetime.now() - datetime.timedelta(hours=3)
            start_time = end_time - datetime.timedelta(hours=3)
            datetime_param = f"{start_time.isoformat()}Z/{end_time.isoformat()}Z"

            # Test for required parameters
            parameter_names = list(KNMI_required_keys)
            params = {
                "coords": coords,
                "datetime": datetime_param,
                "parameter-name": ",".join(parameter_names),
                "f": "CoverageJSON",
            }

            req = requests.get(
                KNMI_OBSERVATIONS_URL,
                headers=self.headers,
                params=params,
                timeout=15,  # Shorter timeout for testing
            )

            if req.status_code == 200:
                doc = json.loads(req.text)
                if "ranges" in doc and doc["ranges"]:
                    latest_data = self._get_latest_observation(doc["ranges"])
                    
                    # Count how many required parameters have non-None values
                    data_score = 0
                    for param in KNMI_required_keys:
                        if param in latest_data and latest_data[param] is not None:
                            data_score += 1
                    
                    _LOGGER.debug(
                        "Station %s data quality: %d/5 parameters available (%s)",
                        station['id'], data_score, 
                        [k for k in KNMI_required_keys if k in latest_data and latest_data[k] is not None]
                    )
                    return data_score
            
            _LOGGER.debug(
                "Station %s data quality test failed: status %s", 
                station['id'], req.status_code
            )
            return 0

        except Exception as ex:
            _LOGGER.debug(
                "Could not test data quality for station %s: %s", 
                station['id'], ex
            )
            return 0

    def _get_weather_stations(self):
        """Get list of all KNMI weather stations."""
        if self._weather_stations is not None:
            return self._weather_stations

        try:
            req = requests.get(
                KNMI_LOCATIONS_URL,
                headers=self.headers,
                timeout=30,
            )

            if req.status_code == 200:
                data = json.loads(req.text)
                stations = []

                for feature in data.get("features", []):
                    if feature.get("type") == "Feature":
                        coords = feature.get("geometry", {}).get("coordinates", [])
                        properties = feature.get("properties", {})

                        if len(coords) >= 2:
                            station = {
                                "id": feature.get("id"),
                                "name": properties.get("name", "Unknown"),
                                "longitude": coords[0],
                                "latitude": coords[1],
                                "elevation": coords[2] if len(coords) > 2 else 0,
                            }
                            stations.append(station)

                self._weather_stations = stations
                _LOGGER.debug("Loaded %d KNMI weather stations", len(stations))
                return stations
            else:
                _LOGGER.error("Failed to get KNMI weather stations: %s", req.status_code)
                return []

        except Exception as ex:
            _LOGGER.warning("Error getting KNMI weather stations: %s", ex)
            return []

    def _test_station_data_quality(self, station):
        """Test data quality for a specific station by checking how many required parameters are available.
        
        Returns a score from 0-5 based on data availability:
        - 5: All required parameters available with recent data
        - 4: Most required parameters (4/5) available
        - 3: Some required parameters (3/5) available  
        - 2: Few required parameters (2/5) available
        - 1: Minimal data (1/5) available
        - 0: No usable data
        """
        try:
            # Test data from last 2 hours to account for processing delay
            end_time = datetime.datetime.now() - datetime.timedelta(hours=2)
            start_time = end_time - datetime.timedelta(hours=1)
            
            # Format times for KNMI API
            datetime_param = f"{start_time.isoformat()}Z/{end_time.isoformat()}Z"
            
            # Parameters we need for irrigation calculations
            test_parameters = [
                KNMI_temp_key_name,
                KNMI_wind_speed_key_name, 
                KNMI_pressure_key_name,
                KNMI_humidity_key_name,
                KNMI_dew_point_key_name,
            ]
            
            coords = f"POINT({station['longitude']} {station['latitude']})"
            
            params = {
                "coords": coords,
                "datetime": datetime_param,
                "parameter-name": ",".join(test_parameters),
                "f": "CoverageJSON",
            }
            
            # Quick test request with short timeout
            req = requests.get(
                KNMI_OBSERVATIONS_URL,
                headers=self.headers,
                params=params,
                timeout=10,  # Shorter timeout for testing
            )
            
            if req.status_code != 200:
                _LOGGER.debug("Station %s API test failed: %s", station['id'], req.status_code)
                return 0
                
            doc = json.loads(req.text)
            
            if "ranges" not in doc or not doc["ranges"]:
                _LOGGER.debug("Station %s has no data ranges", station['id'])
                return 0
                
            # Check data availability
            available_params = 0
            total_params = len(test_parameters)
            
            # Get latest observation and count non-None parameters
            latest_data = self._get_latest_observation(doc["ranges"])
            
            if not latest_data:
                _LOGGER.debug("Station %s has no recent observations", station['id'])
                return 0
                
            for param in test_parameters:
                if param in latest_data and latest_data[param] is not None:
                    available_params += 1
                    
            # Calculate score based on availability percentage
            if available_params == total_params:
                return 5  # Perfect data
            elif available_params >= total_params * 0.8:  # 80% or more
                return 4  # Good data
            elif available_params >= total_params * 0.6:  # 60% or more
                return 3  # Acceptable data
            elif available_params >= total_params * 0.4:  # 40% or more
                return 2  # Limited data
            elif available_params > 0:
                return 1  # Minimal data
            else:
                return 0  # No usable data
                
        except Exception as ex:
            _LOGGER.debug("Error testing station %s data quality: %s", station.get('id', 'unknown'), ex)
            return 0

    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two points using Haversine formula (in km)."""
        # Convert to radians
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)

        # Haversine formula
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))

        # Earth's radius in kilometers
        earth_radius = 6371.0

        return earth_radius * c

    def raiseIOError(self, key):
        """Raise an OSError when a required key is missing in the KNMI API return."""
        raise OSError(f"Missing required key {key} in KNMI API return")

    def validationError(self, key, value, minval, maxval):
        """Raise a ValueError if a value is outside the expected range for a key."""
        raise ValueError(
            f"Value {value} is not valid for {key}. Expected range: {minval}-{maxval}"
        )


# for testing call: python KNMIClient [api_key] [api_version] [latitude] [longitude] [elevation] [weerlive_api_key]
# Weerlive.nl API example: https://weerlive.nl/api/weerlive_api_v2.php?key=demo&locatie=52.0910879,5.1124231
if __name__ == "__main__":
    args = sys.argv[1:]
    weerlive_key = args[5] if len(args) > 5 else None
    client = KNMIClient(args[0], args[1], args[2], args[3], args[4], weerlive_api_key=weerlive_key)
    print(client.get_data())  # noqa: T201
    print(client.get_forecast_data())  # noqa: T201
