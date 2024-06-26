"""This script contains the class Chart, as well as the method:

_interpolate(x, start_date, end_date): creates interpolation object used in 'interpolate'

We store the method here since it's used exlusively in this class.
"""

import pandas as pd
import numpy as np
from scipy.interpolate import RegularGridInterpolator
import dask
import xoak

from . import utils
from . import search
from . import geo

class Chart:
    """
    The Chart object symbolizes the map, including wind and current data, as well as the grid used for path finding.

    A chart at any moment is a bounding box of the underlying available data at a specific date interval. 

    Attributes:
        data_dir (str): the path to the data files
        bbox (List): chart box with minimal/maximal lat/lon (as [lon min, lat min, lon max, lat max])
        start_date (pd.Timestamp): earliest date for which data is contained in the Chart
        end_date (pd.Timestamp): latest date for which data is contained in the Chart
        u_current_all (Xarray): horizontal component of currents, as read from data
        v_current_all (Xarray): vertical component of currents, as read from data
        u_current (Xarray): horizontal component of interpolated current data
        v_current (Xarray): vertical component of interpolated current data
        u_wind_all (Xarray): horizontal component of winds, as read from data
        v_wind_all (Xarray): vertical component of winds, as read from data
        u_wind (RegularGridInterpolator): horizontal component of interpolated wind data
        v_wind (RegularGridInterpolator): vertical component of interpolated wind data
        waves_all (Xarray): height of waves, as read from data
        longitudes (array): grid of longitudes on the chart
        latitudes(array): grid of latitudes on the chart
        grid (Grid): weighted grid to implement different kinds of weighting in the trajectories

    Methods:
        load(data_dir, **kwargs): loads the Chart data for dynamical updating
        interpolate(date, duration): interpolates the loaded data for the selected period
        isLand(longitude, latitude): Determines whether a certain position is land or not.
        find_closest_land(longitude, latitude, radar_radius): Calculates the distance and angle to the closest land within a certain lon/lat radius. 
        find_closest_water(longitude, latitude, radar_radius): Calculates the lon/lat of the closest piece of body to a land site, within a certain lon/lat radius. 
    """

    def __init__(self, bbox, start_date, end_date) -> None:
        """
        Parameters:
            bbox (List): list with 4 elements containing minimal/maximal lat/lon (as [lon min, lat min, lon max, lat max])
            start_date (pd.Timestamp): earliest date for which data is contained in the Chart
            end_date (pd.Timestamp): latest date for which data is contained in the Chart
        """
        
        self.bbox = bbox
        self.start_date = start_date
        self.end_date = end_date

        self.u_current_all = None
        self.v_current_all = None
        self.u_wind_all = None
        self.v_wind_all = None
        self.waves_all = None

        self.longitudes = None
        self.latitudes  = None
        self.grid = None


    def load(self, data_dir: str, **kwargs):
        """Loads the Chart data for dynamical updating. Updated the winds, currents and the weighted grid.

        Args:
            data_dir (str): The root directory of the velocity data

        Returns:
            Chart: The Chart instance
        """

        self.data_dir = data_dir

        with dask.config.set(**{'array.slicing.split_large_chunks': True}):

            self.u_current_all, self.v_current_all  = utils.load_data(start=self.start_date, 
                                                                    end=self.end_date,
                                                                    bbox=self.bbox,
                                                                    data_directory=self.data_dir,
                                                                    source="currents")

            self.u_wind_all, self.v_wind_all        = utils.load_data(start=self.start_date, 
                                                                    end=self.end_date,
                                                                    bbox=self.bbox,
                                                                    data_directory=self.data_dir,
                                                                    source="winds")
            
            self.waves_all                          = utils.load_data(start=self.start_date, 
                                                                    end=self.end_date,
                                                                    bbox=self.bbox,
                                                                    data_directory=self.data_dir,
                                                                    source="waves")
            
            # Addition to use normal coordinates in models.py.
            self.u_wind_all.xoak.set_index(['longitude', 'latitude'], index_type='scipy_kdtree')
            self.v_wind_all.xoak.set_index(['longitude', 'latitude'], index_type='scipy_kdtree')


        map          = self.u_current_all.sel(time=self.start_date, method="nearest")

        self.longitudes = map.longitude.values
        self.latitudes  = map.latitude.values

        self.grid    = search.WeightedGrid.from_map(map, **kwargs)


        return self

    def interpolate(self, date: pd.Timestamp, duration: int):
        """Interpolates the loaded data for a certain timestamp, and a duration in days.

        Args:
            date (pd.Timestamp): Date to start interpolating from
            duration (int): Duration of the interpolation in days

        Returns:
            Chart: The Chart instance
        """

        end_date = date + pd.Timedelta(duration, 'D')

        self.u_current = _interpolate(self.u_current_all, date, end_date) 
        self.v_current = _interpolate(self.v_current_all, date, end_date) 
            
        # Interpolate the wind speeds for the current day
        self.u_wind = _interpolate(self.u_wind_all, date, end_date) 
        self.v_wind = _interpolate(self.v_wind_all, date, end_date) 

        return self
    

    def isLand(self, longitude: float, latitude: float) -> bool:
        """Determine whether a certain position is land or not.

        Args:
            longitude (float): Longitude (WGS84)
            latitude (float): Latitude (WGS84)

        Returns:
            bool: True if the lon/lat coordinate corresponds to land.
        """

        v_x_current = self.u_current_all.sel(time=self.start_date, 
                                             longitude=longitude, 
                                             latitude=latitude, method="nearest")
        v_y_current = self.v_current_all.sel(time=self.start_date, 
                                             longitude=longitude, 
                                             latitude=latitude, method="nearest")

        # If any component of currents is None, the point is on land.
        if np.isnan(v_x_current) or np.isnan(v_y_current):
            return True
        else:       
            return False
        
    def find_closest_land(self, longitude: float, latitude: float, radar_radius: float = 0.05):
        """Calculates the distance and angle to the closest land within a certain lon/lat radius.

        Args:
            position (np.ndarray): current position (lon/lat)
            radar_radius (float): radius around the position that is checked for land, in degrees.
        Returns:
            distance_to_land, angle_to_land (Tuple[float, float]): distance (in km) and angle (in degrees from the North) to the closest land
        """
        r_earth = 6371 # km
        position = np.array([longitude, latitude])

        # select only u_current, since if u is None, then v is None too.
        selected_radius = self.u_current_all.sel(time=self.start_date,
                                                 longitude=slice(longitude - radar_radius, longitude + radar_radius),
                                                 latitude=slice(latitude - radar_radius, latitude + radar_radius))
        
        # calculate whether there is land anywhere
        nan_count = sum(sum(selected_radius.isnull().values))
        isThereLand = False if nan_count == 0 else True

        if isThereLand:
            selected_radius = selected_radius.to_dataset()
            # calculate matrix of distances
            distances = selected_radius.assign(distance = lambda x: (r_earth*np.pi/180)*np.sqrt((x.u.latitude - latitude)**2 
                                                                                                + (x.u.longitude - longitude)**2)*np.cos(latitude*np.pi/180))
            idx_lat_closest = distances.where(distances.u.isnull()).distance.argmin(dim=['latitude', 'longitude'])['latitude'].values
            idx_lon_closest = distances.where(distances.u.isnull()).distance.argmin(dim=['latitude', 'longitude'])['longitude'].values
            lat_closest = distances.latitude[idx_lat_closest].values
            lon_closest = distances.longitude[idx_lon_closest].values

            distance_to_land = distances.distance[idx_lat_closest][idx_lon_closest].values
            angle_to_land = geo.bearing_from_lonlat(position, np.array([lon_closest, lat_closest]))

            return [distance_to_land, angle_to_land]
        
        else:
            return [None, None]


    def find_closest_water(self, longitude: float, latitude: float, radar_radius: float = 0.05):
            """Calculates the distance and angle to the closest water body within a certain lon/lat radius. Used to find a starting point given a landing site on land.

            Args:
                position (np.ndarray): current position (lon/lat)
                radar_radius (float): radius around the position that is checked for land, in degrees.
            Returns:
                closest_water_coordinates (Tuple[float, float]): longitude and latitude to closest square of water.
            """
            r_earth = 6371 # km
            position = np.array([longitude, latitude])

            # select only u_current, since if u is None, then v is None too.
            selected_radius = self.u_current_all.sel(time=self.start_date,
                                                    longitude=slice(longitude - radar_radius, longitude + radar_radius),
                                                    latitude=slice(latitude - radar_radius, latitude + radar_radius))
            
            # calculate whether there is land anywhere
            values_count = sum(sum(selected_radius.notnull().values))
            isThereWater = False if values_count == 0 else True

            if isThereWater:
                selected_radius = selected_radius.to_dataset()
                # calculate matrix of distances
                distances = selected_radius.assign(distance = lambda x: (r_earth*np.pi/180)*np.sqrt((x.u.latitude - latitude)**2 
                                                                                                    + (x.u.longitude - longitude)**2)*np.cos(latitude*np.pi/180))
                idx_lat_closest = distances.where(distances.u.notnull()).distance.argmin(dim=['latitude', 'longitude'])['latitude'].values
                idx_lon_closest = distances.where(distances.u.notnull()).distance.argmin(dim=['latitude', 'longitude'])['longitude'].values
                lat_closest = distances.latitude[idx_lat_closest].values
                lon_closest = distances.longitude[idx_lon_closest].values

                #distance_to_land = distances.distance[idx_lat_closest][idx_lon_closest].values
                #angle_to_land = geo.bearing_from_lonlat(position, np.array([lon_closest, lat_closest]))

                return [lon_closest.item(), lat_closest.item()]
            
            else:
                return [None, None]

        

def _interpolate(x, start_date: pd.Timestamp, end_date: pd.Timestamp) -> RegularGridInterpolator:
    """Wraps the method RegularGridInterpolator from scipy.interpolate. 

    Data for winds and current come in different format, so it implements the interpolator by unpacking the data in different ways.

    Parameters:
        x (Xarray): xarray to interpolate.
        start_date (pd.Timestamp): beginning of time interval over which to interpolate
        end_date (pd.Timestamp): end of time interval over which to interpolate
    Returns:
        RegularGridInterpolator
    """

    X = x.sel(time=slice(start_date, end_date))

    try:
        longitudes = x.longitude.values
        latitudes = x.latitude.values

        return RegularGridInterpolator((np.arange(X.shape[0]), longitudes, latitudes), 
                                    np.transpose(X.values, (0, 2, 1)), 
                                    bounds_error=False, 
                                    fill_value=np.nan)
    except:
        longitudes = np.linspace(x.longitude.min(), x.longitude.max(), x.longitude.shape[1])
        latitudes = np.linspace(x.latitude.min(), x.latitude.max(), x.latitude.shape[0])

        return RegularGridInterpolator((np.arange(X.shape[0]), longitudes, latitudes), 
                                    np.transpose(X.values, (0, 2, 1)), 
                                    bounds_error=False, 
                                    fill_value=np.nan)