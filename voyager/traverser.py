import multiprocessing as mp

from geopy import util
from voyager import vessel

import pandas as pd
from .chart import Chart
from .models import Vessel, Model
from . import utils

class Traverser:

    def __init__(self, mode = 'drift', 
                       craft = 1, 
                       duration = 60,
                       timestep = 1, 
                       destination = [], 
                       speed = 2, 
                       start_date = '', 
                       end_date = '', 
                       launch_freq = 5, 
                       bbox = [], 
                       departure_points = [], 
                       data_directory = '', 
                       vessel_config='configs/vessels.yml') -> None:

        self.craft      = craft
        self.mode       = mode
        self.duration   = duration
        self.dt         = timestep
        self.vessel_config = vessel_config
        # self.n_reps     = n_reps

        self.destination = destination
        self.speed       = speed

        self.data_directory = data_directory

        # Define datetime objects to limit simulation
        self.start_date     = pd.to_datetime(start_date, infer_datetime_format=True)
        self.end_date       = pd.to_datetime(end_date, infer_datetime_format=True) 
        self.dates          = pd.date_range(self.start_date, self.end_date) 
        
        # Interval in days to launch vessels
        self.launch_day_frequency = launch_freq
        
        # The bounding box limits the region of simulation
        self.bbox = bbox

        # Starting points for trajectories
        self.departure_points = departure_points

    @classmethod
    def trajectory(
            cls,
            mode = 'drift', 
            craft = 1, 
            duration = 60,
            timestep = 1, 
            destination = [], 
            speed = 2, 
            date = '', 
            bbox = [], 
            departure_point = [], 
            data_directory = '', 
            vessel_config='configs/vessels.yml',
            chart_kwargs = {}, 
            model_kwargs = {}, 
            chart = None, 
            model = None):


        # The chart object keeps track of the region of interest
        # and the wind/current data for that region
        # It is shared by all vessels
        if not chart:
            start_date = pd.to_datetime(date, infer_datetime_format=True)
            end_date   = start_date + pd.Timedelta(duration, unit='days')
            chart = Chart(bbox, start_date, end_date).load(data_directory, **chart_kwargs)
        
        # The model object describes the equations of movement and
        # traversal across the oceans over time
        if not model:
            model = Model(duration, timestep, **model_kwargs)

        vessel = Vessel.from_position(departure_point, 
                                      craft = craft,
                                      chart = chart,
                                      destination = destination,
                                      speed =speed,
                                      mode = mode,
                                      vessel_config=vessel_config)

        # Interpolate the data for only the duration specified
        chart.interpolate(chart.start_date, duration)

        # Use the interpolated values in the model
        model.use(chart)

        # Run the model
        vessel = model.run(vessel)

        start_date_str = chart.start_date.strftime('%Y-%m-%d')
        stop_date_str  = (chart.start_date + pd.Timedelta(len(vessel.trajectory)*timestep, unit='s')).strftime('%Y-%m-%d')

        return utils.to_GeoJSON(vessel, start_date_str, stop_date_str, timestep)



    def run(self, model_kwargs={}, chart_kwargs={}):

        # The chart object keeps track of the region of interest
        # and the wind/current data for that region
        # It is shared by all vessels
        chart = Chart(self.bbox, self.start_date, self.end_date).load(self.data_directory, **chart_kwargs)
        
        # The model object describes the equations of movement and
        # traversal across the oceans over time
        model = Model(self.duration, self.dt, **model_kwargs)

        results = {}
        for date in self.dates[::self.launch_day_frequency]:

            # Vessel objects are the individual agents traversing the ocean
            vessels = Vessel.from_positions(self.departure_points, 
                                            craft = self.craft,
                                            chart = chart, 
                                            destination = self.destination, 
                                            speed = self.speed, 
                                            mode = self.mode, 
                                            vessel_config=self.vessel_config)
            
            # Interpolate the data for only the duration specified
            chart.interpolate(date, self.duration)

            # Use the interpolated values in the model
            model.use(chart)

            trajectories = []

            for vessel in vessels:

                trajectories.append(model.run(vessel))

            # Add the trajectories for the date
            results.update({date.strftime('%Y-%m-%d'): trajectories})

        return results


    def run_mp(self, model_kwargs={}, chart_kwargs={}):

        # The chart object keeps track of the region of interest
        # and the wind/current data for that region
        # It is shared by all vessels
        chart = Chart(self.bbox, self.start_date, self.end_date).load(self.data_directory, **chart_kwargs)
        
        # The model object describes the equations of movement and
        # traversal across the oceans over time
        model = Model(self.duration, self.dt, **model_kwargs)

        results = {}
        for date in self.dates[::self.launch_day_frequency]:

            # Vessel objects are the individual agents traversing the ocean
            vessels = Vessel.from_positions(self.departure_points, 
                                            craft = self.craft,
                                            chart = chart, 
                                            destination = self.destination, 
                                            speed = self.speed, 
                                            mode = self.mode, 
                                            vessel_config=self.vessel_config)
            
            # Interpolate the data for only the duration specified
            chart.interpolate(date, self.duration)

            # Use the interpolated values in the model
            model.use(chart)

            with mp.Pool(mp.cpu_count()) as p:

                trajectories = p.map(model.run, vessels)

            # Add the trajectories for the date
            results.update({date.strftime('%Y-%m-%d'): trajectories})

        return results

    def as_generator(self):

        # The chart object keeps track of the region of interest
        # and the wind/current data for that region
        # It is shared by all vessels
        chart = Chart(self.bbox, self.start_date, self.end_date).load(self.data_directory)
        
        # The model object describes the equations of movement and
        # traversal across the oceans over time
        model = Model(self.duration, self.dt)

        results = {}
        for date in self.dates[::self.launch_day_frequency]:

            # Vessel objects are the individual agents traversing the ocean
            vessels = Vessel.from_positions(self.departure_points, 
                                            craft = self.craft,
                                            chart = chart, 
                                            destination = self.destination, 
                                            speed = self.speed, 
                                            mode = self.mode, 
                                            vessel_config=self.vessel_config)
            
            # Interpolate the data for only the duration specified
            chart.interpolate(date, self.duration)

            # Use the interpolated values in the model
            model.use(chart)

            with mp.Pool(mp.cpu_count()) as p:

                trajectories = p.map(model.run, vessels)

            # Add the trajectories for the date
            yield {date.strftime('%Y-%m-%d'): trajectories}






