"""Different utils

This script contains tools to calculate different quantities used in the simulation. 
It requires that the packages numpy, json, glob, xarray, pandas and ephem be installed within the Python environment.

This file can be imported as module and contains the following functions:
    * lonlat_from_displacement - calculates new coordinates after displacement, given an origin, using Great Circle approximation
    * normalize_longitude(lon): normalizes the longitude such that lon degrees left of the prime meridian count as the east. 
    * save_to_GeoJSON(data, filename): deprecated, used to save data to GeoJSON format
    * ecmwf_to_xr(winds): Normalizes the ECMWF data into a standard XArray format.
    * cmems_to_xr(currents): Normalizes the CMEMS data into a standard XArray format.
    * load_data(start, end, bbox, data_directory, sourceparallel): Reads the wind and current data from a directory with a specified structure
    * calculate_sunrise(date, position): Calculates the time of sunrise based on date, longitude and latitude, using the ephem package
    * calculate_sunset(date, position): Calculates the time of sunset based on date, longitude and latitude, using the ephem package

"""

import numpy as np
import json
import os
import glob
import xarray as xr
import pandas as pd
from typing import *
import ephem

def lonlat_from_displacement(dx: float, dy: float, origin: Tuple[float, float]) -> Tuple[float, float]:
    """Calculate a new longitude and latitude from a displacement from an origin, using the Great Circle Approximation.

    Args:
        dx (float): Displacement in x-axis
        dy (float): Displacement in y-axis
        origin (Tuple[float, float]): Origin in longitude-latitude, WGS84

    Returns:
        Tuple[float, float]: New coordinates in longitude-latitude, WGS84
    """

    longitude, latitude = origin

    r_earth = 6371 # km

    new_latitude  = latitude  + (dy / r_earth) * (180 / np.pi)
    new_longitude = longitude + (dx / r_earth) * (180 / np.pi) / np.cos(latitude * np.pi/180)

    return np.asscalar(new_longitude), np.asscalar(new_latitude)

def normalize_longitude(lon: np.ndarray) -> np.ndarray:
    """Normalize the longitude such that longitudinal degrees left of the prime meridian count as the east, 
    and the degrees right of the meridian count as the west. Used to normalize data from ECMWF vs CMEMS.

    Args:
        lon (nd.array): An array of longitudinal degrees

    Returns:
        np.ndarray: A normalized array of longitudinal degrees
    """

    east = lon[np.where((lon >= 0) & (lon <= 180))]

    west = lon[np.where((lon > 180) & (lon <= 360))]-360

    return np.concatenate([east, west])


def save_to_GeoJSON(data, filename):
    # DEPR this function is deprecated and not used
    format_dict = to_GeoJSON(data)

    with open(filename, 'w') as file:
        json.dump(format_dict, file, indent=4)


def ecmwf_to_xr(winds: xr.Dataset) -> xr.Dataset:
    """Normalizes the ECMWF data into a standard XArray format.

    Args:
        winds (xr.Dataset): Winds as a Dataset

    Returns:
        xr.Dataset: Winds as a normalized Dataset
    """
    
    # Change variable names
    winds = winds.rename({"u10": "u", "v10": "v"})

    return winds

def cmems_to_xr(currents: xr.Dataset) -> xr.Dataset:
    """Normalizes the ECMWF data into a standard XArray format.

    Args:
        currents (xr.Dataset): Currents as a Dataset

    Returns:
        xr.Dataset: Currents as a normalized Dataset
    """
    # Remove single value in depth dimension
    # Change variable names
    try:
        currents = currents.drop("depth")\
                           .squeeze()\
                           .rename({"uo": "u", "vo": "v"})
    except:
        currents = currents.rename({"uo": "u", "vo": "v"})

    return currents

def load_data(start: pd.Timestamp, end: pd.Timestamp, bbox: List, data_directory: str, source: str, parallel=False) -> Tuple[xr.DataArray, xr.DataArray]:
    """Reads the wind and current data from a directory with a specified structure.

    Args:
        start (pd.Timestamp): The start date 
        end (pd.Timestamp): The end date
        bbox (List): Bounding box of where to fetch data
        data_directory (str): Root directory of the data files
        source (str): Data source, either "currents" or "winds"
        parallel (bool, optional): Whether to load the data in parallel. Defaults to False.

    Raises:
        ValueError: Raised if the data source is not "currents" or "winds"

    Returns:
        Tuple[xr.DataArray, xr.DataArray]: A tuple of the velocity x (east-west) and y (south-north) components respectively.
    """

    start_year = start.year
    end_year   = end.year

    years = pd.date_range(str(start_year), str(end_year)).to_period('Y')\
                                                .format(formatter=lambda x: x.strftime('%Y'))
    years = set(years)

    dates = pd.date_range(start, end)
    
    filenames = []
    for year in years:

        pattern = os.path.join(data_directory, source, year, "*.nc")

        filenames.extend(glob.glob(pattern))

    if source == "currents":
        data = xr.open_mfdataset(filenames, parallel=parallel)
        data = cmems_to_xr(data)

    elif source == "winds":
        data = xr.open_mfdataset(filenames, parallel=parallel)
        data = ecmwf_to_xr(data)

    else:
        raise ValueError("Source must be currents or winds.")

    data = data.sel(time=slice(start, end)).load()
    return data.u, data.v

def calculate_sunrise(date: pd.Timestamp, position: Tuple[float, float]):
    """Calculates the time of sunrise based on date, longitude and latitude, using the ephem package.

    Args:
        date (pd.Timestamp): day of the year
        position (Tuple[float, float]): place in format [longitude, latitude]

    Returns:
        pd.Timestamp: full date and time of sunrise on chosen day
    """
    earth = ephem.Observer()
    earth.lon = str(position[0])
    earth.lat = str(position[1])
    earth.date = date

    sun = ephem.Sun()
    sun.compute()

    sunrise = ephem.localtime(earth.next_rising(sun))
    return pd.Timestamp(sunrise)


def calculate_sunset(date: pd.Timestamp, position: Tuple[float, float]):
    """Calculates the time of sunset based on date, longitude and latitude, using the ephem package.

    Args:
        date (pd.Timestamp): day of the year
        position (Tuple[float, float]): place in format [longitude, latitude]

    Returns:
        pd.Timestamp: full date and time of sunset on chosen day
    """
    earth = ephem.Observer()
    earth.lon = str(position[0])
    earth.lat = str(position[1])
    earth.date = date

    sun = ephem.Sun()
    sun.compute()

    sunset = ephem.localtime(earth.next_setting(sun))
    return pd.Timestamp(sunset)