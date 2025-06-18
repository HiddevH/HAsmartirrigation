"""The KNMI module for Smart Irrigation Integration."""

import datetime
import logging
from enum import Enum
from statistics import mean

import voluptuous as vol
from homeassistant.const import CONF_ELEVATION, CONF_LATITUDE
from homeassistant.core import HomeAssistant

from custom_components.smart_irrigation.calcmodules.calcmodule import \
    SmartIrrigationCalculationModule
from custom_components.smart_irrigation.const import (
    CONF_PYETO_COASTAL, CONF_PYETO_FORECAST_DAYS, CONF_PYETO_SOLRAD_BEHAVIOR)

# Import PyETO calculations for fallback
from custom_components.smart_irrigation.calcmodules.pyeto.pyeto import (
    avp_from_tdew, convert, cs_rad, daylight_hours, deg2rad,
    delta_svp, et_rad, fao56_penman_monteith,
    inv_rel_dist_earth_sun, net_in_sol_rad, net_out_lw_rad,
    net_rad, psy_const, sol_dec, sol_rad_from_sun_hours,
    sol_rad_from_t, sunset_hour_angle, svp_from_t)

_LOGGER = logging.getLogger(__name__)


class SOLRAD_behavior(Enum):
    """Enumeration of solar radiation estimation behaviors for PyETO fallback."""

    EstimateFromTemp = "1"
    EstimateFromSunHours = "2"
    DontEstimate = "3"
    EstimateFromSunHoursAndTemperature = "4"


DEFAULT_COASTAL = False
DEFAULT_SOLRAD_BEHAVIOR = SOLRAD_behavior.EstimateFromTemp
DEFAULT_FORECAST_DAYS = 0

# Mapping keys for weather data
MAPPING_DEWPOINT = "Dewpoint"
MAPPING_EVAPOTRANSPIRATION = "Evapotranspiration"
MAPPING_HUMIDITY = "Humidity"
MAPPING_MAX_TEMP = "Maximum Temperature"
MAPPING_MIN_TEMP = "Minimum Temperature"
MAPPING_PRECIPITATION = "Precipitation"
MAPPING_PRESSURE = "Pressure"
MAPPING_SOLRAD = "Solar Radiation"
MAPPING_TEMPERATURE = "Temperature"
MAPPING_WINDSPEED = "Windspeed"

SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_PYETO_COASTAL, default=DEFAULT_COASTAL): vol.Coerce(bool),
        vol.Optional(
            CONF_PYETO_SOLRAD_BEHAVIOR, default=DEFAULT_SOLRAD_BEHAVIOR
        ): vol.Coerce(SOLRAD_behavior),
        vol.Optional(CONF_PYETO_FORECAST_DAYS, default=DEFAULT_FORECAST_DAYS): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=5)
        ),
    }
)


class KNMI(SmartIrrigationCalculationModule):
    """KNMI calculation module optimized for Netherlands with Makkink ET and PyETO fallback."""

    def __init__(self, hass: HomeAssistant | None, description, config=None) -> None:
        """Initialize the KNMI calculation module.

        Args:
            hass: Home Assistant instance or None.
            description: Description of the calculation module.
            config: Optional configuration dictionary.

        """
        if config is None:
            config = {}
        super().__init__(
            name="KNMI", description=description, schema=SCHEMA, config=config
        )
        self._hass = hass
        
        # PyETO fallback configuration
        self._latitude = hass.config.latitude if hass else 52.3676  # Default to Amsterdam
        self._elevation = hass.config.elevation if hass else 0
        self._coastal = config.get(CONF_PYETO_COASTAL, DEFAULT_COASTAL)
        
        # Handle solrad_behavior as enum
        solrad_behavior = config.get(CONF_PYETO_SOLRAD_BEHAVIOR, DEFAULT_SOLRAD_BEHAVIOR)
        if isinstance(solrad_behavior, SOLRAD_behavior):
            self._solrad_behavior = solrad_behavior.value
        else:
            self._solrad_behavior = solrad_behavior
            
        self.forecast_days = config.get(CONF_PYETO_FORECAST_DAYS, DEFAULT_FORECAST_DAYS)

        if not isinstance(self.forecast_days, int):
            self.forecast_days = DEFAULT_FORECAST_DAYS

    def calculate(self, weather_data, forecast_data):
        """Calculate evapotranspiration delta using KNMI Makkink with PyETO fallback.

        This method prioritizes KNMI Makkink evapotranspiration when available,
        falling back to PyETO calculations for reliability.

        Args:
            weather_data: Dictionary containing current weather data.
            forecast_data: List of dictionaries containing forecasted weather data for upcoming days.

        Returns:
            The mean evapotranspiration delta as a float.

        """
        delta = 0.0
        deltas = []
        if weather_data:
            deltas.append(self.calculate_et_for_day(weather_data))
            # loop over the forecast days
            for x in range(self.forecast_days):
                _LOGGER.debug(
                    "[KNMI: calculate] calculating delta for forecast day: %s", x
                )
                if len(forecast_data) - 1 >= x:
                    deltas.append(self.calculate_et_for_day(forecast_data[x]))
        # return average of the collected deltas
        _LOGGER.debug("[KNMI: calculate] collected deltas: %s", deltas)
        if deltas:
            delta = mean(deltas)
            _LOGGER.debug("[KNMI: calculate]: mean of deltas returned: %s", delta)
        return delta

    def calculate_et_for_day(self, weather_data):
        """Calculate evapotranspiration delta for a single day using Makkink or PyETO fallback.

        Args:
            weather_data: Dictionary containing weather data for the day.

        Returns:
            The evapotranspiration delta as a float.

        """
        if weather_data:
            # Primary: Check for KNMI Makkink evapotranspiration data
            makkink_et = weather_data.get(MAPPING_EVAPOTRANSPIRATION)
            if makkink_et is not None:
                _LOGGER.info(
                    "[KNMI: calculate_et_for_day] Using KNMI Makkink evapotranspiration: %s mm (enhanced accuracy for Netherlands)", 
                    makkink_et
                )
                # IMPORTANT: Makkink ET is DAILY data - don't apply hourly multipliers
                # The coordinator will handle time-based adjustments if needed
                precip = weather_data.get(MAPPING_PRECIPITATION, 0)
                delta = precip - makkink_et
                _LOGGER.debug(
                    "[KNMI: calculate_et_for_day] Delta from Makkink ET: %s mm (precip: %s, ET: %s)", 
                    delta, precip, makkink_et
                )
                return delta
            
            # Fallback: Use PyETO calculation if no Makkink data available
            _LOGGER.info("[KNMI: calculate_et_for_day] Makkink evapotranspiration not available, using PyETO fallback")
            return self._calculate_pyeto_fallback(weather_data)
        
        return 0.0

    def _calculate_pyeto_fallback(self, weather_data):
        """Fallback PyETO calculation when Makkink data is unavailable.

        Args:
            weather_data: Dictionary containing weather data for the day.

        Returns:
            The evapotranspiration delta as a float.

        """
        tdew = weather_data.get(MAPPING_DEWPOINT)
        temp_c_min = weather_data.get(MAPPING_MIN_TEMP)
        temp_c_max = weather_data.get(MAPPING_MAX_TEMP)
        wind_m_s = weather_data.get(MAPPING_WINDSPEED)
        atmos_pres = weather_data.get(MAPPING_PRESSURE)
        sol_rad = weather_data.get(MAPPING_SOLRAD)
        precip = weather_data.get(MAPPING_PRECIPITATION)
        
        if (
            tdew is not None
            and temp_c_min is not None
            and temp_c_max is not None
            and wind_m_s is not None
            and atmos_pres is not None
        ):
            try:
                day_of_year = datetime.datetime.now().timetuple().tm_yday

                sha = sunset_hour_angle(deg2rad(self._latitude), sol_dec(day_of_year))
                daylight_hoursvar = daylight_hours(sha)

                ird = inv_rel_dist_earth_sun(day_of_year)
                et_radvar = et_rad(
                    deg2rad(self._latitude), sol_dec(day_of_year), sha, ird
                )
                cs_radvar = cs_rad(self._elevation, et_radvar)
                
                # Solar radiation estimation if needed
                if (
                    self._solrad_behavior != SOLRAD_behavior.DontEstimate.value
                    or sol_rad is None
                ):
                    if self._solrad_behavior == SOLRAD_behavior.EstimateFromTemp.value:
                        sol_rad = sol_rad_from_t(
                            et_radvar, cs_radvar, temp_c_min, temp_c_max, self._coastal
                        )
                        _LOGGER.debug(
                            "[KNMI: _calculate_pyeto_fallback] estimated sol_rad from temp: %s",
                            sol_rad,
                        )

                # Calculate evapotranspiration using PyETO
                et_0 = fao56_penman_monteith(
                    net_rad(
                        net_in_sol_rad(sol_rad, 0.23),
                        net_out_lw_rad(
                            convert(temp_c_min, "degC", "degK"),
                            convert(temp_c_max, "degC", "degK"),
                            sol_rad,
                            cs_radvar,
                            avp_from_tdew(tdew),
                        ),
                    ),
                    convert(((temp_c_max + temp_c_min) / 2), "degC", "degK"),
                    wind_m_s,
                    delta_svp(((temp_c_max + temp_c_min) / 2)),
                    psy_const(atmos_pres),
                    avp_from_tdew(tdew),
                )
                
                _LOGGER.debug("[KNMI: _calculate_pyeto_fallback] PyETO ET_0: %s mm", et_0)
                
                # Calculate delta (precipitation - evapotranspiration)
                if precip is not None:
                    delta = precip - et_0
                    _LOGGER.debug(
                        "[KNMI: _calculate_pyeto_fallback] Delta from PyETO: %s mm (precip: %s, ET: %s)",
                        delta, precip, et_0
                    )
                    return delta
                else:
                    _LOGGER.warning("[KNMI: _calculate_pyeto_fallback] No precipitation data available")
                    return -et_0
                    
            except Exception as e:
                _LOGGER.error("[KNMI: _calculate_pyeto_fallback] PyETO calculation error: %s", e)
                return 0.0
        else:
            _LOGGER.warning(
                "[KNMI: _calculate_pyeto_fallback] Insufficient weather data for PyETO calculation"
            )
            return 0.0
